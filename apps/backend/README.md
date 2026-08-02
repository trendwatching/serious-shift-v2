# backend — Rust API + web server

Serves the Serious Shift data over HTTP from Postgres, **and** the frontend bundle
built from [`../frontend`](../frontend). One process, one origin: the browser makes
no cross-origin request and there is no proxy hop.

Minimal by design: each read endpoint is one SQL string in [`src/sql.rs`](src/sql.rs)
that lets Postgres build the JSON (`json_agg(row_to_json(...))`); the handlers in
[`src/main.rs`](src/main.rs) are a line each.

Stack: Rust · axum · sqlx (Postgres).

## Endpoints

The four inspection endpoints (`/api/thinkers`, `/api/sources`, `/api/claims`,
`/api/predictions`) require `INSPECTION_TOKEN` and take `?limit=` — default 500,
ceiling 5000. Unbounded they
answered ~7-8 MB each, which on a public URL is a denial of service a handful
of concurrent requests wide. They have no UI contract; the app reads only the
route-scoped v1 map documents.

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
| `GET /api/v1/map/{domain}/{shift}` | one full key shift and five sub-shift summaries |
| `GET /api/v1/map/{domain}/{shift}/{subshift}` | one full sub-shift, parent context, and sibling summaries |
| `GET /api/map` | deprecated full trend map compatibility endpoint; rate and concurrency limited |
| `POST /api/innovations/ingest` | ingests one innovation → `innovations` table (idempotent on `source_innovation_id`). Requires `X-Ingest-Token`; **404 while `INGEST_TOKEN` is unset** |
| `GET /*` | canonical SPA routes deep-link; unknown routes and unmatched `/api/*` paths return real 404 responses |

## Configuration (env)

| Var | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Postgres connection string |
| `PORT` | no | default `8080` |
| `FRONTEND_ORIGIN` | **yes in release** | CORS allowlist (comma-separated). Release builds panic without it; debug builds allow any origin |
| `STATIC_DIR` | no | SPA bundle to serve, default `static` (the image sets `/srv/static`) |
| `INGEST_TOKEN` | only for `/api/innovations/ingest` | shared secret; route 404s while unset |
| `INSPECTION_TOKEN` | only for inspection endpoints | bearer token; endpoints 404 while unset |

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
- **`POST /api/innovations/ingest`** requires the `X-Ingest-Token` header to match
  `INGEST_TOKEN` (constant-time compare). While that var is unset the route 404s.
  The token is checked *before* the body is deserialised.
- **In-memory state** (rate limiter, caches) is per-instance. Move it to a shared
  KV store before scaling horizontally.
- Large lists (`/api/claims`) return whole — add pagination when needed.
