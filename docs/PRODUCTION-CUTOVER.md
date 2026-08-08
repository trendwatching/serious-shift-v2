# Production cutover runbook

Moving `seriousshift.ai` from the current hash-routed site to the redesign.

**Order matters.** Three things will break production if done early:

- The production **`frontend` service owns `www.seriousshift.ai` and auto-deploys
  from the repo.** Merging `mobile-ui` into `main` rebuilds it with the redesign
  and flips the live site with no verification — and Next serving the export
  alone has no SPA fallback, so every deep link would 404. **Freeze or
  disconnect that service before merging**, or skip the merge entirely and point
  the *backend* service at the `mobile-ui` branch for verification (see step 4).

- The new backend **panics on startup without `FRONTEND_ORIGIN`** (deliberate —
  it fails closed rather than allowing every origin). Production does not have
  it set. Merging to `main` before step 1 takes the site down.
- `core/migrate.py` **refuses to run** against production's un-reconciled schema.
  That is the correct behaviour, but the pipeline will not run until step 2.

## Where production actually is

| | Production today | After cutover |
|---|---|---|
| Site | old design, hash routes (`/#/map/society`) | redesign, path routes |
| Served by | separate `frontend` Next service | the backend binary, same origin |
| Backend build | RAILPACK, root `/apps/backend`, **debug** | Dockerfile, release |
| `schema_migrations` | `0001`–`0007` (never got `0008`) | `20250101000000` + 2 |
| Map document | 2026‑07‑26, **zero editorial modules** | current, ~13 modules/shift |
| `/api/claims` | 8.4 MB unpaginated, public | 500 rows, `?limit=` |

Production data is healthy and *ahead* of staging (45,988 claims vs 42,466) —
only the schema bookkeeping and the deployed code are behind.

## Steps

### 1. Set the backend variables (no deploy yet)

```bash
railway variables --set FRONTEND_ORIGIN=https://www.seriousshift.ai \
                  --set PUBLIC_ORIGIN=https://www.seriousshift.ai \
                  --service backend --environment production --skip-deploys
```

`PUBLIC_ORIGIN` is what canonical URLs and `sitemap.xml` are built from. Without
it they fall back to the first `FRONTEND_ORIGIN` entry, which is the same here.
Set a strong `INSPECTION_TOKEN` separately.

