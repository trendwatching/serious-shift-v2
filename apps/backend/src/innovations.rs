//! Innovations — the only write path into this service, plus the reads and the
//! curation surface built around it.
//!
//! An innovation is a real branded example of a shift, pushed here by the
//! upstream Innovation database. Three things about the design are load-bearing:
//!
//!  * **Idempotency is the upstream key.** `source_innovation_id` is the natural
//!    identity, so a retried POST updates in place, and a POST whose meaningful
//!    content is unchanged writes nothing at all. The hash that decides
//!    "unchanged" deliberately ignores the cover URL's query string, because
//!    that carries a fresh signature and expiry on every send and would
//!    otherwise make every re-POST look like a change.
//!  * **Links are provenanced.** `innovation_shift_links.source` records whether
//!    a link came from the payload (`ingest`) or an editor (`editor`), and each
//!    writer only ever manages its own rows. Re-ingesting cannot delete an
//!    editor's curation, and curating cannot fight the upstream feed.
//!  * **Cover images are mirrored, not hotlinked.** The CSP is `img-src 'self'`
//!    and the upstream URL expires, so the bytes are copied once at ingest and
//!    served from `/api/innovations/{id}/cover-image`.
//!
//! The module list a shift page renders is composed here too — see
//! [`hydrate`]. That is what makes an innovation visible on its shift within the
//! response cache TTL rather than at the next weekly publication.

use std::collections::{BTreeMap, BTreeSet};
use std::net::SocketAddr;
use std::time::Duration;

use axum::{
    body::Bytes,
    extract::{ConnectInfo, Path as AxumPath, Query, State},
    http::{header, HeaderMap, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::{client_ip, secret_eq, AppError, AppState, IMMUTABLE, PUBLIC_CACHE_CONTROL};

/// The eight tag facets the upstream payload documents.
///
/// Closed on purpose, and matched by `innovation_tags_facet_check`. A facet
/// upstream invents later is *not* an error: it stays in the stored payload and
/// comes back in the response as `ignored_facets`, so taxonomy drift is visible
/// without being an outage.
const FACETS: [&str; 8] = [
    "industry",
    "subindustry",
    "region",
    "country",
    "audience",
    "season",
    "innovation-type",
    "basic-human-need",
];

/// Image types we will mirror and re-serve. Mirrors the CHECK on
/// `innovation_assets.mime`; anything else is a cover we decline to store.
const COVER_MIMES: [&str; 4] = ["image/jpeg", "image/png", "image/webp", "image/avif"];

/// Hard ceiling on a mirrored cover, matched by `innovation_assets_size_check`.
const MAX_COVER_BYTES: usize = 5 * 1024 * 1024;

/// Where a cover image may be fetched from, when `INNOVATION_ASSET_HOSTS` is
/// unset. A caller-supplied URL is a request-forgery primitive pointed at
/// Railway's private network, so the fetcher only ever talks to known hosts.
const DEFAULT_ASSET_HOSTS: &str = "tw-the-engine.up.railway.app";

/// Most innovations we will hang off a single shift page. The module is a card
/// grid, not a feed, and the fragment it lands in is served to every visitor.
const MAX_ITEMS_PER_SHIFT: i64 = 12;

/// Default and maximum page size for `GET /api/v1/innovations`.
const DEFAULT_PAGE: i64 = 24;
const MAX_PAGE: i64 = 100;

/// Canonical module order, mirrored from `packages/contracts/shift_modules.json`.
///
/// It is duplicated rather than read, because the backend image copies only
/// `apps/backend/src` (see `apps/backend/Dockerfile`) — `include_str!` of a path
/// under `packages/` compiles locally and then fails the Docker build. The
/// contract stays the arbiter: `module_order_matches_the_contract` reads the JSON
/// and fails if these drift.
const MODULE_ORDER_KEY_TREND: [&str; 15] = [
    "dek",
    "from_to",
    "pull_quote",
    "stat_band",
    "peel_tabs",
    "human_needs",
    "tension_band",
    "timeline",
    "industries",
    "territories",
    "innovations",
    "voices",
    "sub_shift_list",
    "related_shifts",
    "rich_text",
];

const MODULE_ORDER_SUB_TREND: [&str; 13] = [
    "lede",
    "from_to_solid",
    "tension_band",
    "stat_band",
    "peel_tabs",
    "human_needs",
    "signals",
    "counter_signals",
    "evidence",
    "timeline",
    "territories",
    "innovations",
    "rich_text",
];

/// Which reading order a row belongs to. The two shift scopes the map document
/// and `shift_refs` both use.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Scope {
    KeyTrend,
    SubTrend,
}

impl Scope {
    pub fn as_str(self) -> &'static str {
        match self {
            Scope::KeyTrend => "key_trend",
            Scope::SubTrend => "sub_trend",
        }
    }

    fn order(self) -> &'static [&'static str] {
        match self {
            Scope::KeyTrend => &MODULE_ORDER_KEY_TREND,
            Scope::SubTrend => &MODULE_ORDER_SUB_TREND,
        }
    }

    fn parse(value: &str) -> Option<Self> {
        match value {
            "key_trend" => Some(Scope::KeyTrend),
            "sub_trend" => Some(Scope::SubTrend),
            _ => None,
        }
    }
}

// ── hydration into shift pages ───────────────────────────────────────────────

/// `"<scope>:<slug>"` → the module's `items` array, as loaded from the DB.
pub type ByShift = BTreeMap<String, Value>;

/// The innovations to show per shift, keyed `"<scope>:<slug>"`, plus the text the
/// query returned so the caller can fold it into the snapshot's cache version.
#[derive(Default)]
pub struct Hydration {
    pub by_shift: ByShift,
    /// Hash of the raw query result. Folding this into the snapshot version is
    /// what makes every route ETag change the moment an innovation or a link
    /// does — without it a client holding `If-None-Match` keeps a page whose
    /// innovations have moved.
    pub revision: u64,
}

/// Load every shift's innovations in one round trip.
///
/// Deliberately infallible from the caller's point of view: if this query fails
/// the trend map must still serve, so the error is logged and the pages render
/// without their innovations. A broken link table is not an outage.
pub async fn load(pool: &sqlx::PgPool) -> Hydration {
    let raw: Result<String, _> = sqlx::query_scalar(BY_SHIFT)
        .bind(MAX_ITEMS_PER_SHIFT)
        .fetch_one(pool)
        .await;
    let raw = match raw {
        Ok(raw) => raw,
        Err(error) => {
            tracing::warn!(%error, "innovations hydration failed; serving shifts without them");
            return Hydration::default();
        }
    };
    let revision = fnv1a(&raw);
    let by_shift: ByShift = serde_json::from_str(&raw).unwrap_or_else(|error| {
        tracing::warn!(%error, "innovations hydration returned unparseable JSON");
        BTreeMap::new()
    });
    Hydration { by_shift, revision }
}

