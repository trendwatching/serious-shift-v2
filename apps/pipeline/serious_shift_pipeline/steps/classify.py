"""Map innovations onto the shifts they exemplify.

Why this is a pipeline step and not part of the ingest handler
--------------------------------------------------------------
`innovations.rs` is the one place the backend writes, and it stays that way. A
classifier there would need an Anthropic client, a second cost-tracking
implementation, and a paid call inside a synchronous request that upstream
retries on timeout. Worse, it could only ever score the one innovation in front
of it — and the thing that most often invalidates a classification is the
*shifts* changing, which happens weekly and touches every innovation at once.

So: a sweep. It runs hourly with the model disabled (pure Python and SQL; the
driving query returns zero rows when nothing has changed, so a quiet hour costs
one round trip), and once a week after `mapgen` with escalation enabled.
Upstream already has a zero-latency path when it knows the answer — the
`shifts` array in the ingest payload, written with source='ingest'.

Two SQL statements do the writing, and their WHERE clauses are the whole safety
story: an editor's link and an upstream link are untouchable, and a *disabled*
auto link is a veto that stays vetoed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

from dataclasses import replace

from ..core import config, db, llm, observability
from ..core.matching import (
    ACCEPT, FLOOR, MAX_KEY_LINKS, MAX_SUB_LINKS, SHORTLIST,
    Corpus, InnovationDoc, ShiftDoc, choose, is_ambiguous, normalize,
    score_all, weighted_terms,
)
from ..prompts import CLASSIFY_MODEL, classify_prompt

MODEL_ENABLED = os.environ.get('SS_CLASSIFY_MODEL', '1') not in ('0', 'false', 'no')
MODEL_CALLS_MAX = int(os.environ.get('SS_CLASSIFY_MODEL_CALLS_MAX', '200'))
ACCEPT_AT = float(os.environ.get('SS_CLASSIFY_ACCEPT', str(ACCEPT)))
FLOOR_AT = float(os.environ.get('SS_CLASSIFY_FLOOR', str(FLOOR)))

BUDGET = config.Budget(per_phase_usd={'classify': float(os.environ.get('SS_CLASSIFY_BUDGET_USD', '2'))})

#: Auto links sort after curated ones. `BY_SHIFT` caps a shift's card grid, so
#: when a shift is oversubscribed the editor's picks are the ones that survive.
AUTO_SORT_BASE = 100

# ── The 16 canonical sectors, for the industry facet ────────────────────────
SECTORS = [
    'Beauty & Personal Care', 'Consumer Tech', 'Digital Tech', 'Entertainment',
    'Fashion & Accessories', 'Financial Services', 'Food & Beverage',
    'Government & Public Sector', 'Health & Wellbeing', 'Home & Living',
    'Media & Publishing', 'Mobility & Transport', 'Nonprofit & Social Cause',
    'Retail & Commerce', 'Travel & Hospitality', 'Work & Education',
]
_SECTOR_BY_TOKEN = {s.split(' & ')[0].lower().replace(' ', '-'): s for s in SECTORS}


def sector_of(slug: str) -> str:
    """Upstream's industry slug → one of our 16 sectors, or ''.

    Substring rather than an exhaustive table: upstream's taxonomy is theirs to
    change, and a slug we cannot place should contribute nothing rather than
    fail the run.
    """
    key = (slug or '').lower()
    if key in _SECTOR_BY_TOKEN:
        return _SECTOR_BY_TOKEN[key]
    for token, sector in _SECTOR_BY_TOKEN.items():
        if token in key or key in token:
            return sector
    return ''


# ── Reading the published map ───────────────────────────────────────────────

def _module(modules, type_):
    for m in modules or []:
        if isinstance(m, dict) and m.get('type') == type_:
            return m.get('data') or {}
    return {}


def _shift_doc(row: dict, scope: str, parent_ref=None) -> ShiftDoc:
    modules = row.get('modules') or []
    from_to = _module(modules, 'from_to') or _module(modules, 'from_to_solid')
    needs = _module(modules, 'human_needs')
    territories = _module(modules, 'territories')
    industries = _module(modules, 'industries')
    tension = _module(modules, 'tension_band')
    panels = _module(modules, 'peel_tabs')
    lede = _module(modules, 'lede').get('text') or _module(modules, 'pull_quote').get('quote') or ''

    territories_text = ' '.join(
        f"{i.get('name', '')} {i.get('text', '')}" for i in (territories.get('items') or [])
    )
    sector_text = {
        i.get('name', ''): i.get('text', '')
        for i in (industries.get('items') or []) if isinstance(i, dict)
    }
    needs_text = f"{needs.get('unlocked', '')} {needs.get('threatened', '')}"

    # Multiplicity is how much a field says about what the shift IS. The name
    # and the from→to are the spine; a narrative panel is context.
    terms = weighted_terms([
        (row.get('name'), 4),
        (row.get('subtitle'), 3),
        (from_to.get('from'), 2),
        (from_to.get('to'), 2),
        (lede, 2),
        (' '.join(i.get('name', '') for i in (territories.get('items') or [])), 2),
        (tension.get('quote'), 1),
        (territories_text, 1),
        ((panels.get('whats_changing') or '')[:400], 1),
        # The sector NAMES only. Their prose is 16 paragraphs and would swamp a
        # 200-word spine; it is reachable through the facet channel instead.
        (' '.join(sector_text), 1),
    ])
    raw = ' '.join(filter(None, [row.get('name'), row.get('subtitle'), from_to.get('to'), territories_text]))
    return ShiftDoc(
        ref=f"{scope}:{row['slug']}", scope=scope, slug=row['slug'],
        domain_id=row.get('domain_id') or '', name=row.get('name') or '',
        parent_ref=parent_ref, terms=terms, sector_text=sector_text,
        needs_text=needs_text, territories_text=territories_text,
        to_text=from_to.get('to') or '', audience_text=tension.get('quote') or '',
        raw_lower=raw.lower(),
    )


def load_corpus(conn):
    """Every shift in the current publication, plus the hash that dates it."""
    body = db.scalar(conn, "SELECT body::text FROM documents WHERE key = 'map'")
    if not body:
        return None, None, {}
    doc = json.loads(body)
    kt_by_id = {k['id']: k for k in doc.get('key_trends') or []}
    shifts = [_shift_doc(k, 'key_trend') for k in kt_by_id.values() if k.get('slug')]
    ref_by_kt = {k['id']: f"key_trend:{k['slug']}" for k in kt_by_id.values() if k.get('slug')}
    for s in doc.get('sub_trends') or []:
        if s.get('slug'):
            shifts.append(_shift_doc(s, 'sub_trend', ref_by_kt.get(s.get('key_trend_id'))))

    digest = hashlib.sha256()
    for shift in sorted(shifts, key=lambda s: s.ref):
        digest.update(f'{shift.ref}|{shift.name}|{shift.to_text}\n'.encode())

    # shift_refs.id is what the links table points at. Only refs from the latest
    # publication are candidates, so a departed shift stops attracting links.
    ids = {
        f"{r['scope']}:{r['slug']}": r['id']
        for r in db.query(conn, """
            SELECT id, scope, slug FROM shift_refs
             WHERE last_published_at = (SELECT max(last_published_at) FROM shift_refs)
        """)
    }
    shifts = [s for s in shifts if s.ref in ids]
    return Corpus(shifts), digest.hexdigest(), ids


SWEEP = """
SELECT i.id, i.title, i.trendbite, i.body, i.brands_list,
       coalesce(json_object_agg(t.facet, t.slugs) FILTER (WHERE t.facet IS NOT NULL), '{}') AS tags
  FROM innovations i
  LEFT JOIN LATERAL (
        SELECT tg.facet, json_agg(tg.slug ORDER BY tg.slug) AS slugs
          FROM innovation_tag_links tl JOIN innovation_tags tg ON tg.id = tl.tag_id
         WHERE tl.innovation_id = i.id GROUP BY tg.facet
  ) t ON true
 WHERE i.state = 'active'
   AND (%(all)s OR i.classified_at IS NULL
        OR i.classified_corpus_hash IS DISTINCT FROM %(hash)s
        OR i.updated_at > i.classified_at)
 GROUP BY i.id
 ORDER BY i.updated_at DESC
 LIMIT %(limit)s
