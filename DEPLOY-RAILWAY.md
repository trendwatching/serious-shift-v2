# Deploying Serious Shift on Railway

One Railway **project** holds everything: a Postgres database plus **three**
services. The web app is served by the backend binary, so there is no separate
Node service.

```
Railway project "serious-shift"
├── Postgres     (Railway plugin)          → DATABASE_URL
├── backend      (Docker, apps/backend)    → public URL — serves the SPA *and* /api/*
├── pipeline     (Docker, apps/pipeline)   → cron: `run ingest`     (Sun 22:00 UTC)
└── synthesize   (Docker, apps/pipeline)   → cron: `run synthesize` (Mon 02:00 UTC)
```

Ingest and synthesis are separate services from one image because they fail,
cost and schedule differently: a broken scrape should not block a map rebuild,
and re-running synthesis for a prompt change should not re-scrape 120 sources.
Either can be triggered on its own.

## How GitHub deploy works here

Railway auto-builds and redeploys on every push. Both services build from **this
repo with the repo root as the build context** — the images copy `packages/` in,
which is the single source of truth for migrations, prompts and contracts.

> **REQUIRED — leave Root Directory empty (the repo root).** Each service instead
> points at its own config file via **Settings → Config-as-code**:
>
>
> | Service      | Config path                 | Dockerfile                 |
> |--------------|-----------------------------|----------------------------|
> | backend      | `railway.backend.json`      | `apps/backend/Dockerfile`  |
> | pipeline     | `railway.ingest.json`       | `apps/pipeline/Dockerfile` |
> | synthesize   | `railway.synthesize.json`   | `apps/pipeline/Dockerfile` |
>
> There is deliberately **no frontend service**: the backend image builds the
> static export and serves it from the same process as `/api/*`.
>
> Setting Root Directory to `apps/backend` (as an earlier revision did) breaks the
> build: the Dockerfile copies `packages/`, which is outside that directory.

Set **Watch Paths** so one app's change doesn't rebuild the other:
- backend → `apps/backend/**`, `apps/frontend/**`
- pipeline / synthesize → `apps/pipeline/**`, `packages/**`

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
  - `INSPECTION_TOKEN = <random secret>` — bearer token for thinkers, sources,
    claims, predictions, and stats. Leave it unset to disable those routes.
  - `INGEST_TOKEN = <random secret>` — shared secret the upstream Innovation
    database sends as `X-Ingest-Token`. Unset ⇒ the ingest route is a 404.
  - `CURATION_TOKEN = <a different random secret>` — bearer token for editing
    innovation↔shift links. Unset ⇒ those routes are 404s. Deliberately separate
    from `INGEST_TOKEN`, so the upstream credential cannot change what a page
    shows. See [`docs/INNOVATIONS-API.md`](docs/INNOVATIONS-API.md).
  - `INNOVATION_ASSET_HOSTS` (optional) — comma-separated hosts a cover image may
    be mirrored from. Defaults to `tw-the-engine.up.railway.app`. Move where
    upstream serves cover images and this has to change first, or every mirror
    reports `host not allowed`.
  - `PUBLIC_ORIGIN` (optional) — absolute origin used for canonical URLs and
    the sitemap. Defaults to the first `FRONTEND_ORIGIN` entry.
  - `PORT = 8080` (optional; the image defaults to it)
- **Networking:** Generate Domain. This is the only public domain users hit.

## 4. Pipeline (scheduled refresh)
New service → **Deploy from repo**.
- **Config-as-code path:** `railway.ingest.json`. Root Directory stays empty.
- **Cron Schedule:** comes from that file (`0 22 * * 0`, Sundays 22:00 UTC).
  Railway runs the container on schedule, then the service sleeps.
