# Serious Shift — Architecture & Team Guide

A short map of how the system fits together, why it's built this way, and where
to change things. Per-block detail lives in each directory's `README.md`; this
doc is the overview.

---

## 1. The mental model

```
   apps/pipeline ──writes──►  Postgres  ◄──reads── apps/backend ──serves──► browser
   (Python, weekly cron)     (packages/db)      (Rust: /api/* + the SPA built
                                                 from apps/frontend)
                          SOURCE OF TRUTH
```

- **One source of truth: Postgres.** Everything — claims, predictions, the trend
  map, thinker bios/images, the scrape manifest — is a row in the DB. There are
  **no data files** in the repo.
- Data flows one direction: the **pipeline** writes the DB, the **backend** reads
  it and serves JSON, the **frontend** renders that JSON.
- The blocks are independent: each has its own README, CI workflow, and deploy.
  They only meet at two **contracts** — the DB schema and the backend's JSON shapes.

---

## 2. The modules

### `apps/pipeline` — Python, batch (the writer)
Scrapes sources → extracts claims via Claude → scores them → generates and
validates the trend map. Two independently triggerable stages (`python -m serious_shift_pipeline.run
ingest` / `synthesize`): ingest runs Sunday 22:00 UTC and synthesis runs Monday
02:00 UTC. Ingest is Haiku spend proportional to what landed; synthesis is a
flat ~$5 of Sonnet and is gated on new claims. Each step is also
a standalone module (`python -m serious_shift_pipeline.<step>`).
- **Key files:** `run.py` (the step table), `steps/scraper/` (content · watermark ·
  handlers · runner), `process_raw.py` (LLM extraction), `scoring.py`,
  `mapgen/` (map generation, one module per phase), `evaluate.py`, plus shared
  `db.py` / `llm.py` / `observability.py`.
- **Why:** kept in Python because the scraping + LLM ecosystem (beautifulsoup,
  feedparser, yt-dlp, Anthropic SDK) is strongest there; it's a scheduled batch
  job, not a live service, so it deploys/scales separately from the API.
- **Change here → visible:** new/changed claims and map content in the DB,
  then in the app after the next pipeline run.

### `apps/backend` — Rust (axum + sqlx), the reader/API
Serves the data over HTTP. Inspection reads are SQL strings in `src/sql.rs`.
The public map API parses one immutable published snapshot and derives the index,
domain, shift, and sub-shift fragments, ETags, and SEO metadata once per document
version. It also serves `robots.txt` and `sitemap.xml` from that same snapshot.
- **Why:** the API surface is essentially "dump these rows as JSON," so letting
  Postgres assemble the JSON keeps it tiny and obviously-correct (no ORM, no
  per-table structs). Replaces the old ~53 MB of static JSON the browser used to download.
- **The one exception to "the pipeline writes, the backend reads":**
  `src/innovations.rs` owns the innovations write path, the innovation↔shift
  mapping, and mirrored cover images. Innovations arrive by push at any time, so
  they are joined into each shift's module list when a route fragment is built
  rather than baked into the weekly document — an ingest or a curation edit is on
  the page within the 60s response cache TTL. The snapshot's cache version carries
  an innovations revision so the ETags stay honest.
  See [`docs/INNOVATIONS-API.md`](docs/INNOVATIONS-API.md).
- **Change here → visible:** the `/api/*` responses the frontend consumes.

### `apps/frontend` — React + Tailwind, the UI
The trend map. A small dependency-free path router wraps the React SPA, built to a **static export** (`next build` with
`output: 'export'` — Next is a build tool here, not a server) and served by the
Rust binary. Same origin as the API, so no CORS and no proxy hop; data is
fetched from the backend via `useData` → `/api/<name>` (same origin).
- **Why a static export:** the app is client-rendered anyway, so an always-on
  Node server bought nothing. The SPA is mounted
  as-is to keep the migration small (the only real change vs. the old app is the
  data source: API instead of bundled JSON).
- **Change here → visible:** the rendered UI at the relevant route.

### `packages/db` — Postgres schema, migrations, ETL (the contract)
Owns the schema. Migrations use **dbmate** (a language-neutral binary), so Python
and Rust agree on the schema without either's ORM winning. Also holds the one-off
SQLite→Postgres import.
- **Why:** the DB is the seam between the writer and the reader; neither app should
  own it. Timestamped dbmate migrations are the only way the schema changes.
