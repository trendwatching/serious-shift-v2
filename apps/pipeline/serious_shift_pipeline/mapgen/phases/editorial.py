"""Phase 4b — editorial prose for Key Trends and their sub-trends."""
from __future__ import annotations

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


def _complete_editorial(value: object, required: set[str]) -> bool:
    return isinstance(value, dict) and all(value.get(field) for field in required)


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

    kt_results = generate_json(
        work,
        lambda item: prompt_kt_editorial(
            item[1]['name'], item[1].get('subtitle', ''), str(by_id[item[0]]['name']), item[2]),
        default=dict, describe=describe,
    )
    with_subs = [item for item in work if item[3]]
    st_results = generate_json(
        with_subs,
        lambda item: prompt_st_editorial(
            item[1]['name'], item[1].get('subtitle', ''), item[3], item[4]),
        default=dict, describe=describe,
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
        raw_kt_citations = e.get('evidence_ids') if isinstance(e, dict) else []
        kt_citations = {int(value) for value in raw_kt_citations or [] if isinstance(value, (int, float)) and not isinstance(value, bool)}
        complete_kt = _complete_editorial(e, KT_REQUIRED) and len(kt_citations) >= 2 and kt_citations <= kt_ids
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
            evidence_ids = se.get('evidence_ids') if isinstance(se, dict) else []
            cited = {int(value) for value in evidence_ids or [] if isinstance(value, (int, float)) and not isinstance(value, bool)}
            complete_st = _complete_editorial(se, ST_REQUIRED) and len(cited) >= 2 and cited <= allowed_ids
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
