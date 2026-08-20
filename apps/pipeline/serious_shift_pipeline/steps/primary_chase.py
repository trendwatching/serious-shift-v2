#!/usr/bin/env python3
"""Chase quoted statistics to their primary sources.

The August 2026 content audit's sharpest finding: every published number was
laundered through a commentator — Stanford HAI quoted by a newsletter, never
fetched, never linked. This step walks recent statistic-bearing claims whose
source is commentary, asks a cheap model whether the passage attributes the
figure to an external origin WITH a URL present in the text, fetches that URL,
and only when the statistic verifiably appears in the fetched document does
the claim gain `primary_source_id`. Publication can then prefer the primary
URL and name the commentator as the via.

Deliberately deterministic about trust: the model may only point at a URL that
already appears verbatim in the passage (never invent one), and the fetched
document is accepted solely on `statistic_verifies` — no model judges the
fetch. Origins that are NAMED but not linked are counted (they are the next
tier of work for the research agent) but nothing is fetched for them.

Usage:
  python -m serious_shift_pipeline.steps.primary_chase [--days 14] [--limit 300] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from urllib.parse import urlparse

from ..core import claim_integrity, db, llm, observability
from ..core.observability import CostTracker, ErrorLog, RunLog
from ..prompts import primary_origin_prompt
from .process_raw import upsert_entity
from .scraper.content import fetch_article_text

#: Characters of commentary shown either side of the statistic.
CONTEXT_CHARS = 1500

#: Platforms/types that already ARE primary material — nothing to chase.
_PRIMARY_PLATFORMS = ("paper", "lab_blog", "primary")
_PRIMARY_TYPES = ("research_paper", "working_paper", "lab_post", "paper", "policy_paper")

_USE_BATCH = os.environ.get("SS_DISABLE_BATCH", "") not in ("1", "true", "yes")


def _context_window(claim: dict, full_text: str) -> str:
    """The passage around the statistic: the anchored quote span when present,
    else the first numeric token of the statistic located in the text, else
    the head of the document."""
    if claim.get("quote_start") is not None and claim.get("quote_end") is not None:
        lo = max(0, claim["quote_start"] - CONTEXT_CHARS)
        return full_text[lo:claim["quote_end"] + CONTEXT_CHARS]
    match = re.search(r"\d[\d,]*(?:\.\d+)?", claim.get("statistic") or "")
    if match:
        pos = full_text.find(match.group(0))
        if pos != -1:
            lo = max(0, pos - CONTEXT_CHARS)
            return full_text[lo:pos + CONTEXT_CHARS]
    return full_text[:2 * CONTEXT_CHARS]


def _plausible_origin_url(url: str | None, own_url: str | None, context: str) -> bool:
    """A URL worth fetching: http(s), present VERBATIM in the passage (the
    model cannot smuggle one in), and not the commentary's own host."""
    if not url or url not in context:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    return parsed.netloc != urlparse(own_url or "").netloc


def _candidates(conn, days: int, limit: int) -> list[dict]:
    return db.query(conn, """
        SELECT c.id, c.claim_text, c.statistic, c.quote_start, c.quote_end,
               s.id AS source_id, s.url AS source_url, s.full_text
        FROM claims c JOIN sources s ON c.source_id = s.id
        WHERE c.has_statistic AND c.primary_source_id IS NULL
          AND COALESCE(c.statistic, '') <> ''
          AND NOT (COALESCE(s.platform, '') = ANY(%s))
          AND NOT (COALESCE(s.source_type, '') = ANY(%s))
          AND COALESCE(s.full_text, '') <> ''
          AND s.created_at > now() - make_interval(days => %s)
        ORDER BY s.created_at DESC
        LIMIT %s""",
        (list(_PRIMARY_PLATFORMS), list(_PRIMARY_TYPES), days, limit))


def _existing_source_by_url(conn, url: str):
    return db.query_one(conn, "SELECT id FROM sources WHERE url = %s AND url <> ''", (url,))


