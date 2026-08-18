"""CLI for map generation.

    python -m serious_shift_pipeline.mapgen.cli               # full rebuild
    python -m serious_shift_pipeline.mapgen.cli --export-only # re-export, no API cost
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from ..core import observability
from ..core.config import BudgetExceeded
from ..core.observability import RunLog
from . import llm as mapgen_llm
from .art import generate_and_attach
from .carryover import load_published_taxonomy
from .config import CLAIMS_PER_DOM, DOMAINS
from .dbutil import get_conn, reset_v2_tables
from .export import (
    _write_map_document, build_map_json_v2, load_kts_from_db,
)
from .phases.art_briefs import phase10_art_briefs
from .phases.domains import phase1_domain_definitions
from .phases.editorial import phase4b_editorial
from .phases.hero_stats import phase8_hero_stats
from .phases.key_trends import phase3_key_trends
from .phases.routing import phase2_claim_routing
from .phases.sub_trends import phase4_sub_trends
from .publish_hook import post_shift_map
from .routing import route_claims_for_domain
from .validation import (PublicationValidationError, _load_contract,
                         validate_map)

MAX_TARGETED_REPAIR_SHIFTS = int(os.environ.get('SS_MAX_TARGETED_REPAIR_SHIFTS', '12'))
# How many validation issues reach the terminal. The rest stay on the run row.
MAX_PRINTED_ISSUES = int(os.environ.get('SS_MAX_PRINTED_ISSUES', '25'))


def _record_validation_failure(exc: PublicationValidationError) -> None:
    """Persist structured failure detail for both orchestrated and manual runs."""
    orchestrated = bool(os.environ.get('SS_RUN_ID'))
    run_id = os.environ.get('SS_RUN_ID') or observability.new_run_id('synthesize')
    run = RunLog(run_id, 'synthesize')
    if orchestrated:
        # The row belongs to run.py, which closes it after the remaining steps.
        # `finish()` matches on run_id alone, so stamping it here set
        # finished_at and status='failed' while classify had yet to run — the
        # exact double-close `_open_export_run` documents avoiding, forty lines
        # below. Attach the detail and leave the lifecycle to its owner.
        run.add_usage(detail=exc.detail())
    else:
        run.start()
        run.finish(status='failed', detail=exc.detail())
    # Capped. A stale taxonomy produces thousands of issues — 2,004 in one real
    # case — and dumping them all buries the one line that says the work is
    # recoverable under a screen-height of JSON nobody scrolls back through.
    # The complete set is on the run row, which is what `detail` is for.
    detail = exc.detail()
    issues = detail['validation']['issues']
    shown = issues[:MAX_PRINTED_ISSUES]
    print(json.dumps({'validation': {'issue_count': detail['validation']['issue_count'],
                                     'issues': shown}}, indent=2), file=sys.stderr)
    if len(issues) > len(shown):
        print(f'  … and {len(issues) - len(shown)} more — the full set is on '
              f"pipeline_runs.detail WHERE run_id = '{run_id}'", file=sys.stderr)
    # The generation is NOT lost, and the message used not to say so. The gate
    # runs once, at the end, against the v2 tables — which are already written.
    # So the ~25 minutes and the API spend are still on disk, and recovery is a
    # free re-export once the underlying issue is fixed. Someone who does not
    # know that reaches for a full rebuild and pays for the same map twice.
    print(
        '\n  The map in the v2 tables is intact — this failed at the gate, not '
        'during generation.\n'
        '  Fix the issues above (most are data, not code), then re-publish for '
        'free with:\n'
        '      python -m serious_shift_pipeline.mapgen.cli --export-only\n'
        '  A full re-run would regenerate every name from the prompts and cost '
        'the same again.',
        file=sys.stderr,
    )


def _open_export_run() -> tuple[str, RunLog | None]:
    """Open a `pipeline_runs` row for a standalone re-export.

    Returns (run_id, run) with `run` None when the orchestrator owns the row —
    it exports SS_RUN_ID and closes the row itself, and closing it twice would
    stamp `finished_at` before the later steps have run.
    """
    orchestrated = bool(os.environ.get('SS_RUN_ID'))
    run_id = os.environ.get('SS_RUN_ID') or observability.new_run_id('export')
    if orchestrated:
        return run_id, None
    run = RunLog(run_id, 'export')
    run.start()
    # Publish this run as the ambient one, so a validation failure inside it
    # attaches to THIS row instead of opening a second `synthesize` row for the
    # same action. Without it one failed re-export left two rows in the history
    # — `export failed` and `synthesize failed` — describing one event, which is
    # precisely the kind of thing that made the history untrustworthy to begin
    # with. `finish()` matches on run_id alone, so the stage stays `export`.
    os.environ['SS_RUN_ID'] = run_id
    return run_id, run


def _close_export_run(run: RunLog | None, *, status: str, detail: dict | None = None) -> None:
    if run is not None:
        run.finish(status=status, detail=detail)


def _db_id(shift_id: object) -> int | None:
    """The numeric row id behind a document id like `kt-42`, or None.

    Unguarded `int(...removeprefix('kt-'))` raised ValueError from INSIDE the
    repair pass, which turned a recoverable gate failure into an unhandled
    traceback — destroying the one message that tells the operator the map is
    intact and re-publishable for free.
    """
    try:
        return int(str(shift_id or '').removeprefix('kt-'))
    except (TypeError, ValueError):
        return None


def _issue_shift_ids(out: dict, issues) -> set[str]:
    """Resolve repairable issue paths back to parent shift document IDs."""
    shift_ids: set[str] = set()
    subs = [sub for sub in out.get('sub_trends') or [] if isinstance(sub, dict)]
    sub_to_parent = {str(sub.get('id')): str(sub.get('key_trend_id')) for sub in subs}
    shifts = out.get('key_trends') or []
    for issue in issues:
        match = re.match(r'key_trends\[(\d+)\]', issue.path)
        if match and int(match.group(1)) < len(shifts):
            shift_ids.add(str(shifts[int(match.group(1))].get('id')))
            continue
        match = re.match(r'sub_trends\[([^\]]+)\]', issue.path)
        if not match:
            continue
        # The validator writes ARRAY INDICES into paths ('sub_trends[39]'),
        # while the id-keyed map only ever matched an id-shaped segment — so
        # every sub-anchored issue silently resolved to no parent and the
        # repair pass regenerated nothing (observed 2026-08-12: 14 issues,
        # 1 request). Index first; id kept as the fallback.
        segment = match.group(1)
        if segment.isdigit() and int(segment) < len(subs):
            shift_ids.add(str(subs[int(segment)].get('key_trend_id')))
        elif segment in sub_to_parent:
            shift_ids.add(sub_to_parent[segment])
    return {shift_id for shift_id in shift_ids if shift_id and shift_id != 'None'}


#: Issue codes whose first remedy is a free re-run of phase 8: hero exclusivity
#: and topicality are assignment decisions, and stat coverage can recover when
#: the assignment shuffles. Runs before any paid editorial regen, because the
#: stat_band the editorial builds is derived from hero_stat.
HERO_REPAIR_CODES = {'duplicate_hero_claim', 'hero_topicality', 'stat_coverage'}


def _targeted_repair_once(conn, api_key: str, out: dict, issues,
                          domain_claims: dict, domain_kts: dict) -> bool:
    """One bounded repair pass over only the invalid parents."""
    repairable = [issue for issue in issues if issue.repairable]
    if not repairable:
        return False
    repaired_heroes = False
    if any(issue.code in HERO_REPAIR_CODES for issue in repairable):
        print('  hero-stat issue(s) present — re-running phase 8 (free SQL) first')
        phase8_hero_stats(conn)
        repaired_heroes = True
    shift_ids = _issue_shift_ids(out, repairable)
    if not shift_ids or len(shift_ids) > MAX_TARGETED_REPAIR_SHIFTS:
        print(f'  targeted repair skipped: {len(shift_ids)} parent shift(s), '
              f'limit is {MAX_TARGETED_REPAIR_SHIFTS}')
        return repaired_heroes

    db_ids = {db_id for shift_id in shift_ids
              for db_id in [_db_id(shift_id)] if db_id is not None}
    filtered = {
        domain_id: [kt for kt in items if kt.get('_db_id') in db_ids]
        for domain_id, items in domain_kts.items()
    }
    filtered = {domain_id: items for domain_id, items in filtered.items() if items}
    if not filtered:
        # A hero reassignment alone still changes the candidate — rebuild and
        # revalidate even when no editorial parent could be resolved.
        return repaired_heroes

    count_ids = {
        int(shifts_match.group(1))
        for issue in repairable
        if issue.code == 'sub_shift_count'
        for shifts_match in [re.match(r'key_trends\[(\d+)\]', issue.path)]
        if shifts_match
    }
    count_db_ids = {
        db_id for index in count_ids
        for db_id in [_db_id((out.get('key_trends') or [])[index].get('id')
                             if index < len(out.get('key_trends') or []) else None)]
        if db_id is not None
    }
    if count_db_ids:
        conn.execute(
            'DELETE FROM domain_sub_trend_claims WHERE sub_trend_id IN '
            '(SELECT id FROM domain_sub_trends WHERE kt_id = ANY(%s))',
            (list(count_db_ids),),
        )
        conn.execute('DELETE FROM domain_sub_trends WHERE kt_id = ANY(%s)',
                     (list(count_db_ids),))
        conn.commit()
        repair_counts = {
            domain_id: [kt for kt in items if kt.get('_db_id') in count_db_ids]
            for domain_id, items in filtered.items()
        }
        phase4_sub_trends(conn, api_key, domain_claims, repair_counts)

    # Editorial is regenerated once for the affected parents. This repairs both
    # their own modules and every child module created or found invalid above.
    phase4b_editorial(conn, api_key, domain_claims, filtered)
    return True


def _publish_candidate(conn, out: dict, *, api_key: str = '', domain_claims=None,
                       domain_kts=None, allow_repair: bool = False) -> dict:
    issues = validate_map(out)
    if issues and allow_repair and api_key and domain_claims is not None and domain_kts is not None:
        print(f'Candidate invalid ({len(issues)} issue(s)); running one targeted repair pass…')
        if _targeted_repair_once(conn, api_key, out, issues, domain_claims, domain_kts):
            out = build_map_json_v2(conn)
            issues = validate_map(out)
    if issues:
        exc = PublicationValidationError(issues)
        _record_validation_failure(exc)
        raise exc

    # Artwork, after the gate and before the write. The taxonomy is final here
    # and nowhere earlier — the repair pass above can re-cluster sub-shifts and
    # mint new slugs, and art is keyed by slug. Both calls swallow their own
    # failures: a Gemini outage, a missing key or a spend ceiling costs this
    # week's new images and never a publication.
    art_stats = {}
    try:
        briefs = phase10_art_briefs(conn, out)
        art_stats = generate_and_attach(conn, out, briefs)
    except Exception as exc:  # noqa: BLE001 — decoration must not block content
        print(f'  art: skipped ({type(exc).__name__}: {exc})')
    if art_stats:
        print(f'  art: {art_stats.get("generated", 0)} generated, '
              f'{art_stats.get("reused", 0)} reused, {art_stats.get("failed", 0)} failed, '
              f'{art_stats.get("attached", 0)} URL(s) on the map '
              f'(${art_stats.get("cost_usd", 0):.2f})')

    _write_map_document(conn, out)
    # Post-commit on purpose, and here rather than in main(): every publish path
    # goes through this function — full rebuild, --editorial-only and the free
    # --export-only recovery — so a receiver cannot go stale against a live site.
    # The site is already serving this map, so a dead receiver must not be able to
    # turn a good publication into a failed run; post_shift_map never raises.
    post_shift_map(out)
    return out

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
        out = _publish_candidate(
            conn, out, api_key=api_key, domain_claims=domain_claims,
            domain_kts=domain_kts, allow_repair=True,
        )
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
        # A re-export publishes, so it belongs in the history. It used not to
        # open a row at all, which left `status` reporting "last synthesize:
        # failed" while the map on the site was fresh — an outage that was not
        # happening, reported during the one window where someone is already
        # anxious about the content.
        run_id, run = _open_export_run()
        try:
            out = build_map_json_v2(conn)
            out = _publish_candidate(conn, out)
        except BaseException:
            _close_export_run(run, status='failed')
            raise
        _close_export_run(run, status='ok', detail={'export': {
            'domains': len(out.get('domains', [])),
            'key_trends': len(out.get('key_trends', [])),
            'sub_trends': len(out.get('sub_trends', [])),
            'links': len(out.get('links', [])),
        }})
        print("✓  map written → documents['map']")
        print(f'   {len(out.get("domains", []))} domains · {len(out.get("key_trends", []))} KTs · '
              f'{len(out.get("sub_trends", []))} sub-trends · {len(out.get("links", []))} links')
        print(f'   recorded as pipeline_runs stage=export run_id={run_id}')
        conn.close(); return

    # Load the publication contract before anything is written. validation's
    # loader raises where config's degrades, and it is only called at the gate —
    # so a mis-copied image or a bad SS_PACKAGES_DIR cost a full 25-minute
    # generation and then crashed inside _write_map_document. Failing here costs
    # milliseconds and nothing else.
    try:
        _load_contract()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'ERROR: cannot read the publication contract — {exc}\n'
              '  The gate reads it too, so generating first would only waste the '
              'run. Check SS_PACKAGES_DIR / packages/contracts.', file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        # Touches NOTHING. This used to truncate the v2 tables before printing
        # its preview — "no API calls made" was true, "no changes" was not,
        # which made it unusable as a pre-flight against a live database.
        print('\nPhase 2 preview — claim counts per domain (dry run):')
        for d in DOMAINS:
            claims = route_claims_for_domain(conn, d, limit=CLAIMS_PER_DOM)
            thinkers = len({c['thinker'] for c in claims})
            print(f'  {d["name"]:<15}  {len(claims):3d} claims  |  {thinkers} thinkers')
        print('\n--dry-run: stopping. No API calls made, nothing written.')
        conn.close(); return

    # Read what is live BEFORE the truncate. `reset_v2_tables` leaves
    # documents['map'] alone, so this would still work afterwards — but a
    # carry-forward that silently depends on which tables a reset happens to
    # spare is a trap for whoever edits the reset next.
    previous = load_published_taxonomy(conn)
    if previous:
        print(f'\nCarrying forward {sum(len(v) for v in previous.values())} '
              f'published key shift(s) across {len(previous)} sphere(s).')

    # ── Always reset v2 tables ───────────────────────────────────────────────
    reset_v2_tables(conn)

    # ── Phase 1 (free) ───────────────────────────────────────────────────────
    phase1_domain_definitions(conn)

    if args.phase1:
        # --phase1 legitimately does DB setup, so the reset above is its job.
        print('\nPhase 2 preview — claim counts per domain:')
        for d in DOMAINS:
            claims = route_claims_for_domain(conn, d, limit=CLAIMS_PER_DOM)
            thinkers = len({c['thinker'] for c in claims})
            print(f'  {d["name"]:<15}  {len(claims):3d} claims  |  {thinkers} thinkers')
        print('\n--phase1: stopping after DB setup. Run without --phase1 to continue.')
        conn.close(); return

    # ── Need API key for paid phases ─────────────────────────────────────────
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        print('ERROR: ANTHROPIC_API_KEY not set.')
        sys.exit(1)

    # The spend ceiling raises from inside whichever phase happens to cross it,
    # and every phase writes as it goes. Uncaught, that surfaced as a raw
    # traceback with the v2 tables half-populated — and the standing advice
    # after a failure ("re-publish for free with --export-only") is actively
    # WRONG in that state: it would publish a partial map over a good one.
    try:
        # ── Phase 2: claim routing (free, SQL) ───────────────────────────────
        domain_claims = phase2_claim_routing(conn)

        # ── Phase 3: Key Trend generation per domain ─────────────────────────
        domain_kts = phase3_key_trends(conn, api_key, domain_claims, previous=previous)

        # ── Phase 4: sub-trend clustering ────────────────────────────────────
        phase4_sub_trends(conn, api_key, domain_claims, domain_kts)

        # ── Hero stats (free, SQL) — must precede the editorial phase, whose
        #    stat_band module is built from hero_stat.value. ──────────────────
        phase8_hero_stats(conn)

        # ── Phase 4b: editorial modules ──────────────────────────────────────
        phase4b_editorial(conn, api_key, domain_claims, domain_kts)
    except BudgetExceeded as exc:
        orchestrated_id = os.environ.get('SS_RUN_ID')
        if not orchestrated_id:
            run_id = observability.new_run_id('synthesize')
            budget_run = RunLog(run_id, 'synthesize')
            budget_run.start()
            budget_run.finish(status='failed', detail={'budget': {'error': str(exc)}})
        else:
            RunLog(orchestrated_id, 'synthesize').add_usage(
                detail={'budget': {'error': str(exc)}})
        print(
            f'\nERROR: spend ceiling reached — {exc}\n'
            '  The v2 tables now hold a PARTIAL map. Nothing was published:\n'
            "  documents['map'] is untouched and the site is still serving the "
            'last good one.\n'
            '  Do NOT run --export-only — it would publish this partial map over '
            'that one.\n'
            '  Raise SS_MAP_BUDGET_USD and re-run in full.',
            file=sys.stderr,
        )
        conn.close(); sys.exit(1)

    # ── Phases 5 (attribution/voices), 6 (interrelatedness/links) and
    # 7 (synthesis insights) are DORMANT — deliberately not called. They were
    # ~40% of the run's calls producing content no sphere renders: voices and
    # related_shifts are hidden by the visibility matrix on all four spheres,
    # and insights reach the view-model but no component (2026-08-10 audit).
    # The phase modules stay on disk; to re-enable one, reinstate its call
    # here and read its docstring first — phase 6 in particular must not come
    # back until prompt_interrelatedness_batch stops writing reasoning from
    # names alone (prompts/map_data.py drops the desc fields).

    # ── Phase 9: export ───────────────────────────────────────────────────────
    print('\nPhase 9 — Exporting map…')
    out = build_map_json_v2(conn)
    out = _publish_candidate(
        conn, out, api_key=api_key, domain_claims=domain_claims,
        domain_kts=domain_kts, allow_repair=True,
    )
    conn.close()

    # Report spend to the run row. mapgen already accumulates it in
    # `llm.COST`, but nothing forwarded it — so a 17-minute rebuild that made
    # hundreds of Sonnet calls recorded $0.00, which makes the run history
    # useless for the more expensive of the two stages.
    _record_spend(out)

    print("\n✓  map → documents['map']")
    print(f'   {len(out["domains"])} domains · {len(out["key_trends"])} KTs · '
          f'{len(out["sub_trends"])} sub-trends · {len(out.get("claims") or [])} claims')
    mapgen_llm.COST.report()
    print('\nDone.')


if __name__ == '__main__':
    try:
        main()
    except PublicationValidationError as exc:
        # An expected outcome, not a crash. `_record_validation_failure` has
        # already written the run row and printed the issues and the recovery;
        # a Python traceback on top of that adds nothing, and it pushes the one
        # line that says the work is recoverable off the bottom of the terminal.
        print(f'\n✗ {exc}', file=sys.stderr)
        sys.exit(1)
