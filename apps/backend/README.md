# backend — Rust API + web server

Serves the Serious Shift data over HTTP from Postgres, **and** the frontend bundle
built from [`../frontend`](../frontend). One process, one origin: the browser makes
no cross-origin request and there is no proxy hop.

Minimal by design: each read endpoint is one SQL string in [`src/sql.rs`](src/sql.rs)
that lets Postgres build the JSON (`json_agg(row_to_json(...))`); the handlers in
[`src/main.rs`](src/main.rs) are a line each.

Stack: Rust · axum · sqlx (Postgres).

## Endpoints

The inspection endpoints (`/api/thinkers`, `/api/sources`, `/api/claims`,
`/api/predictions`, `/api/stats`, **and the deprecated full `/api/map`**) require
`Authorization: Bearer <INSPECTION_TOKEN>`. List routes take `?limit=` — default
500, ceiling 5000. Unbounded they
answered ~7-8 MB each, which on a public URL is a denial of service a handful
of concurrent requests wide. They have no UI contract; the app reads only the
route-scoped v1 map documents.

`/api/map` is on that list because the publication it serves *embeds the rows the
other endpoints gate*: unauthenticated it answered 4.4 MB carrying 193 thinkers
with `credibility_score`, `prediction_accuracy` and bios, plus 452 claims with
per-claim `thinker_credibility` and `consumer_implication`. Gating `/api/claims`
while leaving that open meant the token bought nothing — the same data was one
different URL away.

| Route | Returns |
|---|---|
| `GET /health` | `ok` — queries Postgres, so it fails when the DB is unreachable |
| `GET /api/thinkers` | thinkers + prediction/claim/source counts |
| `GET /api/sources` | sources ⋈ thinker |
| `GET /api/claims` | claims ⋈ thinker/source (ordered by `claim_weight`) |
| `GET /api/predictions` | predictions ⋈ thinker/source |
| `GET /api/stats` | aggregate counts |
| `GET /api/v1/map` | update timestamp, totals, and domain summaries |
| `GET /api/v1/map/{domain}` | domain metadata, key-shift summaries, and insights |
| `GET /api/v1/map/{domain}/{shift}` | one full key shift, key-shift siblings, and five sub-shift summaries |
| `GET /api/v1/map/{domain}/{shift}/{subshift}` | one full sub-shift, parent context, and sibling summaries |
| `GET /api/map` | deprecated full trend map; **operator-gated** (`INSPECTION_TOKEN`), rate and concurrency limited. No client reads it — the SPA uses the v1 fragments |
| `GET /api/v1/innovations` | the ingested corpus, newest first; keyset-paginated, filterable by `shift`/`tag`/`brand` |
| `GET /api/v1/innovations/{id}` | one full innovation record |
| `GET /api/innovations/{id}/cover-image` | the mirrored cover bytes, same-origin so the page's `img-src 'self'` allows them |
| `POST /api/innovations/ingest` | ingests one innovation (idempotent on `source_innovation_id`). Requires `X-Ingest-Token`; **404 while `INGEST_TOKEN` is unset** |
| `PUT /api/innovations/{id}/shifts` | replace the editor-curated innovation↔shift links. Requires `CURATION_TOKEN`; **404 while unset** |
| `DELETE /api/innovations/{id}/shifts/{scope}/{slug}` | remove one link |
| `GET /*` | canonical SPA routes deep-link; unknown routes and unmatched `/api/*` paths return real 404 responses |

The full contract for the innovations routes — request, responses, error codes,
idempotency — is [`docs/INNOVATIONS-API.md`](../../docs/INNOVATIONS-API.md).

## Configuration (env)

