# Serious Shift

AGI consumer-intelligence platform. A Python pipeline ingests leading AGI
thinkers' sources and extracts structured claims/predictions into Postgres; a
Rust API serves them, and the same binary serves the React app that presents the
trend map.

New here? Read **[ARCHITECTURE.md](ARCHITECTURE.md)** — how it fits together, why,
and where to change things.

Monorepo of independently-owned blocks — **each directory's `README.md` is the
source of truth for that block:**

| Block | What | Docs |
|---|---|---|
| `apps/frontend` | React + Tailwind UI (static export, served by the backend) | [apps/frontend/README.md](apps/frontend/README.md) |
| `apps/backend` | Rust (axum + sqlx) read API | [apps/backend/README.md](apps/backend/README.md) |
| `apps/pipeline` | Python scrape → extract → score → map | [apps/pipeline/README.md](apps/pipeline/README.md) |
| `packages/db` | Postgres schema, migrations, ETL | [packages/db/README.md](packages/db/README.md) |

All data — claims, predictions, the trend map, thinker bios/images, and the
scrape source manifest — lives in Postgres; there are no data JSON files.
`serious-shift.db` is the legacy SQLite import source (untracked, local only).

## Architecture

```
   apps/pipeline ──writes──►  Postgres (packages/db)  ◄──reads── apps/backend ──serves──► browser
   (weekly cron)              (source of truth)        (read API + the built SPA)
```
The data contract is the DB schema (`packages/db`); the API contract is the
backend's JSON shapes, which the frontend consumes from the same origin (`/api/*`).

## Local quickstart (end-to-end)

```bash
# 1. Postgres + data
cd packages/db && docker compose up -d
export DATABASE_URL='postgres://serious:serious@localhost:5432/serious_shift?sslmode=disable'
DBMATE_MIGRATIONS_DIR=./migrations dbmate up
pip install "psycopg[binary]"
python etl/sqlite_to_postgres.py --sqlite ../../serious-shift.db --truncate
python etl/verify_parity.py     --sqlite ../../serious-shift.db     # "lossless ✓"

# 2. Pipeline — two independently triggerable stages
cd ../../apps/pipeline
pip install --require-hashes -r requirements-dev.lock
pip install --no-deps --no-build-isolation -e .
pytest
(cd ../.. && python -m serious_shift_pipeline.tools.status)
(cd ../.. && python -m serious_shift_pipeline.run all --dry-run)   # plan only
# python -m serious_shift_pipeline.run ingest       # scrape -> ... -> evaluate
# python -m serious_shift_pipeline.run synthesize   # rebuild the trend map

# 3. Backend  (needs Rust)
cd ../backend && cargo run                                          # :8080

# 4. Frontend (needs Node 22)
# Dev server with hot reload, proxying /api to the backend on :8080:
cd ../frontend && npm install && npm run dev                        # :3000
# Or build the static bundle and let the backend serve it on :8080 (what prod does):
npm run build && STATIC_DIR=$PWD/out cargo run --manifest-path ../backend/Cargo.toml
```

## Deploy

[DEPLOY-RAILWAY.md](DEPLOY-RAILWAY.md) is the current path: Postgres plus
**three application services** — `backend` (Rust API + built SPA), `pipeline`
(Sunday ingest), and `synthesize` (Monday publication). Both application images
build from the repo root so they can copy `packages/` in.

## CI

`.github/workflows/` has one workflow per block plus an always-on governance
workflow. Every block workflow is triggered by relevant root Railway configuration.
High/critical dependency findings block; temporary waivers must be named, owned,
justified, and expiring in `security/audit-waivers.json`. Third-party Actions are
pinned to immutable commits and jobs have read-only permissions and timeouts.
