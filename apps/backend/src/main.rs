//! Serious Shift read API. Replaces the ~53 MB of static JSON the frontend used
//! to download: each endpoint serves the same shape, sourced from Postgres.
//!
//! Env: DATABASE_URL (required), PORT (default 8080),
//!      FRONTEND_ORIGIN (CORS allowlist, comma-separated),
//!      INSPECTION_TOKEN (gates the operator-only reads, including /api/map).

mod seo;
mod sql;

use std::collections::HashMap;
use std::env;
use std::net::{IpAddr, SocketAddr};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use axum::{
    extract::{ConnectInfo, DefaultBodyLimit, Path as AxumPath, Query, State},
    http::{header, HeaderMap, HeaderName, HeaderValue, Method, StatusCode},
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
use tower_http::services::ServeDir;
use tower_http::set_header::SetResponseHeaderLayer;
use tower_http::timeout::TimeoutLayer;

/// CORS from FRONTEND_ORIGIN (comma-separated allowlist).
///
/// Fails closed: a release build with no allowlist refuses to boot rather than
/// serving `Access-Control-Allow-Origin: *` behind a warning nobody reads. Debug
/// builds still fall back to "any origin" so `cargo run` works locally.
fn cors_layer() -> CorsLayer {
    let base = CorsLayer::new()
        .allow_methods([Method::GET, Method::POST])
        .allow_headers([header::CONTENT_TYPE, header::AUTHORIZATION]);
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
fn static_service() -> ServeDir {
    let dir = static_dir();
    let index = Path::new(&dir).join("index.html");
    if !index.is_file() {
        tracing::warn!("no SPA build at {} — serving API only", index.display());
    }
    // Real files are served here. Missing paths continue to `spa`, which can
    // distinguish canonical application routes from genuine 404s.
    ServeDir::new(&dir)
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

#[derive(Clone)]
struct RouteFragment {
    body: Arc<str>,
    etag: HeaderValue,
}

/// One immutable, parsed publication. The legacy body, route fragments and SEO
/// index are derived together so readers can never observe a mixture of two
/// weekly map versions.
struct MapSnapshot {
    loaded_at: Instant,
    full_body: Arc<str>,
    routes: HashMap<String, RouteFragment>,
    site_index: Arc<seo::SiteIndex>,
}

#[derive(Clone)]
struct AppState {
    pool: PgPool,
    /// Shared secret for POST /api/innovations/ingest. None disables the route.
    ingest_token: Option<String>,
    /// Shared secret for the operator-only inspection endpoints.
    inspection_token: Option<String>,
    /// Current immutable publication. Reads are concurrent; only the process
    /// that refreshes after the TTL takes the separate refresh mutex.
    snapshot: Arc<tokio::sync::RwLock<Option<Arc<MapSnapshot>>>>,
    refresh_lock: Arc<tokio::sync::Mutex<()>>,
    /// The exported `index.html`, read once. Every SPA route is this shell with
    /// its `<head>` rewritten.
    shell: Arc<str>,
    /// Absolute origin for canonical URLs and the sitemap.
    origin: Arc<str>,
    /// Deliberately strict compatibility limit for the deprecated full map.
    legacy_map_limiter: Arc<RateLimiter>,
    legacy_map_concurrency: Arc<tokio::sync::Semaphore>,
    /// Public route fragments are intentionally generous for normal browsing,
    /// while still bounded against abusive crawlers.
    public_v1_limiter: Arc<RateLimiter>,
}

#[derive(Debug)]
struct Bucket {
    tokens: f64,
    updated: Instant,
}

#[derive(Debug)]
struct RateLimiter {
    buckets: Mutex<HashMap<IpAddr, Bucket>>,
    capacity: f64,
    refill_per_second: f64,
}

impl RateLimiter {
    fn per_minute(limit: u32, burst: u32) -> Self {
        Self {
            buckets: Mutex::new(HashMap::new()),
            capacity: f64::from(burst),
            refill_per_second: f64::from(limit) / 60.0,
        }
    }

    fn check(&self, ip: IpAddr) -> Result<u32, u64> {
        let now = Instant::now();
        let mut buckets = self.buckets.lock().unwrap();
        if buckets.len() > 4_096 {
            buckets
                .retain(|_, bucket| now.duration_since(bucket.updated) < Duration::from_secs(600));
        }
        let bucket = buckets.entry(ip).or_insert(Bucket {
            tokens: self.capacity,
            updated: now,
        });
        let elapsed = now.duration_since(bucket.updated).as_secs_f64();
        bucket.tokens = (bucket.tokens + elapsed * self.refill_per_second).min(self.capacity);
        bucket.updated = now;
        if bucket.tokens >= 1.0 {
            bucket.tokens -= 1.0;
            Ok(bucket.tokens.floor() as u32)
        } else {
            let retry = ((1.0 - bucket.tokens) / self.refill_per_second).ceil() as u64;
            Err(retry.max(1))
        }
    }
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
    let inspection_token = env::var("INSPECTION_TOKEN")
        .ok()
        .filter(|t| !t.trim().is_empty());
    if inspection_token.is_none() {
        tracing::info!("INSPECTION_TOKEN not set — inspection endpoints are disabled");
    }

    let state = AppState {
        pool,
        ingest_token,
        inspection_token,
        snapshot: Arc::new(tokio::sync::RwLock::new(None)),
        refresh_lock: Arc::new(tokio::sync::Mutex::new(())),
        shell: Arc::from(read_shell()),
        origin: Arc::from(public_origin()),
        legacy_map_limiter: Arc::new(RateLimiter::per_minute(10, 2)),
        legacy_map_concurrency: Arc::new(tokio::sync::Semaphore::new(2)),
        public_v1_limiter: Arc::new(RateLimiter::per_minute(120, 30)),
    };

    // The fallback service needs its own handle: `with_state` below consumes
    // the router's copy.
    let state_for_spa = state.clone();

    // Compose every route and fallback before applying middleware. Axum layers
    // only wrap routes that already exist, so attaching the SPA afterwards left
    // deep links outside CSP/HSTS/frame protections.
    let app = Router::new()
        .route("/health", get(health))
        .route("/api/thinkers", get(thinkers))
        .route("/api/sources", get(sources))
        .route("/api/claims", get(claims))
        .route("/api/predictions", get(predictions))
        .route("/api/stats", get(stats))
        .route("/api/map", get(map))
        .route("/api/v1/map", get(map_index_v1))
        .route("/api/v1/map/:domain", get(map_domain_v1))
        .route("/api/v1/map/:domain/:shift", get(map_shift_v1))
        .route("/api/v1/map/:domain/:shift/:subshift", get(map_subshift_v1))
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
            any(|| async {
                AppError::public(StatusCode::NOT_FOUND, "not_found", "No such endpoint.")
            }),
        )
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
        .fallback_service(static_service().fallback(get(spa).with_state(state_for_spa)))
        // Baseline security headers. These intentionally wrap the completed
        // router, including ServeDir and the SPA fallback.
        .layer(SetResponseHeaderLayer::overriding(
            header::X_CONTENT_TYPE_OPTIONS,
            HeaderValue::from_static("nosniff"),
        ))
        .layer(SetResponseHeaderLayer::overriding(
            header::X_FRAME_OPTIONS,
            HeaderValue::from_static("DENY"),
        ))
        .layer(SetResponseHeaderLayer::overriding(
            header::REFERRER_POLICY,
            HeaderValue::from_static("strict-origin-when-cross-origin"),
        ))
        .layer(SetResponseHeaderLayer::overriding(
            header::STRICT_TRANSPORT_SECURITY,
            HeaderValue::from_static("max-age=31536000; includeSubDomains"),
        ))
        .layer(SetResponseHeaderLayer::overriding(
            header::CONTENT_SECURITY_POLICY,
            HeaderValue::from_static(
                "default-src 'self'; script-src 'self' 'unsafe-inline'; \
                 style-src 'self' 'unsafe-inline'; img-src 'self' data:; \
                 font-src 'self'; connect-src 'self'; frame-ancestors 'none'; \
                 object-src 'none'; media-src 'none'; worker-src 'none'; \
                 base-uri 'self'; form-action 'self'",
            ),
        ))
        .layer(TimeoutLayer::with_status_code(
            StatusCode::REQUEST_TIMEOUT,
            Duration::from_secs(10),
        ))
        .layer(CompressionLayer::new().br(true).gzip(true))
        .layer(cors_layer());

    let port = env::var("PORT").unwrap_or_else(|_| "8080".into());
    // Bind IPv6 dual-stack: Railway's private network is IPv6-only, so a service
    // bound to 0.0.0.0 isn't reachable at <svc>.railway.internal. "[::]" accepts
    // both private IPv6 and the public IPv4 edge (IPv4-mapped).
    let listener = tokio::net::TcpListener::bind(format!("[::]:{port}")).await?;
    tracing::info!("listening on {}", listener.local_addr()?);
    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<SocketAddr>(),
    )
    .await?;
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

static ERROR_SEQUENCE: AtomicU64 = AtomicU64::new(1);

#[derive(Debug)]
struct AppError {
    status: StatusCode,
    code: &'static str,
    message: String,
    request_id: String,
    retry_after: Option<u64>,
    rate_limit: Option<u64>,
}

impl AppError {
    fn public(status: StatusCode, code: &'static str, message: impl Into<String>) -> Self {
        Self {
            status,
            code,
            message: message.into(),
            request_id: next_error_id(),
            retry_after: None,
            rate_limit: None,
        }
    }

    fn internal(error: impl std::fmt::Display) -> Self {
        let request_id = next_error_id();
        tracing::error!(%request_id, error = %error, "request failed");
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            code: "internal_error",
            message: "The request could not be completed.".into(),
            request_id,
            retry_after: None,
            rate_limit: None,
        }
    }

    fn rate_limited(retry_after: u64) -> Self {
        Self {
            status: StatusCode::TOO_MANY_REQUESTS,
            code: "rate_limited",
            message: "Too many requests. Try again shortly.".into(),
            request_id: next_error_id(),
            retry_after: Some(retry_after),
            rate_limit: Some(10),
        }
    }

    fn rate_limited_with_limit(retry_after: u64, limit: u64) -> Self {
        Self {
            status: StatusCode::TOO_MANY_REQUESTS,
            code: "rate_limited",
            message: "Too many requests. Try again shortly.".into(),
            request_id: next_error_id(),
            retry_after: Some(retry_after),
            rate_limit: Some(limit),
        }
    }
}

fn next_error_id() -> String {
    format!(
        "ss-{}-{}",
        std::process::id(),
        ERROR_SEQUENCE.fetch_add(1, Ordering::Relaxed)
    )
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let request_id = self.request_id;
        let mut response = (
            self.status,
            Json(json!({
                "error": {
                    "code": self.code,
                    "message": self.message,
                    "request_id": request_id.clone(),
                }
            })),
        )
            .into_response();
        response.headers_mut().insert(
            HeaderName::from_static("x-request-id"),
            HeaderValue::from_str(&request_id).unwrap(),
        );
        if let Some(seconds) = self.retry_after {
            response.headers_mut().insert(
                header::RETRY_AFTER,
                HeaderValue::from_str(&seconds.to_string()).unwrap(),
            );
            insert_u64_header(
                response.headers_mut(),
                "ratelimit-limit",
                self.rate_limit.unwrap_or(10),
            );
            insert_u64_header(response.headers_mut(), "ratelimit-remaining", 0);
        }
        response
    }
}

