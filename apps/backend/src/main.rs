//! Serious Shift read API. Replaces the ~53 MB of static JSON the frontend used
//! to download: each endpoint serves the same shape, sourced from Postgres.
//!
//! Env: DATABASE_URL (required), PORT (default 8080),
//!      FRONTEND_ORIGIN (CORS allowlist, comma-separated),
//!      INSPECTION_TOKEN (gates the operator-only reads, including /api/map),
//!      INGEST_TOKEN (gates the innovations write endpoint),
//!      CURATION_TOKEN (gates editing innovation↔shift links),
//!      INNOVATION_ASSET_HOSTS (hosts a cover image may be mirrored from).

mod innovations;
mod module_policy;
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
    routing::{any, delete, get, post, put},
    Json, Router,
};
use serde_json::{json, Value};
use sqlx::postgres::PgPoolOptions;
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
        .allow_methods([Method::GET, Method::POST, Method::PUT, Method::DELETE])
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
/// browser. The cacheable assets are handled by the `/assets` and `/shift`
/// nests registered ahead of this one; whatever reaches here gets
/// `STATIC_DEFAULT`.
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

/// `Cache-Control` for the content-addressed bundles under /assets.
///
/// Vite puts a content hash in every filename there — `index-DAHsYQgs.js`, the
/// stylesheet, all five font faces — so a changed file is a changed URL and a
/// stale entry is impossible.
const IMMUTABLE: &str = "public, max-age=31536000, immutable";

/// `Cache-Control` for the generated artwork under /shift.
///
/// Deliberately NOT immutable: these filenames are keyed by slug, not by
/// content, so regenerating the art reuses the URL. `immutable` would pin a
/// stale poster in every browser that had ever loaded it, for a year, with no
/// way to evict it. A day of freshness plus a week of serve-stale-while-you-
/// revalidate gets the CDN benefit and still lets a republish land.
const ARTWORK: &str = "public, max-age=86400, stale-while-revalidate=604800";

