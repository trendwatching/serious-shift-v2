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
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use axum::{
    extract::{DefaultBodyLimit, State},
    http::{header, HeaderMap, HeaderValue, Method, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::postgres::PgPoolOptions;
use sqlx::types::Json as SqlxJson;
use sqlx::PgPool;
use tower_http::compression::CompressionLayer;
use tower_http::cors::{AllowOrigin, Any, CorsLayer};

const MAX_SECTIONS: usize = 20; // /api/personalize abuse guard
const MAX_INDUSTRY_LEN: usize = 100;

/// CORS from FRONTEND_ORIGIN (comma-separated allowlist). Falls back to "any
/// origin" only when unset, with a warning — set it in production.
fn cors_layer() -> CorsLayer {
    let base = CorsLayer::new()
        .allow_methods([Method::GET, Method::POST])
        .allow_headers([header::CONTENT_TYPE]);
    match env::var("FRONTEND_ORIGIN") {
        Ok(v) if !v.trim().is_empty() => {
            let origins: Vec<HeaderValue> =
                v.split(',').filter_map(|o| o.trim().parse().ok()).collect();
            base.allow_origin(AllowOrigin::list(origins))
        }
        _ => {
            tracing::warn!("FRONTEND_ORIGIN not set — allowing any origin (dev only)");
            base.allow_origin(Any)
        }
    }
}

/// Per-IP request timestamps for the /api/personalize rate limiter.
type RateMap = Arc<Mutex<HashMap<String, Vec<Instant>>>>;
/// TTL-cached /api/personalize responses, keyed by request signature.
type ResultCache = Arc<Mutex<HashMap<String, (Instant, Value)>>>;
/// TTL-cached raw document JSON, keyed by document key.
type DocCache = Arc<Mutex<HashMap<String, (Instant, Arc<str>)>>>;

#[derive(Clone)]
struct AppState {
    pool: PgPool,
    anthropic_key: Option<String>,
    // In-memory per-IP rate limiter and result cache for /api/personalize.
    // Single-instance scope (fine for the current deploy); move to a shared
    // KV store if the backend is scaled horizontally.
    rate: RateMap,
    cache: ResultCache,
    // Cached document JSON (map/keynote/synthesis/daily), keyed by document key.
    // These are large and change ~weekly, so we serve the raw JSON text from
    // memory — skipping the Postgres read + serde round-trip on every request.
    docs: DocCache,
}

const PERSONALIZE_MODEL: &str = "claude-sonnet-4-6";
const RATE_LIMIT: usize = 10; // requests…
const RATE_WINDOW: Duration = Duration::from_secs(600); // …per 10 min per IP
const CACHE_TTL: Duration = Duration::from_secs(3600); // personalize cache: 1 hour
const DOC_CACHE_TTL: Duration = Duration::from_secs(60); // documents: refresh within 60s of a regen

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let pool = PgPoolOptions::new()
        .max_connections(10)
        .connect(&env::var("DATABASE_URL").expect("DATABASE_URL must be set"))
        .await?;

    let state = AppState {
        pool,
        anthropic_key: env::var("ANTHROPIC_API_KEY").ok(),
        rate: Arc::new(Mutex::new(HashMap::new())),
        cache: Arc::new(Mutex::new(HashMap::new())),
        docs: Arc::new(Mutex::new(HashMap::new())),
    };

    let app = Router::new()
        .route("/health", get(|| async { "ok" }))
        .route("/api/thinkers", get(thinkers))
        .route("/api/sources", get(sources))
        .route("/api/claims", get(claims))
        .route("/api/predictions", get(predictions))
        .route("/api/stats", get(stats))
        .route("/api/map", get(map))
        .route("/api/keynote", get(keynote))
        .route("/api/synthesis", get(synthesis))
        .route("/api/daily", get(daily))
        .route(
            "/api/personalize",
            post(personalize).layer(DefaultBodyLimit::max(64 * 1024)),
        )
        .route(
            "/api/innovations/ingest",
            post(ingest_innovation).layer(DefaultBodyLimit::max(1024 * 1024)),
        )
        // The assembled documents are large — the map is ~1 MB of JSON once every
        // shift carries its editorial modules — and they compress to roughly a
        // quarter of that. Applied to the whole router so /api/keynote and
        // /api/claims benefit too; responses are only encoded when the client
        // sends Accept-Encoding, so nothing else has to change.
        .layer(CompressionLayer::new().gzip(true))
        .layer(cors_layer())
        .with_state(state);

    let port = env::var("PORT").unwrap_or_else(|_| "8080".into());
    // Bind IPv6 dual-stack: Railway's private network is IPv6-only, so a service
    // bound to 0.0.0.0 isn't reachable at <svc>.railway.internal. "[::]" accepts
    // both private IPv6 and the public IPv4 edge (IPv4-mapped).
    let listener = tokio::net::TcpListener::bind(format!("[::]:{port}")).await?;
    tracing::info!("listening on {}", listener.local_addr()?);
    axum::serve(listener, app).await?;
    Ok(())
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

async fn run(pool: &PgPool, query: &str) -> Result<Json<Value>, AppError> {
    let doc: Value = sqlx::query_scalar(query).fetch_one(pool).await?;
    Ok(Json(doc))
}

async fn thinkers(State(s): State<AppState>) -> Result<Json<Value>, AppError> {
    run(&s.pool, sql::THINKERS).await
}
async fn sources(State(s): State<AppState>) -> Result<Json<Value>, AppError> {
    run(&s.pool, sql::SOURCES).await
}
async fn claims(State(s): State<AppState>) -> Result<Json<Value>, AppError> {
    run(&s.pool, sql::CLAIMS).await
}
async fn predictions(State(s): State<AppState>) -> Result<Json<Value>, AppError> {
    run(&s.pool, sql::PREDICTIONS).await
}
async fn stats(State(s): State<AppState>) -> Result<Json<Value>, AppError> {
    run(&s.pool, sql::STATS).await
}

// ── document endpoints (map / keynote / daily) ─────────────────────────────────

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

async fn fetch_doc(s: &AppState, key: &str) -> Result<Response, AppError> {
    // Fresh cache hit → serve from memory (no DB, no serde).
    if let Some(body) = {
        let cache = s.docs.lock().unwrap();
        cache
            .get(key)
            .and_then(|(at, body)| (at.elapsed() < DOC_CACHE_TTL).then(|| body.clone()))
    } {
        return Ok(doc_response(body));
    }
    // Miss: read the jsonb as text (skips parsing into a Value), cache, serve.
    let body: Option<String> =
        sqlx::query_scalar("SELECT body::text FROM documents WHERE key = $1")
            .bind(key)
            .fetch_optional(&s.pool)
            .await?;
    let body =
        body.ok_or_else(|| AppError(StatusCode::NOT_FOUND, format!("document '{key}' not found")))?;
    let body: Arc<str> = Arc::from(body);
    s.docs
        .lock()
        .unwrap()
        .insert(key.to_string(), (Instant::now(), body.clone()));
    Ok(doc_response(body))
}

async fn map(State(s): State<AppState>) -> Result<Response, AppError> {
    fetch_doc(&s, "map").await
}
async fn keynote(State(s): State<AppState>) -> Result<Response, AppError> {
    fetch_doc(&s, "keynote").await
}
async fn synthesis(State(s): State<AppState>) -> Result<Response, AppError> {
    fetch_doc(&s, "synthesis").await
}
async fn daily(State(s): State<AppState>) -> Result<Response, AppError> {
    fetch_doc(&s, "daily").await
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
    let hits = m.entry(ip.to_string()).or_default();
    hits.retain(|t| now.duration_since(*t) < RATE_WINDOW);
    if hits.len() >= RATE_LIMIT {
        return false;
    }
    hits.push(now);
    true
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
async fn ingest_innovation(
    State(s): State<AppState>,
    Json(req): Json<IngestInnovationReq>,
) -> Result<Response, AppError> {
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