- **Variables:** `DATABASE_URL = ${{Postgres.DATABASE_URL}}`, `ANTHROPIC_API_KEY`.
  - `YOUTUBE_PROXY_URL` — managed secret required for the YouTube source canary.
    Never print it. The pipeline redacts HTTP userinfo before writing errors.
  - `YOUTUBE_PROXY_COST_USD_PER_REQUEST` — optional unit-cost estimate recorded
    with proxy request counts in `pipeline_runs.detail`.
  - `SS_ALERT_WEBHOOK` — **set this.** Cost and failure alerts POST here
    (Slack/Discord/ntfy all accept the payload). Without it alerts only reach
    stdout, and the previous macOS-only implementation reached nothing at all.
  - `SS_BUDGET_TOTAL_USD` (default 35) — hard ceiling; the run *aborts* past it.
  - `SS_COST_ALERT_USD` (default 25) — notify threshold.
  - `SS_DISABLE_BATCH=1` — opt out of the Batch API (2x the cost; only for
    debugging, since batches take minutes to hours to return).
  - `SS_SHIFTS_WEBHOOK_URL` — **synthesize service only** (`railway.synthesize.json`),
    since that is the service that publishes. The key-shift/sub-shift list, grouped
    by sphere, is POSTed there after every successful publication — including a
    manual `--export-only` repair. Unset disables it. Delivery failure prints
    `[shift-map] delivery failed: …` and the run still exits 0, deliberately: the
    map has already committed and the site is already serving it. Payload contract:
    `docs/SHIFT-MAP-WEBHOOK.md`.
- On startup the run **applies any pending migrations**, then scrapes → processes.
  Synthesis is the separate Monday service. A candidate is validated before
  publication; failure exits non-zero and leaves `documents['map']` untouched.
  Success atomically rotates the old map to `documents['map:previous']`.

## 5. Verify
- `https://<domain>/health` → `ok` (it queries Postgres, so it goes red if the DB does).
- `https://<domain>/api/v1/map` → small index JSON. Domain/shift/sub-shift routes
  return only that route's document and honor ETags. `/api/map` is deprecated.
- `/api/stats` without a valid inspection bearer token → `401` (or `404` when
  `INSPECTION_TOKEN` is disabled).
- `https://<domain>/` → the app renders; a deep link like `/map/society` loads directly.
- `https://<domain>/api/nonsense` → JSON 404 with stable `not_found` code.
- An unknown content path renders the accessible Not Found shell with HTTP 404
  and noindex; a valid deep link returns HTTP 200 with canonical/OG metadata.
- Trigger each stage once from the dashboard ("Run now") and watch logs.
- `SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 5;` — every run
  records status, claim delta and spend here, so a failed cron is diagnosable
  after its container is gone. A row still `running` with a NULL `finished_at`
  means the container died mid-flight.

### Controlled synthesis and editorial rollback

Run one controlled staging synthesis only after the route API is deployed. The
validator must report unique slugs/references, exactly five sub-shifts per shift,
all 16 industries once and in order, canonical modules, parent integrity, and
HTTP(S) provenance. If the bounded targeted repair still fails, report the exact
records and keep the live map. During an incident, roll back code to the previous
successful Railway deployment and data by atomically promoting `map:previous`;
do not rerun paid generation while responding.

### YouTube canary

After `YOUTUBE_PROXY_URL` exists, enable one YouTube channel and run ingest.
Check listing and transcript success, item count, latency, request count, cost,
and source status in `pipeline_runs.detail`. Restore all 11 sources only after
that canary passes. The variable is currently a prerequisite, not something the
application can synthesize or infer.

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
`apps/frontend/src/modules/index.jsx` — the front end skips types it doesn't know,
so the backend can ship one first. `test_shift_modules_contract.py` fails if the
three drift apart.

## Notes
- Use Railway **reference variables** (`${{Postgres.DATABASE_URL}}`) so the DB URL
  is never copied around; rotate the key in one place.
- Free tier sleeps idle services (cold start on first hit) and has monthly usage
  limits — fine for a demo; upgrade for steady traffic.
