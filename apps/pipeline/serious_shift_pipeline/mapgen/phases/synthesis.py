"""Phase 7 — per-domain synthesis insights.

DORMANT since 2026-08-10: not called by cli.py. Insights reach the sphere
fragment and the frontend view-model but no component renders them, so the
phase was pure spend. The export still publishes `synthesis_insights` (an
empty list from the empty table) because useData.js checks the key's shape.
To re-enable: reinstate the call in cli.py and build the renderer first; also
dedupe — the 2026-08-10 audit found 16 insights that were ~12 distinct ones.
"""
from __future__ import annotations

from ...core.text import url_slug as slugify
from ...prompts import INSIGHTS_MODEL, prompt_synthesis_insights
from ..config import DOMAINS
from ..dbutil import _slugger
from ..llm import generate_json
from ..parsers import parse_synthesis_insights


def phase7_synthesis(conn, api_key: str, domain_claims: dict):
    print('\nPhase 7 — Synthesis insights per domain (parallel)…')

    # One call per domain, over that domain's top claims.
    with_claims = [d for d in DOMAINS if domain_claims.get(d['id'])]
    raw = generate_json(
        with_claims,
        lambda d: prompt_synthesis_insights(d['name'], d['description'], domain_claims[d['id']][:50]),
        model=INSIGHTS_MODEL,
        default=dict,
        describe=lambda d: d['name'],
    )
    insights_by_domain = {
        d['id']: parse_synthesis_insights(r or {}) for d, r in zip(with_claims, raw)
    }
    results = [(d, insights_by_domain.get(d['id'], [])) for d in DOMAINS]

    # Serial: write insights + claim links.
    slug = _slugger()
    for d, insights in results:
        n_written = 0
        for ins in insights:
            row = conn.execute("""
                INSERT INTO domain_synthesis_insights (slug, domain_id, name, description)
                VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id
            """, (slug(f'si-{d["id"]}-{slugify(ins["name"])}'), d['id'], ins['name'], ins['description'])).fetchone()
            si_id = row['id'] if row else None
            if si_id:
                for cid in ins['contributing_claim_ids']:
                    try:
                        conn.execute("""INSERT INTO domain_synthesis_insight_claims (insight_id, claim_id)
                                        VALUES (%s,%s) ON CONFLICT DO NOTHING""", (si_id, cid))
                    except Exception:
                        pass
                n_written += 1
        print(f'  ✓  {d["name"]}: {n_written} insights')
    conn.commit()
