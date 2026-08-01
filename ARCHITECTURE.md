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
Scrapes sources → extracts claims via Claude → scores them → generates the map &
the trend map. Orchestrated by `run_weekly` (scrape → process → score → map;
the expensive LLM steps are gated on new claims). Each step is also a standalone
module (`python -m serious_shift_pipeline.<step>`).
- **Key files:** `scraper.py`, `process_raw.py` (LLM extraction), `scoring.py`,
  `mapgen/` (map generation, one module per phase), `evaluate.py`, plus shared
  `db.py` / `llm.py` / `observability.py`.
- **Why:** kept in Python because the scraping + LLM ecosystem (beautifulsoup,
  feedparser, yt-dlp, Anthropic SDK) is strongest there; it's a scheduled batch
  job, not a live service, so it deploys/scales separately from the API.
- **Change here → visible:** new/changed claims and map content in the DB,
  then in the app after the next pipeline run.

### `apps/backend` — Rust (axum + sqlx), the reader/API
Serves the data over HTTP. Each read endpoint is **one SQL string** in `src/sql.rs`
(Postgres builds the JSON with `json_agg`); handlers in `src/main.rs` are a line
each. Also hosts `POST /api/personalize` (Claude rewrite, key server-side).
- **Why:** the API surface is essentially "dump these rows as JSON," so letting
  Postgres assemble the JSON keeps it tiny and obviously-correct (no ORM, no
  per-table structs). Replaces the old ~53 MB of static JSON the browser used to download.
- **Change here → visible:** the `/api/*` responses the frontend consumes.

### `apps/frontend` — React + Tailwind, the UI
The trend map. A react-router SPA, built to a **static export** (`next build` with
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
| **API shapes** | `apps/backend/src/sql.rs` (JSON shapes) | backend serves → frontend reads | keep the JSON shape stable, or update the frontend's `useData` consumers |

Everything else is internal to one block.

---

## 4. "How do I change…?" — the cookbook

| I want to… | Edit | It shows up… |
|---|---|---|
| Add a thinker or a source to scrape | DB `scrape_sources` table (+ `thinkers` row) | after the next `scraper` + `process_raw` run |
| Change a thinker's photo or bio | DB `thinkers.image_url` / `bio`, then `mapgen.cli --export-only` | `/api/thinkers` + the map's thinker avatars/bios |
| Tune the extraction (what claims get pulled) | `process_raw.py` prompt | newly-processed sources' claims |
| Change claim ranking | `scoring.py` (depth/freshness/weight formula) | ordering across the map and claim lists |
| Add/modify an API endpoint | `apps/backend/src/sql.rs` + `src/main.rs` | new `/api/*` route |
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
- **`documents` blob table for the map.** It isn't a simple table dump (it is
  assembled across phases), so it's stored as a whole JSON
  the backend serves verbatim.
- **The SPA is served by the backend.** One always-on service instead of two,
  same origin, no proxy hop. Smallest faithful
  migration — behaviour unchanged, only the data source moved to the API.

---

## 6. Run, CI, deploy

- **Run locally:** see the root [`README.md`](README.md#local-quickstart-end-to-end)
  (DB → pipeline → backend → frontend).
- **CI:** `.github/workflows/` — one workflow per block, triggered on changes to
  its path (db applies/validates migrations; pipeline lint+test; backend
  compile+smoke; frontend build).
- **Deploy (free tier):** Neon (Postgres) → Fly.io/Render (backend) → Vercel
  (frontend). Steps in each block's README.

---

## 7. Known gaps / follow-ups

- **`documents['daily']`** has no generator (it was a static seed); it lives in the
  DB but a fresh DB won't have it until a daily-briefing generator is added or a
  backup is restored.
- **Backend hardening before public traffic:** CORS is permissive; `/api/personalize`
  has no rate limit or cache (it spends Anthropic credits per call).
- **`serious-shift.db`** (legacy SQLite) is the local import source only — archive
  it to object storage once a managed Postgres is authoritative.
- **No automated weekly schedule yet** — `run_weekly` is ready; wire a cron
  (GitHub Actions or a Fly/Render scheduled job) when you want auto-refresh.
- **Planned seams not yet built:** `packages/contracts` (a formal OpenAPI spec +
  generated client) and `packages/design-tokens` (Figma → Tailwind). Until then the
  contracts are the DB schema and the backend's JSON shapes.
