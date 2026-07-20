# backend — Rust read API

Serves the Serious Shift data over HTTP from Postgres. Minimal by design: each
read endpoint is one SQL string in [`src/sql.rs`](src/sql.rs) that lets Postgres
build the JSON (`json_agg(row_to_json(...))`); the handlers in
[`src/main.rs`](src/main.rs) are a line each.

Stack: Rust · axum · sqlx (Postgres) · reqwest (for `/api/personalize`).

## Endpoints

| Route | Returns |
|---|---|
| `GET /health` | `ok` |
| `GET /api/thinkers` | thinkers + prediction/claim/source counts |
| `GET /api/sources` | sources ⋈ thinker |
| `GET /api/claims` | claims ⋈ thinker/source (ordered by `claim_weight`) |
| `GET /api/predictions` | predictions ⋈ thinker/source |
| `GET /api/concepts` `/api/tensions` `/api/disagreements` `/api/claim_concepts` | reference data |
| `GET /api/stats` | aggregate counts |
| `GET /api/map` `/api/keynote` `/api/daily` | whole-document blobs (the pipeline writes these) |
| `POST /api/personalize` | rewrites keynote sections for an industry via Claude |
| `POST /api/innovations/ingest` | ingests one innovation from the Innovation database → `innovations` table (idempotent on `source_innovation_id`); `ok`/200, 500 on failure |

## Configuration (env)

| Var | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Postgres connection string |
| `PORT` | no | default `8080` |
| `FRONTEND_ORIGIN` | prod | CORS allowlist (comma-separated origins); unset = any origin (dev only) |
| `ANTHROPIC_API_KEY` | only for `/api/personalize` | server-side only |

## Run locally

```bash
export DATABASE_URL=postgres://serious:serious@localhost:5432/serious_shift
cargo run                       # listens on :8080
curl localhost:8080/api/stats
```

Build/lint: `cargo build --release` · `cargo clippy -- -D warnings` · `cargo fmt`.
CI (compile + a live curl smoke test against Postgres) is `.github/workflows/backend.yml`.

## Deploy (free tier)

You need a Postgres first — see [`../../packages/db/README.md`](../../packages/db/README.md)
for creating a free **Neon** database, running migrations, and loading data. Grab
its connection string (`DATABASE_URL`, includes `?sslmode=require`).

A multi-stage [`Dockerfile`](Dockerfile) is provided; it works on any container host.

### Option A — Fly.io (recommended)

```bash
# one-time: install flyctl, then from apps/backend/
fly launch --no-deploy            # uses the bundled fly.toml; pick a unique app name
fly secrets set DATABASE_URL="postgres://...neon...?sslmode=require"
fly secrets set ANTHROPIC_API_KEY="sk-..."        # optional (personalize)
fly deploy
fly open                          # https://<app>.fly.dev/health  -> ok
```
`min_machines_running = 0` in `fly.toml` scales to zero when idle (free-friendly;
first request after idle has a cold start).

### Option B — Render (no card for free web services)

New → **Web Service** → connect the repo, then:
- Root Directory: `apps/backend` · Runtime: **Docker**
- Health Check Path: `/health`
- Env: `DATABASE_URL`, `ANTHROPIC_API_KEY`

Render's free web services spin down after ~15 min idle (cold start on wake).

### Option C — Koyeb

Create a Docker service from the repo, Dockerfile path `apps/backend/Dockerfile`,
set the same env vars, expose port `8080`.

After deploying, set the frontend's `NEXT_PUBLIC_API_BASE` to the backend URL
(see [`../frontend/README.md`](../frontend/README.md)).

## Hardening
- **CORS** is restricted to `FRONTEND_ORIGIN` (comma-separated allowlist); unset
  falls back to any-origin with a logged warning (dev only) — set it in prod.
- **`/api/personalize`** caps the request (≤ 20 sections, industry ≤ 100 chars,
  64 KB body). It still has no per-IP rate limit or result cache — add those
  (e.g. via a KV store) before heavy public exposure, since each call spends
  Anthropic credits.
- Large lists (`/api/claims`) return whole — add pagination when needed.
