"""Phase 4b — editorial prose for Key Trends and their sub-trends."""
from __future__ import annotations

from ...prompts import prompt_kt_editorial, prompt_st_editorial
from ..config import CLAIMS_PER_KT, DOMAINS
from ..llm import generate_json
from ..modules import _jsonb, kt_modules, st_modules

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

    # One work item per KT, carrying its claims and its already-written sub-trends.
    work = []
    for d in DOMAINS:
        for kt in domain_kts.get(d['id'], []):
            claims = [pool[cid] for cid in kt.get('_claim_ids', []) if cid in pool]
            if not claims:
                claims = domain_claims[d['id']][:CLAIMS_PER_KT]
            work.append((d['id'], kt, claims, subs_by_kt.get(kt['_db_id'], [])))

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
            item[1]['name'], item[1].get('subtitle', ''), item[3], item[2]),
        default=dict, describe=describe,
    )
    st_by_kt = {id(item): r for item, r in zip(with_subs, st_results)}
    results = [
        {'kt': kt_r or {}, 'st': st_by_kt.get(id(item)) or {}}
        for item, kt_r in zip(work, kt_results)
    ]

    kt_done = st_done = 0
    for (_d_id, kt, _claims, subs), result in zip(work, results):
        e = result.get('kt') or {}
        kt_row = kt_rows.get(kt['_db_id'], {'subtitle': kt.get('subtitle', ''), 'hero_stat': None})
        modules = kt_modules(kt_row, e)
        conn.execute(
            'UPDATE domain_key_trends SET modules=%s::jsonb, read_time=%s WHERE id=%s',
            (_jsonb(modules), e.get('read_time') or None, kt['_db_id']),
        )
        if e:
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
            conn.execute(
                'UPDATE domain_sub_trends SET modules=%s::jsonb WHERE id=%s',
                (_jsonb(st_modules(sub, se)), sub['id']),
            )
            if se:
                st_done += 1

    conn.commit()
    print(f'  ✓  {kt_done}/{len(work)} shifts and {st_done} sub-shifts given an editorial body.')
