"""Phase 3b — per-shift research top-up (web).

Phase 3 names the shifts from the sphere-scan evidence; this phase gives each
named shift its own deep-research pass (steps/research.build_pack: search →
re-fetch → verbatim-span verification → claims + evidence_packs) so phase 4's
children and the editorial ALLOWED EVIDENCE draw from a file researched for
THIS shift, not just the sweep that surfaced it.

Later phases read the in-memory pools only, so the new claims are appended to
both `domain_claims[domain_id]` (via routing.claims_by_ids, the same dict
shape the tiers produce) and the shift's preferred `_claim_ids`. Scoring is
refreshed afterwards because hero-stat ranking reads claim_weight, which
fresh rows lack.

A shift whose research call fails keeps its scan-era pool — the run
continues; this phase adds evidence, it never blocks.
"""
from __future__ import annotations

import os
from datetime import date

from ...core import observability
from ...core.observability import ErrorLog
from ...core.text import url_slug
from ...steps.research import build_pack
from ...steps.scoring import score_claims, score_sources
from ..routing import claims_by_ids
from .. import llm as mapgen_llm


def phase3b_research_topup(conn, domain_claims: dict, domain_kts: dict) -> None:
    run_id = os.environ.get('SS_RUN_ID') or observability.new_run_id('synthesize')
    error_log = ErrorLog(run_id)
    total_new = 0
    shifts = sum(len(kts) for kts in domain_kts.values())
    print(f"\nPhase 3b: researching {shifts} named shifts on the live web…")
    for domain_id, kts in domain_kts.items():
        for kt in kts:
            slug = url_slug(kt['name'])
            coverage = build_pack(
                conn,
                {'slug': slug, 'name': kt['name'],
                 'subtitle': kt.get('subtitle', ''), 'sphere': domain_id},
                run_id, mapgen_llm.COST, error_log)
            if not coverage:
                continue
            row = conn.execute(
                'SELECT item_ids FROM evidence_packs '
                'WHERE shift_slug = %s AND run_id = %s', (slug, run_id)).fetchone()
            new_ids = list(row['item_ids']) if row and row['item_ids'] else []
            if not new_ids:
                continue
            kt['_claim_ids'] = list(kt.get('_claim_ids') or []) + new_ids
            domain_claims[domain_id].extend(claims_by_ids(conn, new_ids))
            total_new += len(new_ids)

    # Fresh rows have no claim_weight/freshness yet, and hero-stat ranking
    # (phase 8) orders on them — same free SQL the old score step ran.
    depth_map = score_sources(conn, False)
    score_claims(conn, depth_map, date.today(), False)
    print(f"Phase 3b done: {total_new} verified evidence claims added and scored")
