//! Serious Shift read API. Replaces the ~53 MB of static JSON the frontend used
//! to download: each endpoint serves the same shape, sourced from Postgres.
//!
//! Env: DATABASE_URL (required), ANTHROPIC_API_KEY (for /api/personalize),
//!      PORT (default 8080), FRONTEND_ORIGIN (CORS allowlist, comma-separated).

mod seo;
mod sql;

use std::collections::HashMap;
use std::env;
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use axum::{
    extract::{DefaultBodyLimit, Query, State},
    http::{header, HeaderMap, HeaderValue, Method, StatusCode},
    response::{IntoResponse, Response},
    routing::{any, get, post},
    Json, Router,
};
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::postgres::PgPoolOptions;
use sqlx::types::Json as SqlxJson;
use sqlx::PgPool;
use tower::ServiceBuilder;
use tower_http::compression::CompressionLayer;
use tower_http::cors::{AllowOrigin, Any, CorsLayer};
use tower_http::services::{ServeDir, ServeFile};
use tower_http::set_header::SetResponseHeaderLayer;
use tower_http::set_status::SetStatus;

/// CORS from FRONTEND_ORIGIN (comma-separated allowlist).
///
/// Fails closed: a release build with no allowlist refuses to boot rather than
/// serving `Access-Control-Allow-Origin: *` behind a warning nobody reads. Debug
/// builds still fall back to "any origin" so `cargo run` works locally.
fn cors_layer() -> CorsLayer {
    let base = CorsLayer::new()
        .allow_methods([Method::GET, Method::POST])
        .allow_headers([header::CONTENT_TYPE]);
    match env::var("FRONTEND_ORIGIN") {
        Ok(v) if !v.trim().is_empty() => {
            let origins: Vec<HeaderValue> =
                v.split(',').filter_map(|o| o.trim().parse().ok()).collect();
            assert!(
                !origins.is_empty(),
                "FRONTEND_ORIGIN is set but no entry parsed as a valid origin: {v:?}"
            );
            base.allow_origin(AllowOrigin::list(origins))
        }
        _ if cfg!(debug_assertions) => {
            tracing::warn!("FRONTEND_ORIGIN not set — allowing any origin (debug build only)");
            base.allow_origin(Any)
        }
        _ => panic!(
            "FRONTEND_ORIGIN must be set in release builds. Set it to the \
             frontend's origin (comma-separated for several), e.g. \
             https://app.example.com"
        ),
    }
}

/// Where the exported SPA lives (default ./static).
fn static_dir() -> String {
    env::var("STATIC_DIR").unwrap_or_else(|_| "static".into())
}

/// Serve the exported SPA, falling back to index.html so client-side routes
/// deep-link.
///
/// index.html is deliberately NOT cached here: it names the current hashed
/// bundles, so caching it is what makes a deploy invisible to a returning
/// browser. The immutable assets are handled separately — see
/// `immutable_assets`.
fn static_service() -> ServeDir<SetStatus<ServeFile>> {
    let dir = static_dir();
    let index = Path::new(&dir).join("index.html");
    if !index.is_file() {
        tracing::warn!("no SPA build at {} — serving API only", index.display());
    }
    // 200, not 404: the path is a client-side route, not a missing file.
    ServeDir::new(&dir).fallback(SetStatus::new(ServeFile::new(index), StatusCode::OK))
}

/// The exported `index.html`, or an empty string when there is no SPA build.
fn read_shell() -> String {
    let path = Path::new(&static_dir()).join("index.html");
    std::fs::read_to_string(&path).unwrap_or_else(|_| {
        tracing::warn!(
            "no index.html at {} — SPA metadata disabled",
            path.display()
        );
        String::new()
    })
}

/// Absolute origin for canonical URLs and the sitemap.
///
/// PUBLIC_ORIGIN when set, else the first FRONTEND_ORIGIN entry — which for
/// this deploy is the same host, since the binary serves the app and the API.
fn public_origin() -> String {
    if let Ok(v) = env::var("PUBLIC_ORIGIN") {
        if !v.trim().is_empty() {
            return v.trim().trim_end_matches('/').to_string();
        }
    }
    env::var("FRONTEND_ORIGIN")
        .ok()
        .and_then(|v| {
            v.split(',')
                .next()
                .map(|s| s.trim().trim_end_matches('/').to_string())
        })
        .filter(|s| !s.is_empty())
        .unwrap_or_default()
}

