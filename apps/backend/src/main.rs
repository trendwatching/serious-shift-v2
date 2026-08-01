//! Serious Shift read API. Replaces the ~53 MB of static JSON the frontend used
//! to download: each endpoint serves the same shape, sourced from Postgres.
//!
//! Env: DATABASE_URL (required), ANTHROPIC_API_KEY (for /api/personalize),
//!      PORT (default 8080), FRONTEND_ORIGIN (CORS allowlist, comma-separated).

mod prompts;
mod sql;

use std::collections::HashMap;
use std::env;
use std::hash::{Hash, Hasher};
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
use tower_http::compression::CompressionLayer;
use tower_http::cors::{AllowOrigin, Any, CorsLayer};
use tower_http::services::{ServeDir, ServeFile};
use tower_http::set_status::SetStatus;

const MAX_SECTIONS: usize = 20; // /api/personalize abuse guard
const MAX_INDUSTRY_LEN: usize = 100;

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

/// Serve the exported SPA from STATIC_DIR (default ./static), falling back to
/// index.html so client-side routes deep-link. Hashed assets under /_next are
/// immutable; index.html must not be cached or a deploy would not be picked up.
fn static_service() -> ServeDir<SetStatus<ServeFile>> {
    let dir = env::var("STATIC_DIR").unwrap_or_else(|_| "static".into());
    let index = Path::new(&dir).join("index.html");
    if !index.is_file() {
        tracing::warn!("no SPA build at {} — serving API only", index.display());
    }
    // 200, not 404: the path is a client-side route, not a missing file.
    ServeDir::new(&dir).fallback(SetStatus::new(ServeFile::new(index), StatusCode::OK))
}

/// Per-IP request timestamps for the /api/personalize rate limiter.
type RateMap = Arc<Mutex<HashMap<String, Vec<Instant>>>>;
/// TTL-cached /api/personalize responses, keyed by request signature.
type ResultCache = Arc<Mutex<HashMap<String, (Instant, Value)>>>;
/// TTL-cached raw JSON for the map document (the only one served).
type DocCache = Arc<Mutex<Option<(Instant, Arc<str>)>>>;
/// (UTC day number, Anthropic calls made that day) for the global spend cap.
type BudgetGuard = Arc<Mutex<(u64, usize)>>;

#[derive(Clone)]
struct AppState {
    pool: PgPool,
    anthropic_key: Option<String>,
    /// Shared secret for POST /api/innovations/ingest. None disables the route.
    ingest_token: Option<String>,
    /// Global daily ceiling on /api/personalize Anthropic calls.
    budget: BudgetGuard,
    // In-memory per-IP rate limiter and result cache for /api/personalize.
    // Single-instance scope (fine for the current deploy); move to a shared
    // KV store if the backend is scaled horizontally.
    rate: RateMap,
    cache: ResultCache,
    // Cached map document JSON. It is large (~1 MB) and changes ~weekly, so we
    // serve the raw JSON text from memory — skipping the Postgres read + serde
    // round-trip on every request.
    docs: DocCache,
}

const PERSONALIZE_MODEL: &str = "claude-sonnet-4-6";
const RATE_LIMIT: usize = 10; // requests…
const RATE_WINDOW: Duration = Duration::from_secs(600); // …per 10 min per IP
const CACHE_TTL: Duration = Duration::from_secs(3600); // personalize cache: 1 hour
const DOC_CACHE_TTL: Duration = Duration::from_secs(60); // documents: refresh within 60s of a regen
/// Hard ceiling on Anthropic calls from /api/personalize per UTC day (one call
/// per section). At Sonnet rates with max_tokens=1024 this bounds the endpoint's
/// worst case to a few dollars a day. Override with PERSONALIZE_DAILY_CALL_CAP.
fn personalize_daily_call_cap() -> usize {
    static CAP: std::sync::OnceLock<usize> = std::sync::OnceLock::new();
    *CAP.get_or_init(|| {
        env::var("PERSONALIZE_DAILY_CALL_CAP")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(500)
    })
}

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
        anthropic_key: env::var("ANTHROPIC_API_KEY").ok(),
        ingest_token,
        budget: Arc::new(Mutex::new((0, 0))),
        rate: Arc::new(Mutex::new(HashMap::new())),
        cache: Arc::new(Mutex::new(HashMap::new())),
        docs: Arc::new(Mutex::new(None)),
    };

    let app = Router::new()
        .route("/health", get(health))
        .route("/api/thinkers", get(thinkers))
        .route("/api/sources", get(sources))
        .route("/api/claims", get(claims))
        .route("/api/predictions", get(predictions))
        .route("/api/stats", get(stats))
        .route("/api/map", get(map))
        .route(
            "/api/personalize",
            post(personalize).layer(DefaultBodyLimit::max(64 * 1024)),
        )
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
        // Static SPA, served from the same origin as the API — so the browser
        // makes no cross-origin request and there is no proxy hop. Registered
        // last so every /api route above wins. Unmatched paths fall back to
        // index.html, which is what makes client-side deep links resolve.
        .fallback_service(static_service());

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