"""

# Retract auto links this pass no longer proposes. `AND enabled` is
# load-bearing: a disabled auto row is an editor's veto, and keeping the
# tombstone is what stops the next sweep resurrecting it.
RETRACT = """
DELETE FROM innovation_shift_links
 WHERE innovation_id = %s AND source = 'auto' AND enabled
   AND shift_ref_id <> ALL(%s::bigint[])
"""

# The WHERE on DO UPDATE is the safety property: a pair already owned by
# 'ingest' or 'editor' makes the row a no-op, so an automated pass can neither
# overwrite provenance nor touch a curator's confidence, order or note.
# `enabled` is deliberately absent from the SET list.
UPSERT = """
INSERT INTO innovation_shift_links
       (innovation_id, shift_ref_id, source, confidence, sort_order, note)
SELECT %s, ref_id, 'auto', conf, %s + rank, note
  FROM unnest(%s::bigint[], %s::real[], %s::int[], %s::text[])
       AS t(ref_id, conf, rank, note)
    ON CONFLICT (innovation_id, shift_ref_id) DO UPDATE
   SET confidence = EXCLUDED.confidence,
       sort_order = EXCLUDED.sort_order,
       note       = EXCLUDED.note,
       updated_at = now()
 WHERE innovation_shift_links.source = 'auto'
