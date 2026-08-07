#!/usr/bin/env python3
"""
Pipeline orchestrator.

Two stages, independently triggerable:

  ingest      scrape → extract → score → deduplicate → evaluate
              Fetches new content and turns it into scored, deduplicated claims.
              Costs Haiku money in proportion to how much landed.

  synthesize  mapgen
              Rebuilds the trend map from whatever claims are already in the
              database. Costs Sonnet money, a flat ~$5 regardless of input.

They were one script because they always ran together on a Sunday. They are
separate now because they fail, cost and schedule differently: a scrape that
breaks should not stop you re-running synthesis, and re-running synthesis to
pick up an editorial prompt change should not re-scrape 120 sources.

  python -m serious_shift_pipeline.run ingest
  python -m serious_shift_pipeline.run synthesize
  python -m serious_shift_pipeline.run all          # both, in order (the cron)
  python -m serious_shift_pipeline.run all --dry-run
  python -m serious_shift_pipeline.run ingest --only scrape

Every invocation opens a row in `pipeline_runs` and files its errors against it
in `pipeline_errors`, so a failed run is diagnosable after the container is
gone. Migrations are applied on startup, so a fresh database bootstraps itself.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from .core import db, observability
from .core.observability import ErrorLog, RunLog

PYTHON = sys.executable
MOD = 'serious_shift_pipeline'

# ── Escalation thresholds ───────────────────────────────────────────
# A measured full refresh is ~$18-22 (extraction + map). The old $120 ceiling
# was ~6x that, so it could not fire even on a 5x runaway. Set to ~2x measured.
COST_ALERT_THRESHOLD        = float(os.environ.get('SS_COST_ALERT_USD', '25.00'))
PROCESS_FAIL_RATE_THRESHOLD = 0.25   # notify if >25% of extraction attempts failed
FAILED_SOURCES_THRESHOLD    = 3      # notify if ≥N sources in failed state after run


# ============================================================
# STEP TABLE
# ============================================================

@dataclass(frozen=True)
class Step:
    """One pipeline step, run as its own `python -m` subprocess.

    Subprocesses rather than imports so a step that segfaults, leaks or blows
    its memory ceiling cannot take the orchestrator with it, and so each is
    runnable standalone with the identical command line.
    """
    name: str
    stage: str
    args: list[str]
    label: str
    #: Skipped unless the run asked for it (`--discover`).
    opt_in: bool = False
    #: Only runs when new claims landed, unless --force. The map is a pure
    #: function of the claims: regenerating on unchanged input is pure spend.
    gated: bool = False

    def command(self) -> list[str]:
        return [PYTHON, '-m', f'{MOD}.{self.args[0]}', *self.args[1:]]


STEPS: list[Step] = [
    Step('discover', 'ingest', ['steps.discover'],
         'Discover (gated arXiv/OpenAlex expansion)', opt_in=True),
    Step('scrape', 'ingest', ['steps.scraper', '--all'],
         'Scrape (append-only, per-source watermark)'),
    Step('extract', 'ingest', ['steps.process_raw'],
         'Extract claims (Claude API)'),
    Step('score', 'ingest', ['steps.scoring'],
         'Score claims (source_depth, freshness, claim_weight)'),
    Step('dedupe', 'ingest', ['steps.deduplicate', '--execute'],
         'Deduplicate claims (mark duplicate_of)'),
    Step('evaluate', 'ingest', ['steps.evaluate'],
         'Evaluate predictions + thinker credibility'),
    Step('mapgen', 'synthesize', ['mapgen.cli'],
         'Rebuild the trend map (Claude API clustering)', gated=True),
    # After mapgen, so it classifies against the map that was just published
    # rather than last week's. Also runs standalone on an hourly cron with
    # SS_CLASSIFY_MODEL=0, where it is pure SQL and costs nothing on a quiet
    # hour — that is what keeps a newly ingested innovation from waiting a week
    # for its shift links.
    Step('classify', 'synthesize', ['steps.classify'],
         'Map innovations onto the shifts they exemplify'),
]

STAGES = ('ingest', 'synthesize')


def steps_for(stage: str, *, only: str | None, discover: bool) -> list[Step]:
    """The steps to run, in order, for one stage."""
    out = [s for s in STEPS if s.stage == stage]
    if not discover:
        out = [s for s in out if not s.opt_in]
    if only:
        out = [s for s in out if s.name == only]
        if not out:
            names = ', '.join(s.name for s in STEPS if s.stage == stage)
            sys.exit(f"error: --only {only!r} is not a {stage} step. Choose from: {names}")
    return out


# ============================================================
# DB HELPERS
# ============================================================

def count_high_quality_claims() -> int:
    """signal+strong_signal, non-duplicate claims currently in the DB."""
    with db.connect() as conn:
        return db.scalar(conn,
            """SELECT COUNT(*) FROM claims
               WHERE signal_strength IN ('signal','strong_signal')
                 AND duplicate_of IS NULL""")


def count_failed_sources() -> int:
    """Sources that are broken — deliberately NOT counting 'blocked'.

    A blocked source needs a proxy credential, not a fix. Counting the two
    together pinned this alert permanently at 11 (every YouTube source), which
    made it useless for spotting the next source that actually breaks.
    """
    try:
        with db.connect() as conn:
            return db.scalar(conn,
                "SELECT COUNT(*) FROM source_state WHERE last_run_status = 'failed'")
    except Exception:  # noqa: BLE001 — a missing table must not fail the run
        return 0


def count_blocked_sources() -> int:
    """Sources the host is refusing from this IP. Reported once, not alarmed on."""
    try:
        with db.connect() as conn:
            return db.scalar(conn,
                "SELECT COUNT(*) FROM source_state WHERE last_run_status = 'blocked'")
    except Exception:  # noqa: BLE001
        return 0


def claims_at_last_synthesis() -> int | None:
    """Claim count as of the last successful synthesize run, or None if never.

    This is what makes `synthesize` independently gateable. Previously the gate
    compared claim counts across one combined invocation, so running synthesis
    on its own had nothing to compare against and always regenerated.
    """
    try:
        with db.connect() as conn:
            row = db.query_one(conn,
                """SELECT claims_after FROM pipeline_runs
                   WHERE stage = 'synthesize' AND status = 'ok'
                     AND claims_after IS NOT NULL
                   ORDER BY started_at DESC LIMIT 1""")
        return row['claims_after'] if row else None
    except Exception:  # noqa: BLE001 — treat an unreadable history as "unknown"
        return None


# ============================================================
# NOTIFICATIONS
# ============================================================

def notify(title: str, message: str, urgency: str = 'info') -> None:
    """Raise an operator alert. urgency: 'info' | 'warning' | 'critical'.

    Always prints to stdout, so the alert survives in the container logs even
    when no webhook is configured — the original osascript-only implementation
    silently no-opped on Linux, which meant no alert had ever fired in
    production. If SS_ALERT_WEBHOOK is set, POST a JSON payload to it
    (Slack/Discord/ntfy all accept a `text` field). Delivery failure is logged,
    never raised: alerting must not be able to fail the run it reports on.
    """
    print(f'[ALERT:{urgency}] {title} — {message}', flush=True)

    url = os.environ.get('SS_ALERT_WEBHOOK', '').strip()
    if not url:
        return
    payload = json.dumps({
        'text': f'[{urgency}] {title}\n{message}',
        'title': title, 'message': message, 'urgency': urgency,
    }).encode()
    req = urllib.request.Request(
        url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:  # noqa: BLE001 — alerting must never break the run
        print(f'[ALERT] webhook delivery failed: {e}', flush=True)


def check_escalation(
    *,
    errors: list[dict],
    new_claims: int,
    run_row: dict | None,
    previous_runs: list[dict],
    failed_sources: int,
    no_notify: bool = False,
    _notify_fn=None,     # injectable for tests
) -> list[str]:
    """Evaluate every escalation condition. Returns the triggered messages
    (empty = no escalation) and sends one bundled notification.

    Conditions:
      1. Run cost exceeded COST_ALERT_THRESHOLD
      2. >PROCESS_FAIL_RATE_THRESHOLD of extraction attempts failed
      3. >= FAILED_SOURCES_THRESHOLD sources in 'failed' state
      4. Zero new claims AND the previous run also processed nothing
    """
    _fn = _notify_fn or notify
    alerts: list[str] = []

    if run_row:
        cost = float(run_row.get('cost_usd') or 0)
        if cost > COST_ALERT_THRESHOLD:
            alerts.append(
                f"Run cost ${cost:.2f} exceeds threshold ${COST_ALERT_THRESHOLD:.2f}")

    extract_errors = sum(1 for e in errors if e.get('step') in ('extract', 'write'))
    files_ok = (run_row or {}).get('files_processed', 0) or 0
    total_attempted = files_ok + extract_errors
    if total_attempted > 0:
        fail_rate = extract_errors / total_attempted
        if fail_rate > PROCESS_FAIL_RATE_THRESHOLD:
            alerts.append(
                f"Extraction failure rate {fail_rate:.0%} "
                f"({extract_errors}/{total_attempted} files failed)")

    if failed_sources >= FAILED_SOURCES_THRESHOLD:
        alerts.append(
            f"{failed_sources} sources in 'failed' state "
            f"(threshold: {FAILED_SOURCES_THRESHOLD})")

    # Compared against the previous run *of this stage*. Synthesis never
    # processes files and never adds claims, so measuring it against "whatever
    # ran last" made every back-to-back `synthesize` report silent breakage —
    # an alert that cries wolf is worse than no alert. Only ingest-shaped stages
    # carry the signal, so only they are judged on it.
    stage = (run_row or {}).get('stage')
    if new_claims == 0 and stage in ('ingest', 'full'):
        same_stage = [r for r in previous_runs if r.get('stage') == stage]
        if same_stage and (same_stage[0].get('files_processed') or 0) == 0:
            alerts.append(
                f"Zero new claims this {stage} run AND the previous one — possible silent breakage")

    if alerts and not no_notify:
        urgency = 'critical' if len(alerts) > 1 else 'warning'
        run_id = (run_row or {}).get('run_id', '?')
        _fn(
            title='Serious Shift — Pipeline Alert',
            message=(f"Run {run_id}: {'; '.join(alerts)}\n"
                     f"Detail: SELECT * FROM pipeline_errors WHERE run_id = '{run_id}'"),
            urgency=urgency,
        )
    return alerts


# ============================================================
# STEP RUNNER
# ============================================================

def run_step(step: Step, *, dry_run: bool, env: dict | None) -> int:
    """Run one step as a subprocess. Returns its exit code.

    A non-zero exit is reported but does NOT abort the stage: the steps are
    ordered, not transactional, and a scrape that fails should still let the
    already-downloaded files be extracted.
    """
    print(f"\n{'─' * 60}")
    print(f"  {step.label}")
    cmd = step.command()
    if dry_run:
        print(f"  [dry-run] would run: {' '.join(cmd)}")
        return 0
    rc = subprocess.run(cmd, env=env or os.environ).returncode
    if rc != 0:
        print(f"  ⚠  exited with code {rc}")
    return rc


def run_stage(
    stage: str, *, args, error_log: ErrorLog, subprocess_env: dict | None,
) -> dict[str, str]:
    """Run every step of one stage. Returns {step_name: outcome}."""
    outcomes: dict[str, str] = {}
    selected = steps_for(stage, only=args.only, discover=args.discover)

    for step in selected:
        if step.gated and not args.force:
            reason = gate_reason(stage, dry_run=args.dry_run)
            if reason:
                print(f"\n{'─' * 60}")
                print(f"  {step.label}: skipped — {reason}")
                outcomes[step.name] = f'skipped ({reason})'
                continue

        rc = run_step(step, dry_run=args.dry_run, env=subprocess_env)
        if args.dry_run:
            outcomes[step.name] = 'dry-run'
        elif rc == 0:
            outcomes[step.name] = 'ok'
        else:
            outcomes[step.name] = f'FAILED (exit {rc})'
            error_log.record(
                step=step.name, thinker=None,
                exc=RuntimeError(f'{step.name} exited with code {rc}'),
                retry_attempted=False, outcome='failed', stage=stage,
            )
    return outcomes


def gate_reason(stage: str, *, dry_run: bool) -> str | None:
    """Why the gated step of `stage` should be skipped, or None to run it."""
    if dry_run:
        return None
    baseline = claims_at_last_synthesis()
    if baseline is None:
        return None  # never synthesized — always run the first time
    current = count_high_quality_claims()
    if current <= baseline:
        return f'no new claims since the last map ({current:,} then and now)'
    return None


# ============================================================
# MAIN
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='Serious Shift pipeline', prog='serious_shift_pipeline.run')
    p.add_argument('stage', nargs='?', default='all', choices=[*STAGES, 'all'],
                   help="Which stage to run (default: all)")
    p.add_argument('--only', metavar='STEP',
                   help='Run a single step of the stage (e.g. --only scrape)')
    p.add_argument('--force', action='store_true',
                   help='Run gated steps even when no new claims landed')
    p.add_argument('--dry-run', action='store_true',
                   help='Print what would run without making any changes')
    p.add_argument('--discover', action='store_true',
                   help='Include the opt-in arXiv/OpenAlex discovery step')
    p.add_argument('--no-notify', action='store_true',
                   help='Suppress escalation notifications')
    p.add_argument('--skip-migrate', action='store_true',
                   help='Skip the startup migration step (schema managed externally)')
    p.add_argument('--list-steps', action='store_true',
                   help='Print the step table and exit')
    return p


def main() -> int:
    args = build_parser().parse_args()

    if args.list_steps:
        for stage in STAGES:
            print(f"\n{stage}:")
            for s in STEPS:
                if s.stage != stage:
                    continue
                tags = ' '.join(t for t, on in
                                (('opt-in', s.opt_in), ('gated', s.gated)) if on)
                print(f"  {s.name:<10} {s.label}{f'  [{tags}]' if tags else ''}")
        return 0

    stages = list(STAGES) if args.stage == 'all' else [args.stage]

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not args.dry_run and not api_key:
        print('ERROR: ANTHROPIC_API_KEY not set.')
        return 1

    # Bootstrap the schema before any query. The cron runs unattended against a
    # shared Postgres; doing this here means a database that never had `dbmate
    # up` run against it still works (idempotent, dbmate-compatible).
    if not args.skip_migrate and not args.dry_run:
        from .core import migrate
        print('\n  Applying database migrations…')
        try:
            migrate.apply_pending()
        except Exception as e:  # noqa: BLE001 — surface a clear, actionable failure
            print(f'ERROR: could not apply database migrations: {e}')
            return 1

    stage_label = args.stage if args.stage != 'all' else 'full'
    run_id = observability.new_run_id(stage_label)
    run = RunLog(run_id, stage_label)
    error_log = ErrorLog(run_id)

    # Steps inherit the run id so their errors and spend attach to this run.
    subprocess_env = {**os.environ, 'SS_RUN_ID': run_id}
    if api_key:
        subprocess_env['ANTHROPIC_API_KEY'] = api_key

    started = datetime.now()
    claims_before = 0 if args.dry_run else count_high_quality_claims()
    if not args.dry_run:
        run.start(claims_before=claims_before)

    print(f"\n{'=' * 60}")
    print(f"  SERIOUS SHIFT PIPELINE — {' + '.join(stages)}")
    print(f"  {started:%Y-%m-%d %H:%M}  ·  run {run_id}")
    print(f"  Claims in DB: {claims_before:,}")
    if args.dry_run:
        print('  [DRY-RUN MODE]')
    print('=' * 60)

    outcomes: dict[str, str] = {}
    try:
        for stage in stages:
            outcomes |= run_stage(
                stage, args=args, error_log=error_log, subprocess_env=subprocess_env,
            )
    except KeyboardInterrupt:
        run.finish(status='aborted', detail={'steps': outcomes})
        print('\n  Interrupted.')
        return 130

    claims_after = claims_before if args.dry_run else count_high_quality_claims()
    new_claims = claims_after - claims_before
    elapsed = int((datetime.now() - started).total_seconds())

    if args.dry_run:
        print(f"\n{'=' * 60}\n  DRY RUN COMPLETE")
        for name, outcome in outcomes.items():
            print(f"  {name:<10} {outcome}")
        print('=' * 60)
        return 0

    failed = [n for n, o in outcomes.items() if o.startswith('FAILED')]
    run.finish(
        status='failed' if failed else 'ok',
        claims_after=claims_after,
        detail={'steps': outcomes, 'elapsed_seconds': elapsed},
    )

    # ── Summary ──────────────────────────────────────────────────────
    with db.connect() as conn:
        errors = observability.errors_for_run(conn, run_id)
        run_row = db.query_one(
            conn, 'SELECT * FROM pipeline_runs WHERE run_id = %s', (run_id,))
        previous = [
            r for r in observability.recent_runs(conn, limit=5)
            if r['run_id'] != run_id
        ]

    print(f"\n{'=' * 60}")
    print(f"  RUN COMPLETE  —  {elapsed}s elapsed")
    print(f"  New claims:   {new_claims:+,}  |  Total: {claims_after:,}")
    if run_row:
        print(f"  API cost:     ${float(run_row['cost_usd']):.4f}  "
              f"({run_row['input_tokens']:,} in / {run_row['output_tokens']:,} out)")
    for name, outcome in outcomes.items():
        print(f"  {name:<10} {outcome}")

    if errors:
        print(f"\n  ── Errors this run ({len(errors)}) ──")
        for err in errors[:20]:
            print(f"    [{err['step']}] {err['thinker'] or '—'} | "
                  f"{err['error_class']}: {(err['error_message'] or '')[:70]}")
        if len(errors) > 20:
            print(f"    … and {len(errors) - 20} more")
        print(f"\n  Full detail: SELECT * FROM pipeline_errors WHERE run_id = '{run_id}'")
    else:
        print('  Errors:       0')
    print('=' * 60)

    blocked = count_blocked_sources()
    if blocked:
        print(f"\n  {blocked} source(s) blocked by the host from this IP "
              f"(set YOUTUBE_PROXY_URL or WEBSHARE_PROXY_USERNAME/PASSWORD).")

    alerts = check_escalation(
        errors=errors,
        new_claims=new_claims,
        run_row=run_row,
        previous_runs=previous,
        failed_sources=count_failed_sources(),
        no_notify=args.no_notify,
    )
    if alerts:
        print(f"  ⚠  {len(alerts)} escalation alert(s) sent:")
        for a in alerts:
            print(f"     · {a}")

    run.prune()
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
