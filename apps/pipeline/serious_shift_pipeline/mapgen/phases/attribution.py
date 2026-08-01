"""Phase 5 — attribute each Key Trend to proponents and skeptics."""
from __future__ import annotations

import json

from ...prompts import prompt_thinker_attribution
from ..config import DOMAINS
from ..llm import generate_json
from ..parsers import _collect_by_thinker, parse_thinker_attribution


def phase5_thinker_attribution(conn, api_key: str, domain_claims: dict, domain_kts: dict):
    print('\nPhase 5 — Thinker attribution (parallel)…')

    # Build per-KT thinker groups (pure), one work item per KT.
    work = []  # (kt, groups)
    for d in DOMAINS:
        claims = domain_claims[d['id']]
        for kt in domain_kts.get(d['id'], []):
            preferred_ids = set(kt.get('_claim_ids', []))
            kt_claims = [c for c in claims if c['id'] in preferred_ids] or claims[:60]
            groups = _collect_by_thinker(kt_claims, max_per=8)
            if groups:
                work.append((kt, groups))

    # One call per Key Trend.
    raw = generate_json(
        work,
        lambda item: prompt_thinker_attribution('key_trend', item[0]['name'], item[1]),
        default=dict,
        describe=lambda item: item[0]['name'][:30],
    )
    results = [parse_thinker_attribution(r or {}) for r in raw]

    # Serial: write attribution.
    for (kt, _), attr in zip(work, results):
        conn.execute('UPDATE domain_key_trends SET proponents=%s, skeptics=%s WHERE id=%s',
                     (json.dumps(attr['proponents']), json.dumps(attr['skeptics']), kt['_db_id']))
    conn.commit()
    print(f'  ✓  {len(work)} Key Trends attributed')