- CORS and `PORT` binding are already production-set
  (see `apps/backend`). Remaining follow-ups live in [ARCHITECTURE.md](ARCHITECTURE.md#7-known-gaps--follow-ups).

## Module visibility, without a deploy

Which modules a shift page shows is data. The default matrix lives in
`packages/contracts/shift_modules.json` (mirrored as a const in
`apps/backend/src/module_policy.rs`); a row in `shift_module_visibility`
overrides it for one `(scope, domain_id, module_type)`, and `domain_id = '*'`
overrides it for every sphere at once.

The filter runs when the backend builds a route fragment, so a change is live
within `DOC_CACHE_TTL` (60s) — no deploy, no pipeline run. Hiding is
presentation only: the publication still carries every module and
`validate_map()` still requires them, so a flag can never make a run
unpublishable and un-hiding one never needs a republication.

```sql
-- show human_needs on Economy key shifts after all
INSERT INTO shift_module_visibility (scope, domain_id, module_type, visible, note)
VALUES ('key_trend', 'economy', 'human_needs', true, 'Q4 experiment')
ON CONFLICT (scope, domain_id, module_type)
DO UPDATE SET visible = EXCLUDED.visible, note = EXCLUDED.note, updated_at = now();

-- turn a deferred module on everywhere in one row
INSERT INTO shift_module_visibility (scope, domain_id, module_type, visible)
VALUES ('key_trend', '*', 'voices', true)
ON CONFLICT (scope, domain_id, module_type) DO UPDATE SET visible = true, updated_at = now();

-- back to the contract default
DELETE FROM shift_module_visibility
 WHERE scope = 'key_trend' AND domain_id = 'economy' AND module_type = 'human_needs';
```

A page composed from a `shift_module_overrides` row is exempt from the filter
entirely — an editor who hand-authored the whole module list has already decided
what appears.

## Classifier environment

`steps/classify` runs in two places, and they share one `ACCEPT`.

- **Weekly, with the model**, last in `synthesize`. Resolves the ambiguous band.
- **Daily at 03:00, deterministic** — `railway.classify.json`, a cron service on
  the pipeline image. Without it a newly ingested innovation waits up to a week
  for its links; this is what makes ingest feel immediate, at the cost of a
  container running for a few seconds a day.

**Set `SS_CLASSIFY_MODEL=0` on the daily service.** It is not just a cost
setting: with the model off the pass also does not retract, which is what stops
the daily deterministic run deleting the links the weekly model-assisted run
made, every single day. Both halves of that were fixed together; do not remove
one without the other.

**Do not attach this config over a launch weekend.** Attaching a config is what
arms its cron — the same rule that applies to `railway.ingest.json` and
`railway.synthesize.json`.

| Variable | Default | What it does |
|---|---|---|
| `SS_CLASSIFY_MODEL` | `1` | `0` disables escalation **and retraction** — deterministic only |
| `SS_CLASSIFY_MODEL_ID` | `claude-haiku-4-5` | the escalation model |
| `SS_CLASSIFY_BUDGET_USD` | `2.00` | per-run spend ceiling; hitting it finishes deterministically rather than aborting |
| `SS_CLASSIFY_MODEL_CALLS_MAX` | `200` | count guard, independent of price |
| `SS_CLASSIFY_ACCEPT` | `0.50` | confidence at or above which a link is written |
| `SS_CLASSIFY_FLOOR` | `0.45` | below this nothing is ever linked, not even the model's pick |
| `SS_CLASSIFY_MAX_LINK_RATE` | `0.60` | circuit breaker: stop the pass if more than this share of a sample links |
| `SS_CLASSIFY_BREAKER_SAMPLE` | `25` | how many innovations the breaker judges before it can fire |

### Choosing `SS_CLASSIFY_ACCEPT`

Do not guess at it, and do not read the default as settled — it was 0.72 for a
year, which was the value that made a *two-shift* unit-test fixture pass. Against
the real 306-shift corpus nothing could reach it, so the classifier linked
nothing and reported `0 model call(s), $0.0000` while doing so.

```bash
DATABASE_URL=... python -m serious_shift_pipeline.tools.calibrate_classifier
```

It scores every active innovation against the live corpus and prints what each
candidate threshold would decide, with the lexical / facet / brand contributions
separated. Run it before moving the number and whenever the upstream pushes a
batch; `--record` writes the fixture the DB-free calibration test replays, so the
fixture diff is the review.

`--dry-run` on the classifier itself prints the deterministic ranking and writes
nothing. It never escalates — it marks the rows that *would* have gone to the
model rather than paying for them — so read `(none)` as "the arithmetic found
nothing", not "the model agreed".
