# db — Postgres schema, migrations, ETL

Postgres is the **single source of truth** for all data. This package owns the
schema, its migrations, and the one-off import from the legacy SQLite database.
Neither app owns the schema via an ORM — both the Python **pipeline** (writer)
and the Rust **backend** (reader) depend on the migrations here. The pipeline also
applies these migrations automatically on each run, so a fresh database
self-bootstraps.

```
migrations/   SQL migrations (dbmate)
  20250101000000_baseline.sql   full schema + seed, squashed from 0001-0008
schema.sql    generated dump of the current schema — CI keeps it in step
etl/
  sqlite_to_postgres.py   OPTIONAL one-off import from legacy serious-shift.db
  verify_parity.py        proves the import was lossless
  reconcile_baseline.sql  one-time fix for databases predating the squash
docker-compose.yml        local Postgres 16
```

Migration filenames are UTC timestamps (`dbmate new <name>`), never sequential
counters — two branches adding `0009_*.sql` would silently collide on the same
version and one would never apply. A test enforces the format.

`schema.sql` is **generated** (`dbmate dump`), not a bootstrap path. Create
databases with `dbmate up`, not by piping the dump in: the dump carries a
`schema_migrations` row set, and applying it by hand leaves the database
claiming migrations it never ran.

## Migrations — dbmate

A single static binary, so Rust and Python agree on schema without either's
migration framework. Files use `-- migrate:up` / `-- migrate:down`.

```bash
brew install dbmate
export DATABASE_URL='postgres://serious:serious@localhost:5432/serious_shift?sslmode=disable'
export DBMATE_MIGRATIONS_DIR=./migrations
dbmate up        # apply   ·   dbmate status   ·   dbmate rollback
```

## Local setup

```bash
docker compose up -d
dbmate up        # baseline: schema + seed (thinker roster + scrape manifest)
```

That fully bootstraps a usable database — no data import needed. The pipeline
then produces everything else (claims, predictions, and the `documents['map']`
blob the frontend reads); there are **no JSON files**, everything lives in the
database.

### Optional — import legacy SQLite data
```bash
pip install "psycopg[binary]"
python etl/sqlite_to_postgres.py --sqlite ../../serious-shift.db --truncate
python etl/verify_parity.py     --sqlite ../../serious-shift.db   # "lossless ✓"
```
The ETL normalizes SQLite's dirty data (mixed-type dates → valid dates or NULL),
copies only tables/columns the current schema still has, and bumps identity
sequences; `--truncate` makes re-runs idempotent.

`--truncate` cascades through `thinkers`, which `scrape_sources` and
`source_state` reference — and neither table exists in the legacy SQLite to be
reloaded. Both are therefore snapshotted by thinker *name* before the truncate
and re-keyed to the reloaded thinker ids afterwards, so the 120-source scrape
manifest survives the import. Any thinker the manifest names but the dump does
not carry is recreated, which is why `verify_parity.py` treats `thinkers` as a
superset rather than an exact match. `tests/test_etl_manifest.py` is the guard.

## Tables