/// `Cache-Control` for the content-addressed bundles under /_next/static.
///
/// Next puts a content hash in every filename there, so a changed file is a
/// changed URL and a stale entry is impossible. Without this header the browser
/// revalidated every chunk on every navigation — a round trip per asset to be
/// told nothing had changed.
const IMMUTABLE: &str = "public, max-age=31536000, immutable";

/// TTL-cached raw JSON for the map document (the only one served).
type DocCache = Arc<Mutex<Option<(Instant, Arc<str>)>>>;
/// Route → page metadata, rebuilt whenever the document cache refreshes.
type MetaCache = Arc<Mutex<Option<(Instant, Arc<seo::SiteIndex>)>>>;

#[derive(Clone)]
struct AppState {
    pool: PgPool,
    /// Shared secret for POST /api/innovations/ingest. None disables the route.
    ingest_token: Option<String>,
    // Cached map document JSON. It is large (~1 MB) and changes ~weekly, so we
    // serve the raw JSON text from memory — skipping the Postgres read + serde
    // round-trip on every request.
    docs: DocCache,
    // Route → title/description, derived from the same document. Parsing ~1 MB
    // of JSON per HTML request would be absurd; this is built once per refresh.
    meta: MetaCache,
    /// The exported `index.html`, read once. Every SPA route is this shell with
    /// its `<head>` rewritten.
    shell: Arc<str>,
    /// Absolute origin for canonical URLs and the sitemap.
    origin: Arc<str>,
}

const DOC_CACHE_TTL: Duration = Duration::from_secs(60); // documents: refresh within 60s of a regen

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let pool = PgPoolOptions::new()
        // A read API serving one cached document behind a rate limit does not
        // need ten permanently-open connections.
        .max_connections(4)
        .connect(&env::var("DATABASE_URL").expect("DATABASE_URL must be set"))
        .await?;

    let ingest_token = env::var("INGEST_TOKEN")
        .ok()
        .filter(|t| !t.trim().is_empty());
    if ingest_token.is_none() {
        tracing::warn!("INGEST_TOKEN not set — POST /api/innovations/ingest is disabled");
    }

    let state = AppState {
        pool,
        ingest_token,
        docs: Arc::new(Mutex::new(None)),
        meta: Arc::new(Mutex::new(None)),
        shell: Arc::from(read_shell()),
        origin: Arc::from(public_origin()),
    };

    // The fallback service needs its own handle: `with_state` below consumes
    // the router's copy.
    let state_for_spa = state.clone();

    let app = Router::new()
        .route("/health", get(health))
        .route("/api/thinkers", get(thinkers))
        .route("/api/sources", get(sources))
        .route("/api/claims", get(claims))
        .route("/api/predictions", get(predictions))
        .route("/api/stats", get(stats))
        .route("/api/map", get(map))
        // Generated from the map document, so they track the current shifts
        // rather than whatever was true when the image was built. Both used to
        // fall through to the SPA and answer 200 text/html.
        // "/" explicitly: ServeDir would otherwise answer it with index.html
        // straight off disk and skip the metadata rewrite entirely.
        .route("/", get(spa))
        .route("/robots.txt", get(robots_txt))
        .route("/sitemap.xml", get(sitemap_xml))
        .route(
            "/api/innovations/ingest",
            post(ingest_innovation).layer(DefaultBodyLimit::max(1024 * 1024)),
        )
        // Unknown /api/* paths must 404 as JSON. Without this they reach the SPA
        // fallback below and a mistyped endpoint answers 200 text/html, which an
        // API client would happily try to parse.
        .route(
            "/api/*rest",
            any(|| async { AppError(StatusCode::NOT_FOUND, "no such endpoint".into()) }),
        )
        // The map document is large — ~1 MB of JSON once every shift carries its
        // editorial modules — and compresses to roughly a quarter of that.
        // Applied to the whole router so /api/claims benefits too; responses are
        // only encoded when the client sends Accept-Encoding.
        .layer(CompressionLayer::new().gzip(true))
        .layer(cors_layer())
        .with_state(state)
        // Hashed bundles, cached for a year. Registered before the fallback so
        // these paths never reach the un-cached index.html handler.
        .nest_service(
            "/_next/static",
            ServiceBuilder::new()
                .layer(SetResponseHeaderLayer::overriding(
                    header::CACHE_CONTROL,
                    HeaderValue::from_static(IMMUTABLE),
                ))
                .service(ServeDir::new(Path::new(&static_dir()).join("_next/static"))),
        )
        // Static files first (real assets under /shift, /logo.png, …); anything
        // they do not have falls through to `spa`, which serves index.html with
        // this route's metadata stamped in. Registered last so every /api route
        // above wins.
        .fallback_service(static_service().fallback(get(spa).with_state(state_for_spa)));

    let port = env::var("PORT").unwrap_or_else(|_| "8080".into());
    // Bind IPv6 dual-stack: Railway's private network is IPv6-only, so a service
    // bound to 0.0.0.0 isn't reachable at <svc>.railway.internal. "[::]" accepts
    // both private IPv6 and the public IPv4 edge (IPv4-mapped).
    let listener = tokio::net::TcpListener::bind(format!("[::]:{port}")).await?;
    tracing::info!("listening on {}", listener.local_addr()?);
    axum::serve(listener, app).await?;
    Ok(())
}