"""

OWNED = """
SELECT r.scope, r.slug, l.source
  FROM innovation_shift_links l JOIN shift_refs r ON r.id = l.shift_ref_id
 WHERE l.innovation_id = %s AND l.source IN ('ingest', 'editor')
"""


def _innovation_doc(row: dict) -> InnovationDoc:
    brands = list(row.get('brands_list') or [])
    tags = row.get('tags') or {}
    tag_words = ' '.join(s.replace('-', ' ') for slugs in tags.values() for s in slugs)
    return InnovationDoc(
        id=row['id'],
        terms=weighted_terms([
            (row.get('title'), 3),
            (row.get('trendbite'), 2),
            (' '.join(brands), 2),
            (tag_words, 2),
            ((row.get('body') or '')[:1200], 1),
        ]),
        tags=tags,
        brand_phrases=[b.lower() for b in brands if len(b) >= 4 and ' ' in b],
    )


def _escalate(row, corpus, keys, cost):
    """One Haiku call over the shortlist. Returns [(ref, confidence, note)]."""
    by_ref = {s.ref: s for s in corpus.shifts}
    catalogue = []
    for cand in keys[:SHORTLIST]:
        shift = by_ref.get(cand.ref)
        if shift:
            catalogue.append({
                'ref': shift.ref, 'domain': shift.domain_id, 'name': shift.name,
                'framing': shift.audience_text, 'from': '', 'to': shift.to_text,
            })
    if not catalogue:
        return []
    text, usage = llm.call(llm.Req(prompt=classify_prompt(row, catalogue), model=CLASSIFY_MODEL))
    cost.add(usage, model=CLASSIFY_MODEL)
    try:
        matches = (json.loads(text[text.index('{'):text.rindex('}') + 1]) or {}).get('matches') or []
    except (ValueError, KeyError):
        return []
    det = {c.ref: c.confidence for c in keys}
    out = []
    for m in matches:
        ref = m.get('ref')
        if ref not in det:
            continue
        # Blend, don't replace. The model is breaking a tie the arithmetic set
        # up, so both opinions count — and the cap keeps an escalated match from
        # ever outranking one the scorer was sure about on its own.
        model_conf = max(0.40, min(0.85, float(m.get('confidence') or 0)))
        blended = min(0.90, round(0.5 * det[ref] + 0.5 * model_conf, 3))
        if blended >= FLOOR_AT:
            out.append((ref, blended, str(m.get('reason') or '')[:200]))
    return out


def run(*, limit: int, do_all: bool, dry_run: bool, only: int | None) -> int:
    conn = db.connect()
    corpus, corpus_hash, ref_ids = load_corpus(conn)
    if not corpus or not corpus.shifts:
        print('  ⚠  no published map — nothing to classify against')
        return 0
    print(f'  corpus: {len(corpus.shifts)} shifts, hash {corpus_hash[:12]}')

    rows = db.query(conn, SWEEP, {'all': do_all, 'hash': corpus_hash, 'limit': limit})
    if only:
        rows = [r for r in rows if r['id'] == only]
    if not rows:
        print('  ✓  nothing to classify')
        return 0

    cost = observability.CostTracker(budget=BUDGET, phase='classify')
    calls = linked = 0
    model_on = MODEL_ENABLED
    for row in rows:
        innovation = _innovation_doc(row)
        owned = {f"{r['scope']}:{r['slug']}" for r in db.query(conn, OWNED, (row['id'],))}
        key_budget = MAX_KEY_LINKS - sum(1 for r in owned if r.startswith('key_trend:'))
        sub_budget = MAX_SUB_LINKS - sum(1 for r in owned if r.startswith('sub_trend:'))
        picks, notes = [], {}
        if key_budget > 0 or sub_budget > 0:
            scored = score_all(corpus, innovation, sector_of, exclude=owned)
            keys = [s for s in scored if s.scope == 'key_trend']
            escalate = (
                model_on and not dry_run and calls < MODEL_CALLS_MAX
                and is_ambiguous(keys, accept=ACCEPT_AT, floor=FLOOR_AT)
            )
            verdict = None
            if escalate:
                calls += 1
                try:
                    verdict = _escalate(row, corpus, keys, cost)
                except config.BudgetExceeded:
                    # Spending the budget is not a failure: the deterministic
                    # answer is still a good answer, so stop escalating and
                    # finish the sweep rather than abandoning it half-written.
                    print('  ⚠  classify budget reached — finishing deterministically')
                    model_on = False
                    verdict = None
            if verdict is None:
                picks = choose(scored, key_budget=key_budget, sub_budget=sub_budget, accept=ACCEPT_AT)
            else:
                by_ref = {s.ref: s for s in scored}
                picks = [replace(by_ref[ref], confidence=conf) for ref, conf, _ in verdict
                         if ref in by_ref][:key_budget]
                notes = {ref: note for ref, _, note in verdict if note}

        ids, confs, ranks, texts = [], [], [], []
        for rank, pick in enumerate(picks):
            ref_id = ref_ids.get(pick.ref)
            if not ref_id:
                continue
            ids.append(ref_id)
            confs.append(pick.confidence)
            ranks.append(rank)
            texts.append(notes.get(pick.ref) or pick.note)

        if dry_run:
            print(f'  · {row["id"]} {row["title"][:52]!r} → '
                  + (', '.join(f'{p.ref} {p.confidence}' for p in picks) or '(none)'))
            continue

        db.execute(conn, RETRACT, (row['id'], ids))
        if ids:
            db.execute(conn, UPSERT, (row['id'], AUTO_SORT_BASE, ids, confs, ranks, texts))
            linked += len(ids)
        db.execute(conn,
                   'UPDATE innovations SET classified_at = now(), classified_corpus_hash = %s WHERE id = %s',
                   (corpus_hash, row['id']))
        conn.commit()

    verb = 'would link' if dry_run else 'linked'
    print(f'  ✓  {len(rows)} innovation(s) swept, {verb} {linked}, {calls} model call(s), '
          f'${cost.total_usd:.4f}')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description='Map innovations onto the shifts they exemplify.')
    ap.add_argument('--limit', type=int, default=500)
    ap.add_argument('--all', action='store_true', help='re-classify everything, ignoring freshness')
    ap.add_argument('--dry-run', action='store_true', help='print the ranking, write nothing')
    ap.add_argument('--innovation', type=int, default=None, help='one innovation id')
    args = ap.parse_args()
    print('\nClassify — mapping innovations onto shifts…')
    return run(limit=args.limit, do_all=args.all, dry_run=args.dry_run, only=args.innovation)


if __name__ == '__main__':
    sys.exit(main())
