"""Phase 6 — typed edges between Key Trends across domains."""
from __future__ import annotations

import random

from ...prompts import prompt_interrelatedness_batch
from ..config import DOMAINS
from ..llm import generate_json
from ..parsers import parse_interrelatedness_batch


def phase6_interrelatedness(conn, api_key: str, domain_kts: dict):
    print('\nPhase 6 — Interrelatedness (typed edges, parallel)…')
    MAX_BATCHES = 30

    # Gather KT nodes, build cross-domain pairs, batch them.
    kt_nodes = []
    for d in DOMAINS:
        for kt in domain_kts.get(d['id'], []):
            kt_nodes.append({'id': f'kt:{kt["_db_id"]}', 'name': kt['name'],
                             'desc': kt.get('subtitle', '')[:120], 'domain': d['id']})
    kt_pairs = [
        {'id_a': a['id'], 'name_a': a['name'], 'desc_a': a['desc'], 'type_a': 'key_trend',
         'id_b': b['id'], 'name_b': b['name'], 'desc_b': b['desc'], 'type_b': 'key_trend'}
        for i, a in enumerate(kt_nodes) for b in kt_nodes[i + 1:]
        if a['domain'] != b['domain']
    ]
    random.shuffle(kt_pairs)
    kt_pairs = kt_pairs[:200]
    batches = [kt_pairs[i:i + 25] for i in range(0, len(kt_pairs), 25)][:MAX_BATCHES]

    # One call per batch of candidate pairs.
    raw = generate_json(
        batches,
        prompt_interrelatedness_batch,
        default=dict,
        describe=lambda b: f'{len(b)} pairs',
    )
    results = [parse_interrelatedness_batch(r or {}) for r in raw]

    # Serial: write links.
    n = 0
    for links in results:
        for lnk in links:
            try:
                conn.execute("""
                    INSERT INTO domain_links
                      (source_type, source_id, target_type, target_id, relationship, strength, reasoning)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
                """, (lnk['source_id'].split(':')[0], lnk['source_id'],
                      lnk['target_id'].split(':')[0], lnk['target_id'],
                      lnk['relationship'], lnk['strength'], lnk['reasoning']))
                n += 1
            except Exception:
                pass
    conn.commit()
    print(f'  ✓  {len(batches)} batches → {n} links')