/// `Cache-Control` for everything else static — the favicons, the wordmark, the
/// generic share card, the web manifest. Stable URLs, rarely edited, and small.
///
/// Applied `if_not_present` so it defaults only responses that did not set the
/// header themselves: the SPA shell keeps its own `no-cache`, which is what
/// makes a deploy visible to a returning browser.
const STATIC_DEFAULT: &str = "public, max-age=3600, stale-while-revalidate=86400";

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
    /// Shared secret for editing innovation↔shift links. Separate from
    /// `ingest_token` on purpose: the upstream database's credential should not
    /// be able to change what appears on a page.
    curation_token: Option<String>,
    /// Shared secret for the operator-only inspection endpoints.
    inspection_token: Option<String>,
    /// Only ever used to mirror an innovation's cover image, and only to the
    /// hosts `INNOVATION_ASSET_HOSTS` allows. Built once: a fresh client per
    /// request would discard the connection pool and the TLS session cache.
    http: reqwest::Client,
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
    /// The write path. Authenticated, but a bounded one: a runaway upstream
    /// loop should be slowed here rather than in the database.
    ingest_limiter: Arc<RateLimiter>,
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
    let curation_token = env::var("CURATION_TOKEN")
        .ok()
        .filter(|t| !t.trim().is_empty());
    if curation_token.is_none() {
        tracing::info!("CURATION_TOKEN not set — innovation↔shift curation is disabled");
    }
    let inspection_token = env::var("INSPECTION_TOKEN")
        .ok()
        .filter(|t| !t.trim().is_empty());
    if inspection_token.is_none() {
        tracing::info!("INSPECTION_TOKEN not set — inspection endpoints are disabled");
    }

    // Redirects are off deliberately: the SSRF gate checks the host of the URL we
    // were given, and following a 302 would let an allowlisted host hand us any
    // other one.
    let http = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(15))
        .user_agent("serious-shift-backend/1 (+innovation cover mirror)")
        .build()
        .expect("HTTP client must build");

    let state = AppState {
        pool,
        ingest_token,
        curation_token,
        inspection_token,
        http,
        snapshot: Arc::new(tokio::sync::RwLock::new(None)),
        refresh_lock: Arc::new(tokio::sync::Mutex::new(())),
        shell: Arc::from(read_shell()),
        origin: Arc::from(public_origin()),
        legacy_map_limiter: Arc::new(RateLimiter::per_minute(10, 2)),
        legacy_map_concurrency: Arc::new(tokio::sync::Semaphore::new(2)),
        // 120/min with a 30 burst was too tight for the thing it protects. A
        // reading route costs two calls (index + fragment), the response is a
        // slice of one cached document, and the bucket is keyed by IP — so a
        // room of people behind one office NAT shares it. Walking the map at a
        // normal pace tripped it on 120 of 310 routes in a crawl; the client
        // retries on Retry-After and recovers, so it showed as a stall rather
        // than an error, which is worse to debug and worse to demo.
        //
        // 600/min with a 150 burst still refuses a scraper and still bounds the
        // memory the bucket map can take, while leaving ordinary browsing —
        // including several people at once — nowhere near the ceiling.
        public_v1_limiter: Arc::new(RateLimiter::per_minute(600, 150)),
        ingest_limiter: Arc::new(RateLimiter::per_minute(60, 20)),
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
        .route("/api/v1/innovations", get(innovations::list))
        .route("/api/v1/innovations/:id", get(innovations::detail))
        // Same origin as the page that renders it, which is what makes the
        // mirrored bytes legal under `img-src 'self'`.
        .route(
            "/api/innovations/:id/cover-image",
            get(innovations::cover_image),
        )
        .route(
            "/api/innovations/ingest",
            post(innovations::ingest).layer(DefaultBodyLimit::max(1024 * 1024)),
        )
        .route(
            "/api/innovations/:id/shifts",
            put(innovations::put_shifts).layer(DefaultBodyLimit::max(64 * 1024)),
        )
        // A sub-shift slug is `parent/child`, so the tail is a wildcard rather
        // than a single segment.
        .route(
            "/api/innovations/:id/shifts/:scope/*slug",
            delete(innovations::delete_shift_link),
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
        //
        // This nest was `/_next/static` — a path the Next export used and this
        // Vite build has never emitted, so it matched nothing and every asset on
        // the site was served with NO `Cache-Control` at all. Browsers then fall
        // back to heuristic freshness, which is a fraction of the file's age;
        // right after a deploy every file's age is ~0, so the heuristic is ~0 and
        // the bundle, the stylesheet, the five fonts and all 408 artwork files
        // revalidated on every single navigation. Worst on launch day, when
        // nothing is warm.
        .nest_service(
            "/assets",
            ServiceBuilder::new()
                .layer(SetResponseHeaderLayer::overriding(
                    header::CACHE_CONTROL,
                    HeaderValue::from_static(IMMUTABLE),
                ))
                .service(ServeDir::new(Path::new(&static_dir()).join("assets"))),
        )
        .nest_service(
            "/shift",
            ServiceBuilder::new()
                .layer(SetResponseHeaderLayer::overriding(
                    header::CACHE_CONTROL,
                    HeaderValue::from_static(ARTWORK),
                ))
                .service(ServeDir::new(Path::new(&static_dir()).join("shift"))),
        )
        // Static files first (real assets: /logo.png, /favicon.ico, …); anything
        // they do not have falls through to `spa`, which serves index.html with
        // this route's metadata stamped in. Registered last so every /api route
        // above wins.
        .fallback_service(
            ServiceBuilder::new()
                .layer(SetResponseHeaderLayer::if_not_present(
                    header::CACHE_CONTROL,
                    HeaderValue::from_static(STATIC_DEFAULT),
                ))
                .service(static_service().fallback(get(spa).with_state(state_for_spa))),
        )
        // Keep staging out of the search index. `None` on the published site
        // inserts nothing; see seo::robots_header for why the header is needed
        // alongside robots.txt rather than instead of it.
        .layer(SetResponseHeaderLayer::overriding(
            HeaderName::from_static("x-robots-tag"),
            seo::robots_header(&public_origin()).and_then(|v| HeaderValue::from_str(v).ok()),
        ))
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
            // `script-src` does NOT allow 'unsafe-inline'. The shipped shell has
            // zero inline <script> blocks — one external bundle and nothing
            // else — so the allowance bought nothing and cost the policy its
            // main protection: with 'unsafe-inline' present, any injected
            // <script> in the page executes, which is the exact class of attack
            // a CSP is for. `style-src` keeps it, because React writes inline
            // `style` attributes on nearly every element in this design.
            HeaderValue::from_static(
                "default-src 'self'; script-src 'self'; \
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
    /// Per-field detail, emitted only for 422. Absent everywhere else, so the
    /// envelope every existing client parses is unchanged.
    ///
    /// Boxed because this type is the `Err` of nearly every handler: inline, the
    /// extra `Value` pushed `AppError` past 128 bytes and every `Result` in the
    /// crate got wider to carry a field only one status code sets.
    details: Option<Box<Value>>,
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
            details: None,
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
            details: None,
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
            details: None,
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
            details: None,
        }
    }

    /// A body that parsed but doesn't make sense, with the offending fields
    /// named. 422 rather than 400 so a caller can tell "I sent malformed JSON"
    /// from "I sent JSON you disagree with" — the two need different fixes.
    fn validation(details: Vec<Value>) -> Self {
        Self {
            status: StatusCode::UNPROCESSABLE_ENTITY,
            code: "validation_failed",
            message: "The payload could not be accepted.".into(),
            request_id: next_error_id(),
            retry_after: None,
            rate_limit: None,
            details: Some(Box::new(Value::Array(details))),
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
        let mut error = json!({
            "code": self.code,
            "message": self.message,
            "request_id": request_id.clone(),
        });
        if let Some(details) = self.details {
            error["details"] = *details;
        }
        let mut response = (self.status, Json(json!({ "error": error }))).into_response();
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

/// A sphere as its own page needs it: the summary plus the "what's shifting
/// right now" paragraph.
///
/// Kept separate from `domain_summary` for the same reason `description` is
/// excluded there. `intro` is four paragraphs across the whole document, and
/// the index fragment carries all four domains on first paint. The sphere
/// fragment carries one, for the page that actually prints it.
fn domain_detail(domain: &Value, shift_count: usize) -> Value {
    let mut out = domain_summary(domain, shift_count);
    out["intro"] = domain.get("intro").cloned().unwrap_or(Value::Null);
    out
}

/// Fields on a published shift/sub-shift row that exist only for the generator
/// and the validator, and which no view reads.
///
/// `db_id` is the Postgres primary key — recycled weekly by `reset_v2_tables`
/// and meaningless to a client, so publishing it leaks an internal identifier
/// for nothing. `proponents*`/`skeptics*` are the raw attribution columns the
/// `voices` module is *built from*: shipping both sent every thinker quote
/// twice. `sub_trend_ids` restates the `sub_shifts` array that accompanies it.
/// `authored` tells `build_snapshot` the page came from a module override and is
/// exempt from the visibility filter; it is a publication detail, not content.
const INTERNAL_SHIFT_FIELDS: [&str; 7] = [
    "authored",
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

/// A published sub-shift, with `slug` reduced to the single path segment that
/// addresses it.
///
/// The publication stores a sub-shift's slug as `parent/child`, because that is
/// what makes it unique across the document. But every other place a slug
/// reaches a client it is the bare segment — `sub_shift_summary` strips it, and
/// the route that served this response is `…/{shift}/{subshift}`, where the
/// parent is already a separate segment.
///
/// Serving the compound form on `sub_shift` while serving the bare form on
/// `siblings` in the *same response* is what broke every sub-shift page: the
/// client checks `sub_shift.slug` against the last URL segment before it will
/// render, that check could never pass, and a rejected response is retried and
/// then shown as "temporarily unavailable". All 281 sub-shift pages answered
/// HTTP 200 and rendered an error.
fn sub_shift_detail(row: &Value) -> Value {
    let mut out = shift_detail(row);
    let segment = {
        let full = string_field(row, "slug");
        full.rsplit('/').next().unwrap_or(full).to_owned()
    };
    if let Some(object) = out.as_object_mut() {
        if !segment.is_empty() {
            object.insert("slug".into(), Value::String(segment));
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
///
/// `innovations` is the one part of a shift page that does not come from the
/// publication: it is joined in here, so an example pushed by the upstream
/// database appears on its shifts within `DOC_CACHE_TTL` instead of waiting for
/// the next weekly run. `version` must already carry the innovations revision —
/// see `fetch_snapshot` — or the ETags derived below would not change when they
/// do.
fn build_snapshot(
    body: String,
    version: &str,
    innovations: &innovations::ByShift,
    policy: &module_policy::Policy,
) -> Result<MapSnapshot, serde_json::Error> {
    let document: Value = serde_json::from_str(&body)?;
    let domains = document
        .get("domains")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut shifts = document
        .get("key_trends")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut subs = document
        .get("sub_trends")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    // Composed before any fragment is built, so every response that carries a
    // shift row carries the same module list. `full_body` and the SEO index are
    // deliberately left alone: both read the raw publication, and neither
    // describes examples of a shift.
    for (rows, scope) in [
        (&mut shifts, innovations::Scope::KeyTrend),
        (&mut subs, innovations::Scope::SubTrend),
    ] {
        for row in rows.iter_mut() {
            let key = format!("{}:{}", scope.as_str(), string_field(row, "slug"));
            let items = innovations.get(&key);
            // A page composed from a `shift_module_overrides` row is exempt from
            // the visibility filter. `export.py` flags it, and the rule is
            // most-specific-wins: an editor who authored the whole list has
            // already decided what appears, and a sphere-wide flag must not
            // silently delete a section they placed on purpose.
            let authored = row
                .get("authored")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            let domain = string_field(row, "domain_id").to_owned();
            let modules = row
                .get_mut("modules")
                .and_then(Value::as_array_mut)
                .map(std::mem::take);
            // A row with no `modules` list at all only gains one if there is
            // something to put in it — the front end projects a minimal page
            // from the other fields when the key is absent.
            if let Some(mut modules) = modules {
                innovations::hydrate(&mut modules, scope, items);
                if !authored {
                    policy.apply(&mut modules, scope, &domain);
                }
                row["modules"] = Value::Array(modules);
            } else if items.is_some() {
                let mut modules = Vec::new();
                innovations::hydrate(&mut modules, scope, items);
                if !authored {
                    policy.apply(&mut modules, scope, &domain);
                }
                row["modules"] = Value::Array(modules);
            }
        }
    }
    let (shifts, subs) = (shifts, subs);
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
                    // The one fragment that renders the sphere's intro
                    // paragraph, so the only one that carries it.
                    "domain": domain_detail(domain, domain_shift_count),
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
                            "sub_shift": sub_shift_detail(sub),
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
    let (body, published) = row.ok_or_else(|| {
        AppError::public(
            StatusCode::NOT_FOUND,
            "not_found",
            "Map document not found.",
        )
    })?;
    // The publication's timestamp alone is not the identity of a response any
    // more: two snapshots of the same document can differ in their innovations.
    // Folding the innovations revision in is what keeps `weak_etag` honest, so a
    // client holding `If-None-Match` is told when a page has changed.
    // …and in which modules a sphere shows. Flipping a visibility flag has to
    // move every affected ETag too, or a client holding `If-None-Match` keeps a
    // page whose composition has changed.
    let innovations = innovations::load(&s.pool).await;
    let policy = module_policy::load(&s.pool).await;
    let version = format!(
        "{published}|i{:016x}|p{:016x}",
        innovations.revision, policy.revision
    );
    let snapshot = build_snapshot(body, &version, &innovations.by_shift, &policy)
        .map(Arc::new)
        .map_err(|error| AppError::internal(format!("invalid published map JSON: {error}")))?;
    report_art_coverage(&snapshot);
    Ok(snapshot)
}

/// Warn when the published map names shifts this image has no artwork for.
///
/// The two halves of the site are versioned separately: editorial content is a
/// row in Postgres, artwork is compiled into the frontend build. A synthesis
/// that renames a shift moves its slug — the exporter re-derives every slug from
/// the name — and the artwork, which is keyed by slug, is left behind. The page
/// then falls back to its sphere gradient, which looks deliberate, so nobody
/// reports it.
///
/// This is checked here rather than in CI because CI cannot see it: the build
/// has no database, so `check-heroes` can only compare the manifest against the
/// directory, and both of those come out of the same generator run. It is
/// checked at runtime rather than at startup because the failure arrives with
/// the *data*, not with the deploy — the weekly cron republishes into a
/// container nobody redeployed, and this is the moment that becomes visible.
///
/// A warning, not an error. Missing artwork is cosmetic; failing the map
/// refresh over it would take a working site down to protect a background
/// image.
fn report_art_coverage(snapshot: &MapSnapshot) {
    let dir = Path::new(&static_dir()).join("shift/heroes");
    if !dir.is_dir() {
        return; // API-only deploy, or the static build is absent — not this check's business.
    }
    let missing: Vec<&str> = snapshot
        .site_index
        .shift_slugs
        .iter()
        .filter(|slug| !dir.join(format!("{slug}.svg")).is_file())
        .map(String::as_str)
        .collect();
    let total = snapshot.site_index.shift_slugs.len();
    if missing.is_empty() {
        tracing::info!(shifts = total, "all published shifts have hero artwork");
        return;
    }
    tracing::warn!(
        missing = missing.len(),
        of = total,
        slugs = %missing.iter().take(8).copied().collect::<Vec<_>>().join(", "),
        "published shifts have no hero artwork in this build — a rename since the \
         last art regeneration. Run `npm run heroes` against this origin, then \
         `npm run heroes:og`, commit and redeploy."
    );
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

// ── shared secret comparison ─────────────────────────────────────────────────

/// Constant-time byte comparison, so token checks don't leak length or prefix
/// via timing. Avoids pulling in a crate for ~10 lines.
fn secret_eq(a: &str, b: &str) -> bool {
    let (a, b) = (a.as_bytes(), b.as_bytes());
    if a.len() != b.len() {
        return false;
    }
    a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
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
            "/society",
            "/society/sovereign-collapse",
            "/society/sovereign-collapse/threshold-blindness",
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

    /// A publication with nothing linked to it — the state of every page before
    /// the first innovation is curated onto one.
    fn no_innovations() -> innovations::ByShift {
        innovations::ByShift::new()
    }

    /// No editor rows, so the contract default governs — the production state.
    /// `sample_map` only carries `dek` and `lede`, which the default shows on
    /// every sphere, so this changes nothing for the tests that just need a
    /// snapshot. `a_non_consumer_key_shift_loses_its_commercial_modules` is the
    /// one that exercises the filter.
    fn default_policy() -> module_policy::Policy {
        module_policy::Policy::default()
    }

    #[test]
    fn route_snapshot_has_distinct_scoped_documents_and_etags() {
        let snapshot = build_snapshot(
            sample_map(),
            "2026-08-02 14:00:00+00",
            &no_innovations(),
            &default_policy(),
        )
        .unwrap();
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

        // The client will not render a sub-shift whose slug does not match the
        // last URL segment. The publication stores `parent/child`; the fragment
        // must serve `child`, exactly as the sibling summaries do. Serving the
        // compound form here rendered all 281 sub-shift pages "unavailable".
        assert_eq!(sub_json["sub_shift"]["slug"], "proof-of-human");
        assert_eq!(sub_json["siblings"][0]["slug"], "proof-of-human");
        assert!(sub_json["sub_shift"]["modules"].is_array());
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

    /// One innovation linked to the sample publication's key shift.
    fn one_innovation() -> innovations::ByShift {
        let mut by_shift = innovations::ByShift::new();
        by_shift.insert(
            "key_trend:trust-machines".into(),
            json!([{
                "title": "Proof-of-human badge",
                "brand": "Acme",
                "description": "A verification product.",
                "url": "https://example.com/acme",
                "image": "/api/innovations/7/cover-image?v=0123456789ab"
            }]),
        );
        by_shift
    }

    #[test]
    fn a_linked_innovation_reaches_the_shift_fragment() {
        let snapshot = build_snapshot(
            sample_map(),
            "2026-08-02 14:00:00+00|i0",
            &one_innovation(),
            &default_policy(),
        )
        .unwrap();
        let shift: Value =
            serde_json::from_str(&snapshot.routes.get("society/trust-machines").unwrap().body)
                .unwrap();
        let modules = shift["shift"]["modules"].as_array().unwrap();
        let module = modules
            .iter()
            .find(|m| m["type"] == "innovations")
            .expect("the linked innovation must appear as a module");
        assert_eq!(module["data"]["items"][0]["title"], "Proof-of-human badge");
        // Same-origin, so `img-src 'self'` allows it. An upstream URL would not
        // render at all.
        assert!(module["data"]["items"][0]["image"]
            .as_str()
            .unwrap()
            .starts_with("/api/innovations/"));

        // The sub-shift was not linked, so its page is untouched.
        let sub: Value = serde_json::from_str(
            &snapshot
                .routes
                .get("society/trust-machines/proof-of-human")
                .unwrap()
                .body,
        )
        .unwrap();
        assert!(!sub["sub_shift"]["modules"]
            .as_array()
            .unwrap()
            .iter()
            .any(|m| m["type"] == "innovations"));
    }

    /// The failure this guards is silent: a reader holding `If-None-Match` from
    /// before an innovation was linked would be told `304` and keep the old page
    /// indefinitely, because the publication's own timestamp had not moved.
    #[test]
    fn linking_an_innovation_changes_every_affected_etag() {
        let published = "2026-08-02 14:00:00+00";
        let before = build_snapshot(
            sample_map(),
            &format!("{published}|i0"),
            &no_innovations(),
            &default_policy(),
        )
        .unwrap();
        let after = build_snapshot(
            sample_map(),
            &format!("{published}|i1cf2"),
            &one_innovation(),
            &default_policy(),
        )
        .unwrap();
        let route = "society/trust-machines";
        assert_ne!(
            before.routes.get(route).unwrap().etag,
            after.routes.get(route).unwrap().etag
        );
    }

    /// A publication carries every module; the sphere decides which are shown.
    /// This is the end-to-end proof, through `build_snapshot`, that the filter
    /// runs and that `authored` exempts a page from it.
    #[test]
    fn a_non_consumer_key_shift_loses_its_commercial_modules() {
        let map = json!({
            "updated": "2026-08-02",
            "domains": [{ "id": "society", "name": "Society", "label": "AI × Society",
                          "short_description": "d", "description": "D",
                          "horizon": "2028", "key_trend_ids": ["kt-1"] }],
            "key_trends": [{
                "id": "kt-1", "domain_id": "society", "slug": "trust-machines",
                "name": "Trust Machines", "subtitle": "A shift", "velocity": "rising",
                "read_time": "4 min read", "sub_trend_ids": [],
                "modules": [
                    { "type": "dek", "data": { "text": "A shift" } },
                    { "type": "pull_quote", "data": { "quote": "A line" } },
                    { "type": "industries", "data": { "items": [] } },
                    { "type": "territories", "data": { "items": [] } },
                ],
            }],
            "sub_trends": [],
            "synthesis_insights": [],
        })
        .to_string();

        let snapshot =
            build_snapshot(map.clone(), "v", &no_innovations(), &default_policy()).unwrap();
        let body: Value =
            serde_json::from_str(&snapshot.routes.get("society/trust-machines").unwrap().body)
                .unwrap();
        let types: Vec<&str> = body["shift"]["modules"]
            .as_array()
            .unwrap()
            .iter()
            .map(|m| m["type"].as_str().unwrap())
            .collect();
        assert_eq!(
            types,
            ["dek"],
            "society keeps only the modules the design renders"
        );

        // `authored` is stripped from the response, not merely ignored.
        assert!(body["shift"].get("authored").is_none());
    }

    #[test]
    fn an_authored_page_is_never_filtered() {
        let map = json!({
            "updated": "2026-08-02",
            "domains": [{ "id": "society", "name": "Society", "label": "AI × Society",
                          "short_description": "d", "description": "D",
                          "horizon": "2028", "key_trend_ids": ["kt-1"] }],
            "key_trends": [{
                "id": "kt-1", "domain_id": "society", "slug": "trust-machines",
                "name": "Trust Machines", "subtitle": "A shift", "velocity": "rising",
                "read_time": "4 min read", "sub_trend_ids": [],
                // An editor placed these deliberately, via shift_module_overrides.
                "authored": true,
                "modules": [
                    { "type": "dek", "data": { "text": "A shift" } },
                    { "type": "industries", "data": { "items": [] } },
                ],
            }],
            "sub_trends": [],
            "synthesis_insights": [],
        })
        .to_string();

        let snapshot = build_snapshot(map, "v", &no_innovations(), &default_policy()).unwrap();
        let body: Value =
            serde_json::from_str(&snapshot.routes.get("society/trust-machines").unwrap().body)
                .unwrap();
        let types: Vec<&str> = body["shift"]["modules"]
            .as_array()
            .unwrap()
            .iter()
            .map(|m| m["type"].as_str().unwrap())
            .collect();
        assert_eq!(
            types,
            ["dek", "industries"],
            "an override outranks the sphere rule"
        );
    }

    /// Mirrors `linking_an_innovation_changes_every_affected_etag`. The version
    /// string is built in `fetch_snapshot`; this pins that the policy revision is
    /// part of it, so flipping a flag is visible to a conditional request
    /// immediately rather than at the next weekly publication.
    #[test]
    fn flipping_a_visibility_flag_changes_every_affected_etag() {
        let published = "2026-08-02 14:00:00+00";
        let before = build_snapshot(
            sample_map(),
            &format!("{published}|i0|p{:016x}", 0),
            &no_innovations(),
            &module_policy::Policy::with_revision(0),
        )
        .unwrap();
        let after = build_snapshot(
            sample_map(),
            &format!("{published}|i0|p{:016x}", 0x9e37_79b9_u64),
            &no_innovations(),
            &module_policy::Policy::with_revision(0x9e37_79b9),
        )
        .unwrap();
        for route in ["", "society", "society/trust-machines"] {
            assert_ne!(
                before.routes.get(route).unwrap().etag,
                after.routes.get(route).unwrap().etag,
                "{route} kept its etag across a policy change",
            );
        }
    }

    #[test]
    fn matching_etag_returns_304_without_a_body() {
        let snapshot = build_snapshot(
            sample_map(),
            "version",
            &no_innovations(),
            &default_policy(),
        )
        .unwrap();
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

        let snapshot = build_snapshot(
            sample_map(),
            "version",
            &no_innovations(),
            &default_policy(),
        )
        .unwrap();
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
            curation_token: None,
            inspection_token: None,
            http: reqwest::Client::new(),
            snapshot: Arc::new(tokio::sync::RwLock::new(None)),
            refresh_lock: Arc::new(tokio::sync::Mutex::new(())),
            shell: Arc::from(""),
            origin: Arc::from(""),
            legacy_map_limiter: Arc::new(RateLimiter::per_minute(10, 2)),
            legacy_map_concurrency: Arc::new(tokio::sync::Semaphore::new(2)),
            // 120/min with a 30 burst was too tight for the thing it protects. A
            // reading route costs two calls (index + fragment), the response is a
            // slice of one cached document, and the bucket is keyed by IP — so a
            // room of people behind one office NAT shares it. Walking the map at a
            // normal pace tripped it on 120 of 310 routes in a crawl; the client
            // retries on Retry-After and recovers, so it showed as a stall rather
            // than an error, which is worse to debug and worse to demo.
            //
            // 600/min with a 150 burst still refuses a scraper and still bounds the
            // memory the bucket map can take, while leaving ordinary browsing —
            // including several people at once — nowhere near the ceiling.
            public_v1_limiter: Arc::new(RateLimiter::per_minute(600, 150)),
            ingest_limiter: Arc::new(RateLimiter::per_minute(60, 20)),
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
