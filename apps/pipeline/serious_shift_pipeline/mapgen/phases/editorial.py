"""Phase 4b — editorial prose for Key Trends and their sub-trends."""
from __future__ import annotations

import re

from ...prompts import prompt_kt_editorial, prompt_st_editorial
from ..config import CLAIMS_PER_KT, DOMAINS
from ..llm import generate_json
from ..modules import _jsonb, _short_figure, kt_modules, st_modules


KT_REQUIRED = {
    'from', 'to', 'pull_quote', 'whats_changing', 'why_now',
    'human_needs', 'consumer_tension', 'timeline', 'industries', 'opportunities',
}
ST_REQUIRED = {
    'lede', 'from', 'to', 'quote', 'whats_changing', 'why_now',
    'human_needs', 'signals', 'counter_signals', 'timeline', 'territories',
}

#: How many times to ask for one body. A model that omits a field or overruns a
#: word cap usually gets it right on a second look, and re-requesting only the
#: failures is a handful of calls rather than another full phase.
MAX_EDITORIAL_ATTEMPTS = 3

#: Word ceilings the *publication contract* enforces, mapped onto the editorial
#: fields they are derived from. The prompt asks for less than every one of these
#: (75 against 90 for `whats_changing`, and so on) — this is the hard bound that
#: fails the publication, so it is the bound worth retrying against.
#:
#: Checking it here rather than only at the gate is what makes the difference
#: between one extra call and a dead run: at the gate the whole candidate is
#: already assembled, the repair budget is per-shift, and a fresh rebuild trips
#: every shift at once — so the gate can only ever report the problem.
_SCALAR_LIMITS = {
    'lede': 40, 'from': 30, 'to': 30, 'pull_quote': 18, 'quote': 38,
    'consumer_tension': 38, 'whats_changing': 90, 'why_now': 70,
}
_NESTED_LIMITS = {'human_needs': ('unlocked', 'threatened', 45), 'timeline': ('now', 'next', 45)}
_ITEM_TEXT_LIMITS = {'industries': 40, 'opportunities': 50, 'territories': 50}
_ITEM_STRING_LIMITS = {'signals': 35, 'counter_signals': 35}


def _words(value) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", str(value or '')))


def _within_limits(editorial: object) -> bool:
    """True when every field is inside the ceiling the publication gate applies."""
    if not isinstance(editorial, dict):
        return False
    for field, limit in _SCALAR_LIMITS.items():
        if field in editorial and _words(editorial[field]) > limit:
            return False
    for field, (*keys, limit) in _NESTED_LIMITS.items():
        nested = editorial.get(field)
        if isinstance(nested, dict):
            # `timeline` also carries `beyond`; check every value under the key
            # rather than only the two named, so a new sibling is covered too.
            if any(_words(value) > limit for value in nested.values()):
                return False
        del keys
    for field, limit in _ITEM_TEXT_LIMITS.items():
        for item in editorial.get(field) or []:
            if isinstance(item, dict) and _words(item.get('text')) > limit:
                return False
    for field, limit in _ITEM_STRING_LIMITS.items():
        for item in editorial.get(field) or []:
            if _words(item) > limit:
                return False
    return True


def _complete_editorial(value: object, required: set[str]) -> bool:
    return (isinstance(value, dict)
            and all(value.get(field) for field in required)
            and _within_limits(value))


