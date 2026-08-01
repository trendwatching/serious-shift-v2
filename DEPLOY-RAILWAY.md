# Deploying Serious Shift on Railway

One Railway **project** holds everything: a Postgres database plus **two** services.
The web app is served by the backend binary, so there is no separate Node service.

```
Railway project "serious-shift"
├── Postgres   (Railway plugin)          → DATABASE_URL
├── web        (Docker, apps/backend)    → public URL — serves the SPA *and* /api/*
└── pipeline   (Docker, apps/pipeline)   → no public URL, weekly cron
```

## How GitHub deploy works here

Railway auto-builds and redeploys on every push. Both services build from **this
repo with the repo root as the build context** — the images copy `packages/` in,
which is the single source of truth for migrations, prompts and contracts.

> **REQUIRED — leave Root Directory empty (the repo root).** Each service instead
> points at its own config file via **Settings → Config-as-code**:
>
> | Service  | Config path              | Dockerfile                |
> |----------|--------------------------|---------------------------|
> | web      | `railway.backend.json`   | `apps/backend/Dockerfile` |
> | pipeline | `railway.pipeline.json`  | `apps/pipeline/Dockerfile`|
>
> Setting Root Directory to `apps/backend` (as an earlier revision did) breaks the
> build: the Dockerfile copies `packages/`, which is outside that directory.

Set **Watch Paths** so one app's change doesn't rebuild the other:
- web → `apps/backend/**`, `apps/frontend/**`, `packages/prompts/**`
- pipeline → `apps/pipeline/**`, `packages/**`

**Postgres is added separately** (a Railway database, not from GitHub) and
referenced as `${{Postgres.DATABASE_URL}}`.

> The **pipeline cron applies database migrations automatically** on each run
> (idempotent, dbmate-compatible), so a fresh database bootstraps itself. Step 2
> is still the fastest way to stand the DB up immediately — the backend needs the
> schema present to serve.

## 0. Prerequisites
- A Railway account + the repo pushed to GitHub.
- Locally: `dbmate`, Python with `psycopg`, and the Railway CLI (`npm i -g @railway/cli`) for the one-time data load.

## 1. Postgres
New Project → **Add Postgres**. Railway creates it and exposes `DATABASE_URL`
(reference it from other services as `${{Postgres.DATABASE_URL}}`).

## 2. Schema + seed (one-time, from your machine — optional)
The pipeline cron applies migrations automatically, so this is only needed if you
want the schema up *before* the first cron run. Grab the Postgres **public**
connection string from the Postgres service → Connect.
```bash
export DATABASE_URL='postgres://…railway public url…'   # includes sslmode=require
cd packages/db
DBMATE_MIGRATIONS_DIR=./migrations dbmate up
# → one baseline migration: full schema + thinker roster + scrape source manifest.
```
That's the whole bootstrap — no data import required. The pipeline then scrapes →
extracts claims → builds the map on its first run.

> **Upgrading a database that predates the migration squash?** It still has rows
> `0001`–`0008` in `schema_migrations` and must be reconciled once before you
> deploy. The pipeline refuses to run against an un-reconciled database rather
> than half-applying. See `packages/db/README.md#baseline-squash`.

**Optional — import legacy SQLite data** (historical claims/predictions) instead of
scraping from scratch:
```bash
python etl/sqlite_to_postgres.py --sqlite ../../serious-shift.db --truncate
# (copies only tables/columns that still exist in the current schema; the
#  seeded scrape manifest is preserved across the truncate and re-keyed)
python etl/verify_parity.py --sqlite ../../serious-shift.db
cd ../.. && python -m serious_shift_pipeline.mapgen.cli --export-only
```

## 3. Web service (API + SPA)
New service → **Deploy from repo**.
- **Config-as-code path:** `railway.backend.json`. Root Directory stays empty.
- The image builds the frontend (`next build` → static export) and the Rust
  binary, then serves the export from the same process as `/api/*`. Same origin,
  so no CORS on the hot path and no proxy hop.
- **Variables:**
  - `DATABASE_URL = ${{Postgres.DATABASE_URL}}`
  - `FRONTEND_ORIGIN = https://<your-domain>` — **required.** A release build
    refuses to start without it rather than allowing every origin.
  - `ANTHROPIC_API_KEY = sk-ant-…` (only for `/api/personalize`)
  - `INGEST_TOKEN = <random secret>` — required to enable
    `POST /api/innovations/ingest`; the route returns 404 while unset.
  - `PERSONALIZE_DAILY_CALL_CAP` (optional, default 500) — hard daily ceiling on
    Anthropic calls from `/api/personalize`.
  - `PORT = 8080` (optional; the image defaults to it)
- **Networking:** Generate Domain. This is the only public domain users hit.

## 4. Pipeline (scheduled refresh)
New service → **Deploy from repo**.
- **Config-as-code path:** `railway.pipeline.json`. Root Directory stays empty.
- **Cron Schedule:** comes from that file (`0 22 * * 0`, Sundays 22:00 UTC).
  Railway runs the container on schedule, then the service sleeps.
- **Variables:** `DATABASE_URL = ${{Postgres.DATABASE_URL}}`, `ANTHROPIC_API_KEY`.
  - `SS_ALERT_WEBHOOK` — **set this.** Cost and failure alerts POST here
    (Slack/Discord/ntfy all accept the payload). Without it alerts only reach
    stdout, and the previous macOS-only implementation reached nothing at all.
  - `SS_BUDGET_TOTAL_USD` (default 35) — hard ceiling; the run *aborts* past it.
  - `SS_COST_ALERT_USD` (default 25) — notify threshold.
  - `SS_DISABLE_BATCH=1` — opt out of the Batch API (2x the cost; only for
    debugging, since batches take minutes to hours to return).