def _insert_primary_source(conn, origin_name: str, url: str, text: str, pub_date) -> int:
    entity = upsert_entity(conn, origin_name, kind="publication", discovered=True)
    return db.insert_returning_id(conn, """INSERT INTO sources
        (thinker_id, title, date_published, source_type, platform, url, full_text,
         content_sha256, signal_strength, novelty, keynote_impact, confidence)
        VALUES (%s,%s,%s,'article','primary',%s,%s,%s,
                'signal','repeating_position','background','data_backed')
        RETURNING id""",
        (entity["id"] if entity else None, origin_name[:300], pub_date, url, text,
         hashlib.sha256(text.encode("utf-8")).hexdigest()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Chase statistics to their primary sources")
    parser.add_argument("--days", type=int,
                        default=int(os.environ.get("SS_PRIMARY_CHASE_DAYS", "14")))
    parser.add_argument("--limit", type=int,
                        default=int(os.environ.get("SS_PRIMARY_CHASE_LIMIT", "300")))
    parser.add_argument("--fetch-cap", type=int,
                        default=int(os.environ.get("SS_PRIMARY_CHASE_FETCH_CAP", "100")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY not set.")

    orchestrated = bool(os.environ.get("SS_RUN_ID"))
    run_id = os.environ.get("SS_RUN_ID") or observability.new_run_id("ingest")
    run = RunLog(run_id, "ingest")
    if not orchestrated:
        run.start()
    error_log = ErrorLog(run_id)
    cost_tracker = CostTracker()
    stats = {"examined": 0, "origin_named": 0, "origin_linked": 0,
             "fetched": 0, "verified": 0, "repointed": 0, "unverified": 0}

    with db.connect() as conn:
        rows = _candidates(conn, args.days, args.limit)
        stats["examined"] = len(rows)
        print(f"Primary chase: {len(rows)} statistic claims to audit "
              f"(last {args.days} days)")
        if not rows:
            _finish(run, orchestrated, cost_tracker, stats)
            return 0
        if args.dry_run:
            for r in rows[:20]:
                print(f"  claim {r['id']}: {r['statistic'][:80]}")
            return 0

        reqs = [llm.Req(user=primary_origin_prompt(
                            r["claim_text"], r["statistic"],
                            _context_window(r, r["full_text"])),
                        max_tokens=500, custom_id=f"c{r['id']}")
                for r in rows]
        if _USE_BATCH:
            results = llm.call_batch(reqs)
        else:
            results = {}
            for req in reqs:
                try:
                    results[str(req.custom_id)] = llm.call(req)
                except Exception as exc:  # noqa: BLE001 — per-claim, surfaced below
                    results[str(req.custom_id)] = (None, {"error": repr(exc)})

        # One fetch per URL, shared across every claim that points at it.
        fetched_docs: dict[str, tuple[str, object] | None] = {}
        for row in rows:
            text, usage = results.get(f"c{row['id']}", (None, {"error": "no result"}))
            if usage and not usage.get("error"):
                cost_tracker.add(usage, thinker_name="PRIMARY_CHASE")
            if text is None:
                error_log.record(step="chase", thinker="PIPELINE",
                                 exc=RuntimeError(str(usage.get("error"))),
                                 retry_attempted=False, outcome="skipped",
                                 claim_id=str(row["id"]))
                continue
            try:
                verdict = llm.parse_model_json(text)
            except ValueError as exc:
                error_log.record(step="chase", thinker="PIPELINE", exc=exc,
                                 retry_attempted=False, outcome="skipped",
                                 claim_id=str(row["id"]))
                continue
            if not verdict.get("has_external_origin"):
                continue
            origin_name = (verdict.get("origin_name") or "").strip()
            if origin_name:
                stats["origin_named"] += 1
            url = (verdict.get("origin_url") or "").strip()
            context = _context_window(row, row["full_text"])
            if not origin_name or verdict.get("confidence") == "low" \
                    or not _plausible_origin_url(url, row["source_url"], context):
                continue
            stats["origin_linked"] += 1

            if url not in fetched_docs:
                if stats["fetched"] >= args.fetch_cap:
                    continue
                existing = _existing_source_by_url(conn, url)
                if existing:
                    known = db.query_one(
                        conn, "SELECT full_text, date_published FROM sources WHERE id = %s",
                        (existing["id"],))
                    fetched_docs[url] = (
                        (known["full_text"] or "", known["date_published"])
                        if known else None)
                else:
                    stats["fetched"] += 1
                    try:
                        fetched_text, pub_date = fetch_article_text(url)
                    except Exception as exc:  # noqa: BLE001 — one dead link is routine
                        error_log.record(step="chase_fetch", thinker="PIPELINE", exc=exc,
                                         retry_attempted=False, outcome="skipped",
                                         source_url=url)
                        fetched_docs[url] = None
                        continue
                    if not fetched_text or len(fetched_text) < 400:
                        fetched_docs[url] = None
                        continue
                    fetched_docs[url] = (fetched_text, pub_date)

            cached = fetched_docs.get(url)
            if cached is None:
                continue
            doc_text, pub_date = cached
            # The only acceptance test: the number is verifiably in the
            # fetched document. No model opinion is consulted.
            if not claim_integrity.statistic_verifies(row["statistic"], doc_text):
                stats["unverified"] += 1
                continue
            stats["verified"] += 1
            existing = _existing_source_by_url(conn, url)
            primary_id = existing["id"] if existing else _insert_primary_source(
                conn, origin_name, url, doc_text, pub_date)
            db.execute(conn, "UPDATE claims SET primary_source_id = %s WHERE id = %s",
                       (primary_id, row["id"]))
            conn.commit()
            stats["repointed"] += 1

    _finish(run, orchestrated, cost_tracker, stats)
    print(f"\nPrimary chase done: {stats['repointed']}/{stats['examined']} claims "
          f"re-pointed to a verified primary source "
          f"({stats['origin_named']} named an origin, {stats['origin_linked']} linked one, "
          f"{stats['unverified']} failed verification against the fetch).")
    return stats["repointed"]


def _finish(run: RunLog, orchestrated: bool, cost_tracker: CostTracker, stats: dict) -> None:
    run.add_usage(cost=cost_tracker, detail={"primary_chase": stats})
    if not orchestrated:
        run.finish(status="ok")


if __name__ == "__main__":
    main()