/// Liveness *and* readiness: a static "ok" kept the healthcheck green while
/// Postgres was down, which is precisely when it should go red.
async fn health(State(s): State<AppState>) -> Result<&'static str, AppError> {
    sqlx::query_scalar::<_, i32>("SELECT 1")
        .fetch_one(&s.pool)
        .await?;
    Ok("ok")
}

// ── error type ───────────────────────────────────────────────────────────────

struct AppError(StatusCode, String);

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        (self.0, Json(json!({ "error": self.1 }))).into_response()
    }
}

impl From<sqlx::Error> for AppError {
    fn from(e: sqlx::Error) -> Self {
        AppError(StatusCode::INTERNAL_SERVER_ERROR, e.to_string())
    }
}

// ── read endpoints (one SQL each) ──────────────────────────────────────────────

/// Rows returned by a list endpoint when the caller doesn't say.
const DEFAULT_LIST_LIMIT: i64 = 500;
/// Ceiling on `?limit=`. Whole-table dumps stay possible from psql, not from a
/// public URL: unbounded, `/api/claims` answered ~7 MB and `/api/sources` ~8 MB,
/// which a handful of concurrent requests turns into an outage.
const MAX_LIST_LIMIT: i64 = 5_000;

/// `?limit=` clamped into range. A missing or unparseable value takes the
/// default rather than 400-ing — these are inspection endpoints, and being
/// lenient about the query string is worth more here than being strict.
fn list_limit(q: &HashMap<String, String>) -> i64 {
    q.get("limit")
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(DEFAULT_LIST_LIMIT)
        .clamp(1, MAX_LIST_LIMIT)
}

async fn run_list(pool: &PgPool, query: &str, limit: i64) -> Result<Json<Value>, AppError> {
    let doc: Value = sqlx::query_scalar(query)
        .bind(limit)
        .fetch_one(pool)
        .await?;
    Ok(Json(doc))
}

async fn thinkers(
    State(s): State<AppState>,
    Query(q): Query<HashMap<String, String>>,
) -> Result<Json<Value>, AppError> {
    run_list(&s.pool, sql::THINKERS, list_limit(&q)).await
}
async fn sources(
    State(s): State<AppState>,
    Query(q): Query<HashMap<String, String>>,
) -> Result<Json<Value>, AppError> {
    run_list(&s.pool, sql::SOURCES, list_limit(&q)).await
}
async fn claims(
    State(s): State<AppState>,
    Query(q): Query<HashMap<String, String>>,
) -> Result<Json<Value>, AppError> {
    run_list(&s.pool, sql::CLAIMS, list_limit(&q)).await
}
async fn predictions(
    State(s): State<AppState>,
    Query(q): Query<HashMap<String, String>>,
) -> Result<Json<Value>, AppError> {
    run_list(&s.pool, sql::PREDICTIONS, list_limit(&q)).await
}
async fn stats(State(s): State<AppState>) -> Result<Json<Value>, AppError> {
    let doc: Value = sqlx::query_scalar(sql::STATS).fetch_one(&s.pool).await?;
    Ok(Json(doc))
}

// ── /api/map ───────────────────────────────────────────────────────────────────

/// Serve a cached document as raw JSON. The body is the verbatim text from
/// Postgres (jsonb::text) — no parse/re-serialize — with cache headers so the
/// browser/proxy cache it too.
fn doc_response(body: Arc<str>) -> Response {
    (
        [
            (
                header::CONTENT_TYPE,
                HeaderValue::from_static("application/json"),
            ),
            // Short window on purpose. These documents are rewritten whenever the
            // pipeline runs, and a long stale-while-revalidate meant a browser
            // served yesterday's copy for up to a day after a regeneration —
            // the content looked "missing" even though the API was correct.
            (
                header::CACHE_CONTROL,
                HeaderValue::from_static("public, max-age=60, stale-while-revalidate=300"),
            ),
        ],
        body.as_ref().to_owned(),
    )
        .into_response()
}