`INGEST_TOKEN` and `CURATION_TOKEN` gate the innovations write and curation
routes; each route is a 404 while its token is absent. Leave both absent for the
cutover itself — nothing about moving the domain depends on them — and set them
afterwards, once staging has accepted a real payload end to end
([`INNOVATIONS-API.md`](INNOVATIONS-API.md#7-operating-it)). They must be
different values from each other and from staging's: the upstream database's
credential should not be able to change what appears on a page.

Before enabling YouTube, provision managed `YOUTUBE_PROXY_URL` on the pipeline
service; never put the credential in this runbook or a command transcript.

### 2. Reconcile the schema

**Corrected 2026-08-08.** Production holds `0001`–**`0006`**, not `0001`–`0007`
as this runbook previously said. `0007` creates `shift_module_overrides` and adds
`domain_key_trends.modules` / `.read_time`, `domain_sub_trends.modules` and
`domains_v2.horizon` — none of which exist in production. `reconcile_baseline.sql`
requires that table and correctly refuses:

> Cannot reconcile: the baseline expects tables that do not exist
> (shift_module_overrides). This database is behind the pre-squash chain, not
> merely un-squashed.

Read-only check first:

```bash
psql "$PROD_DATABASE_URL" -Atc "SELECT string_agg(version,',' ORDER BY version) FROM schema_migrations;"
# expect: 0001,0002,0003,0004,0005,0006
```

**Back up before any DDL** — this is the only step that is not trivially
reversible:

```bash
pg_dump "$PROD_DATABASE_URL" --no-owner --no-acl -Fc -f prod-$(date +%Y%m%d-%H%M).dump
```

Then, in order:

```bash
psql "$PROD_DATABASE_URL" -v ON_ERROR_STOP=1 -f packages/db/etl/0007_map_rich_fields_up.sql
psql "$PROD_DATABASE_URL" -Atc "INSERT INTO schema_migrations(version) VALUES ('0007') ON CONFLICT DO NOTHING;"
psql "$PROD_DATABASE_URL" -v ON_ERROR_STOP=1 -f packages/db/etl/reconcile_baseline.sql
DATABASE_URL="$PROD_DATABASE_URL" python -m serious_shift_pipeline.core.migrate
```

`0007_map_rich_fields_up.sql` is 0007's **up half only**, recovered from git
history. Do not run the original migration file through `psql -f`: it is a dbmate
file carrying both halves, so psql executes the down section immediately after
the up one, creates the table, drops it again, and reports success.

Expected after: `20250101000000` plus the six dated migrations, 27 tables,
schema identical to staging.

Rehearsed 2026-08-08 against a `pg_restore` of production into a scratch
Postgres: 48,104 claims intact, zero column differences from staging afterwards.
Rehearse again rather than trusting this — the restore takes under a minute:

```bash
docker run -d --name ss-rehearse -e POSTGRES_PASSWORD=x -p 55432:5432 postgres:18
pg_restore -d postgresql://postgres:x@127.0.0.1:55432/postgres --no-owner --no-acl prod.dump
```

Expected after: `{20250101000000}`.

### 3. Point the services at the Dockerfiles

Same fix already applied to staging. Root directory must be **empty** — the
images copy `packages/`, which sits outside `apps/`.

| Service | Config path | Root |
|---|---|---|
| backend | `railway.backend.json` | *(empty)* |
| pipeline | `railway.ingest.json` | *(empty)* |
| synthesize *(create)* | `railway.synthesize.json` | *(empty)* |

The `synthesize` service needs `DATABASE_URL` and `ANTHROPIC_API_KEY`.

### 4. Deploy the backend — without touching the live site

Two ways, and the second is safer:

**a. Point the backend service at `mobile-ui`.** No merge, so the `frontend`
service never rebuilds and the live site cannot move. The backend builds the
redesign and serves it on its own Railway URL for verification. Merge to `main`
later, once the domain has moved and the frontend service is gone.

**b. Merge to `main`** — only after freezing/disconnecting the `frontend`
service, otherwise it deploys the redesign to `www.seriousshift.ai` immediately:

```bash
git checkout main && git merge --no-ff mobile-ui && git push origin main
```

Either way the backend rebuilds from the Dockerfile: frontend static export +
release Rust binary in one image.

### 5. Verify on the Railway URL — before touching the domain

`https://backend-production-d723.up.railway.app` is still private to users at
this point. Check:

- `/health` → `ok`
- `/` renders the redesign; `/map/society` loads directly (no `#`)
- `/#/map/society` redirects to `/map/society`  ← the legacy-link path
- `/robots.txt` is `text/plain`; `/sitemap.xml` is `application/xml`
- `/map/society` has its own `<title>` and `og:` tags
- `/api/v1/map` is the small index; route fragments have distinct ETags
- `/api/nonsense` → JSON 404 with stable `not_found` code
- an invalid content path → accessible HTML, HTTP 404, and noindex
- inspection routes → 401 without a bearer token; 404 if disabled
- `POST /api/innovations/ingest` → 404 while `INGEST_TOKEN` is absent, 401 with it
  set and no `X-Ingest-Token`
- `PUT /api/innovations/1/shifts` → 404 while `CURATION_TOKEN` is absent
- `GET /api/v1/innovations` → `{"items": [...], "limit": 24, "next_cursor": …}`
- `SELECT count(*) FROM shift_refs` → the map's key shifts plus sub-shifts, **not
  zero**. Publication writes that registry, so a database migrated after its last
  publication has none, and every innovation link silently lands in `unknown`.
  Back-fill it before enabling ingest — see
  [`INNOVATIONS-API.md`](INNOVATIONS-API.md#first-time-setup-back-fill-shift_refs).

### 6. Move the domain  ← the visible flip

Remove `www.seriousshift.ai` (and the apex) from the **frontend** service, add
it to the **backend** service. Railway reissues the certificate; expect a short
window where the domain is resolving to the new service.

**This is the point of no return for users.** Everything before it is
invisible to them.

### 7. Remove the frontend service

Only once the domain is live on the backend and verified. It has no other role
— the backend image builds and serves the export itself.

### 8. Refresh the content

Run a controlled synthesis after the application deployment so the newly
enforced module and provenance contract is applied to the live candidate.

```bash
# ingest is optional here — production's claims are already ahead of staging.
railway run --service synthesize --environment production -- \
  python -m serious_shift_pipeline.run synthesize
```

Publication is conditional: validate unique route
slugs/references, five sub-shifts, the ordered 16-industry contract, module
shape/order, route-owned editorial citations, concise copy, duplicate prose,
referential integrity, and evidence/voice/stat URLs before promotion. One
bounded targeted repair is permitted. Failure must leave the current map
untouched and exit non-zero.

## Rollback

Before step 6, rollback is: point the domain back at the `frontend` service.
After step 7, roll application code back to the previous successful Railway
deployment. Roll editorial data back by atomically promoting
`documents['map:previous']`; do not rerun synthesis during an incident.

The schema reconciliation (step 2) is not rolled back by either — but it only
dropped empty tables and rewrote bookkeeping rows, and the old backend's
`/api/stats` is the only thing that referenced them.

---

## Cloning staging instead of migrating production

`railway environment new <name> --duplicate staging` is the other route. It
copies services, their settings and their variables — but **not volumes**, so
the new environment gets an **empty Postgres**.

That matters here, because the data is not interchangeable:

| | rows |
|---|---|
| production Postgres | 45,988 claims · 2,233 sources · 10,279 predictions |
| a freshly cloned Postgres | 0 |

So a clone is a new, empty environment — it does not replace the existing
`production` environment, and it does not inherit `seriousshift.ai`.

### What a clone still needs afterwards

1. **Data.** Either accept an empty database and let `run ingest` rebuild from
   the 120-source manifest (weeks of back-catalogue, real API spend), or dump
   and restore the production Postgres into the cloned one:
   ```bash
   pg_dump "$PROD_DATABASE_URL" --no-owner --no-acl -Fc -f prod.dump
   pg_restore -d "$CLONE_DATABASE_URL" --no-owner --no-acl prod.dump
   ```
   A restored copy still needs the reconciliation (step 2) — it carries
   production's `0001`–`0007` bookkeeping with it.

2. **Branch.** Cloned services track whatever staging tracks (`mobile-ui`).
   Point them at `main` if that is what should deploy to production.

3. **The domain.** `seriousshift.ai` stays on the old `production` environment's
   `frontend` service until it is moved (step 6).

4. **Anything staging-only.** Nothing today — the variables are deliberately
   references (`${{Postgres.DATABASE_URL}}`,
   `https://${{RAILWAY_PUBLIC_DOMAIN}}`) so they re-resolve in the clone rather
   than pointing back at staging. `ANTHROPIC_API_KEY` is a literal and is meant
   to be.

5. **YouTube proxy.** A clone does not make a missing managed proxy credential
   appear. Set `YOUTUBE_PROXY_URL`, canary one channel, verify listing/transcript
   telemetry, then restore all 11 sources.

### Which route to pick

- **Migrate the existing `production` environment** (steps 1–8 above) if you
  want to keep the data and the domain where they are. Fewer moving parts.
- **Clone** if you want to stand the new stack up beside the old one, verify it
  on its own URL, and switch the domain when ready — at the cost of moving
  ~46k claims across first.
