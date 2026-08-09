#!/usr/bin/env python3
"""
calibrate_classifier.py — what the innovation→shift classifier would decide, and
at which threshold.

Why this exists
---------------
`ACCEPT` is one number that decides whether every innovation reaches a page, and
it was wrong for a year without anyone being able to see it. The value shipped
(0.72) was the one that made a two-shift unit-test fixture pass; against the real
306-shift corpus nothing could reach it, so the classifier linked nothing, said
`0 model call(s), $0.0000`, and looked perfectly healthy doing it.

The failure was not the number. It was that no instrument existed that would have
shown the number was wrong. `classify --dry-run` prints what won — it cannot show
what a different threshold would have chosen, which is the entire question.

So this scores every active innovation against the live corpus and prints, per
innovation: the channels it can be judged on, the top candidates with the lexical
/ facet / brand contributions separated, and the decision each candidate
threshold would make. Run it before moving `ACCEPT`, and again whenever the
upstream pushes a batch — with `--record`, the fixture diff *is* the calibration
review.

It imports the scoring rather than reimplementing it. A harness with its own copy
of the maths measures the harness.

Usage
-----
  DATABASE_URL=... python -m serious_shift_pipeline.tools.calibrate_classifier
  DATABASE_URL=... python -m serious_shift_pipeline.tools.calibrate_classifier --innovation 5
  DATABASE_URL=... python -m serious_shift_pipeline.tools.calibrate_classifier --record

Read-only unless `--record` is passed, and even then it writes only a test
fixture on local disk. It never touches the database.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..core import db, matching as m
from ..steps import classify as C

DEFAULT_THRESHOLDS = (0.45, 0.50, 0.55, 0.60, 0.72)
FIXTURE = Path(__file__).resolve().parents[2] / 'tests' / 'fixtures' / 'classifier_calibration.json'


def _facet_share(corpus, innovation, shift) -> tuple[float, int]:
    """(share of available facet weight that hit, number of facets carried).

    `facet()` already returns exactly that share — `hits` and `weight` are both
    sums of `FACET_WEIGHTS`, not counts — so this reports it rather than trying
    to recover a hit count from it. The facet channel is the one most likely to
    be silently dead and the one carrying the most weight when it fires, which
    is why it gets its own column.
    """
    carried = sum(1 for f in m.FACET_WEIGHTS if innovation.tags.get(f))
    if not carried:
        return 0.0, 0
    return m.facet(corpus, innovation, shift, C.sector_of), carried


def collect(conn, *, top: int, only: int | None) -> tuple[dict, list[dict]]:
    corpus, corpus_hash, ref_ids = C.load_corpus(conn)
    if not corpus or not corpus.shifts:
        print('  ⚠  no published map — nothing to calibrate against', file=sys.stderr)
        return {}, []

    rows = db.query(conn, C.SWEEP, {'all': True, 'hash': corpus_hash, 'limit': 500})
    if only:
        rows = [r for r in rows if r['id'] == only]

    out = []
    for row in sorted(rows, key=lambda r: r['id']):
        innovation = C._innovation_doc(row)
        owned = {f"{r['scope']}:{r['slug']}" for r in db.query(conn, C.OWNED, (row['id'],))}
        scored = m.score_all(corpus, innovation, C.sector_of, exclude=owned)
        keys = [s for s in scored if s.scope == 'key_trend']
        best = keys[0] if keys else None
        share, carried = _facet_share(corpus, innovation, next(
            (s for s in corpus.shifts if best and s.ref == best.ref), corpus.shifts[0]))
        out.append({
            'id': row['id'],
            'title': row['title'],
            'scale': round(m.available_weight(innovation), 2),
            'facet_share_at_top1': round(share, 3),
            'facets_carried': carried,
            'owned': sorted(owned),
            'key_budget': max(0, m.MAX_KEY_LINKS - sum(1 for r in owned if r.startswith('key_trend:'))),
            'sub_budget': max(0, m.MAX_SUB_LINKS - sum(1 for r in owned if r.startswith('sub_trend:'))),
            'scored': [
                {'ref': s.ref, 'scope': s.scope, 'parent_ref': s.parent_ref,
                 'conf': s.confidence, 'lex': round(s.lexical, 3),
                 'facet': round(s.facet, 3), 'brand': round(s.brand, 3)}
                for s in scored[:max(top, 8)]
            ],
        })
    return {'corpus_hash': corpus_hash, 'shifts': len(corpus.shifts)}, out


def decisions(entry: dict, threshold: float) -> list[str]:
    """Replay `choose` at one threshold, from recorded scores only."""
    scored = [m.Scored(s['ref'], s['scope'], s['parent_ref'], s['conf'],
                       s['lex'], s['facet'], s['brand']) for s in entry['scored']]
    picks = m.choose(
        scored, key_budget=entry['key_budget'], sub_budget=entry['sub_budget'],
        accept=threshold,
        owned_parents={r for r in entry['owned'] if r.startswith('key_trend:')},
    )
    return [p.ref for p in picks]


def report(meta: dict, entries: list[dict], thresholds, top: int) -> None:
    print(f"\ncorpus: {meta['shifts']} shifts  hash={meta['corpus_hash'][:12]}")
    print(f"accept in force: {m.ACCEPT:.2f}   floor: {m.FLOOR:.2f}\n")

    head = f"  {'id':>4} {'scale':>5} {'facet':>6}  {'innovation':<40}"
    print(head + "".join(f"{t:>7.2f}" for t in thresholds))
    print("  " + "-" * (len(head) + 7 * len(thresholds)))

    for e in entries:
        marks = "".join(f"{len(decisions(e, t)) or '-':>7}" for t in thresholds)
        facet = f"{e['facet_share_at_top1']:.0%}" if e['facets_carried'] else '—'
        print(f"  {e['id']:>4} {e['scale']:>5.2f} {facet:>6}  {e['title'][:40]:<40}{marks}")
        for s in e['scored'][:top]:
            print(f"        {s['conf']:.3f}  {s['ref'][:46]:<48}"
                  f"lex {s['lex']:.3f}  facet {s['facet']:.2f}  brand {s['brand']:.2f}")
        if e['owned']:
            print(f"        owned (live): {', '.join(e['owned'])}")
        print()

    print("  threshold sweep")
    for t in thresholds:
        linked = [e for e in entries if decisions(e, t)]
        n_links = sum(len(decisions(e, t)) for e in entries)
        share = f"{len(linked) / len(entries):.0%}" if entries else "—"
        print(f"    T={t:.2f}   {len(linked):>3}/{len(entries)} innovations ({share:>4}), "
              f"{n_links:>3} links written")

    tops = sorted(e['scored'][0]['conf'] for e in entries if e['scored'])
    if tops:
        pct = lambda q: tops[min(len(tops) - 1, int(q * len(tops)))]  # noqa: E731
        print(f"\n  top-1 confidence   p10 {pct(0.10):.3f}   p50 {pct(0.50):.3f}   p90 {pct(0.90):.3f}")
    tagged = [e for e in entries if e['facets_carried']]
    if tagged:
        hit = sum(1 for e in tagged if e['facet_share_at_top1'] > 0)
        print(f"  facet channel      {hit}/{len(tagged)} tagged innovations hit at top-1 "
              f"({hit / len(tagged):.0%})")
        print("  (below ~10% the fix is FACET_HIT_IDF or a wider facet target, "
              "NOT available_weight — see matching.py)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--top', type=int, default=3, help='candidates shown per innovation')
    ap.add_argument('--innovation', type=int, default=None, help='one innovation id')
    ap.add_argument('--thresholds', default=','.join(str(t) for t in DEFAULT_THRESHOLDS))
    ap.add_argument('--record', action='store_true',
                    help=f'write {FIXTURE.name} for the DB-free calibration test')
    args = ap.parse_args()
    thresholds = [float(t) for t in args.thresholds.split(',') if t.strip()]

    with db.connect() as conn:
        meta, entries = collect(conn, top=args.top, only=args.innovation)
    if not entries:
        print('  no active innovations to calibrate against')
        return 0

    report(meta, entries, thresholds, args.top)

    if args.record:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps({'meta': meta, 'innovations': entries},
                                      indent=1, sort_keys=True) + '\n')
        print(f"\n  recorded → {FIXTURE}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