/// The trend map — the only document the frontend reads.
async fn map(State(s): State<AppState>) -> Result<Response, AppError> {
    // Fresh cache hit → serve from memory (no DB, no serde).
    if let Some(body) = {
        let cache = s.docs.lock().unwrap();
        cache
            .as_ref()
            .and_then(|(at, body)| (at.elapsed() < DOC_CACHE_TTL).then(|| body.clone()))
    } {
        return Ok(doc_response(body));
    }
    // Miss: read the jsonb as text (skips parsing into a Value), cache, serve.
    let body: Option<String> =
        sqlx::query_scalar("SELECT body::text FROM documents WHERE key = 'map'")
            .fetch_optional(&s.pool)
            .await?;
    let body =
        body.ok_or_else(|| AppError(StatusCode::NOT_FOUND, "map document not found".into()))?;
    let body: Arc<str> = Arc::from(body);
    *s.docs.lock().unwrap() = Some((Instant::now(), body.clone()));
    Ok(doc_response(body))
}

// ── /api/personalize (faithful port of api/personalize.js) ─────────────────────

#[derive(Deserialize)]
struct PersonalizeReq {
    industry: String,
    sections: Vec<Value>,
}

/// Client IP from X-Forwarded-For (we run behind Railway's proxy).
fn client_ip(headers: &HeaderMap) -> String {
    headers
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.split(',').next())
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|| "unknown".into())
}

/// Sliding-window per-IP limiter. Returns false when the IP is over the limit.
fn rate_ok(state: &AppState, ip: &str) -> bool {
    let mut m = state.rate.lock().unwrap();
    let now = Instant::now();
    // Evict IPs whose window has fully expired. Without this the map grows
    // without bound — a slow leak and a memory-exhaustion vector, since the key
    // is attacker-supplied. Bounded by the number of distinct IPs seen in one
    // RATE_WINDOW, so the scan stays cheap.
    m.retain(|_, hits| hits.iter().any(|t| now.duration_since(*t) < RATE_WINDOW));
    let hits = m.entry(ip.to_string()).or_default();
    hits.retain(|t| now.duration_since(*t) < RATE_WINDOW);
    if hits.len() >= RATE_LIMIT {
        return false;
    }
    hits.push(now);
    true
}

/// Reserve `calls` against the global daily Anthropic budget for
/// /api/personalize. The per-IP limiter above is single-instance and trivially
/// defeated by a distributed caller rotating IPs; this is the backstop that
/// bounds worst-case spend. Returns false once the day's cap is exhausted.
fn budget_ok(state: &AppState, calls: usize) -> bool {
    let day = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() / 86_400)
        .unwrap_or(0);
    let mut g = state.budget.lock().unwrap();
    if g.0 != day {
        *g = (day, 0); // new UTC day — reset
    }
    if g.1 + calls > personalize_daily_call_cap() {
        return false;
    }
    g.1 += calls;
    true
}

