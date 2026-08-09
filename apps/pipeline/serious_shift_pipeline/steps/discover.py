#!/usr/bin/env python3
"""
Discovery — widen the source base beyond curated feeds.

Runs exploratory arXiv + OpenAlex queries tuned to the four Serious Shift
domains, applies the reputability gate (steps/gate.py), and ingests accepted
papers as raw files (via the shared scraper paper-ingest). Complements the
seeded `scrape_sources` feeds; use for backfills or to widen coverage.

Usage
  python -m serious_shift_pipeline.steps.discover                 # last 180 days
  python -m serious_shift_pipeline.steps.discover --since 2026-01-01
  python -m serious_shift_pipeline.steps.discover --min-citations 10 --min-authority 0.5
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta

from ..core import sources_api
from .scraper import Log, ingest_papers

# Domain-tuned OpenAlex search strings (topical relevance) + arXiv categories.
DOMAIN_QUERIES = {
    "society":       "artificial intelligence society governance trust democracy",
    "economy":       "artificial intelligence economy productivity labor growth",
    "consumers":     "artificial intelligence consumer behavior adoption marketing",
    "organizations": "artificial intelligence enterprise organizations management work",
}
ARXIV_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG", "cs.CY", "econ.GN"]


def run(*, since: str | None = None, min_citations: int = 5,
        min_authority: float = 0.4, per_page: int = 50,
        arxiv_max: int = 100) -> int:
    since = since or (date.today() - timedelta(days=180)).isoformat()
    until = datetime.now().strftime("%Y-%m-%d")
    gate_params = {"min_citations": min_citations, "min_authority": min_authority}
    log = Log()
    total = 0

    print(f"Discovery since {since} — arXiv {ARXIV_CATEGORIES}")
    try:
        papers = sources_api.arxiv_search(ARXIV_CATEGORIES, since=since, max_results=arxiv_max)
        # arXiv is a curated venue tier; gate mainly stamps authority here.
        _, n = ingest_papers(papers, since, until, "paper", log,
                              apply_gate=True, gate_params={"min_citations": 0,
                                                            "min_authority": min_authority})
        total += n
        print(f"  arXiv ingested: {n}")
    except Exception as e:  # noqa: BLE001 — one source failing must not stop discovery
        print(f"  arXiv discovery failed: {type(e).__name__}: {e}")

    for domain, q in DOMAIN_QUERIES.items():
        print(f"Discovery — OpenAlex [{domain}]: {q!r}")
        try:
            works = sources_api.openalex_search(
                q, since=since, min_citations=min_citations, per_page=per_page)
            _, n = ingest_papers(works, since, until, "paper", log,
                                  apply_gate=True, gate_params=gate_params)
            total += n
            print(f"  {domain} ingested: {n}")
        except Exception as e:  # noqa: BLE001
            print(f"  OpenAlex [{domain}] failed: {type(e).__name__}: {e}")

    log.summary()
    print(f"\nDiscovery total ingested: {total}")
    return total


def main():
    ap = argparse.ArgumentParser(description="Serious Shift source discovery")
    ap.add_argument("--since", default=None, help="YYYY-MM-DD (default: 180 days ago)")
    ap.add_argument("--min-citations", type=int, default=5)
    ap.add_argument("--min-authority", type=float, default=0.4)
    ap.add_argument("--per-page", type=int, default=50)
    args = ap.parse_args()
    run(since=args.since, min_citations=args.min_citations,
        min_authority=args.min_authority, per_page=args.per_page)


if __name__ == "__main__":
    main()
