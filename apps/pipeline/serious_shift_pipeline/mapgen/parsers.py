"""Parse model responses into the shapes the phases write.

Every parser is total: malformed output yields an empty result rather than
raising, because one bad response must not lose a whole phase.
"""
from __future__ import annotations


def parse_thinker_attribution(raw) -> dict:
    """Return {'proponents': [{name, quote}], 'skeptics': [...]}. Accepts either the
    new object form or a bare name list (back-compat)."""
    result: dict[str, list] = {'proponents': [], 'skeptics': []}
    if not isinstance(raw, dict):
        return result
    for k in ('proponents', 'skeptics'):
        for x in raw.get(k, []) or []:
            if isinstance(x, dict) and x.get('name'):
                result[k].append({'name': str(x['name']), 'quote': str(x.get('quote', ''))})
            elif isinstance(x, str) and x:
                result[k].append({'name': x, 'quote': ''})
    return result


def _collect_by_thinker(claims: list, max_per: int = 8) -> dict:
    grouped: dict = {}
    for c in claims:
        t = c.get('thinker', '')
        if not t:
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
