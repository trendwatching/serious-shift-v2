#!/usr/bin/env python3
"""Load a curated roster-expansion seed file into thinkers + scrape_sources.

The seed is a reviewed JSON array (see packages/db/seeds/) produced by the
roster research: each entry names a thinker/org, its diversity axes
(stance/region/discipline/incentive — the columns routing spreads on), a
one-line rationale, and the scrapeable sources with their handler method.

Idempotent: an existing thinker is updated in place (axes + bio only — scores
and history are never touched), an existing (thinker, method, url) source row
is skipped. Nothing is deleted. Dry-run by default; --execute writes.

Usage:
  DATABASE_URL=... python -m serious_shift_pipeline.tools.load_roster \
      --seed packages/db/seeds/roster_expansion_2026-08.json [--execute]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from ..core import db

VALID_STANCE = {"advocate", "critic", "analyst"}
VALID_METHODS = {"rss", "substack", "org_blog", "scrape_index", "youtube",
                 "arxiv_author", "arxiv_category", "openalex_query"}
VALID_KINDS = {"person", "org", "publication"}


def _clean_entry(entry: dict) -> tuple[dict | None, str | None]:
    """(normalized entry, None) or (None, reason it was rejected)."""
    name = (entry.get("name") or "").strip()
    if not name:
        return None, "missing name"
    stance = (entry.get("stance") or "").strip() or None
    if stance is not None and stance not in VALID_STANCE:
        return None, f"{name}: bad stance {stance!r}"
    kind = (entry.get("entity_kind") or "person").strip()
    if kind not in VALID_KINDS:
        return None, f"{name}: bad entity_kind {kind!r}"
    sources = []
    for src in entry.get("sources") or []:
        method = (src.get("method") or "").strip()
        url = (src.get("url") or "").strip()
        rss = (src.get("rss") or "").strip()
        channel = (src.get("channel_url") or "").strip()
        if method not in VALID_METHODS:
            continue
        if not (url or rss or channel):
            continue
        sources.append({
            "platform": (src.get("platform") or method).strip(),
            "method": method,
            "url": url or None,
            "rss": rss or None,
            "channel_url": channel or None,
        })
    if not sources:
        return None, f"{name}: no usable sources"
    return {
        "name": name[:200],
        "entity_kind": kind,
        "stance": stance,
        "region": (entry.get("region") or "").strip() or None,
        "discipline": (entry.get("discipline") or "").strip() or None,
        "incentive": (entry.get("incentive") or "").strip() or None,
        "bio": (entry.get("why") or "").strip() or None,
        "sources": sources,
    }, None


def load_seed(path: str) -> tuple[list[dict], list[str]]:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, list):
        sys.exit("ERROR: seed must be a JSON array")
    entries, rejects = [], []
    for item in raw:
        entry, reason = _clean_entry(item if isinstance(item, dict) else {})
        if entry:
            entries.append(entry)
        else:
            rejects.append(reason or "unparseable entry")
    return entries, rejects


def apply(conn, entries: list[dict], execute: bool) -> dict:
    stats: Counter[str] = Counter()
    for entry in entries:
        existing = db.query_one(conn, "SELECT id FROM thinkers WHERE name = %s",
                                (entry["name"],))
        if existing:
            stats["thinkers_updated"] += 1
            thinker_id = existing["id"]
            if execute:
                db.execute(conn, """UPDATE thinkers SET entity_kind = %s,
                    stance = %s, region = %s, discipline = %s, incentive = %s,
                    bio = COALESCE(NULLIF(%s, ''), bio), updated_at = now()
                    WHERE id = %s""",
                    (entry["entity_kind"], entry["stance"], entry["region"],
                     entry["discipline"], entry["incentive"], entry["bio"] or "",
                     thinker_id))
        else:
            stats["thinkers_new"] += 1
            thinker_id = None
            if execute:
                thinker_id = db.insert_returning_id(conn, """INSERT INTO thinkers
                    (name, entity_kind, stance, region, discipline, incentive, bio)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (entry["name"], entry["entity_kind"], entry["stance"],
                     entry["region"], entry["discipline"], entry["incentive"],
                     entry["bio"]))
        for src in entry["sources"]:
            if thinker_id is not None:
                dup = db.query_one(conn, """SELECT id FROM scrape_sources
                    WHERE thinker_id = %s AND method = %s
                      AND COALESCE(url, '') = COALESCE(%s, '')
                      AND COALESCE(rss, '') = COALESCE(%s, '')
                      AND COALESCE(channel_url, '') = COALESCE(%s, '')""",
                    (thinker_id, src["method"], src["url"], src["rss"],
                     src["channel_url"]))
                if dup:
                    stats["sources_existing"] += 1
                    continue
            stats["sources_new"] += 1
            if execute and thinker_id is not None:
                db.execute(conn, """INSERT INTO scrape_sources
                    (thinker_id, platform, method, url, rss, channel_url)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (thinker_id, src["platform"], src["method"], src["url"],
                     src["rss"], src["channel_url"]))
    if execute:
        conn.commit()
    return dict(stats)


def diversity_report(conn) -> None:
    """Roster spread on the axes routing balances — 'unlabeled' is the debt."""
    print("\nRoster diversity after load:")
    for axis in ("stance", "region", "discipline", "incentive"):
        rows = db.query(conn, f"""SELECT COALESCE({axis}, 'unlabeled') AS v,
            COUNT(*) AS n FROM thinkers WHERE NOT discovered
            GROUP BY 1 ORDER BY n DESC""")
        line = ", ".join(f"{r['v']} {r['n']}" for r in rows)
        print(f"  {axis:<11} {line}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Load roster expansion seed")
    parser.add_argument("--seed", required=True)
    parser.add_argument("--execute", action="store_true",
                        help="write to the DB (default: dry-run report only)")
    args = parser.parse_args()

    entries, rejects = load_seed(args.seed)
    print(f"Seed: {len(entries)} usable entries, {len(rejects)} rejected")
    for reason in rejects[:15]:
        print(f"  ✗ {reason}")

    with db.connect() as conn:
        stats = apply(conn, entries, execute=args.execute)
        mode = "APPLIED" if args.execute else "DRY-RUN (pass --execute to write)"
        print(f"\n{mode}: {stats}")
        if args.execute:
            diversity_report(conn)
    return 0


if __name__ == "__main__":
    main()