/// Constant-time byte comparison, so token checks don't leak length or prefix
/// via timing. Avoids pulling in a crate for ~10 lines.
fn secret_eq(a: &str, b: &str) -> bool {
    let (a, b) = (a.as_bytes(), b.as_bytes());
    if a.len() != b.len() {
        return false;
    }
    a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

fn cache_key(industry: &str, sections: &[Value]) -> String {
    let mut h = std::collections::hash_map::DefaultHasher::new();
    industry.hash(&mut h);
    serde_json::to_string(sections)
        .unwrap_or_default()
        .hash(&mut h);
    format!("{industry}:{:x}", h.finish())
}

async fn personalize(
    State(s): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<PersonalizeReq>,
) -> Result<Json<Value>, AppError> {
    if req.industry.is_empty() || req.sections.is_empty() {
        return Err(AppError(
            StatusCode::BAD_REQUEST,
            "Missing industry or sections".into(),
        ));
    }
    if req.industry.len() > MAX_INDUSTRY_LEN || req.sections.len() > MAX_SECTIONS {
        return Err(AppError(
            StatusCode::BAD_REQUEST,
            "Request too large".into(),
        ));
    }
    if !rate_ok(&s, &client_ip(&headers)) {
        return Err(AppError(
            StatusCode::TOO_MANY_REQUESTS,
            "Rate limit exceeded".into(),
        ));
    }

    // Cache hit? (lock is dropped before any await)
    // Checked before the budget so cached responses stay free and never consume
    // the day's allowance.
    let ck = cache_key(&req.industry, &req.sections);
    {
        let mut c = s.cache.lock().unwrap();
        let fresh = match c.get(&ck) {
            Some((t, v)) if t.elapsed() < CACHE_TTL => Some(v.clone()),
            _ => None,
        };
        if let Some(v) = fresh {
            return Ok(Json(v));
        }
        c.remove(&ck); // stale or absent
    }

    let key = s.anthropic_key.clone().ok_or_else(|| {
        AppError(
            StatusCode::INTERNAL_SERVER_ERROR,
            "ANTHROPIC_API_KEY not configured".into(),
        )
    })?;

    // One Anthropic call per section — reserve them against the daily cap.
    if !budget_ok(&s, req.sections.len()) {
        return Err(AppError(
            StatusCode::SERVICE_UNAVAILABLE,
            "Daily personalization budget exhausted".into(),
        ));
    }

    let client = reqwest::Client::new();
    let industry = req.industry.clone();
    let futs = req.sections.into_iter().map(|section| {
        let client = client.clone();
        let key = key.clone();
        let industry = industry.clone();
        async move { rewrite_section(&client, &key, &industry, section).await }
    });
    let rewritten: Vec<Value> = futures::future::join_all(futs).await;

    let out = json!({ "sections": rewritten, "industry": industry });
    s.cache
        .lock()
        .unwrap()
        .insert(ck, (Instant::now(), out.clone()));
    Ok(Json(out))
}

async fn rewrite_section(
    client: &reqwest::Client,
    api_key: &str,
    industry: &str,
    mut section: Value,
) -> Value {
    let body_text = section
        .get("body")
        .and_then(|b| b.as_str())
        .unwrap_or("")
        .to_string();
    let prompt = prompts::rewrite_section(industry, &body_text);

    let resp = client
        .post("https://api.anthropic.com/v1/messages")
        .header("x-api-key", api_key)
        .header("anthropic-version", "2023-06-01")
        .header("content-type", "application/json")
        .timeout(std::time::Duration::from_secs(25))
        .json(&json!({
            "model": PERSONALIZE_MODEL,
            "max_tokens": 1024,
            "messages": [{ "role": "user", "content": prompt }],
        }))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            let data: Value = r.json().await.unwrap_or(Value::Null);
            let text = data
                .pointer("/content/0/text")
                .and_then(|t| t.as_str())
                .unwrap_or(&body_text)
                .to_string();
            if let Some(obj) = section.as_object_mut() {
                obj.insert("body".into(), json!(text));
                obj.insert("personalized".into(), json!(true));
            }
            section
        }
        _ => {
            // Match the JS fallback: keep the original body, flag the error.
            if let Some(obj) = section.as_object_mut() {
                obj.insert("error".into(), json!(true));
            }
            section
        }
    }
}

// ── /api/innovations/ingest (write endpoint) ───────────────────────────────────

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
