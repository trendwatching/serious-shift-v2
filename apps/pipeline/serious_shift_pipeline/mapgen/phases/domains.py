"""Phase 1 — write the fixed domain rows."""
from __future__ import annotations

from ..config import DOMAIN_FLOWS_PRESET, DOMAINS


def phase1_domain_definitions(conn):
    print('\nPhase 1 — Writing domain definitions to DB…')
    for d in DOMAINS:
        conn.execute("""
            INSERT INTO domains_v2 (id, name, label, short_description, description, sort_order, horizon)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
              name = EXCLUDED.name, label = EXCLUDED.label,
              short_description = EXCLUDED.short_description,
              description = EXCLUDED.description, sort_order = EXCLUDED.sort_order,
              horizon = EXCLUDED.horizon
        """, (d['id'], d['name'], d['label'], d['short_description'], d['description'],
              d['sort_order'], d.get('horizon')))
    for f in DOMAIN_FLOWS_PRESET:
        conn.execute("""
            INSERT INTO domain_flows (source_id, target_id, strength, description)
            VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING
        """, (f['source'], f['target'], f['strength'], f['description']))
    conn.commit()
    print(f'  ✓  {len(DOMAINS)} domains + {len(DOMAIN_FLOWS_PRESET)} domain flows written.')
