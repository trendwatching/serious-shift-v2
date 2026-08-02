"""Parse model responses into the shapes the phases write.

Every parser is total: malformed output yields an empty result rather than
raising, because one bad response must not lose a whole phase.
"""
from __future__ import annotations

import unicodedata


def _normalise(text: str) -> str:
    """Collapse whitespace and unify quote glyphs, for verbatim comparison.

    Models reliably re-wrap lines and swap ' for \u2019 while otherwise copying
    exactly. Those differences are not misattribution, so they must not cause a
    true quote to be rejected — everything else must.
    """
    t = unicodedata.normalize('NFKC', text or '')
    for a, b in (('\u2019', "'"), ('\u2018', "'"), ('\u201c', '"'), ('\u201d', '"'),
                 ('\u2014', '-'), ('\u2013', '-')):
        t = t.replace(a, b)
    return ' '.join(t.split()).strip().lower()


def parse_thinker_attribution(raw, thinker_groups: dict | None = None) -> dict:
    """Return {'proponents': [{name, quote}], 'skeptics': [...]}.

    Every entry is verified against the evidence that was sent in: the quote must
    match one of that thinker's verbatim `quote` spans, and the name must be a
    thinker we actually supplied. Anything else is dropped.

    This is a check, not a request. The prompt asks for verbatim quotes, but the
    UI publishes the result inside quotation marks under a real person's name —
    so "the model was told not to" is not a strong enough guarantee. Before this
    existed, paraphrases written by our own extractor were rendered as things
    Satya Nadella said.

    `thinker_groups` is optional only for back-compat with callers that have no
    evidence to check against; without it nothing can be verified, so every
    entry is dropped rather than trusted.
    """
    result: dict[str, list] = {'proponents': [], 'skeptics': []}
    if not isinstance(raw, dict):
        return result

    # {thinker name -> {normalised quote -> original quote}}
    allowed: dict[str, dict[str, str]] = {}
    for name, clms in (thinker_groups or {}).items():
        quotes = {}
        for c in clms:
            q = (c.get('quote') or '').strip() if isinstance(c, dict) else ''
            if q:
                quotes[_normalise(q)] = q
        allowed[_normalise(name)] = quotes

    for k in ('proponents', 'skeptics'):
        for x in raw.get(k, []) or []:
            if not isinstance(x, dict) or not x.get('name'):
                continue
            name = str(x['name']).strip()
            said = allowed.get(_normalise(name))
            if not said:
                continue  # not a thinker we supplied, or they had no quotes
            verbatim = said.get(_normalise(str(x.get('quote', ''))))
            if not verbatim:
                continue  # not something this thinker demonstrably said
            # Store OUR copy of the quote, not the model's, so any whitespace or
            # punctuation drift never reaches the page.
            result[k].append({'name': name, 'quote': verbatim})
    return result


def _collect_by_thinker(claims: list, max_per: int = 8, *, curated_only: bool = False) -> dict:
    """Group claims by thinker.

    `curated_only` drops auto-discovered entities. They are paper co-authors the
    ingest created on the fly, and their credibility score comes from a venue
    authority fallback rather than any track record — so presenting them in
    "Who is saying this" beside named public figures overstates what we know
    about them. 22 of 70 voices were such names before this.
    """
    grouped: dict = {}
    for c in claims:
        t = c.get('thinker', '')
        if not t:
            continue
        if curated_only and c.get('thinker_discovered'):
            continue
        grouped.setdefault(t, [])
        if len(grouped[t]) < max_per:
            grouped[t].append(c)
    return grouped


# ── Phase 7: Interrelatedness ───────────────────────────────────────────────

def parse_interrelatedness_batch(raw) -> list:
    VALID = {'reinforces','contradicts','prerequisite_for','competes_with','accelerated_by'}
    if isinstance(raw, dict):
        for k in ('links','relationships','edges','results','data'):
            if k in raw and isinstance(raw[k], list):
                raw = raw[k]; break
        else:
            raw = []
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            src = item.get('source_id')
            tgt = item.get('target_id')
            rel = item.get('relationship','')
            str_ = float(item.get('strength',0))
            rsn = str(item.get('reasoning',''))
            if src is None or tgt is None or str_ < 0.4 or rel not in VALID:
                continue
            result.append({'source_id': str(src), 'target_id': str(tgt),
                           'relationship': rel, 'strength': str_, 'reasoning': rsn})
        except (TypeError, ValueError):
            continue
    return result


# ── Phase 8: Synthesis insights per domain ──────────────────────────────────

def parse_synthesis_insights(raw) -> list:
    if isinstance(raw, dict):
        raw = raw.get('insights', [])
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get('name','').strip()
        desc = item.get('description','').strip()
        ids  = [int(c) for c in item.get('contributing_claim_ids',[])
                if isinstance(c, (int,float)) and not isinstance(c, bool)]
        if name and desc and ids:
            result.append({'name': name, 'description': desc, 'contributing_claim_ids': ids})
    return result
