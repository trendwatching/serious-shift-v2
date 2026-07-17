# Deploying Serious Shift on Railway

One Railway **project** holds everything: a Postgres database plus three services
(backend, frontend, pipeline). Railway auto-deploys each service from this repo on
push; each service has its own **Root Directory** so the monorepo just works.

```
Railway project "serious-shift"
├── Postgres        (Railway plugin)            → DATABASE_URL
├── backend         (root: apps/backend, Docker) → public URL  e.g. backend.up.railway.app
├── frontend        (root: apps/frontend, Next)  → public URL  e.g. app.up.railway.app
└── pipeline        (root: apps/pipeline, cron)   → no public URL, runs on a schedule
```

## How GitHub deploy works here
Railway's "Deploy from GitHub repo" auto-builds and redeploys on every push. This
is a **monorepo**, so create **one service per app from the same repo**.

> **REQUIRED — set each service's Root Directory.** This is the #1 gotcha: if it's
> left at the repo root, the builder scans `./` (no single app there) and fails
> with *"could not determine how to build the app."* In each service →
> **Settings → Root Directory**, set:
> `apps/backend` · `apps/frontend` · `apps/pipeline`.

Once Root Directory is set, Railway reads that folder:
- `apps/backend`, `apps/pipeline` → their `railway.json` pins the **Dockerfile**
  builder (backend also sets healthcheck `/health`; pipeline sets the weekly
  **cron** `0 22 * * 0`, so you don't configure those by hand).
- `apps/frontend` → no Dockerfile → Railway auto-detects Next.js (`npm` build/start).

Also set each service's **Watch Paths** (e.g. `apps/backend/**`) so one app's change
doesn't rebuild the others. **Postgres is added separately** (a Railway database,
not from GitHub) and referenced as `${{Postgres.DATABASE_URL}}`.

> The **pipeline cron applies the database migrations automatically** on each run
> (idempotent, dbmate-compatible), so a fresh database is bootstrapped on the first
> run. Step 2 below is still the fastest way to stand the DB up immediately and to
> load the one-time historical data; the backend needs the schema present to serve.

## 0. Prerequisites
- A Railway account + the repo pushed to GitHub.
- Locally: `dbmate`, Python with `psycopg`, and the Railway CLI (`npm i -g @railway/cli`) for the one-time data load.

## 1. Postgres
New Project → **Add Postgres**. Railway creates it and exposes `DATABASE_URL`
(reference it from other services as `${{Postgres.DATABASE_URL}}`).

## 2. Schema + seed (one-time, from your machine — optional)
The pipeline cron applies migrations automatically, so this is only needed if you
want the schema up *before* the first cron run (e.g. so the backend serves data).
Grab the Postgres **public** connection string from the Postgres service → Connect.
```bash
export DATABASE_URL='postgres://…railway public url…'   # includes sslmode=require
cd packages/db
DBMATE_MIGRATIONS_DIR=./migrations dbmate up
# → 0001 creates the schema, 0002 seeds the thinker roster + scrape source manifest.
```
That's the whole bootstrap — no data import required. The pipeline then scrapes →
extracts claims → builds the map/keynote on its first run.

**Optional — import legacy SQLite data** (historical claims/predictions) instead of
scraping from scratch:
```bash
python etl/sqlite_to_postgres.py --sqlite ../../serious-shift.db --truncate
# (copies only tables/columns that still exist in the current schema)
cd ../.. && python -m serious_shift_pipeline.steps.generate_map_data --export-only
```

## 3. Backend service
New service → **Deploy from repo**.
- **Root Directory:** `apps/backend` (Railway uses the bundled `Dockerfile`).
- **Variables:**
  - `DATABASE_URL = ${{Postgres.DATABASE_URL}}`
  - `ANTHROPIC_API_KEY = sk-ant-…` (for `/api/personalize`)
  - `PORT = 8080` — pin it so the frontend can reach the backend over private
    networking at a known port (Railway otherwise assigns one).
- **Networking:** No public domain needed — the frontend proxies to it over the
  **private network** (`<service>.railway.internal`). Enable private networking
  (on by default within a project). `FRONTEND_ORIGIN`/CORS is no longer required
  because the browser never calls the backend directly (see step 4).

## 4. Frontend service
New service → **Deploy from repo**.
- **Root Directory:** `apps/frontend` (Nixpacks detects Next.js: `npm ci` → `npm run build` → `npm run start`).
- **How it talks to the backend:** the browser only ever calls the frontend's own
  origin (`/api/*`); Next.js proxies that to the backend server-side
  (`next.config.mjs` → `rewrites`). **No CORS, no public backend URL in the client.**
- **Variables:** `BACKEND_ORIGIN = http://backend.railway.internal:8080`
  (the backend service's private address + its `PORT`). Use the backend's public
  URL instead only if you don't want private networking.
  > `BACKEND_ORIGIN` is read by the Next **server**, not the browser — it is not a
  > `NEXT_PUBLIC_*` var and isn't inlined into the client bundle.
- **Networking:** Generate Domain (this is the only public domain users hit; point
  `www.yourdomain.com` here).

## 5. Pipeline (scheduled refresh)
New service → **Deploy from repo**.
- **Root Directory:** `apps/pipeline` (Railway uses the bundled `Dockerfile`).
- **Cron Schedule:** comes from `railway.json` (`0 22 * * 0`, Sundays 22:00 UTC).
  Railway runs the container on schedule, then the service sleeps.
- **Watch Paths:** `apps/pipeline/**` (a migration change is vendored into the
  package, so it lives under this path too).
- **Variables:** `DATABASE_URL = ${{Postgres.DATABASE_URL}}`, `ANTHROPIC_API_KEY`.
- On startup the run **applies any pending migrations** to `DATABASE_URL` (the
  migrations are bundled in the image), then scrapes → processes → (gated)
  regenerates. Pass `--skip-migrate` only if you manage the schema externally.
  A full refresh spends ~$60–100 of Anthropic credits; the run is cost-guarded
  and gates the expensive map/keynote steps on new claims.

## 6. Verify
- `https://<backend-domain>/health` → `ok`; `/api/stats` → JSON counts.
- `https://<frontend-domain>` → map/thinkers/keynote render (data from the API).
- Trigger the pipeline once from the dashboard ("Run now") and watch logs.

## Notes
- Use Railway **reference variables** (`${{Postgres.DATABASE_URL}}`) so the DB URL
  is never copied around; rotate the key in one place.
- Free tier sleeps idle services (cold start on first hit) and has monthly usage
  limits — fine for a demo; upgrade for steady traffic.
- CORS, the `/api/personalize` caps, and `PORT` binding are already production-set
  (see `apps/backend`). Remaining follow-ups live in [ARCHITECTURE.md](ARCHITECTURE.md#7-known-gaps--follow-ups).