impl From<sqlx::Error> for AppError {
    fn from(e: sqlx::Error) -> Self {
        AppError::internal(e)
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

fn require_inspection(s: &AppState, headers: &HeaderMap) -> Result<(), AppError> {
    let Some(expected) = s.inspection_token.as_deref() else {
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

async fn thinkers(
    State(s): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<HashMap<String, String>>,
) -> Result<Json<Value>, AppError> {
    require_inspection(&s, &headers)?;
    run_list(&s.pool, sql::THINKERS, list_limit(&q)).await
}
async fn sources(
    State(s): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<HashMap<String, String>>,
) -> Result<Json<Value>, AppError> {
    require_inspection(&s, &headers)?;
    run_list(&s.pool, sql::SOURCES, list_limit(&q)).await
}
async fn claims(
    State(s): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<HashMap<String, String>>,
) -> Result<Json<Value>, AppError> {
    require_inspection(&s, &headers)?;
    run_list(&s.pool, sql::CLAIMS, list_limit(&q)).await
}
async fn predictions(
    State(s): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<HashMap<String, String>>,
) -> Result<Json<Value>, AppError> {
    require_inspection(&s, &headers)?;
    run_list(&s.pool, sql::PREDICTIONS, list_limit(&q)).await
}
async fn stats(State(s): State<AppState>, headers: HeaderMap) -> Result<Json<Value>, AppError> {
    require_inspection(&s, &headers)?;
    let doc: Value = sqlx::query_scalar(sql::STATS).fetch_one(&s.pool).await?;
    Ok(Json(doc))
}

// ── /api/map ───────────────────────────────────────────────────────────────────

const PUBLIC_CACHE_CONTROL: &str = "public, max-age=60, stale-while-revalidate=300";

fn string_field<'a>(value: &'a Value, key: &str) -> &'a str {
    value.get(key).and_then(Value::as_str).unwrap_or_default()
}

fn key_shift_summary(shift: &Value, sub_count: usize) -> Value {
    json!({
        "id": shift.get("id").cloned().unwrap_or(Value::Null),
        "domain_id": shift.get("domain_id").cloned().unwrap_or(Value::Null),
        "slug": shift.get("slug").cloned().unwrap_or(Value::Null),
        "name": shift.get("name").cloned().unwrap_or(Value::Null),
        "subtitle": shift.get("subtitle").cloned().unwrap_or(Value::Null),
        "velocity": shift.get("velocity").cloned().unwrap_or(Value::Null),
        "read_time": shift.get("read_time").cloned().unwrap_or(Value::Null),
        "sub_shift_count": sub_count,
    })
}

fn sub_shift_summary(sub: &Value) -> Value {
    let full_slug = string_field(sub, "slug");
    json!({
        "id": sub.get("id").cloned().unwrap_or(Value::Null),
        "key_trend_id": sub.get("key_trend_id").cloned().unwrap_or(Value::Null),
        "domain_id": sub.get("domain_id").cloned().unwrap_or(Value::Null),
        "slug": full_slug.rsplit('/').next().unwrap_or(full_slug),
        "name": sub.get("name").cloned().unwrap_or(Value::Null),
        "subtitle": sub.get("subtitle").cloned().unwrap_or(Value::Null),
        "description": sub.get("description").cloned().unwrap_or(Value::Null),
    })
}

fn domain_summary(domain: &Value, shift_count: usize) -> Value {
    // `description` is deliberately absent. It is a ~900-character paragraph per
    // domain that no view renders — the deck and the domain sheet both read
    // `short_description` — so including it added ~3.6 KB of dead weight to the
    // index fragment every visitor fetches on first paint. The SEO layer reads
    // the long copy straight off the publication (see seo.rs), not from here.
    json!({
        "id": domain.get("id").cloned().unwrap_or(Value::Null),
        "name": domain.get("name").cloned().unwrap_or(Value::Null),
        "label": domain.get("label").cloned().unwrap_or(Value::Null),
        "short_description": domain.get("short_description").cloned().unwrap_or(Value::Null),
        "horizon": domain.get("horizon").cloned().unwrap_or(Value::Null),
        "key_shift_count": shift_count,
    })
}

/// Fields on a published shift/sub-shift row that exist only for the generator
/// and the validator, and which no view reads.
///
/// `db_id` is the Postgres primary key — recycled weekly by `reset_v2_tables`
/// and meaningless to a client, so publishing it leaks an internal identifier
/// for nothing. `proponents*`/`skeptics*` are the raw attribution columns the
/// `voices` module is *built from*: shipping both sent every thinker quote
/// twice. `sub_trend_ids` restates the `sub_shifts` array that accompanies it.
const INTERNAL_SHIFT_FIELDS: [&str; 6] = [
    "db_id",
    "proponents",
    "proponents_detail",
    "skeptics",
    "skeptics_detail",
    "sub_trend_ids",
];

/// The published row minus the generator-only fields above. Everything a view
/// actually reads — including the whole `modules` list — is passed through
/// untouched, so this narrows the payload without narrowing the contract.
fn shift_detail(row: &Value) -> Value {
    let mut out = row.clone();
    if let Some(object) = out.as_object_mut() {
        for field in INTERNAL_SHIFT_FIELDS {
            object.remove(field);
        }
    }
    out
}

fn domain_index_summary(
    domain: &Value,
    shifts: &[&Value],
    subs_by_shift: &HashMap<&str, Vec<&Value>>,
) -> Value {
    let mut summary = domain_summary(domain, shifts.len());
    let previews: Vec<Value> = shifts
        .iter()
        .take(4)
        .map(|shift| {
            key_shift_summary(
                shift,
                subs_by_shift
                    .get(string_field(shift, "id"))
                    .map_or(0, |items| items.len()),
            )
        })
        .collect();
    summary["key_shifts"] = Value::Array(previews);
    summary
}

fn weak_etag(version: &str, identity: &str) -> HeaderValue {
    // Deterministic FNV-1a is sufficient here: this is a cache validator, not a
    // signature. Including route identity prevents two fragments from sharing
    // an ETag even when their bytes happen to match.
    let mut hash = 0xcbf29ce484222325u64;
    for byte in version.bytes().chain([0]).chain(identity.bytes()) {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    HeaderValue::from_str(&format!("W/\"{hash:016x}\"")).unwrap()
}

fn route_fragment(version: &str, identity: &str, value: Value) -> RouteFragment {
    RouteFragment {
        body: Arc::from(serde_json::to_string(&value).expect("JSON Value must serialize")),
        etag: weak_etag(version, identity),
    }
}

/// Parse one publication and derive every public response exactly once.
fn build_snapshot(body: String, version: &str) -> Result<MapSnapshot, serde_json::Error> {
    let document: Value = serde_json::from_str(&body)?;
    let domains = document
        .get("domains")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let shifts = document
        .get("key_trends")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let subs = document
        .get("sub_trends")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let insights = document
        .get("synthesis_insights")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    let mut shifts_by_domain: HashMap<&str, Vec<&Value>> = HashMap::new();
    let mut subs_by_shift: HashMap<&str, Vec<&Value>> = HashMap::new();
    for shift in &shifts {
        shifts_by_domain
            .entry(string_field(shift, "domain_id"))
            .or_default()
            .push(shift);
    }
    for sub in &subs {
        subs_by_shift
            .entry(string_field(sub, "key_trend_id"))
            .or_default()
            .push(sub);
    }

    let updated = document.get("updated").cloned().unwrap_or(Value::Null);
    let domain_summaries: Vec<Value> = domains
        .iter()
        .map(|domain| {
            let domain_shifts = shifts_by_domain
                .get(string_field(domain, "id"))
                .cloned()
                .unwrap_or_default();
            domain_index_summary(domain, &domain_shifts, &subs_by_shift)
        })
        .collect();
    let mut routes = HashMap::new();
    routes.insert(
        String::new(),
        route_fragment(
            version,
            "index",
            json!({
                "updated": updated,
                "totals": {
                    "domains": domains.len(),
                    "key_shifts": shifts.len(),
                    "sub_shifts": subs.len(),
                },
                "domains": domain_summaries,
            }),
        ),
    );

    for domain in &domains {
        let domain_id = string_field(domain, "id");
        if domain_id.is_empty() {
            continue;
        }
        let domain_shifts = shifts_by_domain.get(domain_id).cloned().unwrap_or_default();
        let domain_shift_count = domain_shifts.len();
        let summaries: Vec<Value> = domain_shifts
            .iter()
            .map(|shift| {
                key_shift_summary(
                    shift,
                    subs_by_shift
                        .get(string_field(shift, "id"))
                        .map_or(0, |items| items.len()),
                )
            })
            .collect();
        let domain_insights: Vec<Value> = insights
            .iter()
            .filter(|item| string_field(item, "domain_id") == domain_id)
            .cloned()
            .collect();
        routes.insert(
            domain_id.to_string(),
            route_fragment(
                version,
                domain_id,
                json!({
                    "updated": updated,
                    "domain": domain_summary(domain, domain_shift_count),
                    "key_shifts": summaries.clone(),
                    "insights": domain_insights,
                }),
            ),
        );

        for shift in &domain_shifts {
            let shift_slug = string_field(shift, "slug");
            let shift_id = string_field(shift, "id");
            if shift_slug.is_empty() || shift_id.is_empty() {
                continue;
            }
            let route_id = format!("{domain_id}/{shift_slug}");
            let shift_subs = subs_by_shift.get(shift_id).cloned().unwrap_or_default();
            let sub_summaries: Vec<Value> = shift_subs
                .iter()
                .map(|sub| sub_shift_summary(sub))
                .collect();
            routes.insert(
                route_id.clone(),
                route_fragment(
                    version,
                    &route_id,
                    json!({
                        "updated": updated,
                        "domain": domain_summary(domain, domain_shift_count),
                        "shift": shift_detail(shift),
                        "siblings": summaries.clone(),
                        "sub_shifts": sub_summaries,
                    }),
                ),
            );

            for sub in &shift_subs {
                let full_slug = string_field(sub, "slug");
                let sub_slug = full_slug.rsplit('/').next().unwrap_or(full_slug);
                if sub_slug.is_empty() {
                    continue;
                }
                let sub_route_id = format!("{route_id}/{sub_slug}");
                let siblings: Vec<Value> = shift_subs
                    .iter()
                    .map(|sibling| sub_shift_summary(sibling))
                    .collect();
                routes.insert(
                    sub_route_id.clone(),
                    route_fragment(
                        version,
                        &sub_route_id,
                        json!({
                            "updated": updated,
                            "domain": domain_summary(domain, domain_shift_count),
                            "parent_shift": key_shift_summary(shift, shift_subs.len()),
                            "sub_shift": shift_detail(sub),
                            "siblings": siblings,
                        }),
                    ),
                );
            }
        }
    }

    Ok(MapSnapshot {
        loaded_at: Instant::now(),
        site_index: Arc::new(seo::build_index(&body)),
        full_body: Arc::from(body),
        routes,
    })
}

async fn fetch_snapshot(s: &AppState) -> Result<Arc<MapSnapshot>, AppError> {
    let row: Option<(String, String)> =
        sqlx::query_as("SELECT body::text, updated_at::text FROM documents WHERE key = 'map'")
            .fetch_optional(&s.pool)
            .await?;
    let (body, version) = row.ok_or_else(|| {
        AppError::public(
            StatusCode::NOT_FOUND,
            "not_found",
            "Map document not found.",
        )
    })?;
    build_snapshot(body, &version)
        .map(Arc::new)
        .map_err(|error| AppError::internal(format!("invalid published map JSON: {error}")))
}

/// Current snapshot, with one refresh under concurrent misses. If Postgres is
/// briefly unavailable after the TTL, keep serving the last known good map.
async fn map_snapshot(s: &AppState) -> Result<Arc<MapSnapshot>, AppError> {
    if let Some(snapshot) = s.snapshot.read().await.as_ref().cloned() {
        if snapshot.loaded_at.elapsed() < DOC_CACHE_TTL {
            return Ok(snapshot);
        }
    }

    let _refresh = s.refresh_lock.lock().await;
    if let Some(snapshot) = s.snapshot.read().await.as_ref().cloned() {
        if snapshot.loaded_at.elapsed() < DOC_CACHE_TTL {
            return Ok(snapshot);
        }
    }

    match fetch_snapshot(s).await {
        Ok(snapshot) => {
            *s.snapshot.write().await = Some(snapshot.clone());
            Ok(snapshot)
        }
        Err(error) => {
            if let Some(snapshot) = s.snapshot.read().await.as_ref().cloned() {
                tracing::warn!(request_id = %error.request_id, "map refresh failed; serving last good snapshot");
                Ok(snapshot)
            } else {
                Err(error)
            }
        }
    }
}

async fn site_index(s: &AppState) -> Arc<seo::SiteIndex> {
    map_snapshot(s)
        .await
        .map(|snapshot| snapshot.site_index.clone())
        .unwrap_or_else(|_| Arc::new(seo::SiteIndex::default()))
}

fn json_response(body: Arc<str>) -> Response {
    (
        [
            (
                header::CONTENT_TYPE,
                HeaderValue::from_static("application/json"),
            ),
            (
                header::CACHE_CONTROL,
                HeaderValue::from_static(PUBLIC_CACHE_CONTROL),
            ),
        ],
        body.as_ref().to_owned(),
    )
        .into_response()
}

fn fragment_response(fragment: &RouteFragment, headers: &HeaderMap, remaining: u32) -> Response {
    let not_modified = headers
        .get(header::IF_NONE_MATCH)
        .is_some_and(|value| value == fragment.etag);
    let mut response = if not_modified {
        StatusCode::NOT_MODIFIED.into_response()
    } else {
        json_response(fragment.body.clone())
    };
    response
        .headers_mut()
        .insert(header::ETAG, fragment.etag.clone());
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static(PUBLIC_CACHE_CONTROL),
    );
    insert_u64_header(response.headers_mut(), "ratelimit-limit", 120);
    insert_u64_header(
        response.headers_mut(),
        "ratelimit-remaining",
        u64::from(remaining),
    );
    response
}

async fn public_fragment(
    s: &AppState,
    headers: &HeaderMap,
    peer: SocketAddr,
    identity: String,
) -> Result<Response, AppError> {
    let remaining = s
        .public_v1_limiter
        .check(client_ip(headers, peer))
        .map_err(|seconds| AppError::rate_limited_with_limit(seconds, 120))?;
    let snapshot = map_snapshot(s).await?;
    let fragment = snapshot.routes.get(&identity).ok_or_else(|| {
        AppError::public(StatusCode::NOT_FOUND, "not_found", "Map route not found.")
    })?;
    Ok(fragment_response(fragment, headers, remaining))
}

async fn map_index_v1(
    State(s): State<AppState>,
    headers: HeaderMap,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
) -> Result<Response, AppError> {
    public_fragment(&s, &headers, peer, String::new()).await
}

async fn map_domain_v1(
    State(s): State<AppState>,
    AxumPath(domain): AxumPath<String>,
    headers: HeaderMap,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
) -> Result<Response, AppError> {
    public_fragment(&s, &headers, peer, domain).await
}

async fn map_shift_v1(
    State(s): State<AppState>,
    AxumPath((domain, shift)): AxumPath<(String, String)>,
    headers: HeaderMap,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
) -> Result<Response, AppError> {
    public_fragment(&s, &headers, peer, format!("{domain}/{shift}")).await
}

async fn map_subshift_v1(
    State(s): State<AppState>,
    AxumPath((domain, shift, subshift)): AxumPath<(String, String, String)>,
    headers: HeaderMap,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
) -> Result<Response, AppError> {
    public_fragment(&s, &headers, peer, format!("{domain}/{shift}/{subshift}")).await
}

fn client_ip(headers: &HeaderMap, peer: SocketAddr) -> IpAddr {
    // Railway normalises X-Forwarded-For at its public edge. Do not trust the
    // header during direct/local operation, where a client can supply it.
    if env::var_os("RAILWAY_ENVIRONMENT_ID").is_some() {
        if let Some(ip) = headers
            .get("x-forwarded-for")
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.split(',').next())
            .and_then(|value| value.trim().parse().ok())
        {
            return ip;
        }
    }
    peer.ip()
}

fn insert_u64_header(headers: &mut HeaderMap, name: &'static str, value: u64) {
    headers.insert(
        HeaderName::from_static(name),
        HeaderValue::from_str(&value.to_string()).unwrap(),
    );
}

/// The legacy full trend map — an operator surface, not a public one.
///
/// It requires INSPECTION_TOKEN for the same reason `/api/claims` and
/// `/api/thinkers` do: the publication embeds the data those endpoints gate.
/// Unauthenticated, this route answered 4.4 MB containing 193 thinkers with
/// their `credibility_score`, `prediction_accuracy` and bios, and 452 claims
/// with per-claim `thinker_credibility` and `consumer_implication` — so the
/// token check on the inspection endpoints could be walked around by asking a
/// different URL for the same rows. No client needs it: the SPA reads only the
/// route-scoped `/api/v1/map/*` fragments.
///
/// Still rate and concurrency limited behind the token, because every response
/// is large and expensive to compress.
async fn map(
    State(s): State<AppState>,
    headers: HeaderMap,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
) -> Result<Response, AppError> {
    require_inspection(&s, &headers)?;
    let remaining = s
        .legacy_map_limiter
        .check(client_ip(&headers, peer))
        .map_err(AppError::rate_limited)?;
    let permit = s
        .legacy_map_concurrency
        .clone()
        .try_acquire_owned()
        .map_err(|_| AppError::rate_limited(1))?;

    let mut response = json_response(map_snapshot(&s).await?.full_body.clone());
    let response_headers = response.headers_mut();
    response_headers.insert(
        HeaderName::from_static("deprecation"),
        HeaderValue::from_static("true"),
    );
    response_headers.insert(
        header::LINK,
        HeaderValue::from_static("</api/v1/map>; rel=\"successor-version\""),
    );
    insert_u64_header(response_headers, "ratelimit-limit", 10);
    insert_u64_header(
        response_headers,
        "ratelimit-remaining",
        u64::from(remaining),
    );
    // Keep the permit alive until the response body has been consumed.
    response.extensions_mut().insert(Arc::new(permit));
    Ok(response)
}

// ── SPA shell, robots, sitemap ────────────────────────────────────────────────

/// Serve the app shell with this route's metadata stamped into its `<head>`.
///
/// Registered as the fallback, so it handles every path the API and the static
/// files did not. A route we have no metadata for still gets the shell verbatim
/// — the client router resolves it, and unknown shifts render the app's own
/// not-found state.
/// True when a path looks like a file request rather than a client-side route.
///
/// App routes are built from slugs, which strip punctuation — so no real route
/// ever contains a dot in its last segment. Anything that does is asking for an
/// asset, and answering that with the app shell at 200 is actively harmful: a
/// mistyped `<script src>` silently receives HTML instead of failing, and search
/// engines read 200-with-shell on arbitrary URLs as soft 404s.
fn looks_like_asset(path: &str) -> bool {
    path.rsplit('/').next().is_some_and(|seg| seg.contains('.'))
}

async fn spa(State(s): State<AppState>, uri: axum::http::Uri) -> Response {
    if s.shell.is_empty() {
        return (StatusCode::NOT_FOUND, "no SPA build").into_response();
    }
    let path = uri.path();
    if looks_like_asset(path) {
        return (StatusCode::NOT_FOUND, "not found").into_response();
    }
    let idx = site_index(&s).await;
    let (status, html) = match idx.pages.get(path) {
        Some(meta) => (StatusCode::OK, seo::render(&s.shell, path, meta, &s.origin)),
        None if path == "/" => (StatusCode::OK, s.shell.to_string()),
        None => (StatusCode::NOT_FOUND, seo::render_not_found(&s.shell)),
    };
    (
        status,
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
        return Err(AppError::public(
            StatusCode::NOT_FOUND,
            "not_found",
            "Not found.",
        ));
    };
    let presented = headers
        .get("x-ingest-token")
        .and_then(|v| v.to_str().ok())
        .unwrap_or_default();
    if !secret_eq(presented, expected) {
        return Err(AppError::public(
            StatusCode::UNAUTHORIZED,
            "unauthorized",
            "Unauthorized.",
        ));
    }

    let req: IngestInnovationReq = serde_json::from_slice(&body).map_err(|_| {
        AppError::public(
            StatusCode::BAD_REQUEST,
            "invalid_request",
            "Request body is not valid JSON.",
        )
    })?;

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
    fn asset_like_paths_are_404ed_not_answered_with_the_app_shell() {
        // A missing asset answered with 200 HTML makes a broken <script src>
        // silently succeed, and reads as a soft 404 to a crawler.
        for p in [
            "/nonexistent.js",
            "/styles.css",
            "/foo.json",
            "/a/b/image.png",
        ] {
            assert!(looks_like_asset(p), "{p} should be treated as an asset");
        }
    }

    #[test]
    fn real_app_routes_are_never_mistaken_for_assets() {
        // Slugs strip punctuation, so no route's last segment contains a dot.
        for p in [
            "/",
            "/map/society",
            "/map/society/sovereign-collapse",
            "/map/society/sovereign-collapse/threshold-blindness",
            "/some/deep/path",
        ] {
            assert!(!looks_like_asset(p), "{p} is a route, not an asset");
        }
    }

    #[test]
    fn secret_comparison_is_length_and_content_sensitive() {
        assert!(secret_eq("abc123", "abc123"));
        assert!(!secret_eq("abc123", "abc124"));
        assert!(!secret_eq("abc", "abc123"));
        assert!(!secret_eq("", "x"));
    }

    #[test]
    fn legacy_rate_limit_enforces_its_burst() {
        let limiter = RateLimiter::per_minute(10, 2);
        let ip: IpAddr = "203.0.113.7".parse().unwrap();
        assert_eq!(limiter.check(ip), Ok(1));
        assert_eq!(limiter.check(ip), Ok(0));
        assert!(limiter.check(ip).is_err());
    }

    #[test]
    fn forwarded_ip_is_ignored_outside_railway() {
        std::env::remove_var("RAILWAY_ENVIRONMENT_ID");
        let mut headers = HeaderMap::new();
        headers.insert("x-forwarded-for", HeaderValue::from_static("198.51.100.4"));
        let peer: SocketAddr = "127.0.0.1:1234".parse().unwrap();
        assert_eq!(client_ip(&headers, peer), peer.ip());
    }

    fn sample_map() -> String {
        json!({
            "updated": "2026-08-02",
            "domains": [{
                "id": "society", "name": "Society", "label": "AI × Society",
                "short_description": "A domain", "description": "Longer domain copy",
                "horizon": "2028", "key_trend_ids": ["kt-1"]
            }],
            "key_trends": [{
                "id": "kt-1", "domain_id": "society", "slug": "trust-machines",
                "name": "Trust Machines", "subtitle": "A shift", "velocity": "rising",
                "read_time": "4 min read", "sub_trend_ids": ["st-1"],
                "db_id": 4173, "proponents": "Ada Lovelace", "skeptics": "Alan Turing",
                "proponents_detail": [{"name": "Ada Lovelace", "quote": "It holds."}],
                "skeptics_detail": [{"name": "Alan Turing", "quote": "It does not."}],
                "modules": [{"type": "dek", "data": {"text": "A shift"}}]
            }],
            "sub_trends": [{
                "id": "st-1", "key_trend_id": "kt-1", "domain_id": "society",
                "slug": "trust-machines/proof-of-human", "name": "Proof of Human",
                "subtitle": "A sub-shift", "description": "Sub copy",
                "modules": [{"type": "lede", "data": {"text": "Sub copy"}}]
            }],
            "synthesis_insights": [{
                "id": 1, "domain_id": "society", "name": "Trust moves",
                "description": "Verification becomes a product."
            }]
        })
        .to_string()
    }

    #[test]
    fn route_snapshot_has_distinct_scoped_documents_and_etags() {
        let snapshot = build_snapshot(sample_map(), "2026-08-02 14:00:00+00").unwrap();
        let index = snapshot.routes.get("").unwrap();
        let domain = snapshot.routes.get("society").unwrap();
        let shift = snapshot.routes.get("society/trust-machines").unwrap();
        let sub = snapshot
            .routes
            .get("society/trust-machines/proof-of-human")
            .unwrap();

        let index_json: Value = serde_json::from_str(&index.body).unwrap();
        let domain_json: Value = serde_json::from_str(&domain.body).unwrap();
        let shift_json: Value = serde_json::from_str(&shift.body).unwrap();
        let sub_json: Value = serde_json::from_str(&sub.body).unwrap();
        assert!(index_json.get("totals").is_some());
        assert!(index_json.get("key_trends").is_none());
        assert_eq!(
            index_json["domains"][0]["key_shifts"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        assert!(domain_json.get("key_shifts").is_some());
        assert!(shift_json.get("shift").is_some());
        assert!(shift_json.get("siblings").is_some());
        assert!(shift_json.get("sub_shifts").is_some());
        assert!(sub_json.get("parent_shift").is_some());
        assert!(sub_json.get("siblings").is_some());
        assert_ne!(index.etag, domain.etag);
        assert_ne!(domain.etag, shift.etag);
        assert_ne!(shift.etag, sub.etag);

        // The shift fragment carries the module list the page renders...
        assert!(shift_json["shift"]["modules"].is_array());
        assert_eq!(shift_json["shift"]["slug"], "trust-machines");
        // ...and none of the generator-only fields. `db_id` is an internal
        // primary key; the `*_detail` columns are what the `voices` module is
        // built from, so publishing both sent every quote twice.
        for field in INTERNAL_SHIFT_FIELDS {
            assert!(
                shift_json["shift"].get(field).is_none(),
                "shift fragment must not publish {field:?}"
            );
        }

        // No view reads a domain's long `description`; only `short_description`.
        for scope in [&index_json["domains"][0], &domain_json["domain"]] {
            assert!(scope.get("short_description").is_some());
            assert!(
                scope.get("description").is_none(),
                "domain summaries must not carry the unread long description"
            );
        }
    }

    #[test]
    fn internal_fields_are_stripped_without_touching_anything_else() {
        let row = json!({
            "id": "kt-1", "slug": "s", "name": "N", "subtitle": "sub",
            "description": "kept — it is the dek fallback",
            "hero_stat": {"value": "24 months"},
            "modules": [{"type": "dek", "data": {"text": "t"}}],
            "db_id": 99, "sub_trend_ids": ["st-1"],
            "proponents": "a", "skeptics": "b",
            "proponents_detail": [], "skeptics_detail": [],
        });
        let out = shift_detail(&row);
        for field in INTERNAL_SHIFT_FIELDS {
            assert!(out.get(field).is_none(), "{field} should be stripped");
        }
        for field in [
            "id",
            "slug",
            "name",
            "subtitle",
            "description",
            "hero_stat",
            "modules",
        ] {
            assert_eq!(out.get(field), row.get(field), "{field} must pass through");
        }
    }

    #[test]
    fn matching_etag_returns_304_without_a_body() {
        let snapshot = build_snapshot(sample_map(), "version").unwrap();
        let fragment = snapshot.routes.get("society").unwrap();
        let mut headers = HeaderMap::new();
        headers.insert(header::IF_NONE_MATCH, fragment.etag.clone());
        let response = fragment_response(fragment, &headers, 29);
        assert_eq!(response.status(), StatusCode::NOT_MODIFIED);
        assert_eq!(response.headers().get(header::ETAG), Some(&fragment.etag));
    }

    #[test]
    fn route_fragments_fit_compressed_response_budgets() {
        use std::io::Write;

        let snapshot = build_snapshot(sample_map(), "version").unwrap();
        for (route, budget) in [
            ("", 25 * 1024),
            ("society", 75 * 1024),
            ("society/trust-machines", 100 * 1024),
            ("society/trust-machines/proof-of-human", 100 * 1024),
        ] {
            let body = snapshot.routes.get(route).unwrap().body.as_bytes();
            let mut compressed = Vec::new();
            {
                let mut writer = brotli::CompressorWriter::new(&mut compressed, 4096, 6, 20);
                writer.write_all(body).unwrap();
            }
            assert!(
                compressed.len() <= budget,
                "{route:?} compressed to {} bytes (budget {budget})",
                compressed.len()
            );
        }
    }

    #[tokio::test]
    async fn concurrent_cold_reads_share_one_snapshot_refresh() {
        let Ok(database_url) = std::env::var("DATABASE_URL") else {
            return; // DB-backed in CI; unit-only local runs remain self-contained.
        };
        let pool = PgPoolOptions::new()
            .max_connections(4)
            .connect(&database_url)
            .await
            .unwrap();
        let state = AppState {
            pool,
            ingest_token: None,
            inspection_token: None,
            snapshot: Arc::new(tokio::sync::RwLock::new(None)),
            refresh_lock: Arc::new(tokio::sync::Mutex::new(())),
            shell: Arc::from(""),
            origin: Arc::from(""),
            legacy_map_limiter: Arc::new(RateLimiter::per_minute(10, 2)),
            legacy_map_concurrency: Arc::new(tokio::sync::Semaphore::new(2)),
            public_v1_limiter: Arc::new(RateLimiter::per_minute(120, 30)),
        };

        let mut tasks = tokio::task::JoinSet::new();
        for _ in 0..20 {
            let cloned = state.clone();
            tasks.spawn(async move { map_snapshot(&cloned).await.unwrap() });
        }
        let mut snapshots = Vec::new();
        while let Some(result) = tasks.join_next().await {
            snapshots.push(result.unwrap());
        }
        assert_eq!(snapshots.len(), 20);
        assert!(snapshots
            .iter()
            .skip(1)
            .all(|snapshot| Arc::ptr_eq(&snapshots[0], snapshot)));
    }
}