/// The map document as raw text, from cache when fresh.
async fn map_doc(s: &AppState) -> Result<Arc<str>, AppError> {
    if let Some(body) = {
        let cache = s.docs.lock().unwrap();
        cache
            .as_ref()
            .and_then(|(at, body)| (at.elapsed() < DOC_CACHE_TTL).then(|| body.clone()))
    } {
        return Ok(body);
    }
    let body: Option<String> =
        sqlx::query_scalar("SELECT body::text FROM documents WHERE key = 'map'")
            .fetch_optional(&s.pool)
            .await?;
    let body =
        body.ok_or_else(|| AppError(StatusCode::NOT_FOUND, "map document not found".into()))?;
    let body: Arc<str> = Arc::from(body);
    *s.docs.lock().unwrap() = Some((Instant::now(), body.clone()));
    Ok(body)
}

/// Route index, rebuilt when the document cache turns over.
async fn site_index(s: &AppState) -> Arc<seo::SiteIndex> {
    if let Some(idx) = {
        let c = s.meta.lock().unwrap();
        c.as_ref()
            .and_then(|(at, idx)| (at.elapsed() < DOC_CACHE_TTL).then(|| idx.clone()))
    } {
        return idx;
    }
    // A missing document must not break page serving — fall back to an empty
    // index, which leaves the shell's build-time metadata in place.
    let idx = match map_doc(s).await {
        Ok(doc) => Arc::new(seo::build_index(&doc)),
        Err(_) => Arc::new(seo::SiteIndex::default()),
    };
    *s.meta.lock().unwrap() = Some((Instant::now(), idx.clone()));
    idx
}

/// The trend map — the only document the frontend reads.
async fn map(State(s): State<AppState>) -> Result<Response, AppError> {
    Ok(doc_response(map_doc(&s).await?))
}

// ── SPA shell, robots, sitemap ────────────────────────────────────────────────

/// Serve the app shell with this route's metadata stamped into its `<head>`.
///
/// Registered as the fallback, so it handles every path the API and the static
/// files did not. A route we have no metadata for still gets the shell verbatim
/// — the client router resolves it, and unknown shifts render the app's own
/// not-found state.
async fn spa(State(s): State<AppState>, uri: axum::http::Uri) -> Response {
    if s.shell.is_empty() {
        return (StatusCode::NOT_FOUND, "no SPA build").into_response();
    }
    let path = uri.path();
    let idx = site_index(&s).await;
    let html = match idx.pages.get(path) {
        Some(meta) => seo::render(&s.shell, path, meta, &s.origin),
        None => s.shell.to_string(),
    };
    (
        [
            (
                header::CONTENT_TYPE,
                HeaderValue::from_static("text/html; charset=utf-8"),
            ),
            // Never cached: it names the current hashed bundles, and it now also
            // carries metadata that changes with the map.
            (header::CACHE_CONTROL, HeaderValue::from_static("no-cache")),
        ],
        html,
    )
        .into_response()
}

async fn robots_txt(State(s): State<AppState>) -> Response {
    (
        [(
            header::CONTENT_TYPE,
            HeaderValue::from_static("text/plain; charset=utf-8"),
        )],
        seo::robots(&s.origin),
    )
        .into_response()
}

async fn sitemap_xml(State(s): State<AppState>) -> Response {
    let idx = site_index(&s).await;
    (
        [
            (
                header::CONTENT_TYPE,
                HeaderValue::from_static("application/xml"),
            ),
            (
                header::CACHE_CONTROL,
                HeaderValue::from_static("public, max-age=3600"),
            ),
        ],
        idx.sitemap(&s.origin),
    )
        .into_response()
}

// ── /api/innovations/ingest (write endpoint) ───────────────────────────────────

