"""CLI for map generation.

    python -m serious_shift_pipeline.mapgen.cli               # full rebuild
    python -m serious_shift_pipeline.mapgen.cli --export-only # re-export, no API cost
"""
from __future__ import annotations

import argparse
import os
import sys

from ..core import observability
from ..core.observability import RunLog
from . import llm as mapgen_llm
from .config import CLAIMS_PER_DOM, DOMAINS
from .dbutil import get_conn, reset_v2_tables
from .export import (
    _write_map_document, build_map_json_v2, load_kts_from_db,
)
from .phases.attribution import phase5_thinker_attribution
from .phases.domains import phase1_domain_definitions
from .phases.editorial import phase4b_editorial
from .phases.hero_stats import phase8_hero_stats
from .phases.interrelatedness import phase6_interrelatedness
from .phases.key_trends import phase3_key_trends
from .phases.routing import phase2_claim_routing
from .phases.sub_trends import phase4_sub_trends
from .phases.synthesis import phase7_synthesis
from .routing import route_claims_for_domain

def _record_spend(out: dict) -> None:
    """Attach this rebuild's Anthropic spend to the pipeline run.

    The orchestrator exports SS_RUN_ID and closes the row itself; run standalone,
    this opens and closes its own so a manual rebuild is still costed.
    """
    orchestrated = bool(os.environ.get('SS_RUN_ID'))
    run_id = os.environ.get('SS_RUN_ID') or observability.new_run_id('synthesize')
    run = RunLog(run_id, 'synthesize')
    if not orchestrated:
        run.start()
    run.add_usage(
        cost=mapgen_llm.COST,
        detail={'mapgen': {
            'domains': len(out.get('domains', [])),
            'key_trends': len(out.get('key_trends', [])),
            'sub_trends': len(out.get('sub_trends', [])),
            'synthesis_insights': len(out.get('synthesis_insights', [])),
            'links': len(out.get('links', [])),
        }},
    )
    if not orchestrated:
        run.finish(status='ok')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run',     action='store_true', help='Print claim counts only')
    parser.add_argument('--phase1',      action='store_true', help='DB setup + domain insert only (no API)')
    parser.add_argument('--export-only', action='store_true', help='Re-export from existing v2 data')
    parser.add_argument('--editorial-only', action='store_true',
                        help='Regenerate the editorial modules for existing Key Trends, then '
                             're-export. Does NOT reset the v2 tables or re-cluster.')
    parser.add_argument('--limit', type=int, default=0, metavar='N',
                        help='With --editorial-only: only process the first N Key Trends per '
                             'domain. Use a small N to smoke-test the path before paying for '
                             'the full set.')
    args = parser.parse_args()

    conn = get_conn()

    # ── Editorial-only ───────────────────────────────────────────────────────
    # Deliberately on this side of reset_v2_tables: the taxonomy is left exactly
    # as it is, so slugs (and therefore any authored module overrides) still match.
    if args.editorial_only:
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            print('ERROR: ANTHROPIC_API_KEY not set.')
            sys.exit(1)
        print('--editorial-only: regenerating modules for the existing map…')
        domain_kts = load_kts_from_db(conn)
        if args.limit:
            domain_kts = {k: v[:args.limit] for k, v in domain_kts.items()}
            print(f'  --limit {args.limit}: capped to the first {args.limit} shift(s) per domain.')
        total = sum(len(v) for v in domain_kts.values())
        if not total:
            print('ERROR: no Key Trends in the database — run a full rebuild first.')
            conn.close(); sys.exit(1)
        print(f'  {total} Key Trends found across {len(DOMAINS)} domains.')
        # Domain definitions are an idempotent upsert with no truncate, so they
        # are safe here — and necessary: horizon and the domain labels live on
        # domains_v2 and would otherwise stay unset on a database that has only
        # ever had the taxonomy phases run against it.
        phase1_domain_definitions(conn)
        domain_claims = phase2_claim_routing(conn)
        phase8_hero_stats(conn)          # stat_band module needs hero_stat first
        phase4b_editorial(conn, api_key, domain_claims, domain_kts)
        print('\nPhase 9 — Exporting map…')
        out = build_map_json_v2(conn)
        _write_map_document(conn, out)
        n_mod = sum(len(kt.get('modules') or []) for kt in out['key_trends'])
        _record_spend(out)
        print("✓  map written → documents['map']")
        print(f'   {len(out["key_trends"])} KTs carrying {n_mod} modules · '
              f'{len(out["sub_trends"])} sub-trends')
        mapgen_llm.COST.report()
        conn.close(); return

    # ── Export-only ──────────────────────────────────────────────────────────
    if args.export_only:
        print('--export-only: reading existing v2 data…')
        out = build_map_json_v2(conn)
        _write_map_document(conn, out)
        print("✓  map written → documents['map']")
        print(f'   {len(out["domains"])} domains · {len(out["key_trends"])} KTs · '
              f'{len(out["sub_trends"])} sub-trends · {len(out["links"])} links')
        conn.close(); return

    # ── Always reset v2 tables ───────────────────────────────────────────────
    reset_v2_tables(conn)

    # ── Phase 1 (free) ───────────────────────────────────────────────────────
    phase1_domain_definitions(conn)

    if args.dry_run or args.phase1:
        # Show claim counts per domain
        print('\nPhase 2 preview — claim counts per domain (dry run):')
        for d in DOMAINS:
            claims = route_claims_for_domain(conn, d, limit=CLAIMS_PER_DOM)
            thinkers = len({c['thinker'] for c in claims})
            print(f'  {d["name"]:<15}  {len(claims):3d} claims  |  {thinkers} thinkers')
        if args.phase1:
            print('\n--phase1: stopping after DB setup. Run without --phase1 to continue.')
        else:
            print('\n--dry-run: stopping. No API calls made.')
        conn.close(); return

    # ── Need API key for paid phases ─────────────────────────────────────────
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        print('ERROR: ANTHROPIC_API_KEY not set.')
        sys.exit(1)

    # ── Phase 2: claim routing (free, SQL) ───────────────────────────────────
    domain_claims = phase2_claim_routing(conn)

    # ── Phase 3: Key Trend generation per domain ─────────────────────────────
    domain_kts = phase3_key_trends(conn, api_key, domain_claims)

    # ── Phase 4: sub-trend clustering ────────────────────────────────────────
    phase4_sub_trends(conn, api_key, domain_claims, domain_kts)

    # ── Hero stats (free, SQL) — must precede the editorial phase, whose
    #    stat_band module is built from hero_stat.value. ────────────────────────
    phase8_hero_stats(conn)

    # ── Phase 4b: editorial modules ──────────────────────────────────────────
    phase4b_editorial(conn, api_key, domain_claims, domain_kts)

    # ── Phase 5: thinker attribution ─────────────────────────────────────────
    phase5_thinker_attribution(conn, api_key, domain_claims, domain_kts)

    # ── Phase 6: interrelatedness ─────────────────────────────────────────────
    phase6_interrelatedness(conn, api_key, domain_kts)

    # ── Phase 7: synthesis insights ───────────────────────────────────────────
    phase7_synthesis(conn, api_key, domain_claims)

    # ── Phase 9: export ───────────────────────────────────────────────────────
    print('\nPhase 9 — Exporting map…')
    out = build_map_json_v2(conn)
    _write_map_document(conn, out)
    conn.close()

    # Report spend to the run row. mapgen already accumulates it in
    # `llm.COST`, but nothing forwarded it — so a 17-minute rebuild that made
    # hundreds of Sonnet calls recorded $0.00, which makes the run history
    # useless for the more expensive of the two stages.
    _record_spend(out)

    print("\n✓  map → documents['map']")
    print(f'   {len(out["domains"])} domains · {len(out["key_trends"])} KTs · '
          f'{len(out["sub_trends"])} sub-trends')
    print(f'   {len(out["claims"])} claims · {len(out["synthesis_insights"])} insights · '
          f'{len(out["links"])} links')
    mapgen_llm.COST.report()
    print('\nDone.')


if __name__ == '__main__':
    main()
