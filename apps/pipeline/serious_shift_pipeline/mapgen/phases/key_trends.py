"""Phase 3 — generate each domain's Key Trends."""
from __future__ import annotations

from ...core.text import url_slug as slugify
from ...prompts import MIN_KTS_PER_DOM, prompt_domain_key_trends
from ...prompts import fmt_claims_block  # noqa: F401  (kept for prompt helpers)
from ..config import DOMAINS
from ..dbutil import _slugger
from ..llm import generate_json


def phase3_key_trends(conn, api_key: str, domain_claims: dict) -> dict:
    """
    Returns {domain_id: [kt_dict_with_db_id, ...]}
    Writes ≥MIN_KTS_PER_DOM Key Trends per domain to domain_key_trends.
    """
    print('\nPhase 3 — Generating Key Trends per domain (parallel)…')

    # One independent call per domain.
    results = generate_json(
        DOMAINS,
        lambda d: prompt_domain_key_trends(d, domain_claims[d['id']], MIN_KTS_PER_DOM),
        default=lambda: {'key_trends': []},
        describe=lambda d: d['name'],
    )

    # Serial: assign slugs + write (single connection, deterministic order).
    slug = _slugger()
    domain_kts: dict = {}
    for d, result in zip(DOMAINS, results):
        kts = result.get('key_trends', [])
        if len(kts) < MIN_KTS_PER_DOM:
            print(f'  {d["name"]}: only {len(kts)} KTs (target {MIN_KTS_PER_DOM})')
        written = []
        for j, kt in enumerate(kts, start=1):
            kt['_db_id'] = conn.execute("""
                INSERT INTO domain_key_trends
                  (slug, domain_id, name, subtitle, velocity, sort_order)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
            """, (slug(f'kt-{slugify(kt["name"])}'), d['id'],
                  kt['name'], kt.get('subtitle', ''), kt.get('velocity', 'rising'), j)).fetchone()['id']
            kt['_claim_ids'] = [int(cid) for cid in kt.get('claim_ids', [])
                                if isinstance(cid, (int, float))]
            written.append(kt)
        domain_kts[d['id']] = written
        print(f'  ✓  {d["name"]}: {len(written)} KTs')

    conn.commit()
    return domain_kts
