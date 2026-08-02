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

### 2. Reconcile the schema

Read-only check first — it should print `0001 … 0007`:

```bash
psql "$PROD_DATABASE_URL" -Atc "SELECT string_agg(version,',' ORDER BY version) FROM schema_migrations;"
```

Then:

```bash
psql "$PROD_DATABASE_URL" -v ON_ERROR_STOP=1 -f packages/db/etl/reconcile_baseline.sql
```

This applies `0008`'s drops retroactively (five empty concept-graph tables) and
stamps the baseline. It refuses if any of those tables has rows, or if the
database is behind the pre-squash chain. Verified against a faithful simulation
of this exact state; idempotent.

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
- `/api/nonsense` → `404 {"error":"no such endpoint"}`

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

Production's map is from 26 July and carries **no editorial modules**, so shift
pages will render from the projected fallback until this runs.

```bash
# ingest is optional here — production's claims are already ahead of staging.
railway run --service synthesize --environment production -- \
  python -m serious_shift_pipeline.run synthesize
```

~$5 of Sonnet, ~17 minutes. This is also what applies the **quote
misattribution fix** to production's pages: until it runs, the "Who is saying
this" panel keeps showing paraphrases attributed to named people.

## Rollback

Before step 6, rollback is: point the domain back at the `frontend` service.
After step 7, restoring the old site means redeploying the `frontend` service
from a commit before the merge.

The schema reconciliation (step 2) is not rolled back by either — but it only
dropped empty tables and rewrote bookkeeping rows, and the old backend's
`/api/stats` is the only thing that referenced them.
