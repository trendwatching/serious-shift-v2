# pipeline — ingestion & intelligence (Python, Postgres)

Scrapes AGI thinkers' sources, extracts structured claims/predictions via the
Anthropic API, scores them, and generates the trend map — all written to
**Postgres** (the backend then serves it). A scheduled batch service, not a
request server.

Two stages, independently triggerable:

| Stage | Steps | Cost shape |
|---|---|---|
| `ingest` | scrape → extract → score → dedupe → evaluate | Haiku, proportional to what landed |
| `synthesize` | mapgen | Sonnet, ~$5 flat regardless of input |

```bash
python -m serious_shift_pipeline.run ingest
python -m serious_shift_pipeline.run synthesize
python -m serious_shift_pipeline.run all              # both, in order
python -m serious_shift_pipeline.run all --dry-run    # plan only
python -m serious_shift_pipeline.run ingest --only scrape
python -m serious_shift_pipeline.run --list-steps
```

They are separate because they fail, cost and schedule differently: a broken
scrape should not block a map rebuild, and re-running synthesis for a prompt
change should not re-scrape 120 sources. On Railway they are two services
(`pipeline` → ingest, `synthesize`) built from one image.

## Structure — where to change things

```
serious_shift_pipeline/
  run.py          THE FLOW — read this first. A data-driven step table; the
                  `ingest` / `synthesize` stages are slices of it.
  core/           shared infrastructure (no pipeline logic here)
    db.py            Postgres access (connect / query / execute / normalize_date)
    llm.py           Anthropic client + robust JSON parsing
    config.py        model id + pricing (env-overridable)
    voice.py         the tone of voice — edit here to change how ALL content reads
    observability.py cost tracking + run history/errors (→ Postgres, not files)
  steps/          the pipeline, in flow order — edit a step here
    scraper/            fetch sources → raw_content/*.txt
      content.py          one URL → dated, de-duplicated text on disk
      watermark.py        source_state reads/writes — what the next run fetches
      handlers.py         the eight source handlers and their dispatch
      runner.py           manifest loading, fan-out, CLI
    process_raw.py      Claude extraction → claims/sources/predictions  (prompt lives here)
    scoring.py          source_depth · freshness · claim_weight (free, no API)
    mapgen/               → validated candidate → documents['map']
      config.py             domain table, tuning constants, module-order contract
      routing.py            which claims each domain's generation sees
      llm.py                batched Claude calls + per-run cost accounting
      parsers.py            model responses → the shapes phases write
      modules.py            {type,data} module lists (see packages/contracts)
      export.py             assembles the document the frontend reads
      phases/               one module per generation phase
      cli.py                `python -m serious_shift_pipeline.mapgen.cli`
    evaluate.py         prediction status + credibility scores
    deduplicate.py      mark duplicate claims
  tools/          run on demand, not part of a stage
    ingest.py     ad-hoc single-URL ingest
    status.py     DB/health dashboard
    queries.py    read queries (also the backend's functional spec)
```

`mapgen` is gated: it only runs when new claims have landed since the last
successful `synthesize` run, because the map is a pure function of the claims
and regenerating on unchanged input is pure spend. `--force` overrides.
**To change behaviour, edit the relevant `steps/` file; shared plumbing lives
in `core/`.**

Publication is a separate, atomic step. The assembled candidate must pass the
route/module contract (unique slugs and references, exactly five sub-shifts per
shift, the 16 industries exactly once and in order, required module fields, and
HTTP(S) provenance for every evidence/voice item). One bounded targeted repair
pass may regenerate only the invalid parents. If the candidate still fails,
the run exits non-zero with structured issue details and `documents['map']`
remains untouched. A successful promotion copies the old map to
`documents['map:previous']` in the same transaction before replacing it.

Every invocation opens a row in `pipeline_runs` and files its errors against it
in `pipeline_errors`. Those used to be JSONL files under `./logs`, which died
with the container — so a failed cron left an alert and no detail. An
interrupted run now leaves a visible `running` row.

## Configuration (env)

| Var | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Postgres |
| `ANTHROPIC_API_KEY` | for extraction/generation | scraper & scoring don't need it |
| `RAW_CONTENT_DIR` | no | default `./raw_content` |
| `SS_RUN_RETENTION_DAYS` | no | run/error history kept, default `180` |
| `SS_MAX_ITEMS_PER_SOURCE` | no | items one source may contribute per run, default `30`. Extraction is priced per file, so without this a single high-volume feed sets the bill for the whole run. |
| `SS_YTDLP_TIMEOUT` | no | seconds to wait for a YouTube channel listing, default `120`. YouTube refuses datacenter IPs and often stalls rather than erroring; a longer wait just burns run time. |
| `SS_MAX_WORKERS` | no | parallelism for scrape/extract/generate (default `8`). Lower it if you hit API rate limits. |
| `SS_MAX_TARGETED_REPAIR_SHIFTS` | no | maximum parent shifts in the single targeted repair pass, default `12` |
| `WEBSHARE_PROXY_USERNAME` / `WEBSHARE_PROXY_PASSWORD` | no | route YouTube transcript fetches through a Webshare residential proxy — needed on cloud hosts, where YouTube IP-blocks datacenter IPs. |
| `YOUTUBE_PROXY_URL` | no | alternative to Webshare: any `http://user:pass@host:port` proxy for YouTube (used for both yt-dlp listing and transcripts). |
| `YOUTUBE_PROXY_COST_USD_PER_REQUEST` | no | optional unit cost used to estimate proxy spend in run telemetry; default `0` |