| Var | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Postgres connection string |
| `PORT` | no | default `8080` |
| `FRONTEND_ORIGIN` | **yes in release** | CORS allowlist (comma-separated). Release builds panic without it; debug builds allow any origin |
| `STATIC_DIR` | no | SPA bundle to serve, default `static` (the image sets `/srv/static`) |
| `INGEST_TOKEN` | only for `/api/innovations/ingest` | shared secret (`X-Ingest-Token`); route 404s while unset |
| `CURATION_TOKEN` | only for innovation↔shift curation | bearer token; routes 404 while unset. Separate from `INGEST_TOKEN` so the upstream credential cannot change a page |
| `INNOVATION_ASSET_HOSTS` | no | comma-separated hosts a cover image may be mirrored from; defaults to `tw-the-engine.up.railway.app` |
| `INSPECTION_TOKEN` | only for inspection endpoints | bearer token; endpoints (incl. `/api/map`) 404 while unset |
| `PUBLIC_ORIGIN` | no | absolute origin for canonical URLs and the sitemap; defaults to the first `FRONTEND_ORIGIN` entry |
| `RAILWAY_ENVIRONMENT_ID` | Railway-provided | when present, trust Railway `X-Forwarded-For`; otherwise use the socket peer |

## Run locally

```bash
export DATABASE_URL=postgres://serious:serious@localhost:5432/serious_shift
cargo run                       # listens on :8080
curl localhost:8080/api/stats
```

Build/lint: `cargo build --release` · `cargo clippy -- -D warnings` · `cargo fmt`.
CI (compile + a live curl smoke test against Postgres) is `.github/workflows/backend.yml`.

## Deploy

[`../../DEPLOY-RAILWAY.md`](../../DEPLOY-RAILWAY.md) is the current path. The
[`Dockerfile`](Dockerfile) is multi-stage and **builds from the repo root** — it
compiles the frontend bundle, compiles this crate (which embeds
`packages/prompts` via `include_str!`), and ships both in a slim runtime image:

```bash
docker build -f apps/backend/Dockerfile .     # from the repo root, not this dir
```

## Hardening

- **Map snapshots** parse one published document per version, then derive all
  route fragments, ETags, and SEO metadata together behind an async read lock.
  One refresh mutex prevents a cold-request stampede; a failed refresh keeps the
  previous in-memory snapshot serving.
- **Public v1 map routes** are limited to 120 requests/minute/client with burst
  30. Responses use per-route weak ETags, short cache/SWR headers, and Brotli or
  gzip compression. Unknown slugs return JSON 404s.
- **CORS** is restricted to `FRONTEND_ORIGIN` (comma-separated allowlist). A
  **release build refuses to start** without it — a misconfigured CORS policy
  should fail loudly, not serve `*` behind a log line. Debug builds still allow
  any origin so `cargo run` works.
- **Inspection auth** is constant-time and never logs credentials. Disabled
  inspection routes return 404; missing/invalid bearer credentials return 401.
- **The innovations write path** is the only place this service writes, and it is
  gated three ways: a constant-time shared-secret check before the body is parsed
  at all, a 60/min rate limit, and a 1 MB body cap. A route whose secret is unset
  returns 404 rather than 401, so it does not advertise itself.
- **Cover images are mirrored, never proxied on demand.** The fetcher accepts
  `https://` only, only hosts on `INNOVATION_ASSET_HOSTS`, with redirects
  disabled, a 10s timeout and a 5 MiB cap — a URL out of a request body is
  otherwise a request-forgery primitive aimed at Railway's private network.
  Serving the bytes from our own origin is also what satisfies `img-src 'self'`.
- **Security middleware** wraps the complete router, including static assets,
  SPA deep links and fallbacks. Valid routes return 200; unknown app paths render
  the accessible shell with HTTP 404 and noindex; unknown API/assets are ordinary
  404 responses. Public errors expose stable codes plus a request ID, while the
  detailed database error stays in structured server logs.
- **Legacy `/api/map`** is deprecated and constrained to 10 requests/minute,
  burst 2, and two concurrent responses. Route-scoped v1 is 120/minute, burst 30.
  All requests have a ten-second timeout.
- **In-memory state** (rate limiter, caches) is per-instance. Move it to a shared
  KV store before scaling horizontally.
- Inspection list pagination is deliberately capped at 5,000 rows per request.
