"""
Serious Shift scraper — append-only, watermark-based refresh.

Fetch modes
  --auto-since (default)  Per-source watermark from the source_state table.
                          Each source resumes from where it last stopped.
  --since DATE            Global override — use DATE for all sources.
                          Use this for backfills; it bypasses source_state.
  --until DATE            Upper bound (default: today). Rarely needed.

Usage
  python -m serious_shift_pipeline.steps.scraper --all
  python -m serious_shift_pipeline.steps.scraper --thinker "Ethan Mollick"
  python -m serious_shift_pipeline.steps.scraper --all --since 2023-01-01
  python -m serious_shift_pipeline.steps.scraper --all --mode historical --since 2023-01-01

Watermark invariant
  source_state.last_item_date advances ONLY after a successful fetch.
  Extraction (process_raw) reads raw_content/ independently, so a crash between
  scrape and extract leaves the watermark where it was: the files already on
  disk are extracted on the next run, and are NOT re-fetched.

Layout
  content.py    one URL → dated, de-duplicated text on disk
  watermark.py  source_state reads/writes — the invariant above
  handlers.py   the eight source handlers and their dispatch
  runner.py     manifest loading, fan-out, CLI

This was a single 1,251-line module mixing all four concerns with no tests.
The watermark is the part that decides whether a week of sources is fetched or
silently skipped, so it is now isolated and covered by tests/test_watermark.py.

Names are re-exported here so `from ..steps import scraper` keeps working.
"""
from .content import (  # noqa: F401
    RAW_DIR, SKIP_PATTERNS, ScrapeFetchError, extract_date_from_url,
    external_id_in_db, fetch_article_text, in_range, parse_date, raw_file_exists,
    save_raw, should_skip_url, thinker_dir, url_in_db,
)
from .handlers import (  # noqa: F401
    handle_manual, ingest_papers, scrape_arxiv_author, scrape_arxiv_category,
    scrape_blog, scrape_openalex, scrape_org_blog, scrape_rss, scrape_substack,
    scrape_youtube,
)
from .runner import Log, load_thinker_sources, main, scrape_thinker  # noqa: F401
from .watermark import (  # noqa: F401
    FALLBACK_SINCE, get_since_for_source, get_thinker_id, update_source_state,
)
