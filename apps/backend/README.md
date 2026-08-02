# backend — Rust API + web server

Serves the Serious Shift data over HTTP from Postgres, **and** the frontend bundle
built from [`../frontend`](../frontend). One process, one origin: the browser makes
no cross-origin request and there is no proxy hop.

Minimal by design: each read endpoint is one SQL string in [`src/sql.rs`](src/sql.rs)
that lets Postgres build the JSON (`json_agg(row_to_json(...))`); the handlers in
[`src/main.rs`](src/main.rs) are a line each.

Stack: Rust · axum · sqlx (Postgres).

## Endpoints

The four list endpoints (`/api/thinkers`, `/api/sources`, `/api/claims`,
`/api/predictions`) take `?limit=` — default 500, ceiling 5000. Unbounded they
answered ~7-8 MB each, which on a public URL is a denial of service a handful
of concurrent requests wide. They have no UI contract; the app only reads
`/api/map`.

| Route | Returns |
|---|---|
| `GET /health` | `ok` — queries Postgres, so it fails when the DB is unreachable |
| `GET /api/thinkers` | thinkers + prediction/claim/source counts |
| `GET /api/sources` | sources ⋈ thinker |
| `GET /api/claims` | claims ⋈ thinker/source (ordered by `claim_weight`) |
| `GET /api/predictions` | predictions ⋈ thinker/source |
| `GET /api/stats` | aggregate counts |
| `GET /api/map` | the assembled trend map (the pipeline writes it) — the only document the UI reads |
| `POST /api/innovations/ingest` | ingests one innovation → `innovations` table (idempotent on `source_innovation_id`). Requires `X-Ingest-Token`; **404 while `INGEST_TOKEN` is unset** |
| `GET /*` | the SPA. Unmatched paths return `index.html` so client-side routes deep-link; unmatched `/api/*` paths return a JSON 404 |

## Configuration (env)

| Var | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Postgres connection string |
| `PORT` | no | default `8080` |
| `FRONTEND_ORIGIN` | **yes in release** | CORS allowlist (comma-separated). Release builds panic without it; debug builds allow any origin |
| `STATIC_DIR` | no | SPA bundle to serve, default `static` (the image sets `/srv/static`) |
| `INGEST_TOKEN` | only for `/api/innovations/ingest` | shared secret; route 404s while unset |

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