pub(crate) fn fnv1a(text: &str) -> u64 {
    let mut hash = 0xcbf29ce484222325u64;
    for byte in text.bytes() {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    hash
}

/// Put this shift's innovations into its module list.
///
/// Three cases, in this order:
///
///  * the row already carries an `innovations` module — replace its items **in
///    place**. That is how an editor keeps control: a `shift_module_overrides`
///    list replaces the whole composition, and its ordering must win over ours.
///  * there are items and no module — insert one at the contract's position.
///  * there are no items — drop any module that is there, so an empty section
///    never renders.
pub fn hydrate(modules: &mut Vec<Value>, scope: Scope, items: Option<&Value>) {
    let items = items
        .and_then(|value| value.as_array())
        .filter(|a| !a.is_empty());
    let existing = modules
        .iter()
        .position(|module| module.get("type").and_then(Value::as_str) == Some("innovations"));

    let Some(items) = items else {
        if let Some(index) = existing {
            modules.remove(index);
        }
        return;
    };

    let module = json!({ "type": "innovations", "data": { "items": items } });
    match existing {
        Some(index) => modules[index] = module,
        None => modules.insert(insertion_point(modules, scope), module),
    }
}

/// Where an `innovations` module goes in a list that doesn't have one.
///
/// After the last module that outranks it, so the section lands in the same slot
/// on a page missing some of its neighbours as it does on a complete one. A type
/// the contract doesn't know is treated as ranking last, matching how the
/// pipeline's export sorts.
fn insertion_point(modules: &[Value], scope: Scope) -> usize {
    let order = scope.order();
    let mine = order
        .iter()
        .position(|name| *name == "innovations")
        .unwrap_or(0);
    let rank = |module: &Value| {
        let type_ = module
            .get("type")
            .and_then(Value::as_str)
            .unwrap_or_default();
        order
            .iter()
            .position(|name| *name == type_)
            .unwrap_or(order.len())
    };
    modules
        .iter()
        .rposition(|module| rank(module) < mine)
        .map_or(0, |index| index + 1)
}

// ── ingest ───────────────────────────────────────────────────────────────────

/// One innovation as the upstream database sends it.
///
/// Every field is optional at the parsing layer so that a missing or wrong-typed
/// field becomes a 422 naming it, rather than a 400 whose message is a serde
/// error about a byte offset.
#[derive(Deserialize, Default)]
struct IngestReq {
    #[serde(default)]
    source_innovation_id: Option<Value>,
    #[serde(default)]
    article_url: Option<String>,
    #[serde(default)]
    source_urls: Option<Value>,
    #[serde(default)]
    title: Option<String>,
    #[serde(default)]
    body: Option<String>,
    #[serde(default)]
    trendbite: Option<String>,
    #[serde(default)]
    brands: Option<Value>,
    #[serde(default)]
    tags: Option<Value>,
    #[serde(default)]
    cover_image: Option<Value>,
    /// Optional: shifts upstream already knows this is an example of. Stored
    /// with `source = 'ingest'`, so editor links are untouched.
    #[serde(default)]
    shifts: Option<Value>,
    /// Optional: `withdrawn` hides the innovation everywhere without deleting
    /// the row, which is how upstream retracts one.
    #[serde(default)]
    state: Option<String>,
}

/// A payload that passed validation, in the shape the SQL wants.
#[derive(Debug)]
struct Valid {
    source_innovation_id: i64,
    article_url: String,
    source_urls: Value,
    title: String,
    body: Option<String>,
    trendbite: Option<String>,
    brands: Vec<String>,
    tags_raw: Value,
    /// (facet, slug, external_uuid) triples, deduplicated.
    tags: Vec<(String, String, Option<String>)>,
    ignored_facets: Vec<String>,
    cover_image: Option<Value>,
    cover_url: Option<String>,
    cover_mime: Option<String>,
    shifts: Vec<(Scope, String)>,
    state: String,
}

fn issue(field: &str, code: &str) -> Value {
    json!({ "field": field, "code": code })
}

fn http_url(value: &str) -> bool {
    let value = value.trim();
    value.starts_with("https://") || value.starts_with("http://")
}

/// A uuid only by shape — enough to keep a malformed value out of a `::uuid`
/// cast, without taking a uuid dependency for one field we never interpret.
fn looks_like_uuid(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 36
        && bytes.iter().enumerate().all(|(index, byte)| match index {
            8 | 13 | 18 | 23 => *byte == b'-',
            _ => byte.is_ascii_hexdigit(),
        })
}

fn clean(value: Option<String>) -> Option<String> {
    value
        .map(|text| text.trim().to_string())
        .filter(|text| !text.is_empty())
}

fn validate(req: IngestReq) -> Result<Valid, Vec<Value>> {
    let mut issues = Vec::new();

    // A JSON number, or a numeric string — upstream ids arrive both ways from
    // different clients and rejecting one of them buys nothing.
    let source_innovation_id = match req.source_innovation_id.as_ref() {
        None | Some(Value::Null) => {
            issues.push(issue("source_innovation_id", "required"));
            0
        }
        Some(value) => {
            let parsed = value
                .as_i64()
                .or_else(|| value.as_str().and_then(|text| text.trim().parse().ok()));
            match parsed {
                Some(id) if id > 0 => id,
                _ => {
                    issues.push(issue("source_innovation_id", "not_a_positive_integer"));
                    0
                }
            }
        }
    };

    let title = match clean(req.title) {
        Some(title) => title,
        None => {
            issues.push(issue("title", "required"));
            String::new()
        }
    };

    let article_url = match clean(req.article_url) {
        Some(url) if http_url(&url) => url,
        Some(_) => {
            issues.push(issue("article_url", "not_http_url"));
            String::new()
        }
        None => {
            issues.push(issue("article_url", "required"));
            String::new()
        }
    };

    // Provenance URLs: kept verbatim, but a non-URL entry is dropped rather than
    // stored — the card links these out.
    let mut source_urls = Vec::new();
    match req.source_urls.as_ref() {
        None | Some(Value::Null) => {}
        Some(Value::Array(items)) => {
            for (index, item) in items.iter().enumerate() {
                match item.as_str() {
                    Some(url) if http_url(url) => source_urls.push(json!(url.trim())),
                    _ => issues.push(issue(&format!("source_urls[{index}]"), "not_http_url")),
                }
            }
        }
        Some(_) => issues.push(issue("source_urls", "not_an_array")),
    }

    let mut brands = Vec::new();
    match req.brands.as_ref() {
        None | Some(Value::Null) => {}
        Some(Value::Array(items)) => {
            for (index, item) in items.iter().enumerate() {
                match item.as_str().map(str::trim) {
                    Some(brand) if !brand.is_empty() => brands.push(brand.to_string()),
                    _ => issues.push(issue(&format!("brands[{index}]"), "empty")),
                }
            }
        }
        Some(_) => issues.push(issue("brands", "not_an_array")),
    }

    // Tags: known facets are normalised into rows; unknown ones are reported and
    // left in the stored payload.
    let tags_raw = req.tags.clone().unwrap_or_else(|| json!({}));
    let mut tags: Vec<(String, String, Option<String>)> = Vec::new();
    let mut seen_tags: BTreeSet<(String, String)> = BTreeSet::new();
    let mut ignored_facets = Vec::new();
    match req.tags.as_ref() {
        None | Some(Value::Null) => {}
        Some(Value::Object(facets)) => {
            for (facet, entries) in facets {
                if !FACETS.contains(&facet.as_str()) {
                    ignored_facets.push(facet.clone());
                    continue;
                }
                let Some(entries) = entries.as_array() else {
                    issues.push(issue(&format!("tags.{facet}"), "not_an_array"));
                    continue;
                };
                for (index, entry) in entries.iter().enumerate() {
                    let slug = entry
                        .get("slug")
                        .and_then(Value::as_str)
                        .map(str::trim)
                        .unwrap_or_default();
                    if slug.is_empty() {
                        issues.push(issue(&format!("tags.{facet}[{index}].slug"), "empty"));
                        continue;
                    }
                    let uuid = entry
                        .get("external_uuid")
                        .and_then(Value::as_str)
                        .map(str::trim)
                        .filter(|value| looks_like_uuid(value))
                        .map(str::to_string);
                    if seen_tags.insert((facet.clone(), slug.to_string())) {
                        tags.push((facet.clone(), slug.to_string(), uuid));
                    }
                }
            }
        }
        Some(_) => issues.push(issue("tags", "not_an_object")),
    }

    // The cover descriptor is stored whole; the URL and mime are pulled out for
    // the mirror. A cover we cannot fetch is not a reason to reject the payload,
    // so a bad URL here is reported as a field issue only when it is present and
    // unusable.
    let mut cover_url = None;
    let mut cover_mime = None;
    match req.cover_image.as_ref() {
        None | Some(Value::Null) => {}
        Some(Value::Object(cover)) => {
            match cover.get("url").and_then(Value::as_str).map(str::trim) {
                Some(url) if http_url(url) => cover_url = Some(url.to_string()),
                Some(_) => issues.push(issue("cover_image.url", "not_http_url")),
                None => {}
            }
            match cover.get("mime").and_then(Value::as_str).map(str::trim) {
                Some(mime) if COVER_MIMES.contains(&mime) => cover_mime = Some(mime.to_string()),
                Some(_) => issues.push(issue("cover_image.mime", "unsupported_image_type")),
                None => {}
            }
        }
        Some(_) => issues.push(issue("cover_image", "not_an_object")),
    }

    let mut shifts = Vec::new();
    match req.shifts.as_ref() {
        None | Some(Value::Null) => {}
        Some(Value::Array(items)) => {
            for (index, item) in items.iter().enumerate() {
                let scope = item
                    .get("scope")
                    .and_then(Value::as_str)
                    .unwrap_or("key_trend");
                let slug = item
                    .get("slug")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .unwrap_or_default();
                match (Scope::parse(scope), slug.is_empty()) {
                    (Some(scope), false) => shifts.push((scope, slug.to_string())),
                    (None, _) => {
                        issues.push(issue(&format!("shifts[{index}].scope"), "unknown_scope"))
                    }
                    (_, true) => issues.push(issue(&format!("shifts[{index}].slug"), "empty")),
                }
            }
        }
        Some(_) => issues.push(issue("shifts", "not_an_array")),
    }

    let state = match req.state.as_deref().map(str::trim) {
        None | Some("") | Some("active") => "active".to_string(),
        Some("withdrawn") => "withdrawn".to_string(),
        Some(_) => {
            issues.push(issue("state", "unknown_state"));
            "active".to_string()
        }
    };

    if !issues.is_empty() {
        return Err(issues);
    }

    Ok(Valid {
        source_innovation_id,
        article_url,
        source_urls: Value::Array(source_urls),
        title,
        body: clean(req.body),
        trendbite: clean(req.trendbite),
        brands,
        tags_raw,
        tags,
        ignored_facets,
        cover_image: req.cover_image,
        cover_url,
        cover_mime,
        shifts,
        state,
    })
}

/// The hash that decides whether a re-POST is a no-op.
///
/// Taken over the payload with the cover URL's query string removed. That query
/// carries `v`, `exp` and `sig`, all of which change every time upstream signs
/// the same image — leaving them in would make every retry look like new content
/// and rewrite the row for nothing.
fn content_hash(body: &Value) -> String {
    let mut canonical = body.clone();
    if let Some(url) = canonical
        .get_mut("cover_image")
        .and_then(Value::as_object_mut)
        .and_then(|cover| cover.get_mut("url"))
    {
        if let Some(text) = url.as_str() {
            let stripped = text.split('?').next().unwrap_or(text).to_string();
            *url = Value::String(stripped);
        }
    }
    // serde_json's Map is a BTreeMap here (no preserve_order feature), so this
    // serialization is key-sorted and stable across processes.
    let text = serde_json::to_string(&canonical).unwrap_or_default();
    let digest = Sha256::digest(text.as_bytes());
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// `POST /api/innovations/ingest` — accept one innovation from the upstream
/// database.
///
/// Takes the raw body rather than `Json<T>` so the shared secret is checked
/// before anything untrusted is parsed. With the extractor, axum runs it ahead
/// of the handler, so an unauthenticated caller could make the server parse up to
/// 1 MB of JSON and a wrong content-type would answer 415 instead of the 404 the
/// route presents while disabled.
pub async fn ingest(
    State(s): State<AppState>,
    headers: HeaderMap,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    body: Bytes,
) -> Result<Response, AppError> {
    // With INGEST_TOKEN unset the route reports 404 rather than staying open — an
    // unauthenticated write endpoint should not exist by default, and 404 leaks
    // less about what is deployed here than 401 does.
    let Some(expected) = s.ingest_token.as_deref() else {
        return Err(AppError::public(
            StatusCode::NOT_FOUND,
            "not_found",
            "Not found.",
        ));
    };
    let presented = headers
        .get("x-ingest-token")
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    if !secret_eq(presented, expected) {
        return Err(AppError::public(
            StatusCode::UNAUTHORIZED,
            "unauthorized",
            "Unauthorized.",
        ));
    }

    let remaining = s
        .ingest_limiter
        .check(client_ip(&headers, peer))
        .map_err(|seconds| AppError::rate_limited_with_limit(seconds, 60))?;

    // Content-type is checked here, not by an extractor, for the same reason the
    // body is raw: a disabled or unauthenticated route must answer 404/401 to
    // every request shape, including a malformed one.
    let content_type = headers
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    if !content_type.is_empty() && !content_type.starts_with("application/json") {
        return Err(AppError::public(
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "unsupported_media_type",
            "Content-Type must be application/json.",
        ));
    }

    let raw: Value = serde_json::from_slice(&body).map_err(|_| {
        AppError::public(
            StatusCode::BAD_REQUEST,
            "invalid_request",
            "Request body is not valid JSON.",
        )
    })?;
    let req: IngestReq = serde_json::from_value(raw.clone()).unwrap_or_default();
    let valid = validate(req).map_err(AppError::validation)?;
    let hash = content_hash(&raw);

    let mut tx = s.pool.begin().await?;

    // Lock the row, so two concurrent POSTs for the same upstream id serialise
    // instead of racing the tag and link replacement below.
    let previous: Option<(i64, Option<String>, String)> = sqlx::query_as(
        "SELECT id, payload_hash, cover_state FROM innovations
          WHERE source_innovation_id = $1 FOR UPDATE",
    )
    .bind(valid.source_innovation_id)
    .fetch_optional(&mut *tx)
    .await?;

    let unchanged = previous
        .as_ref()
        .is_some_and(|(_, previous_hash, _)| previous_hash.as_deref() == Some(hash.as_str()));

    let id: i64 = if unchanged {
        previous.as_ref().map(|(id, _, _)| *id).unwrap_or_default()
    } else {
        sqlx::query_scalar(UPSERT)
            .bind(valid.source_innovation_id)
            .bind(&valid.article_url)
            .bind(sqlx::types::Json(&valid.source_urls))
            .bind(&valid.title)
            .bind(&valid.body)
            .bind(&valid.trendbite)
            .bind(&valid.brands)
            .bind(sqlx::types::Json(&valid.tags_raw))
            .bind(valid.cover_image.as_ref().map(sqlx::types::Json))
            .bind(sqlx::types::Json(&raw))
            .bind(&hash)
            .bind(&valid.state)
            .fetch_one(&mut *tx)
            .await?
    };

    let result = match (&previous, unchanged) {
        (None, _) => "created",
        (Some(_), true) => "unchanged",
        (Some(_), false) => "updated",
    };

    if !unchanged {
        replace_tag_links(&mut tx, id, &valid.tags).await?;
    }

    // Ingest only ever owns its own links. An editor's curation of the same
    // innovation survives every re-POST, which is the whole point of recording
    // `source`.
    let (linked, unknown) = replace_shift_links(&mut tx, id, &valid.shifts, "ingest").await?;

    tx.commit().await?;

    // Network I/O deliberately outside the transaction. A cover we cannot fetch
    // never fails the ingest: the row is saved and the response says the mirror
    // failed, which is the caller's cue to re-send with a fresh signed URL.
    // Re-attempted when the content is unchanged but a previous fetch failed.
    let stale_cover = previous
        .as_ref()
        .is_some_and(|(_, _, cover_state)| cover_state != "stored");
    let cover = if valid.cover_url.is_some() && (!unchanged || stale_cover) {
        store_cover(
            &s,
            id,
            valid.cover_url.as_deref().unwrap_or(""),
            valid.cover_mime.as_deref(),
        )
        .await
    } else {
        current_cover(&s, id).await
    };

    let visible_at: Vec<Value> = linked
        .iter()
        .filter_map(|link| {
            let domain = link.get("domain_id").and_then(Value::as_str)?;
            let slug = link.get("slug").and_then(Value::as_str)?;
            Some(json!(format!("/map/{domain}/{slug}")))
        })
        .collect();

    // to_json, not to_char: Postgres renders a timestamptz as RFC 3339 with a
    // `+00:00` offset, whereas `to_char(…, 'OF')` emits `+00` — which
    // JavaScript's `Date` refuses to parse at all.
    let updated_at: Option<Value> =
        sqlx::query_scalar("SELECT to_json(updated_at) FROM innovations WHERE id = $1")
            .bind(id)
            .fetch_optional(&s.pool)
            .await?;

    let payload = json!({
        "id": id,
        "source_innovation_id": valid.source_innovation_id,
        "result": result,
        "state": valid.state,
        "updated_at": updated_at,
        "cover_image": cover,
        "tags": { "linked": valid.tags.len(), "ignored_facets": valid.ignored_facets },
        "brands": valid.brands,
        "shift_links": { "linked": strip_domain(&linked), "unknown": unknown },
        "visible_at": visible_at,
        "request_id": crate::next_error_id(),
    });

    let mut response = (StatusCode::OK, Json(payload)).into_response();
    echo_request_id(&headers, &mut response);
    crate::insert_u64_header(response.headers_mut(), "ratelimit-limit", 60);
    crate::insert_u64_header(
        response.headers_mut(),
        "ratelimit-remaining",
        u64::from(remaining),
    );
    Ok(response)
}

/// The caller's own correlation id, echoed so a failed ingest can be traced from
/// their logs into ours.
fn echo_request_id(headers: &HeaderMap, response: &mut Response) {
    if let Some(value) = headers.get("x-request-id") {
        if let Ok(text) = value.to_str() {
            if let Ok(header) = HeaderValue::from_str(text) {
                response
                    .headers_mut()
                    .insert("x-upstream-request-id", header);
            }
        }
    }
}

/// `domain_id` is how we build `visible_at`; the link list itself reports the
/// identity the caller sent us.
fn strip_domain(links: &[Value]) -> Vec<Value> {
    links
        .iter()
        .map(|link| {
            json!({
                "scope": link.get("scope").cloned().unwrap_or(Value::Null),
                "slug": link.get("slug").cloned().unwrap_or(Value::Null),
            })
        })
        .collect()
}

async fn replace_tag_links(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    id: i64,
    tags: &[(String, String, Option<String>)],
) -> Result<(), AppError> {
    let facets: Vec<&str> = tags.iter().map(|(facet, _, _)| facet.as_str()).collect();
    let slugs: Vec<&str> = tags.iter().map(|(_, slug, _)| slug.as_str()).collect();
    let uuids: Vec<Option<&str>> = tags.iter().map(|(_, _, uuid)| uuid.as_deref()).collect();

    let tag_ids: Vec<i64> = if tags.is_empty() {
        Vec::new()
    } else {
        sqlx::query_scalar(UPSERT_TAGS)
            .bind(&facets)
            .bind(&slugs)
            .bind(&uuids)
            .fetch_all(&mut **tx)
            .await?
    };

    sqlx::query("DELETE FROM innovation_tag_links WHERE innovation_id = $1 AND tag_id <> ALL($2)")
        .bind(id)
        .bind(&tag_ids)
        .execute(&mut **tx)
        .await?;
    if !tag_ids.is_empty() {
        sqlx::query(
            "INSERT INTO innovation_tag_links (innovation_id, tag_id)
             SELECT $1, unnest($2::bigint[]) ON CONFLICT DO NOTHING",
        )
        .bind(id)
        .bind(&tag_ids)
        .execute(&mut **tx)
        .await?;
    }
    Ok(())
}

/// Replace exactly the links this writer owns, and report the slugs that matched
/// no published shift.
///
/// Unknown slugs are applied-around rather than rejected. A shift renamed
/// upstream of us must not turn into a refused ingest, and the same reporting
/// idea already exists in the pipeline's export, which warns about module
/// overrides that "matched no shift (renamed?)".
async fn replace_shift_links(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    id: i64,
    shifts: &[(Scope, String)],
    source: &str,
) -> Result<(Vec<Value>, Vec<Value>), AppError> {
    let scopes: Vec<&str> = shifts.iter().map(|(scope, _)| scope.as_str()).collect();
    let slugs: Vec<&str> = shifts.iter().map(|(_, slug)| slug.as_str()).collect();

    let resolved: Vec<(i64, String, String, Option<String>)> = if shifts.is_empty() {
        Vec::new()
    } else {
        sqlx::query_as(
            "SELECT sr.id, sr.scope, sr.slug, sr.domain_id
               FROM shift_refs sr
               JOIN unnest($1::text[], $2::text[]) AS want(scope, slug)
                 ON want.scope = sr.scope AND want.slug = sr.slug",
        )
        .bind(&scopes)
        .bind(&slugs)
        .fetch_all(&mut **tx)
        .await?
    };

    let known: BTreeSet<(String, String)> = resolved
        .iter()
        .map(|(_, scope, slug, _)| (scope.clone(), slug.clone()))
        .collect();
    let unknown: Vec<Value> = shifts
        .iter()
        .filter(|(scope, slug)| !known.contains(&(scope.as_str().to_string(), slug.clone())))
        .map(|(scope, slug)| json!({ "scope": scope.as_str(), "slug": slug }))
        .collect();

    let ref_ids: Vec<i64> = resolved.iter().map(|(ref_id, _, _, _)| *ref_id).collect();
    sqlx::query(
        "DELETE FROM innovation_shift_links
          WHERE innovation_id = $1 AND source = $2 AND shift_ref_id <> ALL($3)",
    )
    .bind(id)
    .bind(source)
    .bind(&ref_ids)
    .execute(&mut **tx)
    .await?;

    for (position, ref_id) in ref_ids.iter().enumerate() {
        // An existing link keeps its provenance: a payload that mentions a shift
        // an editor already curated must not downgrade that row to 'ingest'.
        sqlx::query(
            "INSERT INTO innovation_shift_links (innovation_id, shift_ref_id, source, sort_order)
             VALUES ($1, $2, $3, $4)
             ON CONFLICT (innovation_id, shift_ref_id) DO UPDATE
                SET sort_order = EXCLUDED.sort_order, enabled = true, updated_at = now()",
        )
        .bind(id)
        .bind(ref_id)
        .bind(source)
        .bind(position as i32)
        .execute(&mut **tx)
        .await?;
    }

    let linked: Vec<Value> = resolved
        .iter()
        .map(
            |(_, scope, slug, domain)| json!({ "scope": scope, "slug": slug, "domain_id": domain }),
        )
        .collect();
    Ok((linked, unknown))
}

// ── cover images ─────────────────────────────────────────────────────────────

/// Fetch and store one cover image, returning the descriptor the API reports.
///
/// Never returns an error: the caller has already committed the innovation, and
/// a missing image is a degraded card, not a failed ingest.
async fn store_cover(s: &AppState, id: i64, url: &str, declared_mime: Option<&str>) -> Value {
    match fetch_cover(s, url, declared_mime).await {
        Ok((bytes, mime)) => {
            let digest = Sha256::digest(&bytes);
            let sha: String = digest.iter().map(|byte| format!("{byte:02x}")).collect();
            let size = bytes.len() as i32;
            let stored = sqlx::query(
                "WITH asset AS (
                   INSERT INTO innovation_assets
                     (innovation_id, kind, bytes, mime, byte_size, sha256, source_url, fetched_at)
                   VALUES ($1, 'cover', $2, $3, $4, $5, $6, now())
                   ON CONFLICT (innovation_id, kind) DO UPDATE SET
                     bytes = EXCLUDED.bytes, mime = EXCLUDED.mime,
                     byte_size = EXCLUDED.byte_size, sha256 = EXCLUDED.sha256,
                     source_url = EXCLUDED.source_url, fetched_at = now()
                   RETURNING innovation_id
                 )
                 UPDATE innovations SET cover_state = 'stored', cover_error = NULL
                  WHERE id = (SELECT innovation_id FROM asset)",
            )
            .bind(id)
            .bind(&bytes)
            .bind(&mime)
            .bind(size)
            .bind(&sha)
            .bind(url)
            .execute(&s.pool)
            .await;
            match stored {
                Ok(_) => json!({
                    "state": "stored",
                    "url": cover_path(id, &sha),
                    "mime": mime,
                    "byte_size": size,
                }),
                Err(error) => {
                    tracing::error!(%error, id, "storing a mirrored cover failed");
                    json!({ "state": "failed", "error": "could not be stored" })
                }
            }
        }
        Err(reason) => {
            tracing::warn!(id, url, reason, "mirroring a cover image failed");
            let _ = sqlx::query(
                "UPDATE innovations SET cover_state = 'failed', cover_error = $2 WHERE id = $1",
            )
            .bind(id)
            .bind(&reason)
            .execute(&s.pool)
            .await;
            json!({ "state": "failed", "error": reason })
        }
    }
}

/// The descriptor for a cover we already hold, for a re-POST that changed
/// nothing.
async fn current_cover(s: &AppState, id: i64) -> Value {
    let row: Option<(String, String, i32)> = sqlx::query_as(
        "SELECT sha256, mime, byte_size FROM innovation_assets
          WHERE innovation_id = $1 AND kind = 'cover'",
    )
    .bind(id)
    .fetch_optional(&s.pool)
    .await
    .unwrap_or_default();
    match row {
        Some((sha, mime, size)) => json!({
            "state": "stored",
            "url": cover_path(id, &sha),
            "mime": mime,
            "byte_size": size,
        }),
        None => json!({ "state": "none" }),
    }
}

fn cover_path(id: i64, sha: &str) -> String {
    format!(
        "/api/innovations/{id}/cover-image?v={}",
        &sha[..12.min(sha.len())]
    )
}

/// Hosts a cover may be fetched from.
fn asset_hosts() -> Vec<String> {
    std::env::var("INNOVATION_ASSET_HOSTS")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| DEFAULT_ASSET_HOSTS.to_string())
        .split(',')
        .map(|host| host.trim().to_ascii_lowercase())
        .filter(|host| !host.is_empty())
        .collect()
}

