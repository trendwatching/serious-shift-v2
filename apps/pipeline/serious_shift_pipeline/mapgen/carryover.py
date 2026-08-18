"""What the last publication decided, carried into this one.

A synthesis run truncates the v2 tables and re-invents every name from the
prompts. Until now nothing carried across that boundary, and because
`export.py` derives each published slug from the name, a rename silently moved
a page: its artwork, its `shift_module_overrides` row, its `shift_refs`
identity and every innovation link pointing at it were all left behind. Each of
those is reported as a warning and none of them fails a run, which is why the
map could drift for weeks without anyone being told.

This module supplies the missing memory, and it is deliberately two separate
things:

  `load_published_taxonomy` — what phase 3 shows the model, so the prompt can
  ask for continuity instead of a blank sheet.

  `pin_slugs` — what `export.py` uses to decide a published slug. This is the
  half that actually protects anything. It runs at export because that is the
  one place every publish path passes through, and because the taxonomy is only
  final there: the targeted repair pass can re-cluster sub-shifts after phase 4
  has already run.

The division of labour matters. The prompt ASKS for stability and is free to be
ignored — the 18 Aug 2026 review was explicit that a run must never fail because
the model changed more than we hoped. Pinning is what makes that safe: when a
shift is renamed, it keeps its slug, so "more change than expected" costs a
label and not a page's identity. The two have to land together; the prompt alone
would be a wish, and pinning alone would freeze the map's vocabulary forever.
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher

from ..core.text import url_slug as slugify

#: How alike two slugs must be before we call the second a rename of the first
#: rather than a new shift. Measured on the SLUGS, in order, because word order
#: is meaning in a coined two-word name: "Trust Proxy" and "Proxy Trust" are two
#: shifts, and an order-insensitive measure (a stemmed token set) scores them
#: 1.0 and hands one of them the other's live URL.
#:
#: Calibrated against real names on the map:
#:   silent-commerce → silent-commerce-rising   0.81  rename
#:   proof-premium   → proof-premium-effect     0.79  rename
#:   capacity-collapse → capacity-crunch        0.62  distinct
#:   trust-proxy     → trust-collapse           0.56  distinct
#:   trust-proxy     → proxy-trust              0.45  distinct
#: The gap between 0.62 and 0.79 is where the line goes. Erring low is the
#: cheaper mistake: a missed rename mints a new URL and strands one page's art,
#: while a false rename hands a live URL — and its artwork, overrides and inbound
#: links — to a shift that is not the one readers bookmarked.
RENAME_SIMILARITY = 0.65


def _key(name: object) -> str:
    """The identity two names are compared on: `url_slug`, exactly as the URL does.

    Not a stemmed token set. Stemming would fold "Trust Proxy" and "Proxy
    Trust" into one shift, and word order is meaning in a coined two-word name.
    `url_slug` is the equivalence that actually governs identity here — two
    names that slugify the same ARE one page — so "Proof Premium", "proof
    premium" and "Proof  Premium" match, and nothing looser does.
    """
    return slugify(str(name or '')) or ''



def _similarity(a: object, b: object) -> float:
    """How alike two names are as URLs would see them, 0.0–1.0, order-sensitive."""
    left, right = _key(a), _key(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def load_published_taxonomy(conn) -> dict[str, list[dict]]:
    """The key shifts the site is serving right now, grouped by domain.

    Reads `documents['map']` — the document the backend actually serves, so
    what we carry forward is what a reader can see, not what some table happens
    to hold. Falls back to `shift_refs`, which survives the v2 truncation and
    therefore still answers after a half-finished run.

    Returns `{}` when there is no publication yet. That is the first-run case
    and every caller treats it as "no constraint", so a fresh database behaves
    exactly as it did before this module existed.
    """
    row = conn.execute(
        "SELECT body FROM documents WHERE key = 'map'").fetchone()
    if row and row['body']:
        body = row['body']
        if isinstance(body, str):
            body = json.loads(body)
        shifts = body.get('key_trends') if isinstance(body, dict) else None
        if isinstance(shifts, list) and shifts:
            out: dict[str, list[dict]] = {}
            for i, shift in enumerate(shifts):
                if not isinstance(shift, dict):
                    continue
                slug, name = shift.get('slug'), shift.get('name')
                if not slug or not name:
                    continue
                out.setdefault(str(shift.get('domain_id') or ''), []).append({
                    'slug': str(slug),
                    'name': str(name),
                    'subtitle': str(shift.get('subtitle') or ''),
                    'sort_order': i,
                })
            if out:
                return out

    # No document, or one with nothing usable in it. `shift_refs` is the
    # durable record of identity — it is written after every publication
    # precisely because `domain_key_trends.id` is recycled every week.
    refs = conn.execute("""
        SELECT slug, title, domain_id FROM shift_refs
         WHERE scope = 'key_trend' ORDER BY domain_id, slug
    """).fetchall()
    out = {}
    for i, ref in enumerate(refs):
        if not ref['slug'] or not ref['title']:
            continue
        out.setdefault(str(ref['domain_id'] or ''), []).append({
            'slug': str(ref['slug']),
            'name': str(ref['title']),
            'subtitle': '',
            'sort_order': i,
        })
    return out


def pin_slugs(rows: list[dict], previous: dict[str, list[dict]]) -> tuple[dict, dict]:
    """Decide each key shift's published slug, reusing the live one where we can.

    `rows` are this run's key shifts in export order — dicts carrying at least
    `id`, `domain_id` and `name`. `previous` is `load_published_taxonomy`'s
    output. Returns `(slug_by_row_id, report)`.

    Three passes, in this order, because each is more of a guess than the last:

      1. Same name, same domain — the shift did not move. Reuse its slug.
      2. Similar name, same domain — a rename. Reuse the slug anyway, which is
         the whole point: the page keeps its artwork, its overrides and its
         inbound links, and only its label changes.
      3. Anything left is genuinely new. Derive a fresh slug from the name.

    Matching is confined to a domain because a shift is not the same shift in a
    different sphere, and because `previous` is already grouped that way.
    Pass 2 is greedy over the best scores first so the outcome cannot depend on
    row order.

    `report` counts `carried`, `renamed`, `added` and `retired` for the run log.
    Nothing here fails, and nothing here is a gate — the 18 Aug 2026 review asked
    for drift to be steered by the prompt and never to fail a run.
    """
    # Every slug the last publication used is spoken for before anyone asks for
    # one — including the slugs of shifts that just retired. A retired slug looks
    # free, but artwork, overrides and innovation links are all keyed on it and
    # outlive the shift, so handing it to an unrelated newcomer would dress that
    # page in the departed shift's hero image and inherit its editor overrides.
    # Retired slugs are released by the next run, once a publication without them
    # has pruned what pointed at them.
    published: set[str] = {
        entry['slug'] for entries in previous.values() for entry in entries}
    #: Slugs a row of THIS run has been given. Kept apart from `published`
    #: because pass 2 must be able to claim a published slug (that is what a
    #: carry-forward is) while pass 3 must not (that is what reuse would be).
    claimed: set[str] = set()
    slug_by_id: dict = {}
    renames: list[tuple[str, str]] = []

    # Which previous shifts are still available to match against, per domain.
    unclaimed = {dom: list(entries) for dom, entries in previous.items()}

    # ── Pass 1: the name did not change ──────────────────────────────────
    unmatched: list[dict] = []
    for row in rows:
        dom = str(row.get('domain_id') or '')
        pool = unclaimed.get(dom) or []
        hit = next((p for p in pool if _key(p['name']) == _key(row.get('name'))), None)
        if hit is None:
            unmatched.append(row)
            continue
        pool.remove(hit)
        slug_by_id[row['id']] = hit['slug']
        claimed.add(hit['slug'])

    # ── Pass 2: the name changed, the shift did not ──────────────────────
    # Score every remaining pairing, then take them best-first so two new names
    # cannot race for the same predecessor.
    candidates = []
    for row in unmatched:
        dom = str(row.get('domain_id') or '')
        for prev in unclaimed.get(dom) or []:
            score = _similarity(row.get('name'), prev['name'])
            if score >= RENAME_SIMILARITY:
                candidates.append((score, str(row['id']), row, prev, dom))
    candidates.sort(key=lambda c: (-c[0], c[1]))

    still_unmatched = list(unmatched)
    for _score, _tie, row, prev, dom in candidates:
        if row['id'] in slug_by_id or prev['slug'] in claimed:
            continue
        pool = unclaimed.get(dom) or []
        if prev not in pool:
            continue
        pool.remove(prev)
        slug_by_id[row['id']] = prev['slug']
        claimed.add(prev['slug'])
        renames.append((prev['name'], str(row.get('name'))))
        still_unmatched.remove(row)

    # ── Pass 3: genuinely new shifts ─────────────────────────────────────
    # Globally unique, not per domain: `shift_refs` and `shift_module_overrides`
    # are both keyed on (scope, slug) with no domain, so two spheres coining the
    # same name must not produce the same slug. Disambiguating against `taken`
    # also means a new shift can never steal a slug still in use by a carried
    # one.
    for row in still_unmatched:
        base = slugify(str(row.get('name') or '')) or 'shift'
        slug, n = base, 1
        while slug in claimed or slug in published:
            n += 1
            slug = f'{base}-{n}'
        slug_by_id[row['id']] = slug
        claimed.add(slug)

    carried = len(rows) - len(unmatched)
    retired = sum(len(pool) for pool in unclaimed.values())
    report = {
        'carried': carried,
        'renamed': len(renames),
        'added': len(still_unmatched),
        'retired': retired,
        'renames': renames,
        'had_previous': bool(previous),
    }
    return slug_by_id, report
