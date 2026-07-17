#!/usr/bin/env python3
"""
Claim scoring (Postgres): source_depth, freshness_score, claim_weight.

Consolidates the legacy add_source_depth.py + add_freshness.py into one free
(no-API) maintenance step. Run it after process_raw so newly-extracted claims
get ranked — the map/keynote queries order by claim_weight.

  source_depth  : 1-5 from source length (type overrides for essays / tweets)
  freshness     : recency tier, boosted to 1.0 for validated thinker+domain,
                  halved for each older claim in a thinker+domain+concept group
  claim_weight  : (source_depth/5) * signal_numeric * (specificity/5) * freshness

Usage:  DATABASE_URL=... python -m serious_shift_pipeline.steps.scoring [--dry-run]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime

from ..core import db

SIGNAL_NUMERIC = {"strong_signal": 1.0, "signal": 0.7, "background": 0.3, "noise": 0.1}
MIN_DEPTH_BY_TYPE = {"essay": 4, "book": 4, "policy_paper": 4}
MAX_DEPTH_BY_TYPE = {"tweet_thread": 2, "social_media": 2}


def depth_from_chars(n: int) -> int:
    if n >= 50_000:
        return 5
    if n >= 25_000:
        return 4
    if n >= 10_000:
        return 3
    if n >= 2_500:
        return 2
    return 1


def base_freshness(date_value, today: date) -> float:
    """Recency tier in [0.1, 1.0]; unknown/unparseable dates get 0.4."""
    if not date_value:
        return 0.4
    try:
        pub = datetime.strptime(str(date_value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return 0.4
    age = (today - pub).days
    if age <= 90:
        return 1.0          # future-dated or last 3 months
    if age <= 180:
        return 0.8
    if age <= 365:
        return 0.6
    if age <= 730:
        return 0.4
    if age <= 1095:
        return 0.2
    return 0.1


def score_sources(conn, dry_run: bool) -> dict:
    """Compute + write sources.source_depth; return {source_id: depth}."""
    claim_chars = {
        r["source_id"]: r["n"] or 0
        for r in db.query(conn, "SELECT source_id, SUM(LENGTH(claim_text)) AS n FROM claims GROUP BY source_id")
    }
    depth_map = {}
    for s in db.query(conn, "SELECT id, source_type, full_text FROM sources"):
        chars = len(s["full_text"]) if s["full_text"] else claim_chars.get(s["id"], 0)
        depth = depth_from_chars(chars)
        st = s["source_type"] or ""
        if st in MIN_DEPTH_BY_TYPE:
            depth = max(depth, MIN_DEPTH_BY_TYPE[st])
        if st in MAX_DEPTH_BY_TYPE:
            depth = min(depth, MAX_DEPTH_BY_TYPE[st])
        depth_map[s["id"]] = depth
        if not dry_run:
            db.execute(conn, "UPDATE sources SET source_depth = %s WHERE id = %s", (depth, s["id"]))
    return depth_map


def score_claims(conn, depth_map: dict, today: date, dry_run: bool) -> int:
    """Compute + write claims.freshness_score and claims.claim_weight."""
    claims = db.query(conn, """
        SELECT c.id, c.thinker_id, c.source_id, c.domain, c.signal_strength,
               c.specificity, s.date_published
        FROM claims c LEFT JOIN sources s ON c.source_id = s.id""")
    validated = {
        (r["thinker_id"], r["domain"])
        for r in db.query(conn, "SELECT thinker_id, domain FROM predictions WHERE status IN ('true','partially_true')")
    }
    claim_concepts = defaultdict(set)
    for r in db.query(conn, "SELECT claim_id, concept_id FROM claim_concepts"):
        claim_concepts[r["claim_id"]].add(r["concept_id"])

    # base recency, then validated boost
    freshness = {c["id"]: base_freshness(c["date_published"], today) for c in claims}
    for c in claims:
        if (c["thinker_id"], c["domain"] or "technology_capability") in validated:
            freshness[c["id"]] = 1.0

    # superseded penalty: in each thinker+domain+concept group, every claim
    # older than the newest is halved (compounding across groups).
    groups = defaultdict(list)
    claim_dates = {}
    for c in claims:
        dom = c["domain"] or "technology_capability"
        claim_dates[c["id"]] = str(c["date_published"] or "2024-01-01")[:10]
        concepts = claim_concepts.get(c["id"])
        if concepts:
            for con in concepts:
                groups[(c["thinker_id"], dom, con)].append(c["id"])
        else:
            groups[(c["thinker_id"], dom, None)].append(c["id"])
    for ids in groups.values():
        if len(ids) < 2:
            continue
        for cid in sorted(ids, key=lambda i: claim_dates.get(i, ""), reverse=True)[1:]:
            freshness[cid] *= 0.5
    for cid in freshness:
        freshness[cid] = max(0.01, min(1.0, freshness[cid]))

    for c in claims:
        depth = depth_map.get(c["source_id"]) or 3
        sig = SIGNAL_NUMERIC.get(c["signal_strength"], 0.5)
        spec = (c["specificity"] or 3) / 5.0
        weight = round((depth / 5.0) * sig * spec * freshness[c["id"]], 4)
        if not dry_run:
            db.execute(conn, "UPDATE claims SET freshness_score = %s, claim_weight = %s WHERE id = %s",
                       (freshness[c["id"]], weight, c["id"]))
    return len(claims)


def main():
    ap = argparse.ArgumentParser(description="Score source_depth, freshness, and claim_weight")
    ap.add_argument("--dry-run", action="store_true", help="Compute but write nothing")
    args = ap.parse_args()
    today = date.today()
    with db.connect() as conn:
        depth_map = score_sources(conn, args.dry_run)
        n_claims = score_claims(conn, depth_map, today, args.dry_run)
    suffix = " (dry-run, no writes)" if args.dry_run else ""
    print(f"Scored {len(depth_map)} sources and {n_claims} claims{suffix}.")


if __name__ == "__main__":
    main()