/// Constant-time byte comparison, so token checks don't leak length or prefix
/// via timing. Avoids pulling in a crate for ~10 lines.
fn secret_eq(a: &str, b: &str) -> bool {
    let (a, b) = (a.as_bytes(), b.as_bytes());
    if a.len() != b.len() {
        return false;
    }
    a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

/// One innovation pushed by the upstream Innovation database. Scalars we
/// query/join on become columns; the variable-shape nested fields stay as JSON.
/// Everything is optional so a partial payload still ingests (nulls, not 400s).
#[derive(Deserialize)]
struct IngestInnovationReq {
    #[serde(default)]
    source_innovation_id: Option<i64>,
    #[serde(default)]
    article_url: Option<String>,
    #[serde(default)]
    source_urls: Value,
    #[serde(default)]
    title: Option<String>,
    #[serde(default)]
    body: Option<String>,
    #[serde(default)]
    trendbite: Option<String>,
    #[serde(default)]
    brands: Value,
    #[serde(default)]
    tags: Value,
    #[serde(default)]
    cover_image: Option<Value>,
}

/// Ingest one innovation into the `innovations` table. Idempotent on
/// `source_innovation_id` (re-POSTing updates in place). Returns 200 `ok` on
/// success; any DB error becomes a 500 via `From<sqlx::Error> for AppError`.
/// Takes the raw body rather than `Json<T>` so the shared secret is checked
/// *before* anything untrusted is deserialised. With the extractor, axum runs it
/// ahead of the handler — so an unauthenticated caller could make the server
/// parse up to 1 MB of JSON, and a wrong content-type answered 415 instead of
/// the 404 the route is supposed to present while disabled.
async fn ingest_innovation(
    State(s): State<AppState>,
    headers: HeaderMap,
    body: axum::body::Bytes,
) -> Result<Response, AppError> {
    // With INGEST_TOKEN unset the route reports 404 rather than staying open — an
    // unauthenticated write endpoint should not exist by default, and 404 leaks
    // less about what is deployed here than 401 does.
    let Some(expected) = s.ingest_token.as_deref() else {
        return Err(AppError(StatusCode::NOT_FOUND, "Not found".into()));
    };
    let presented = headers
        .get("x-ingest-token")
        .and_then(|v| v.to_str().ok())
        .unwrap_or_default();
    if !secret_eq(presented, expected) {
        return Err(AppError(StatusCode::UNAUTHORIZED, "Unauthorized".into()));
    }

    let req: IngestInnovationReq = serde_json::from_slice(&body)
        .map_err(|e| AppError(StatusCode::BAD_REQUEST, format!("invalid JSON: {e}")))?;

    sqlx::query(
        r#"
        INSERT INTO innovations
          (source_innovation_id, article_url, source_urls, title, body,
           trendbite, brands, tags, cover_image)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (source_innovation_id) DO UPDATE SET
          article_url = EXCLUDED.article_url,
          source_urls = EXCLUDED.source_urls,
          title       = EXCLUDED.title,
          body        = EXCLUDED.body,
          trendbite   = EXCLUDED.trendbite,
          brands      = EXCLUDED.brands,
          tags        = EXCLUDED.tags,
          cover_image = EXCLUDED.cover_image,
          updated_at  = now()
        "#,
    )
    .bind(req.source_innovation_id)
    .bind(req.article_url)
    .bind(SqlxJson(req.source_urls))
    .bind(req.title)
    .bind(req.body)
    .bind(req.trendbite)
    .bind(SqlxJson(req.brands))
    .bind(SqlxJson(req.tags))
    .bind(req.cover_image.map(SqlxJson))
    .execute(&s.pool)
    .await?;

    Ok((StatusCode::OK, "ok").into_response())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn q(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect()
    }

    #[test]
    fn absent_limit_takes_the_default() {
        assert_eq!(list_limit(&q(&[])), DEFAULT_LIST_LIMIT);
    }

    #[test]
    fn explicit_limit_is_honoured() {
        assert_eq!(list_limit(&q(&[("limit", "25")])), 25);
    }

    #[test]
    fn limit_is_clamped_to_the_ceiling() {
        // Unbounded, /api/claims answered ~7 MB. The ceiling is what keeps a
        // public URL from being a whole-table dump.
        assert_eq!(list_limit(&q(&[("limit", "999999")])), MAX_LIST_LIMIT);
    }

    #[test]
    fn nonsense_and_negative_limits_do_not_produce_an_error_or_an_empty_page() {
        // These are inspection endpoints; leniency beats a 400 here. A negative
        // or zero limit must still return a usable page, not nothing.
        assert_eq!(list_limit(&q(&[("limit", "abc")])), DEFAULT_LIST_LIMIT);
        assert_eq!(list_limit(&q(&[("limit", "-5")])), 1);
        assert_eq!(list_limit(&q(&[("limit", "0")])), 1);
    }

    #[test]
    fn secret_comparison_is_length_and_content_sensitive() {
        assert!(secret_eq("abc123", "abc123"));
        assert!(!secret_eq("abc123", "abc124"));
        assert!(!secret_eq("abc", "abc123"));
        assert!(!secret_eq("", "x"));
    }
}