Never print or paste proxy values into logs or tickets. HTTP proxy userinfo is
redacted centrally before errors reach stdout or `pipeline_errors`. Each scrape
stores per-source status, item count, latency, proxy usage, source success rate,
and estimated proxy cost in `pipeline_runs.detail`.

Run modules from the **repo root** (`raw_content` is cwd-relative).

The I/O-bound steps run concurrently (scraping per thinker, Claude extraction per
file, map generation per domain/Key-Trend) via a bounded thread pool —
DB writes stay serial. This cuts a full run from hours to a fraction. Tune with
`SS_MAX_WORKERS`.

## Source manifest — `scrape_sources` table

What to scrape lives in the database (table `scrape_sources`), not a JSON file —
the scraper reads it via `load_thinker_sources()`. One row per source:

| Column | Notes |
|---|---|
| `thinker_id` | FK → `thinkers` |
| `platform` | `blog` · `substack` · `x` · `youtube` · `linkedin` · `podcast` · `manual` |
| `method` | `scrape_index` (crawl a blog index) · `rss` (feed) · `youtube` (channel transcripts) · `manual` (placeholder, not auto-fetched) |
| `url`, `rss`, `channel_url`, `handle`, `note` | per-method fields |

Add/edit sources with SQL, e.g.:
```sql
INSERT INTO scrape_sources (thinker_id, platform, method, rss)
SELECT id, 'substack', 'rss', 'https://example.substack.com/feed'
FROM thinkers WHERE name = 'Sam Altman';
```
The initial manifest (120 sources) is seeded by the baseline migration. It is
preserved across the optional legacy SQLite import — see
`packages/db/etl/sqlite_to_postgres.py`, which used to delete it via a CASCADE.

## Run locally

```bash
# Postgres + data first — see ../../packages/db/README.md
python -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements-dev.lock
pip install --no-deps --no-build-isolation -e .
export DATABASE_URL=postgres://serious:serious@localhost:5432/serious_shift
export ANTHROPIC_API_KEY=sk-...

pytest                                            # SQL-validation + unit + (DB-gated) integration
python -m serious_shift_pipeline.tools.status            # health snapshot
python -m serious_shift_pipeline.tools.verify_publication # does the LIVE map still satisfy the contract?
python -m serious_shift_pipeline.run all --dry-run       # plan, no changes
python -m serious_shift_pipeline.run ingest              # scrape → … → evaluate
python -m serious_shift_pipeline.run synthesize          # rebuild the map

# individual steps
python -m serious_shift_pipeline.steps.scraper --thinker "Ethan Mollick"
python -m serious_shift_pipeline.steps.process_raw --thinker "Ethan Mollick"
python -m serious_shift_pipeline.steps.scoring
python -m serious_shift_pipeline.tools.ingest --url URL --thinker "Sam Altman"
python -m serious_shift_pipeline.steps.deduplicate --execute [--use-api]
python -m serious_shift_pipeline.steps.evaluate
```

### Re-validating an already-published map

`mapgen` validates a candidate before promoting it, so a document can only be
published if it passed the contract **as it stood at publication time**. Tightening
the contract therefore leaves every already-published document silently
non-conformant, with nothing re-checking it and the site still serving it.

`tools.verify_publication` closes that gap. It is read-only and free — run it after
any change to `mapgen/validation.py` or `packages/contracts/shift_modules.json`,
and against staging before a cutover:

```bash
# the live document in Postgres (what the backend reads)
python -m serious_shift_pipeline.tools.verify_publication

# a deployed origin, via the operator-gated full-map endpoint
python -m serious_shift_pipeline.tools.verify_publication \
    --url https://backend-staging-1c16.up.railway.app --token "$INSPECTION_TOKEN"
```

Exit 0 = conformant, 1 = issues (grouped by code, with a sample per code), 2 =
unreadable. Issues are remediated by a synthesis run, not by editing the document.

Lint/type: `ruff check` · `mypy serious_shift_pipeline`. CI: `.github/workflows/pipeline.yml`.
Production dependencies are in `requirements.lock`; development/test tooling is
in `requirements-dev.lock`. Regenerate both with Python 3.13 and `pip-compile
--generate-hashes`; Docker installs the production lock with `--require-hashes`
and installs this local package without dependency resolution or build isolation.

## Scheduling (deploy)

Both stages are batch jobs. On Railway they are two cron services built from
one image (`railway.ingest.json`, `railway.synthesize.json`): ingest runs
Sunday 22:00 UTC, synthesize Monday 02:00 UTC — four hours later, so it sees a
finished ingest. Either can also be triggered on its own from the dashboard.

### YouTube proxy rollout

`YOUTUBE_PROXY_URL` is required on Railway before YouTube is considered healthy.
Canary exactly one of the 11 YouTube sources first. Verify channel listing,
transcript fetch, non-zero item count, latency, redacted logs, and proxy cost in
`pipeline_runs.detail`; only then restore the full manifest. If the canary fails,
remove/disable the proxy variable and leave the sources classified `blocked`
rather than repeatedly retrying them as generic failures.

A full refresh spends roughly **$8–9** of Anthropic credits with the Batch API
enabled (the default; the weekly run is latency-insensitive, so every bulk
phase submits at half price). The run is budget-guarded via
`SS_BUDGET_TOTAL_USD` and synthesis is gated on new claims having landed.