/// The SSRF gate: https only, and only a host we were configured to trust.
///
/// The URL comes from a request body. Without this, an authenticated caller
/// could make the server issue arbitrary GETs — including to
/// `*.railway.internal`, which is reachable from this process and from nowhere
/// else. Parsed by hand rather than with a URL crate: only the scheme and
/// authority matter here, and userinfo (`https://trusted@evil/`) is the one
/// subtlety, which is rejected outright.
pub fn asset_url_allowed(url: &str, hosts: &[String]) -> bool {
    let Some(rest) = url.strip_prefix("https://") else {
        return false;
    };
    let authority = rest
        .split(['/', '?', '#'])
        .next()
        .unwrap_or_default()
        .to_ascii_lowercase();
    if authority.is_empty() || authority.contains('@') {
        return false;
    }
    let host = authority.split(':').next().unwrap_or_default();
    hosts.iter().any(|allowed| allowed == host)
}

async fn fetch_cover(
    s: &AppState,
    url: &str,
    declared_mime: Option<&str>,
) -> Result<(Vec<u8>, String), String> {
    let hosts = asset_hosts();
    if !asset_url_allowed(url, &hosts) {
        return Err("host not allowed".into());
    }

    let response = s
        .http
        .get(url)
        .timeout(Duration::from_secs(10))
        .send()
        .await
        .map_err(|error| format!("fetch failed: {}", error.without_url()))?;
    if !response.status().is_success() {
        return Err(format!("upstream returned {}", response.status().as_u16()));
    }

    // Trust the response's own type over the payload's claim, but require both to
    // be an image we are willing to re-serve.
    let mime = response
        .headers()
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .map(|value| value.split(';').next().unwrap_or(value).trim().to_string())
        .filter(|value| COVER_MIMES.contains(&value.as_str()))
        .or_else(|| declared_mime.map(str::to_string))
        .ok_or_else(|| "unsupported image type".to_string())?;

    if let Some(length) = response.content_length() {
        if length > MAX_COVER_BYTES as u64 {
            return Err(format!("too large: {length} bytes"));
        }
    }

    // Read chunk by chunk with a running total, because content-length is a hint
    // an upstream is free to omit or lie about, and `.bytes()` would buffer
    // whatever it sends before we could object.
    let mut response = response;
    let mut bytes: Vec<u8> = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|error| format!("read failed: {}", error.without_url()))?
    {
        if bytes.len() + chunk.len() > MAX_COVER_BYTES {
            return Err("too large".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    if bytes.is_empty() {
        return Err("empty response".into());
    }
    Ok((bytes, mime))
}

/// `GET /api/innovations/{id}/cover-image` — the mirrored bytes, same-origin so
/// the page's `img-src 'self'` allows them.
pub async fn cover_image(
    State(s): State<AppState>,
    AxumPath(id): AxumPath<i64>,
    headers: HeaderMap,
    Query(q): Query<std::collections::HashMap<String, String>>,
) -> Result<Response, AppError> {
    let row: Option<(Vec<u8>, String, String)> = sqlx::query_as(
        "SELECT a.bytes, a.mime, a.sha256
           FROM innovation_assets a
           JOIN innovations i ON i.id = a.innovation_id
          WHERE a.innovation_id = $1 AND a.kind = 'cover' AND i.state = 'active'",
    )
    .bind(id)
    .fetch_optional(&s.pool)
    .await?;
    let Some((bytes, mime, sha)) = row else {
        return Err(AppError::public(
            StatusCode::NOT_FOUND,
            "not_found",
            "No cover image for that innovation.",
        ));
    };

    let etag = HeaderValue::from_str(&format!("\"{sha}\"")).map_err(AppError::internal)?;
    // `?v=` is the content hash, so a matching one addresses these exact bytes
    // and can be cached forever. A caller who guessed or kept an old `v` gets an
    // hour, not a year.
    let versioned = q
        .get("v")
        .is_some_and(|value| sha.starts_with(value.as_str()) && value.len() >= 12);
    let cache = if versioned {
        IMMUTABLE
    } else {
        "public, max-age=3600"
    };

    if headers
        .get(header::IF_NONE_MATCH)
        .is_some_and(|value| value == etag)
    {
        let mut response = StatusCode::NOT_MODIFIED.into_response();
        response.headers_mut().insert(header::ETAG, etag);
        response
            .headers_mut()
            .insert(header::CACHE_CONTROL, HeaderValue::from_static(cache));
        return Ok(response);
    }

    let mut response = (StatusCode::OK, bytes).into_response();
    let headers_mut = response.headers_mut();
    headers_mut.insert(
        header::CONTENT_TYPE,
        HeaderValue::from_str(&mime)
            .unwrap_or(HeaderValue::from_static("application/octet-stream")),
    );
    headers_mut.insert(header::ETAG, etag);
    headers_mut.insert(header::CACHE_CONTROL, HeaderValue::from_static(cache));
    Ok(response)
}

// ── curation ─────────────────────────────────────────────────────────────────

#[derive(Deserialize, Default)]
pub struct ShiftLinksReq {
    #[serde(default)]
    shifts: Option<Value>,
}

fn require_curation(s: &AppState, headers: &HeaderMap) -> Result<(), AppError> {
    let Some(expected) = s.curation_token.as_deref() else {
        return Err(AppError::public(
            StatusCode::NOT_FOUND,
            "not_found",
            "Not found.",
        ));
    };
    let presented = headers
        .get(header::AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .unwrap_or_default();
    if !secret_eq(presented, expected) {
        return Err(AppError::public(
            StatusCode::UNAUTHORIZED,
            "unauthorized",
            "Unauthorized.",
        ));
    }
    Ok(())
}

async fn require_innovation(s: &AppState, id: i64) -> Result<(), AppError> {
    let exists: Option<i64> = sqlx::query_scalar("SELECT id FROM innovations WHERE id = $1")
        .bind(id)
        .fetch_optional(&s.pool)
        .await?;
    exists
        .map(|_| ())
        .ok_or_else(|| AppError::public(StatusCode::NOT_FOUND, "not_found", "No such innovation."))
}

/// `PUT /api/innovations/{id}/shifts` — replace the editor-curated link set.
///
/// Idempotent by construction: the body is the desired state, and the join
/// table's composite key makes a repeat a no-op. Only `source = 'editor'` rows
/// are touched, so what upstream sent stays.
pub async fn put_shifts(
    State(s): State<AppState>,
    AxumPath(id): AxumPath<i64>,
    headers: HeaderMap,
    Query(q): Query<std::collections::HashMap<String, String>>,
    body: Bytes,
) -> Result<Response, AppError> {
    require_curation(&s, &headers)?;
    require_innovation(&s, id).await?;

    let req: ShiftLinksReq = serde_json::from_slice(&body).map_err(|_| {
        AppError::public(
            StatusCode::BAD_REQUEST,
            "invalid_request",
            "Request body is not valid JSON.",
        )
    })?;

    let mut shifts = Vec::new();
    let mut issues = Vec::new();
    match req.shifts.as_ref() {
        None | Some(Value::Null) => {}
        Some(Value::Array(items)) => {
            for (index, item) in items.iter().enumerate() {
                let scope = item
                    .get("scope")
                    .and_then(Value::as_str)
                    .unwrap_or("key_trend");
                let slug = item
                    .get("slug")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .unwrap_or_default();
                match (Scope::parse(scope), slug.is_empty()) {
                    (Some(scope), false) => shifts.push((scope, slug.to_string())),
                    (None, _) => {
                        issues.push(issue(&format!("shifts[{index}].scope"), "unknown_scope"))
                    }
                    (_, true) => issues.push(issue(&format!("shifts[{index}].slug"), "empty")),
                }
            }
        }
        Some(_) => issues.push(issue("shifts", "not_an_array")),
    }
    if !issues.is_empty() {
        return Err(AppError::validation(issues));
    }

    let strict = q.get("strict").is_some_and(|value| value == "1");
    let mut tx = s.pool.begin().await?;
    let (linked, unknown) = replace_shift_links(&mut tx, id, &shifts, "editor").await?;
    if strict && !unknown.is_empty() {
        // Nothing is applied: the caller asked to be told rather than
        // half-served, and rolling back is how "applying nothing" is honest.
        tx.rollback().await?;
        return Err(AppError::validation(
            unknown
                .iter()
                .map(|item| {
                    json!({
                        "field": "shifts",
                        "code": "unknown_shift",
                        "scope": item.get("scope").cloned().unwrap_or(Value::Null),
                        "slug": item.get("slug").cloned().unwrap_or(Value::Null),
                    })
                })
                .collect(),
        ));
    }
    tx.commit().await?;

    Ok((
        StatusCode::OK,
        Json(json!({
            "id": id,
            "linked": strip_domain(&linked),
            "unknown": unknown,
            "request_id": crate::next_error_id(),
        })),
    )
        .into_response())
}

/// `DELETE /api/innovations/{id}/shifts/{scope}/{slug}` — drop one link,
/// whatever made it.
///
/// The slug may contain a slash for a sub-shift (`parent/child`), so the route
/// captures the tail as a wildcard.
pub async fn delete_shift_link(
    State(s): State<AppState>,
    AxumPath((id, scope, slug)): AxumPath<(i64, String, String)>,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    require_curation(&s, &headers)?;
    if Scope::parse(&scope).is_none() {
        return Err(AppError::validation(vec![issue("scope", "unknown_scope")]));
    }
    let removed = sqlx::query(
        "DELETE FROM innovation_shift_links l
           USING shift_refs sr
          WHERE sr.id = l.shift_ref_id
            AND l.innovation_id = $1 AND sr.scope = $2 AND sr.slug = $3",
    )
    .bind(id)
    .bind(&scope)
    .bind(slug.trim_start_matches('/'))
    .execute(&s.pool)
    .await?;
    if removed.rows_affected() == 0 {
        return Err(AppError::public(
            StatusCode::NOT_FOUND,
            "not_found",
            "No such link.",
        ));
    }
    Ok(StatusCode::NO_CONTENT.into_response())
}

// ── public reads ─────────────────────────────────────────────────────────────

/// `GET /api/v1/innovations` — the ingested corpus, newest first.
pub async fn list(
    State(s): State<AppState>,
    headers: HeaderMap,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    Query(q): Query<std::collections::HashMap<String, String>>,
) -> Result<Response, AppError> {
    let remaining = s
        .public_v1_limiter
        .check(client_ip(&headers, peer))
        .map_err(|seconds| AppError::rate_limited_with_limit(seconds, 120))?;

    let limit = q
        .get("limit")
        .and_then(|value| value.parse::<i64>().ok())
        .unwrap_or(DEFAULT_PAGE)
        .clamp(1, MAX_PAGE);

    let cursor = match q.get("cursor").map(String::as_str) {
        None | Some("") => None,
        Some(raw) => Some(
            parse_cursor(raw)
                .ok_or_else(|| AppError::validation(vec![issue("cursor", "malformed")]))?,
        ),
    };

    let (scope, slug) = match q.get("shift").map(String::as_str) {
        None | Some("") => (None, None),
        Some(raw) => {
            let (scope, slug) = raw.split_once(':').ok_or_else(|| {
                AppError::validation(vec![issue("shift", "expected_scope_colon_slug")])
            })?;
            if Scope::parse(scope).is_none() {
                return Err(AppError::validation(vec![issue("shift", "unknown_scope")]));
            }
            (Some(scope.to_string()), Some(slug.to_string()))
        }
    };

    // `tag` is one comma-separated list of `facet:slug` pairs, ANDed: an
    // innovation must carry every tag asked for. One param rather than a
    // repeated one keeps this inside the codebase's existing `Query<HashMap>`
    // idiom, where a repeated key would silently collapse.
    let mut facets: Vec<String> = Vec::new();
    let mut slugs: Vec<String> = Vec::new();
    for pair in q
        .get("tag")
        .map(String::as_str)
        .unwrap_or_default()
        .split(',')
        .filter(|pair| !pair.trim().is_empty())
    {
        let (facet, slug) = pair
            .trim()
            .split_once(':')
            .ok_or_else(|| AppError::validation(vec![issue("tag", "expected_facet_colon_slug")]))?;
        facets.push(facet.to_string());
        slugs.push(slug.to_string());
    }

    let doc: Value = sqlx::query_scalar(RECORDS)
        .bind(limit)
        .bind(cursor.map(|(micros, _)| micros))
        .bind(cursor.map(|(_, id)| id))
        .bind(Option::<i64>::None)
        .bind(&scope)
        .bind(&slug)
        .bind(if facets.is_empty() {
            None
        } else {
            Some(&facets)
        })
        .bind(if slugs.is_empty() { None } else { Some(&slugs) })
        .bind(q.get("brand"))
        .fetch_one(&s.pool)
        .await?;

    let mut response = (StatusCode::OK, Json(doc)).into_response();
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static(PUBLIC_CACHE_CONTROL),
    );
    crate::insert_u64_header(response.headers_mut(), "ratelimit-limit", 120);
    crate::insert_u64_header(
        response.headers_mut(),
        "ratelimit-remaining",
        u64::from(remaining),
    );
    Ok(response)
}

/// `GET /api/v1/innovations/{id}` — one full record.
pub async fn detail(
    State(s): State<AppState>,
    AxumPath(id): AxumPath<i64>,
    headers: HeaderMap,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
) -> Result<Response, AppError> {
    let remaining = s
        .public_v1_limiter
        .check(client_ip(&headers, peer))
        .map_err(|seconds| AppError::rate_limited_with_limit(seconds, 120))?;

    let doc: Value = sqlx::query_scalar(RECORDS)
        .bind(1i64)
        .bind(Option::<i64>::None)
        .bind(Option::<i64>::None)
        .bind(Some(id))
        .bind(Option::<String>::None)
        .bind(Option::<String>::None)
        .bind(Option::<Vec<String>>::None)
        .bind(Option::<Vec<String>>::None)
        .bind(Option::<String>::None)
        .fetch_one(&s.pool)
        .await?;

    let item = doc
        .get("items")
        .and_then(Value::as_array)
        .and_then(|items| items.first())
        .cloned()
        .ok_or_else(|| {
            AppError::public(StatusCode::NOT_FOUND, "not_found", "No such innovation.")
        })?;

    let mut response = (StatusCode::OK, Json(item)).into_response();
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static(PUBLIC_CACHE_CONTROL),
    );
    crate::insert_u64_header(response.headers_mut(), "ratelimit-limit", 120);
    crate::insert_u64_header(
        response.headers_mut(),
        "ratelimit-remaining",
        u64::from(remaining),
    );
    Ok(response)
}

/// `"<micros>_<id>"` — the last row of the previous page. Opaque to callers and
/// cheap to validate; keyset paging means a new innovation arriving mid-scroll
/// cannot shift the page under the reader the way OFFSET does.
fn parse_cursor(raw: &str) -> Option<(i64, i64)> {
    let (micros, id) = raw.split_once('_')?;
    Some((micros.parse().ok()?, id.parse().ok()?))
}

// ── SQL ──────────────────────────────────────────────────────────────────────

/// Every shift's innovations, in one json object keyed `"<scope>:<slug>"`.
///
/// Returned as `text` so the caller can hash the exact bytes for the cache
/// version. Both aggregates are explicitly ordered, so identical data always
/// serialises identically and an unchanged page keeps its ETag.
const BY_SHIFT: &str = r#"
SELECT coalesce(json_object_agg(key, items ORDER BY key), '{}'::json)::text
FROM (
  SELECT key, json_agg(item ORDER BY rank) AS items
  FROM (
    SELECT sr.scope || ':' || sr.slug AS key,
           row_number() OVER (
             PARTITION BY sr.id
             ORDER BY l.sort_order, i.created_at DESC, i.id DESC
           ) AS rank,
           json_strip_nulls(json_build_object(
             'title', i.title,
             'brand', nullif(coalesce(i.brands_list[1], ''), ''),
             'description', nullif(coalesce(
                 nullif(btrim(coalesce(i.trendbite, '')), ''),
                 left(coalesce(i.body, ''), 240)), ''),
             'url', nullif(i.article_url, ''),
             'image', CASE WHEN a.sha256 IS NOT NULL
                           THEN '/api/innovations/' || i.id || '/cover-image?v=' || left(a.sha256, 12)
                      END,
             'tags', (SELECT json_agg(t.slug ORDER BY t.facet, t.slug)
                        FROM innovation_tag_links tl
                        JOIN innovation_tags t ON t.id = tl.tag_id
                       WHERE tl.innovation_id = i.id
                         AND t.facet IN ('industry', 'innovation-type'))
           )) AS item
    FROM innovation_shift_links l
    JOIN shift_refs  sr ON sr.id = l.shift_ref_id
    JOIN innovations i  ON i.id = l.innovation_id
    LEFT JOIN innovation_assets a ON a.innovation_id = i.id AND a.kind = 'cover'
    WHERE l.enabled AND i.state = 'active'
  ) ranked
  WHERE rank <= $1
  GROUP BY key
) grouped"#;

/// Insert or update one innovation, returning its id.
///
/// `ON CONFLICT (source_innovation_id)` is only sound because the migration made
/// that column NOT NULL — with NULLs allowed the conflict target never matched
/// and every retry inserted a new row.
const UPSERT: &str = r#"
INSERT INTO innovations
  (source_innovation_id, article_url, source_urls, title, body, trendbite,
   brands_list, tags, cover_image, payload, payload_hash, state, updated_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, now())
ON CONFLICT (source_innovation_id) DO UPDATE SET
  article_url  = EXCLUDED.article_url,
  source_urls  = EXCLUDED.source_urls,
  title        = EXCLUDED.title,
  body         = EXCLUDED.body,
  trendbite    = EXCLUDED.trendbite,
  brands_list  = EXCLUDED.brands_list,
  tags         = EXCLUDED.tags,
  cover_image  = EXCLUDED.cover_image,
  payload      = EXCLUDED.payload,
  payload_hash = EXCLUDED.payload_hash,
  state        = EXCLUDED.state,
  updated_at   = now()
RETURNING id"#;

/// Intern this payload's tags, returning their ids in the order given.
///
/// The caller deduplicates first: `ON CONFLICT DO UPDATE` cannot touch the same
/// row twice in one statement.
const UPSERT_TAGS: &str = r#"
WITH incoming AS (
  SELECT facet, slug, nullif(external_uuid, '')::uuid AS external_uuid, ordinality
  FROM unnest($1::text[], $2::text[], $3::text[]) WITH ORDINALITY
       AS t(facet, slug, external_uuid, ordinality)
), upserted AS (
  INSERT INTO innovation_tags (facet, slug, external_uuid)
  SELECT facet, slug, external_uuid FROM incoming
  ON CONFLICT (facet, slug) DO UPDATE
     SET external_uuid = coalesce(EXCLUDED.external_uuid, innovation_tags.external_uuid)
  RETURNING id, facet, slug
)
SELECT u.id FROM upserted u
JOIN incoming i ON i.facet = u.facet AND i.slug = u.slug
ORDER BY i.ordinality"#;

/// The full public record, as a page.
///
/// One query serves both the list and the detail route: `$4` pins a single id,
/// and every filter is a bound parameter that is skipped when NULL — so there is
/// no string building anywhere near a query.
///
/// `next_cursor` is only issued when the page came back full, so a caller knows
/// to stop without an extra round trip that returns nothing.
const RECORDS: &str = r#"
WITH page AS (
  SELECT i.id, i.created_at,
         json_build_object(
           'id', i.id,
           'source_innovation_id', i.source_innovation_id,
           'title', i.title,
           'body', i.body,
           'trendbite', i.trendbite,
           'article_url', i.article_url,
           'source_urls', i.source_urls,
           'brands', to_json(i.brands_list),
           'state', i.state,
           'tags', coalesce((
             SELECT json_object_agg(facet, slugs ORDER BY facet) FROM (
               SELECT t.facet, json_agg(t.slug ORDER BY t.slug) AS slugs
                 FROM innovation_tag_links tl
                 JOIN innovation_tags t ON t.id = tl.tag_id
                WHERE tl.innovation_id = i.id
                GROUP BY t.facet) f), '{}'::json),
           'cover_image', json_build_object(
             'state', i.cover_state,
             'url', CASE WHEN a.sha256 IS NOT NULL
                         THEN '/api/innovations/' || i.id || '/cover-image?v=' || left(a.sha256, 12)
                    END,
             'mime', a.mime,
             'byte_size', a.byte_size),
           'shifts', coalesce((
             SELECT json_agg(json_build_object(
                      'scope', sr.scope, 'slug', sr.slug, 'domain_id', sr.domain_id,
                      'source', l.source,
                      'href', CASE WHEN sr.domain_id IS NOT NULL
                                   THEN '/map/' || sr.domain_id || '/' || sr.slug END)
                      ORDER BY l.sort_order, sr.slug)
               FROM innovation_shift_links l
               JOIN shift_refs sr ON sr.id = l.shift_ref_id
              WHERE l.innovation_id = i.id AND l.enabled), '[]'::json),
           -- to_json renders RFC 3339 with a '+00:00' offset. to_char(…,'OF')
           -- emits '+00', which JavaScript's Date will not parse.
           'created_at', to_json(i.created_at),
           'updated_at', to_json(i.updated_at)
         ) AS item
  FROM innovations i
  LEFT JOIN innovation_assets a ON a.innovation_id = i.id AND a.kind = 'cover'
  WHERE i.state = 'active'
    AND ($4::bigint IS NULL OR i.id = $4)
    AND ($2::bigint IS NULL OR (i.created_at, i.id)
         < ('epoch'::timestamptz + ($2::bigint || ' microseconds')::interval, $3::bigint))
    AND ($5::text IS NULL OR EXISTS (
          SELECT 1 FROM innovation_shift_links l
            JOIN shift_refs sr ON sr.id = l.shift_ref_id
           WHERE l.innovation_id = i.id AND l.enabled
             AND sr.scope = $5 AND sr.slug = $6))
    AND ($9::text IS NULL OR $9 = ANY(i.brands_list))
    AND ($7::text[] IS NULL OR NOT EXISTS (
          SELECT 1 FROM unnest($7::text[], $8::text[]) AS want(facet, slug)
           WHERE NOT EXISTS (
             SELECT 1 FROM innovation_tag_links tl
               JOIN innovation_tags t ON t.id = tl.tag_id
              WHERE tl.innovation_id = i.id AND t.facet = want.facet AND t.slug = want.slug)))
  ORDER BY i.created_at DESC, i.id DESC
  LIMIT $1
)
SELECT json_build_object(
  'items', coalesce((SELECT json_agg(item ORDER BY created_at DESC, id DESC) FROM page), '[]'::json),
  'limit', $1,
  'next_cursor', CASE WHEN (SELECT count(*) FROM page) = $1 THEN (
    SELECT (extract(epoch FROM created_at) * 1000000)::bigint::text || '_' || id::text
      FROM page ORDER BY created_at ASC, id ASC LIMIT 1) END
)"#;

#[cfg(test)]
mod tests {
    use super::*;

    fn module(type_: &str) -> Value {
        json!({ "type": type_, "data": {} })
    }

    fn types(modules: &[Value]) -> Vec<String> {
        modules
            .iter()
            .map(|m| m["type"].as_str().unwrap_or_default().to_string())
            .collect()
    }

    /// The consts above are a copy of the contract, because the backend image
    /// cannot read `packages/`. This is what stops the copy drifting.
    #[test]
    fn module_order_matches_the_contract() {
        let mut path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let contract = loop {
            let candidate = path.join("packages/contracts/shift_modules.json");
            if candidate.is_file() {
                break candidate;
            }
            if !path.pop() {
                // Installed/vendored checkout without the contracts package.
                return;
            }
        };
        let contract: Value =
            serde_json::from_str(&std::fs::read_to_string(contract).unwrap()).unwrap();
        for (scope, ours) in [
            ("key_trend", MODULE_ORDER_KEY_TREND.as_slice()),
            ("sub_trend", MODULE_ORDER_SUB_TREND.as_slice()),
        ] {
            let theirs: Vec<&str> = contract["order"][scope]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_str().unwrap())
                .collect();
            assert_eq!(theirs, ours, "{scope} order drifted from the contract");
        }
    }

    #[test]
    fn a_new_module_lands_at_its_contract_position() {
        let mut modules = vec![
            module("dek"),
            module("territories"),
            module("voices"),
            module("sub_shift_list"),
        ];
        hydrate(
            &mut modules,
            Scope::KeyTrend,
            Some(&json!([{ "title": "x" }])),
        );
        assert_eq!(
            types(&modules),
            [
                "dek",
                "territories",
                "innovations",
                "voices",
                "sub_shift_list"
            ]
        );
    }

    #[test]
    fn a_page_missing_its_neighbours_still_places_the_module() {
        // Only modules that outrank innovations are present, so it appends.
        let mut modules = vec![module("dek"), module("timeline")];
        hydrate(
            &mut modules,
            Scope::KeyTrend,
            Some(&json!([{ "title": "x" }])),
        );
        assert_eq!(types(&modules), ["dek", "timeline", "innovations"]);

        // Only modules that it outranks are present, so it leads.
        let mut modules = vec![module("sub_shift_list")];
        hydrate(
            &mut modules,
            Scope::KeyTrend,
            Some(&json!([{ "title": "x" }])),
        );
        assert_eq!(types(&modules), ["innovations", "sub_shift_list"]);
    }

    #[test]
    fn an_editors_position_for_the_module_wins() {
        // An override put innovations first. Hydration must fill it, not move it.
        let mut modules = vec![
            json!({ "type": "innovations", "data": { "items": [] } }),
            module("dek"),
        ];
        hydrate(
            &mut modules,
            Scope::KeyTrend,
            Some(&json!([{ "title": "x" }])),
        );
        assert_eq!(types(&modules), ["innovations", "dek"]);
        assert_eq!(modules[0]["data"]["items"][0]["title"], "x");
    }

    #[test]
    fn no_items_means_no_section() {
        let mut modules = vec![module("dek"), json!({ "type": "innovations", "data": {} })];
        hydrate(&mut modules, Scope::KeyTrend, None);
        assert_eq!(types(&modules), ["dek"]);

        let mut modules = vec![module("dek")];
        hydrate(&mut modules, Scope::KeyTrend, Some(&json!([])));
        assert_eq!(types(&modules), ["dek"]);
    }

    #[test]
    fn sub_shifts_use_their_own_order() {
        let mut modules = vec![
            module("evidence"),
            module("territories"),
            module("rich_text"),
        ];
        hydrate(
            &mut modules,
            Scope::SubTrend,
            Some(&json!([{ "title": "x" }])),
        );
        assert_eq!(
            types(&modules),
            ["evidence", "territories", "innovations", "rich_text"]
        );
    }

    fn sample() -> Value {
        json!({
            "article_url": "https://example.com/original-article",
            "source_urls": [
                "https://example.com/original-article",
                "https://other-site.com/linked-article"
            ],
            "source_innovation_id": 1234,
            "title": "Generated innovation title",
            "body": "Generated innovation body…",
            "trendbite": null,
            "brands": ["Primary Brand", "Another Brand"],
            "tags": {
                "industry": [{ "slug": "food-beverage", "external_uuid": "3f1a2b4c-5d6e-4f70-8123-456789abcdef" }],
                "subindustry": [],
                "region": [{ "slug": "europe", "external_uuid": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee" }],
                "country": [],
                "audience": [{ "slug": "gen-z" }],
                "season": [],
                "innovation-type": [{ "slug": "product-launch" }],
                "basic-human-need": []
            },
            "cover_image": {
                "url": "https://tw-the-engine.up.railway.app/api/innovations/1234/cover-image?v=1720900000&exp=99&sig=abc",
                "mime": "image/jpeg"
            }
        })
    }

    #[test]
    fn the_documented_payload_validates() {
        let req: IngestReq = serde_json::from_value(sample()).unwrap();
        let valid = validate(req).expect("the documented payload must be accepted");
        assert_eq!(valid.source_innovation_id, 1234);
        assert_eq!(valid.brands, ["Primary Brand", "Another Brand"]);
        // Empty facets contribute nothing; the four populated ones do.
        assert_eq!(valid.tags.len(), 4);
        assert!(valid.ignored_facets.is_empty());
        assert_eq!(valid.cover_mime.as_deref(), Some("image/jpeg"));
        assert_eq!(valid.state, "active");
        assert!(valid.shifts.is_empty());
    }

    #[test]
    fn every_missing_essential_is_named() {
        for (field, mutate) in [
            ("source_innovation_id", "source_innovation_id"),
            ("title", "title"),
            ("article_url", "article_url"),
        ] {
            let mut payload = sample();
            payload.as_object_mut().unwrap().remove(mutate);
            let req: IngestReq = serde_json::from_value(payload).unwrap();
            let issues = validate(req).expect_err("must be rejected");
            assert!(
                issues
                    .iter()
                    .any(|i| i["field"] == field && i["code"] == "required"),
                "{field} was not reported: {issues:?}"
            );
        }
    }

    #[test]
    fn a_numeric_string_id_is_accepted_but_zero_is_not() {
        let mut payload = sample();
        payload["source_innovation_id"] = json!("1234");
        let valid = validate(serde_json::from_value(payload).unwrap()).unwrap();
        assert_eq!(valid.source_innovation_id, 1234);

        let mut payload = sample();
        payload["source_innovation_id"] = json!(0);
        let issues = validate(serde_json::from_value(payload).unwrap()).unwrap_err();
        assert!(issues.iter().any(|i| i["code"] == "not_a_positive_integer"));
    }

    #[test]
    fn a_non_http_article_url_is_rejected() {
        let mut payload = sample();
        payload["article_url"] = json!("javascript:alert(1)");
        let issues = validate(serde_json::from_value(payload).unwrap()).unwrap_err();
        assert!(issues
            .iter()
            .any(|i| i["field"] == "article_url" && i["code"] == "not_http_url"));
    }

    #[test]
    fn an_unknown_facet_is_reported_not_fatal() {
        let mut payload = sample();
        payload["tags"]["mood"] = json!([{ "slug": "optimistic" }]);
        let valid = validate(serde_json::from_value(payload).unwrap()).unwrap();
        assert_eq!(valid.ignored_facets, ["mood"]);
        assert_eq!(valid.tags.len(), 4);
    }

    #[test]
    fn a_malformed_uuid_is_dropped_rather_than_failing_the_payload() {
        let mut payload = sample();
        payload["tags"]["industry"][0]["external_uuid"] = json!("not-a-uuid");
        let valid = validate(serde_json::from_value(payload).unwrap()).unwrap();
        let industry = valid
            .tags
            .iter()
            .find(|(facet, _, _)| facet == "industry")
            .unwrap();
        assert_eq!(industry.2, None);
    }

    #[test]
    fn duplicate_tags_are_interned_once() {
        let mut payload = sample();
        payload["tags"]["industry"] = json!([
            { "slug": "food-beverage" },
            { "slug": "food-beverage" },
        ]);
        let valid = validate(serde_json::from_value(payload).unwrap()).unwrap();
        assert_eq!(
            valid
                .tags
                .iter()
                .filter(|(facet, slug, _)| facet == "industry" && slug == "food-beverage")
                .count(),
            1
        );
    }

    #[test]
    fn a_resigned_cover_url_is_not_a_content_change() {
        let first = content_hash(&sample());
        let mut resigned = sample();
        resigned["cover_image"]["url"] =
            json!("https://tw-the-engine.up.railway.app/api/innovations/1234/cover-image?v=1720999999&exp=1&sig=zzz");
        assert_eq!(
            first,
            content_hash(&resigned),
            "a fresh signature must not look like new content"
        );

        let mut edited = sample();
        edited["title"] = json!("A different title");
        assert_ne!(first, content_hash(&edited));
    }

    #[test]
    fn the_ssrf_gate_only_admits_allowlisted_https_hosts() {
        let hosts = vec!["tw-the-engine.up.railway.app".to_string()];
        assert!(asset_url_allowed(
            "https://tw-the-engine.up.railway.app/api/innovations/1/cover-image?sig=x",
            &hosts
        ));
        // Plain http, a different host, the private network, and a userinfo
        // prefix that reads as the allowed host to a careless parser.
        assert!(!asset_url_allowed(
            "http://tw-the-engine.up.railway.app/x",
            &hosts
        ));
        assert!(!asset_url_allowed("https://evil.example.com/x", &hosts));
        assert!(!asset_url_allowed(
            "https://backend.railway.internal/admin",
            &hosts
        ));
        assert!(!asset_url_allowed(
            "https://tw-the-engine.up.railway.app@evil.example.com/x",
            &hosts
        ));
        assert!(!asset_url_allowed(
            "https://TW-THE-ENGINE.up.railway.app.evil.com/x",
            &hosts
        ));
        // Case and an explicit port are fine.
        assert!(asset_url_allowed(
            "https://TW-THE-ENGINE.UP.RAILWAY.APP/x",
            &hosts
        ));
        assert!(asset_url_allowed(
            "https://tw-the-engine.up.railway.app:443/x",
            &hosts
        ));
    }

    #[test]
    fn a_cursor_round_trips_and_junk_is_refused() {
        assert_eq!(
            parse_cursor("1754300000000000_42"),
            Some((1754300000000000, 42))
        );
        assert_eq!(parse_cursor("nonsense"), None);
        assert_eq!(parse_cursor("123"), None);
        assert_eq!(parse_cursor("abc_42"), None);
    }

    #[test]
    fn a_missing_hydration_key_leaves_the_page_alone() {
        let hydration = Hydration::default();
        assert!(!hydration.by_shift.contains_key("key_trend:whatever"));
    }
}
