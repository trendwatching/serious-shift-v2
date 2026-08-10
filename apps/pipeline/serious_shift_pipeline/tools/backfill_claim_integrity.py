#!/usr/bin/env python3
"""
backfill_claim_integrity.py — sweep existing claims against their source text.

Extraction historically inserted `quote` and `statistic` verbatim from the
model with no check against `sources.full_text`; the 2026-08-10 audit found
published numbers no source ever said ("1,337 employees", "$200 billion").
New ingests are verified at insert (steps/process_raw.py); this tool applies
the same verifier (core/claim_integrity.py) to everything already in the DB.

Downgrade-only, never delete: a failing quote is emptied, a failing statistic
clears has_statistic. Claims whose source has no stored full_text are left
untouched — absence of the source is not evidence against the claim.

Usage:
    DATABASE_URL=... python -m serious_shift_pipeline.tools.backfill_claim_integrity
    ... --apply         # write the downgrades (default is a dry run)

After --apply, re-run scoring and evaluation so ranking sees the cleaned flags:
    python -m serious_shift_pipeline.steps.scoring
    python -m serious_shift_pipeline.steps.evaluate
"""
from __future__ import annotations

import argparse

from ..core import db
from ..core.claim_integrity import quote_verifies, statistic_verifies

BATCH = 500
SAMPLES = 10


def sweep(conn, apply: bool) -> tuple[dict[str, int], list[str]]:
    counts: dict[str, int] = {"checked": 0, "no_source_text": 0,
                              "quote_dropped": 0, "statistic_dropped": 0}
    samples: list[str] = []
    last_id = 0
    while True:
        rows = db.query(conn, """
            SELECT c.id, c.quote, c.has_statistic, c.statistic, s.full_text
            FROM claims c JOIN sources s ON s.id = c.source_id
            WHERE c.id > %s
              AND (COALESCE(c.quote, '') <> '' OR c.has_statistic)
            ORDER BY c.id LIMIT %s""", (last_id, BATCH))
        if not rows:
            break
        for r in rows:
            last_id = r["id"]
            counts["checked"] += 1
            if not (r["full_text"] or "").strip():
                counts["no_source_text"] += 1
                continue
            drop_quote = bool(r["quote"]) and not quote_verifies(r["quote"], r["full_text"])
            drop_stat = bool(r["has_statistic"]) and not statistic_verifies(
                r["statistic"] or "", r["full_text"])
            if drop_quote:
                counts["quote_dropped"] += 1
                if len(samples) < SAMPLES:
                    samples.append(f"  c{r['id']} quote: {str(r['quote'])[:90]!r}")
            if drop_stat:
                counts["statistic_dropped"] += 1
                if len(samples) < SAMPLES:
                    samples.append(f"  c{r['id']} stat:  {str(r['statistic'])[:90]!r}")
            if apply and (drop_quote or drop_stat):
                db.execute(conn, """
                    UPDATE claims SET
                        quote = CASE WHEN %s THEN '' ELSE quote END,
                        has_statistic = CASE WHEN %s THEN FALSE ELSE has_statistic END,
                        statistic = CASE WHEN %s THEN NULL ELSE statistic END
                    WHERE id = %s""", (drop_quote, drop_stat, drop_stat, r["id"]))
    return counts, samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--apply", action="store_true",
                        help="write the downgrades (default: dry run, no writes)")
    args = parser.parse_args()

    with db.connect() as conn:
        counts, samples = sweep(conn, apply=args.apply)

    mode = "APPLIED" if args.apply else "DRY RUN (no writes)"
    print(f"claim integrity backfill — {mode}")
    print(f"  claims checked:        {counts['checked']}")
    print(f"  skipped (no source):   {counts['no_source_text']}")
    print(f"  quotes dropped:        {counts['quote_dropped']}")
    print(f"  statistics dropped:    {counts['statistic_dropped']}")
    if samples:
        print("sample offenders:")
        for line in samples:
            print(line)
    if not args.apply and (counts["quote_dropped"] or counts["statistic_dropped"]):
        print("re-run with --apply to write, then re-run steps.scoring and steps.evaluate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
