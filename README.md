# Serious Shift

AGI consumer-intelligence platform. A Python pipeline ingests leading AGI
thinkers' sources and extracts structured claims/predictions into Postgres; a
Rust API serves them; a Next.js app presents the trend map, thinker profiles,
daily briefing, and keynote.

New here? Read **[ARCHITECTURE.md](ARCHITECTURE.md)** — how it fits together, why,
and where to change things.

Monorepo of independently-owned blocks — **each directory's `README.md` is the
source of truth for that block:**

| Block | What | Docs |
|---|---|---|
| `apps/frontend` | Next.js + Tailwind UI | [apps/frontend/README.md](apps/frontend/README.md) |
| `apps/backend` | Rust (axum + sqlx) read API | [apps/backend/README.md](apps/backend/README.md) |
| `apps/pipeline` | Python scrape → extract → score → map/keynote | [apps/pipeline/README.md](apps/pipeline/README.md) |
| `packages/db` | Postgres schema, migrations, ETL | [packages/db/README.md](packages/db/README.md) |

All data — claims, predictions, the trend map, thinker bios/images, and the
scrape source manifest — lives in Postgres; there are no data JSON files.
`serious-shift.db` is the legacy SQLite import source (untracked, local only).

## Architecture

```
   apps/pipeline ──writes──►  Postgres (packages/db)  ◄──reads── apps/backend ──HTTP──► apps/frontend
   (batch, scheduled)         (source of truth)        (read API + /personalize)        (Next.js)
```
The data contract is the DB schema (`packages/db`); the API contract is the
backend's JSON shapes, which the frontend consumes via `NEXT_PUBLIC_API_BASE`.

## Local quickstart (end-to-end)

```bash
# 1. Postgres + data
cd packages/db && docker compose up -d
export DATABASE_URL='postgres://serious:serious@localhost:5432/serious_shift?sslmode=disable'
DBMATE_MIGRATIONS_DIR=./migrations dbmate up
pip install "psycopg[binary]"
python etl/sqlite_to_postgres.py --sqlite ../../serious-shift.db --truncate
python etl/verify_parity.py     --sqlite ../../serious-shift.db     # "lossless ✓"

# 2. Pipeline
cd ../../apps/pipeline && pip install -e ".[dev]" && pytest
(cd ../.. && python -m serious_shift_pipeline.tools.status)

# 3. Backend  (needs Rust)
cd ../backend && cargo run                                          # :8080

# 4. Frontend (needs Node 22)
cd ../frontend && cp .env.example .env.local && npm install && npm run dev   # :3000
```

## Deploy (free tier)

| Block | Host | Guide |
|---|---|---|
| Database | **Neon** (free Postgres) | [packages/db/README.md](packages/db/README.md#deploy-a-free-postgres--neon) |
| Backend | **Fly.io** / Render / Koyeb (Docker) | [apps/backend/README.md](apps/backend/README.md#deploy-free-tier) |
| Frontend | **Vercel** (Hobby) | [apps/frontend/README.md](apps/frontend/README.md#deploy-free-tier--vercel) |

Order: create the Neon DB and load it → deploy the backend with that
`DATABASE_URL` → deploy the frontend with `NEXT_PUBLIC_API_BASE` = the backend URL.

## CI

`.github/workflows/` has one workflow per block (db, pipeline, backend, frontend),
each triggered on changes to its path.