def _cited(editorial: object, key: str = 'evidence_ids') -> set[int]:
    """The claim ids an editorial body cites, ignoring anything non-numeric."""
    raw = editorial.get(key) if isinstance(editorial, dict) else []
    return {
        int(value) for value in raw or []
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


def _generate_until_complete(items, prompt_of, is_complete, *, describe, label):
    """Generate one body per item, then re-request only the ones that failed.

    Incomplete or overlong bodies used to be written as a NULL module list, which
    turned one absent field into nine missing modules and a publication the gate
    could never accept. Retrying the failures costs a few calls; not retrying
    them cost the entire run.
    """
    results = generate_json(items, prompt_of, default=dict, describe=describe)
    for attempt in range(2, MAX_EDITORIAL_ATTEMPTS + 1):
        pending = [i for i, (item, r) in enumerate(zip(items, results))
                   if not is_complete(item, r)]
        if not pending:
            break
        print(f'    {label}: {len(pending)} incomplete or overlong — '
              f'attempt {attempt}/{MAX_EDITORIAL_ATTEMPTS}')
        retried = generate_json([items[i] for i in pending], prompt_of,
                                default=dict, describe=describe)
        for index, result in zip(pending, retried):
            if is_complete(items[index], result):
                results[index] = result
    still = sum(1 for item, r in zip(items, results) if not is_complete(item, r))
    if still:
        print(f'    {label}: {still} still incomplete after '
              f'{MAX_EDITORIAL_ATTEMPTS} attempts')
    return results


def _verified_stat(editorial: dict, claims: list[dict]) -> dict | None:
    """Attach provenance from our database, never from model-authored text."""
    raw = editorial.get('stat') if isinstance(editorial, dict) else None
    if not isinstance(raw, dict):
        return None
    raw_claim_id = raw.get('claim_id')
    if isinstance(raw_claim_id, bool) or not isinstance(raw_claim_id, (int, float, str)):
        return None
    try:
        claim_id = int(raw_claim_id)
    except (TypeError, ValueError):
        return None
    claim = next((item for item in claims if item.get('id') == claim_id), None)
    value = _short_figure(claim.get('statistic')) if claim else None
    url = str(claim.get('source_url') or '') if claim else ''
    if not claim or not claim.get('has_statistic') or not value or not url.startswith(('http://', 'https://')):
        return None
    source = claim.get('thinker') or claim.get('source_title') or ''
    date = str(claim.get('date_published') or '')[:4]
    return {
        'value': value,
        'text': claim.get('claim_text') or '',
        'source': ', '.join(part for part in (source, date) if part),
        'url': url,
    }

def phase4b_editorial(conn, api_key: str, domain_claims: dict, domain_kts: dict):
    """Writes the module list for every Key Trend and sub-trend."""
    print('\nPhase 4b — Writing editorial modules per Key Trend (parallel)…')

    pool = {c['id']: c for d in DOMAINS for c in domain_claims[d['id']]}
    by_id = {d['id']: d for d in DOMAINS}

    # The KT rows as stored — `hero_stat` (phase 8, which runs before this) and
    # `subtitle` both feed modules, so read them once rather than per KT.
    kt_rows = {r['id']: dict(r) for r in conn.execute(
        'SELECT id, subtitle, hero_stat FROM domain_key_trends').fetchall()}

    # Sub-trends grouped by parent in one query (rather than one query per KT).
    subs_by_kt: dict = {}
    for r in conn.execute("""
        SELECT id, kt_id, name, subtitle, description FROM domain_sub_trends
        ORDER BY kt_id, sort_order
    """).fetchall():
        subs_by_kt.setdefault(r['kt_id'], []).append(dict(r))

    claim_ids_by_sub: dict = {}
    for r in conn.execute("""
        SELECT sub_trend_id, claim_id
        FROM domain_sub_trend_claims
        ORDER BY sub_trend_id, claim_id
    """).fetchall():
        claim_ids_by_sub.setdefault(r['sub_trend_id'], []).append(r['claim_id'])

    # One work item per KT, carrying its claims and its already-written sub-trends.
    work = []
    for d in DOMAINS:
        for kt in domain_kts.get(d['id'], []):
            subs = subs_by_kt.get(kt['_db_id'], [])
            claims_by_sub = {
                sub['id']: [pool[cid] for cid in claim_ids_by_sub.get(sub['id'], []) if cid in pool]
                for sub in subs
            }
            # Parent editorial may cite only evidence that is actually published
            # on one of its children.  Earlier selection pools can contain claims
            # discarded during single-owner routing; exposing those to the model
            # creates citations readers cannot inspect anywhere on the shift.
            routed_ids = {
                claim['id'] for claims in claims_by_sub.values() for claim in claims
            }
            claims = [
                pool[cid] for cid in kt.get('_claim_ids', [])
                if cid in routed_ids and cid in pool
            ]
            if not claims:
                claims = [
                    claim for claim in domain_claims[d['id']]
                    if claim['id'] in routed_ids
                ][:CLAIMS_PER_KT]
            work.append((d['id'], kt, claims, subs, claims_by_sub))

    if not work:
        print('  (no Key Trends to enrich)')
        return

    # Two independent calls per Key Trend (its own editorial, and its sub-trends'),
    # so they go out as two batches and are merged back by index.
    def describe(item):
        return item[1]['name'][:30]

    def kt_is_complete(item, result):
        allowed = {claim['id'] for claim in item[2]}
        cited = _cited(result)
        return (_complete_editorial(result, KT_REQUIRED)
                and len(cited) >= 2 and cited <= allowed)

    def st_is_complete(item, result):
        """Complete only when every one of this shift's sub-shifts got a usable
        body — a partially-filled response leaves the rest with no modules."""
        by_name = {
            str(se.get('name', '')).strip().lower(): se
            for se in ((result or {}).get('sub_trends') or []) if isinstance(se, dict)
        }
        for sub in item[3]:
            se = by_name.get(sub['name'].strip().lower())
            allowed = {claim['id'] for claim in item[4].get(sub['id'], [])}
            cited = _cited(se)
            if not (_complete_editorial(se, ST_REQUIRED)
                    and len(cited) >= 2 and cited <= allowed):
                return False
        return True

    kt_results = _generate_until_complete(
        work,
        lambda item: prompt_kt_editorial(
            item[1]['name'], item[1].get('subtitle', ''), str(by_id[item[0]]['name']), item[2]),
        kt_is_complete, describe=describe, label='shift editorial',
    )
    with_subs = [item for item in work if item[3]]
    st_results = _generate_until_complete(
        with_subs,
        lambda item: prompt_st_editorial(
            item[1]['name'], item[1].get('subtitle', ''), item[3], item[4]),
        st_is_complete, describe=describe, label='sub-shift editorial',
    )
    st_by_kt = {id(item): r for item, r in zip(with_subs, st_results)}
    results = [
        {'kt': kt_r or {}, 'st': st_by_kt.get(id(item)) or {}}
        for item, kt_r in zip(work, kt_results)
    ]

    kt_done = st_done = 0
    for (_d_id, kt, _claims, subs, claims_by_sub), result in zip(work, results):
        e = result.get('kt') or {}
        kt_row = kt_rows.get(kt['_db_id'], {'subtitle': kt.get('subtitle', ''), 'hero_stat': None})
        kt_ids = {claim['id'] for claim in _claims}
        kt_citations = _cited(e)
        complete_kt = (_complete_editorial(e, KT_REQUIRED)
                       and len(kt_citations) >= 2 and kt_citations <= kt_ids)
        modules = kt_modules(kt_row, e) if complete_kt else []
        conn.execute(
            'UPDATE domain_key_trends SET modules=%s::jsonb, read_time=%s WHERE id=%s',
            (_jsonb(modules), e.get('read_time') or None, kt['_db_id']),
        )
        if complete_kt:
            kt_done += 1

        # Match editorial back to sub-trends by name (the prompt is told not to
        # rename them); anything unmatched still gets a module list built from the
        # row itself, so the sub-shift page is never empty.
        editorial_by_name = {
            str(se.get('name', '')).strip().lower(): se
            for se in ((result.get('st') or {}).get('sub_trends') or [])
            if isinstance(se, dict)
        }
        for sub in subs:
            se = editorial_by_name.get(sub['name'].strip().lower()) or {}
            allowed = claims_by_sub.get(sub['id'], [])
            allowed_ids = {claim['id'] for claim in allowed}
            cited = _cited(se)
            complete_st = (_complete_editorial(se, ST_REQUIRED)
                           and len(cited) >= 2 and cited <= allowed_ids)
            if complete_st:
                se = dict(se)
                se['stat'] = _verified_stat(se, allowed)
            conn.execute(
                'UPDATE domain_sub_trends SET modules=%s::jsonb WHERE id=%s',
                (_jsonb(st_modules(sub, se)) if complete_st else None, sub['id']),
            )
            if complete_st:
                st_done += 1

    conn.commit()
    expected_subs = sum(len(item[3]) for item in work)
    print(f'  ✓  {kt_done}/{len(work)} shifts and {st_done}/{expected_subs} sub-shifts given a validated editorial body.')
