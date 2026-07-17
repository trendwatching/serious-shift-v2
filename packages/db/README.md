# db — Postgres schema, migrations, ETL

Postgres is the **single source of truth** for all data. This package owns the
schema, its migrations, and the one-off import from the legacy SQLite database.
Neither app owns the schema via an ORM — both the Python **pipeline** (writer)
and the Rust **backend** (reader) depend on the migrations here. The pipeline also
applies these migrations automatically on each run (it bundles a copy), so a fresh
database self-bootstraps.

```
migrations/   SQL migrations (dbmate, forward-only)
  0001_schema.sql   the full schema (only tables the code uses)
  0002_seed.sql     bootstrap seed — thinker roster + portraits/bios + scrape manifest
etl/
  sqlite_to_postgres.py   OPTIONAL one-off import from legacy serious-shift.db
  verify_parity.py        proves the import was lossless
docker-compose.yml        local Postgres 16
```

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
dbmate up        # 0001 schema + 0002 seed (thinker roster + scrape manifest)
```

That fully bootstraps a usable database — no data import needed. The pipeline
then produces everything else (claims, predictions, and the `documents`
map/keynote/synthesis/daily blobs); there are **no JSON files**, everything lives
in the database.

### Optional — import legacy SQLite data
```bash
pip install "psycopg[binary]"
python etl/sqlite_to_postgres.py --sqlite ../../serious-shift.db --truncate
python etl/verify_parity.py     --sqlite ../../serious-shift.db   # "lossless ✓"
```
The ETL normalizes SQLite's dirty data (mixed-type dates → valid dates or NULL),
copies only tables/columns the current schema still has, and bumps identity
sequences; `--truncate` makes re-runs idempotent.

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
| `concepts` | cross-thinker concepts (keynote relevance) |
| `tensions` | mapped disagreements (side_a vs side_b, consumer implications) |

### Relationships (junctions)
| Table | Links |
|---|---|
| `claim_concepts` | claims ↔ concepts |
| `concept_thinkers` | concepts ↔ thinkers (stance) |
| `thinker_disagreements` | thinker ↔ thinker (topic) |

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
| `documents` | whole-JSON blobs keyed `map` / `keynote` / `synthesis` / `daily`, served by the backend at `/api/<key>`. Written by the pipeline generators (`generate_map_data`, `generate_keynote`). |

## Deploy a free Postgres — Neon

1. Create a project at neon.tech → copy the `postgres://…?sslmode=require` string.
2. Apply schema + load data against it:
   ```bash
   export DATABASE_URL='postgres://…neon…?sslmode=require'
   DBMATE_MIGRATIONS_DIR=./migrations dbmate up
   python etl/sqlite_to_postgres.py --sqlite ../../serious-shift.db --truncate
   python etl/verify_parity.py     --sqlite ../../serious-shift.db
   ```
3. Populate `documents` by running the pipeline generators
   (`python -m serious_shift_pipeline.steps.generate_map_data --export-only` rebuilds
   `documents['map']` from existing rows with no API cost; `generate_keynote`
   rebuilds the keynote). Use the same `DATABASE_URL` for the backend and pipeline.

Use a separate Neon branch/project per environment; supply `DATABASE_URL` via the
platform secret store. The local `serious-shift.db` is the import source only —
archive it to object storage and keep it out of git once Neon is authoritative.
