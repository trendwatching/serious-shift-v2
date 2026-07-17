# pipeline — ingestion & intelligence (Python, Postgres)

Scrapes AGI thinkers' sources, extracts structured claims/predictions via the
Anthropic API, scores them, and generates the trend map + keynote — all written
to **Postgres** (the backend then serves it). A scheduled batch service, not a
request server.

## Structure — where to change things

```
serious_shift_pipeline/
  run_weekly.py   THE FLOW — read this first; orchestrates the steps below
  core/           shared infrastructure (no pipeline logic here)
    db.py            Postgres access (connect / query / execute / normalize_date)
    llm.py           Anthropic client + robust JSON parsing
    config.py        model id + pricing (env-overridable)
    voice.py         the tone of voice — edit here to change how ALL content reads
    observability.py cost tracking + JSONL logs
  steps/          the pipeline, in flow order — edit a step here
    scraper.py          fetch sources → raw_content/*.txt (per-source watermark)
    process_raw.py      Claude extraction → claims/sources/predictions  (prompt lives here)
    scoring.py          source_depth · freshness · claim_weight (free, no API)
    generate_map_data.py  → documents['map']      (Claude; served at /api/map)
    generate_keynote.py   → documents['keynote']  (Claude; served at /api/keynote)
    evaluate.py         prediction status + credibility scores
    deduplicate.py      mark duplicate claims
  tools/          run on demand, not part of run_weekly
    ingest.py     ad-hoc single-URL ingest
    status.py     DB/health dashboard
    queries.py    read queries (also the backend's functional spec)
```

`run_weekly` runs `scraper → process_raw → scoring → (generate_map_data, generate_keynote)`;
the two LLM generators are gated on new claims. **To change behaviour, edit the
relevant `steps/` file; shared plumbing lives in `core/`.**

## Configuration (env)

| Var | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Postgres |
| `ANTHROPIC_API_KEY` | for extraction/generation | scraper & scoring don't need it |
| `RAW_CONTENT_DIR` | no | default `./raw_content` |
| `SS_LOGS_DIR` | no | default `./logs` |
| `SS_MAX_WORKERS` | no | parallelism for scrape/extract/generate (default `8`). Lower it if you hit API rate limits. |
| `WEBSHARE_PROXY_USERNAME` / `WEBSHARE_PROXY_PASSWORD` | no | route YouTube transcript fetches through a Webshare residential proxy — needed on cloud hosts, where YouTube IP-blocks datacenter IPs. |
| `YOUTUBE_PROXY_URL` | no | alternative to Webshare: any `http://user:pass@host:port` proxy for YouTube (used for both yt-dlp listing and transcripts). |

Run modules from the **repo root** (raw_content + logs are cwd-relative).

The I/O-bound steps run concurrently (scraping per thinker, Claude extraction per
file, map/keynote generation per domain/Key-Trend) via a bounded thread pool —
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
The initial manifest is seeded by migration `0003`.

## Run locally

```bash
# Postgres + data first — see ../../packages/db/README.md
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL=postgres://serious:serious@localhost:5432/serious_shift
export ANTHROPIC_API_KEY=sk-...

pytest                                            # SQL-validation + unit + (DB-gated) integration
python -m serious_shift_pipeline.tools.status           # health snapshot
python -m serious_shift_pipeline.run_weekly --dry-run   # plan, no changes
python -m serious_shift_pipeline.run_weekly             # full run (scrape→extract→score→map→keynote)

# individual steps
python -m serious_shift_pipeline.steps.scraper --thinker "Ethan Mollick"
python -m serious_shift_pipeline.steps.process_raw --thinker "Ethan Mollick"
python -m serious_shift_pipeline.steps.scoring
python -m serious_shift_pipeline.tools.ingest --url URL --thinker "Sam Altman"
python -m serious_shift_pipeline.steps.deduplicate --execute [--use-api]
python -m serious_shift_pipeline.steps.evaluate
```

Lint/type: `ruff check` · `mypy serious_shift_pipeline`. CI: `.github/workflows/pipeline.yml`.

## Scheduling (deploy)

`run_weekly` is a batch job — run it on a schedule (GitHub Actions cron, or a
Render/Fly scheduled job) with `DATABASE_URL` + `ANTHROPIC_API_KEY` in the
environment. A full refresh spends roughly $60–100 of Anthropic credits;
`run_weekly` cost-guards and gates the expensive map/keynote steps on new claims.