Source of truth for all application data. (`schema_migrations` is dbmate's own
bookkeeping table and isn't listed.)

### Core entities
| Table | Purpose |
|---|---|
| `thinkers` | one row per thinker — name, affiliation, credibility/accuracy/outlier scores, bio, `image_url` |
| `sources` | articles/talks/podcasts/papers ⋈ thinker; title, date, url, full_text, signal/novelty/depth |
| `claims` | atomic extracted claims ⋈ source+thinker; domain, signal_strength, specificity, `claim_weight`, `freshness_score`, `duplicate_of` |
| `predictions` | falsifiable predictions ⋈ claim+thinker+source; status, consensus_alignment, evaluation_date |
| `pipeline_runs` | one row per stage invocation: status, claim deltas, spend |
| `pipeline_errors` | structured per-step failures, keyed by `run_id` |

### Trend map — domain-first v2 (canonical)
| Table | Purpose |
|---|---|
| `domains_v2` | 4 strategic domains |
| `domain_key_trends` | key trends per domain (≥8 each; attach directly to a domain) |
| `domain_sub_trends` | sub-trends per key trend |
| `domain_sub_trend_claims` | sub-trends ↔ claims |
| `domain_synthesis_insights` | synthesis insights per domain |
| `domain_synthesis_insight_claims` | insights ↔ claims |
| `domain_links` | typed edges between map nodes |
| `domain_flows` | domain → domain directional influence |

### Pipeline operational
| Table | Purpose |
|---|---|
| `scrape_sources` | the scrape manifest — per-thinker sources (platform, method, url/rss/channel) the scraper reads (was `scraper_config.json`) |
| `source_state` | per-source scrape watermark (last_item_date, last_run_status) |

### Documents
| Table | Purpose |
|---|---|
| `documents` | whole-JSON blobs. Only `map` exists and only `map` has a reader — the backend serves it at `/api/map`. Written by the synthesize stage. |
| `shift_module_overrides` | editor-authored module lists, keyed by slug; survives the weekly truncate |

### Innovations — real branded examples of a shift
Written by `POST /api/innovations/ingest` and the curation API, never by the
pipeline. Full contract: [`docs/INNOVATIONS-API.md`](../../docs/INNOVATIONS-API.md).

| Table | Purpose |
|---|---|
| `innovations` | one row per upstream innovation; `source_innovation_id` is the NOT NULL unique idempotency key. Keeps the verbatim `payload` and a `payload_hash` so an unchanged re-POST writes nothing |
| `innovation_tags` | the upstream taxonomy interned as `(facet, slug)` — eight closed facets |
| `innovation_tag_links` | innovations ↔ tags |
| `shift_refs` | **durable shift identity**, `(scope, slug)`. Upserted by publication, never deleted. Exists because `domain_key_trends.id` is recycled by the weekly `TRUNCATE … RESTART IDENTITY`, so a foreign key into it would be cascade-deleted every Monday |
| `innovation_shift_links` | the many-to-many mapping, `PRIMARY KEY (innovation_id, shift_ref_id)`. `source` records whether a link came from the payload (`ingest`), an editor (`editor`) or a future suggester (`auto`); each writer only manages its own rows |
| `innovation_assets` | the mirrored cover image bytes. Its own table so the row every list query reads stays skinny |

## Deploy a free Postgres — Neon

1. Create a project at neon.tech → copy the `postgres://…?sslmode=require` string.
2. Apply schema + load data against it:
   ```bash
   export DATABASE_URL='postgres://…neon…?sslmode=require'
   DBMATE_MIGRATIONS_DIR=./migrations dbmate up
   python etl/sqlite_to_postgres.py --sqlite ../../serious-shift.db --truncate
   python etl/verify_parity.py     --sqlite ../../serious-shift.db
   ```
3. Populate `documents` by running synthesis
   (`python -m serious_shift_pipeline.run synthesize`, or
   `python -m serious_shift_pipeline.mapgen.cli --export-only` to re-export
   without any API calls). Use the same `DATABASE_URL` for backend and pipeline.

Use a separate Neon branch/project per environment; supply `DATABASE_URL` via the
platform secret store. The local `serious-shift.db` is the import source only —
archive it to object storage and keep it out of git once Neon is authoritative.


## Baseline squash

Migrations `0001`–`0008` were squashed into `20250101000000_baseline.sql`. The
baseline was generated by applying the old chain to an empty database and
dumping the result, so it is byte-identical to what the sequence produced — it
simply omits the tables `0001` created and `0008` later dropped.

**A database that ran the old migrations must be reconciled once**, before
deploying a build that contains the baseline. Otherwise the runner sees an
unknown version and tries to re-create tables that already exist.
`core/migrate.py` refuses to run against an un-reconciled database and points
here, so the failure is loud rather than destructive.

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f etl/reconcile_baseline.sql
```

Pure bookkeeping — no DDL, no data touched. The script refuses to run unless
the recorded versions are exactly the pre-squash set, and is a no-op against an
already-reconciled database. Afterwards `SELECT version FROM schema_migrations`
returns `20250101000000` plus whatever has been added since.

Fresh databases need none of this: `dbmate up` applies the baseline and records
the single row.
