"""Phase 4 — generate sub-trends under each Key Trend."""
from __future__ import annotations

from ...core.text import url_slug as slugify
from ...prompts import prompt_sub_trends
from ..config import CLAIMS_PER_KT, DOMAINS
from ..dbutil import _slugger
from ..llm import generate_json


def _validated_sub_trends(result: object, allowed_claim_ids: set[int]) -> list[dict]:
    """Keep model taxonomy only when it satisfies the publication contract.

    Claim assignment is single-owner within a parent. Unknown IDs and repeated
    IDs are dropped instead of being over-routed into generic sibling pages.
    Structural defects remain visible to the publication validator, which can
    trigger the one bounded repair pass.
    """
    raw = result.get('sub_trends') if isinstance(result, dict) else None
    if not isinstance(raw, list):
        return []
    seen: set[int] = set()
    out = []
    for item in raw:
        if not isinstance(item, dict) or not all(item.get(k) for k in ('name', 'subtitle', 'description')):
            continue
        ids = []
        for value in item.get('claim_ids') or []:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            claim_id = int(value)
            if claim_id in allowed_claim_ids and claim_id not in seen:
                seen.add(claim_id)
                ids.append(claim_id)
        out.append({**item, 'claim_ids': ids[:8]})
    return out


def phase4_sub_trends(conn, api_key: str, domain_claims: dict, domain_kts: dict):
    """Writes to domain_sub_trends + domain_sub_trend_claims."""
    print('\nPhase 4 — Clustering sub-trends per Key Trend (parallel)…')

    all_domain_claims = {c['id']: c for d in DOMAINS for c in domain_claims[d['id']]}

    # Build the per-KT claim pool (pure, no I/O), one work item per KT.
    work = []  # (domain_id, kt, preferred_claims)
    for d in DOMAINS:
        full_pool = domain_claims[d['id']]
        for kt in domain_kts.get(d['id'], []):
            preferred_ids = set(kt.get('_claim_ids', []))
            preferred = [all_domain_claims[cid] for cid in preferred_ids if cid in all_domain_claims]
            remaining = CLAIMS_PER_KT - len(preferred)
            if remaining > 0:
                preferred += [c for c in full_pool if c['id'] not in preferred_ids][:remaining]
            if preferred:
                work.append((d['id'], kt, preferred))

    # One call per Key Trend.
    results = generate_json(
        work,
        lambda item: prompt_sub_trends(item[1]['name'], item[1].get('subtitle', ''), item[2]),
        default=lambda: {'sub_trends': []},
        describe=lambda item: item[1]['name'][:30],
    )

    # Serial: write sub-trends + claim links, refine KT velocity.
    slug = _slugger()
    for (d_id, kt, claims), result in zip(work, results):
        velocity = result.get('key_trend_velocity', kt.get('velocity', 'rising'))
        conn.execute('UPDATE domain_key_trends SET velocity=%s WHERE id=%s', (velocity, kt['_db_id']))
        sub_trends = _validated_sub_trends(result, {claim['id'] for claim in claims})
        for i, st in enumerate(sub_trends, start=1):
            st_db_id = conn.execute("""
                INSERT INTO domain_sub_trends
                  (slug, kt_id, domain_id, name, subtitle, description, sort_order)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, (slug(f'st-{slugify(st["name"])}'), kt['_db_id'], d_id,
                  st['name'], st.get('subtitle', ''), st['description'], i)).fetchone()['id']
            for cid in st.get('claim_ids', []):
                try:
                    conn.execute("""INSERT INTO domain_sub_trend_claims (sub_trend_id, claim_id)
                                    VALUES (%s,%s) ON CONFLICT DO NOTHING""", (st_db_id, int(cid)))
                except Exception:
                    pass
        print(f'  ✓  {kt["name"][:48]}: {len(sub_trends)} sub-trends, vel={velocity}')

    conn.commit()