- **Tables:** documented in [`packages/db/README.md`](packages/db/README.md#tables).

---

## 3. The two contracts (where the blocks meet)

| Contract | Defined in | Producer → consumer | If you change it… |
|---|---|---|---|
| **DB schema** | `packages/db/migrations/*.sql` | pipeline writes → backend reads | add a migration; update the writer (pipeline) and reader (backend SQL) |
| **API shapes** | `apps/backend/src/main.rs` + `packages/contracts` | backend serves → frontend reads | keep route-scoped v1 shapes stable, or update `useDomains` and its fixtures |
| **Innovations ingest** | [`docs/INNOVATIONS-API.md`](docs/INNOVATIONS-API.md) + `apps/backend/src/innovations.rs` | upstream Innovation database writes → backend stores | it is someone else's client: keep `source_innovation_id` idempotency and the error codes stable |

Everything else is internal to one block. The third contract is the only one with a
producer outside this repo.

---

## 4. "How do I change…?" — the cookbook

| I want to… | Edit | It shows up… |
|---|---|---|
| Add a thinker or a source to scrape | DB `scrape_sources` table (+ `thinkers` row) | after the next `scraper` + `process_raw` run |
| Change a thinker's photo or bio | DB `thinkers.image_url` / `bio`, then `mapgen.cli --export-only` | `/api/thinkers` + the map's thinker avatars/bios |
| Tune the extraction (what claims get pulled) | `process_raw.py` prompt | newly-processed sources' claims |
| Change claim ranking | `scoring.py` (depth/freshness/weight formula) | ordering across the map and claim lists |
| Add/modify an API endpoint | `apps/backend/src/sql.rs` + `src/main.rs` | new `/api/*` route |
| Put an innovation on a shift page | `PUT /api/innovations/{id}/shifts` (or send `shifts[]` at ingest) | that shift's page, within 60s |
| Change the database schema | `dbmate new <name>` in `packages/db/migrations` (+ writer/reader) | everywhere downstream |
| Change UI / layout / styling | `apps/frontend/src/` (views, components, Tailwind) | the rendered page |
| Change what env/secrets are used | per-block README "Configuration" + the platform's secret store | runtime behaviour |

---

## 5. Key decisions (and why)

- **Postgres is the only source of truth; no data JSON.** Prevents drift between a
  file and the DB; one place to back up and query. (Migrating off the legacy
  SQLite file + static JSON was the core of this refactor.)
- **Monorepo, independently deployable blocks.** Each block has its own README, CI
  workflow, and host — owned and shipped separately, but versioned together.
- **Pipeline stays Python; backend is Rust; the UI is a static React bundle.** Use each ecosystem
  where it's strongest; the batch pipeline and the live API have different runtimes
  and scaling needs, so they're separate services.
- **Backend lets Postgres build the JSON (`json_agg`).** Minimal, reviewable, and
  reproduces the old static-file shapes exactly.
- **dbmate migrations.** Language-neutral, so the schema isn't tied to a Python or
  Rust migration tool.
- **Validated last-good publication.** The candidate is assembled across phases,
  checked against the route/module/provenance contract, then atomically promoted.
  `documents['map:previous']` always holds the rollback document. The backend
  exposes route-scoped fragments; only deprecated `/api/map` serves the full blob.
- **The SPA is served by the backend.** One always-on service instead of two,
  same origin, no proxy hop. Smallest faithful
  migration — behaviour unchanged, only the data source moved to the API.

---

## 6. Run, CI, deploy

- **Run locally:** see the root [`README.md`](README.md#local-quickstart-end-to-end)
  (DB → pipeline → backend → frontend).
- **CI:** `.github/workflows/` — one workflow per block, including hash/audit
  gates, Rust/Python/frontend tests, axe, Playwright, and visual regression.
- **Deploy:** Railway Postgres + backend + pipeline ingest + synthesis. The backend
  image serves the SPA; there is no production Node hop. See `DEPLOY-RAILWAY.md`.

---

## 6b. Innovation → shift classification

`steps/classify` maps innovations onto the shifts they exemplify, writing
`innovation_shift_links` with `source='auto'` and a confidence.

Deterministic first: TF-IDF cosine over the *shift corpus itself* (0.55), a
structured-tag facet channel (0.30) and an exact brand-name match (0.15),
renormalised over the channels an innovation can actually be judged on. Only
genuinely ambiguous cases — a top pick between the floor and accept, or three
candidates inside the tie margin — cost one Haiku call.

It runs last in `synthesize`, after `mapgen`, so it classifies against the map
that was just published. It is also safe to run standalone on an hourly cron
with `SS_CLASSIFY_MODEL=0`, where it is pure SQL and returns zero rows on a
quiet hour — that is what stops a newly ingested innovation waiting a week for
its links.

Two invariants, both enforced in SQL rather than in Python:

* a link whose `source` is `'ingest'` or `'editor'` is never overwritten (the
  `ON CONFLICT DO UPDATE … WHERE source = 'auto'` makes the row a no-op);
* a *disabled* auto link is an editor's veto and is never resurrected (the
  retraction `DELETE` carries `AND enabled`, so the tombstone survives).

A sub-shift link is only ever written beneath an accepted parent, so an
innovation cannot appear on a child page whose parent page does not show it.

## 7. Known gaps / follow-ups

- **`documents['daily']`** has no generator (it was a static seed); it lives in the
  DB but a fresh DB won't have it until a daily-briefing generator is added or a
  backup is restored.
- **Predictions are never resolved.** 1,756 of 8,922 are past their evaluation
  date, so `accuracy` defaults to 0.5 for everyone — and that is 85% of the
  credibility weight, which `claim_weight` multiplies by.
- **`serious-shift.db`** (legacy SQLite) is the local import source only — archive
  it to object storage once a managed Postgres is authoritative.
- **YouTube proxy rollout is operationally gated.** All 11 blocked sources are
  YouTube. Configure `YOUTUBE_PROXY_URL`, canary one channel, then restore all
  sources only after listing/transcript metrics are healthy. Credentials are
  redacted and source success, item count, latency, proxy request count, and
  estimated cost are persisted in `pipeline_runs.detail`.
- **Hero art is generated for key shifts only, and is opt-in.** `steps/imagegen`
  is not built yet; two hand-made heroes ship as static assets
  (`hero-cognitive-erosion`, `hero-capacity-collapse-graded`) and every other
  shift falls back to its gradient hero, which is a finished design rather than
  a placeholder.
- **The module contract is checked in.** `packages/contracts/shift_modules.json`
  owns module order, required fields, and the canonical industry list. A formal
  OpenAPI schema and generated client remain optional future work; runtime route
  validation already prevents malformed response documents reaching the UI.