- On startup the run **applies any pending migrations**, then scrapes → processes
  → (gated) regenerates the map. Pass `--skip-migrate` if you manage the schema
  externally. A full refresh spends roughly **$8–9** of Anthropic credits with
  batching enabled; the run is budget-guarded and gates the expensive map regen
  on new claims having landed.

## 5. Verify
- `https://<domain>/health` → `ok` (it queries Postgres, so it goes red if the DB does).
- `https://<domain>/api/map` → the trend-map JSON; `/api/stats` → counts.
- `https://<domain>/` → the app renders; a deep link like `/map/society` loads directly.
- `https://<domain>/api/nonsense` → `404 {"error":"no such endpoint"}` (not HTML).
- Trigger the pipeline once from the dashboard ("Run now") and watch logs.

## 6. Shift modules (the editorial page content)

A shift page is an ordered list of **modules** (`{type, data}`) rather than a fixed
set of sections, so its composition is data. Generated modules live in
`domain_key_trends.modules` / `domain_sub_trends.modules`; editor-authored ones live
in `shift_module_overrides` and **survive the weekly rebuild** (which
`TRUNCATE … RESTART IDENTITY CASCADE`s the shift tables — hence a separate table,
keyed by URL slug rather than by row id).

Install the Railway CLI once: `npm i -g @railway/cli && railway link`. `railway run`
injects a service's env — including `DATABASE_URL` — into a **local** process, so it
talks to the Railway Postgres.

```bash
# 1. Apply the migration (idempotent; shares dbmate's schema_migrations table).
railway run --service pipeline python -m serious_shift_pipeline.core.migrate

# 2. Generate the modules for the shifts already in the database.
#    Two Claude calls per shift (~$5–15 total). Does NOT re-scrape or re-cluster,
#    and does not reset the shift tables, so slugs — and any overrides — still match.
railway run --service pipeline python -m serious_shift_pipeline.mapgen.cli --editorial-only

# 3. Check the served document actually carries modules.
railway run --service pipeline python -c "
from serious_shift_pipeline.core import db; import json
with db.connect() as c:
    doc = c.execute(\"SELECT body FROM documents WHERE key='map'\").fetchone()['body']
    kts = doc['key_trends']
    print(f'{len(kts)} shifts, {sum(len(k.get(\"modules\") or []) for k in kts)} modules')
    print('example:', [m['type'] for m in (kts[0].get('modules') or [])])"
```
Then open a shift on the public frontend. The backend caches documents for 60 s.

The weekly cron (`0 22 * * 0`) regenerates modules as part of its normal run — no
extra scheduling needed.

### Adding or removing a module by hand

Seed an override from what's already generated, then edit it. Full-replacement
semantics: an enabled override wins outright for that shift.

```sql
-- start from the generated list ('cognitive-erosion' is the URL slug you see
-- at /map/society/cognitive-erosion)
INSERT INTO shift_module_overrides (scope, slug, modules, note)
SELECT 'key_trend', 'cognitive-erosion', modules, 'hand-edited'
FROM domain_key_trends WHERE modules IS NOT NULL AND slug LIKE '%cognitive-erosion%'
ON CONFLICT (scope, slug) DO UPDATE SET modules = EXCLUDED.modules, updated_at = now();

-- drop a section
UPDATE shift_module_overrides SET modules = (
  SELECT jsonb_agg(m) FROM jsonb_array_elements(modules) m WHERE m->>'type' <> 'industries'
), updated_at = now() WHERE scope='key_trend' AND slug='cognitive-erosion';

-- append an editor-written section
UPDATE shift_module_overrides SET modules = modules || jsonb_build_object(
  'type','rich_text','data', jsonb_build_object('heading','Editor’s note','body','…')
), updated_at = now() WHERE scope='key_trend' AND slug='cognitive-erosion';

-- reordering is just reordering the array; revert to generated by deleting the row
DELETE FROM shift_module_overrides WHERE scope='key_trend' AND slug='cognitive-erosion';
```
Republish with `railway run --service pipeline python -m
serious_shift_pipeline.mapgen.cli --export-only` (free, no API calls).
The export prints a warning for any override that matched no shift — normally that
means the shift was renamed, so the slug moved.

Some modules are **derived at export**, not generated by the model: `voices`
(thinker attribution), `evidence` (claims joined to a sub-shift), `related_shifts`
(interrelatedness edges), plus the domain sheet's synthesis block. They cost no
model spend, so `--export-only` alone refreshes them after a schema or data change.

Module types and their `data` shapes: [packages/contracts/shift_modules.json](packages/contracts/shift_modules.json). Adding a
new type means declaring it there, emitting it from `kt_modules`/`st_modules` in
`mapgen/modules.py`, and registering a component in
`apps/frontend/src/shift/modules.jsx` — the front end skips types it doesn't know,
so the backend can ship one first. `test_shift_modules_contract.py` fails if the
three drift apart.

## Notes
- Use Railway **reference variables** (`${{Postgres.DATABASE_URL}}`) so the DB URL
  is never copied around; rotate the key in one place.
- Free tier sleeps idle services (cold start on first hit) and has monthly usage
  limits — fine for a demo; upgrade for steady traffic.
- CORS, the `/api/personalize` caps, and `PORT` binding are already production-set
  (see `apps/backend`). Remaining follow-ups live in [ARCHITECTURE.md](ARCHITECTURE.md#7-known-gaps--follow-ups).
