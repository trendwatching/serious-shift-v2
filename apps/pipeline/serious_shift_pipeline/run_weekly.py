#!/usr/bin/env python3
"""
run_weekly.py — Serious Shift weekly pipeline orchestrator.

Sequence (each step is a package module run via `python -m`)
  1. scraper          — fetch new raw content (append-only, per-source watermark)
  2. process_raw      — extract claims via Claude API → Postgres
  2.5 scoring         — source_depth / freshness / claim_weight (free, no API)
  2.6 deduplicate     — mark claims.duplicate_of (free heuristic)
  2.7 evaluate        — prediction status + thinker credibility_score (free, no API)
  3. generate_map_data    — rebuild documents['map'] + ['synthesis'] ┐ only runs if
  4. generate_keynote     — rebuild documents['keynote']             ┘ new claims landed

Steps 2.6–2.7 run every cron so credibility scores and duplicate flags stay current
in the DB. The gate on steps 3–4 prevents burning the map/keynote regen spend
(~$5-15) on a week where sources were quiet or broken and nothing new landed.

Database migrations (packages/db, dbmate format) are applied automatically at
the start of each run, so the cron is self-sufficient against a fresh database.
Pass --skip-migrate if you manage the schema externally.

Usage (run from the repo root; DATABASE_URL + ANTHROPIC_API_KEY in env)
  python -m serious_shift_pipeline.run_weekly
  python -m serious_shift_pipeline.run_weekly --skip-scrape  # process + regen only
  python -m serious_shift_pipeline.run_weekly --skip-regen   # scrape + process only
  python -m serious_shift_pipeline.run_weekly --dry-run      # print plan, no changes
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

from .core import db

# Logs live under cwd (the repo root the operator runs from), matching the
# converted step modules (SS_LOGS_DIR).
LOGS_DIR  = os.environ.get('SS_LOGS_DIR', os.path.join(os.getcwd(), 'logs'))
ERROR_LOG = os.path.join(LOGS_DIR, 'error_log.jsonl')
TOKEN_LOG = os.path.join(LOGS_DIR, 'token_log.jsonl')
PYTHON    = sys.executable
# Each pipeline step is now a package module, run as `python -m …`.
MOD = 'serious_shift_pipeline'

# ── Escalation thresholds ───────────────────────────────────────────
# Sonnet-era full refresh is ~$60-100; alert on anomalies above that band.
COST_ALERT_THRESHOLD        = 120.00 # USD; notify if single run exceeds this
PROCESS_FAIL_RATE_THRESHOLD = 0.25   # notify if >25% of process_raw attempts failed
FAILED_SOURCES_THRESHOLD    = 3      # notify if ≥N sources in failed state after run

# ── Regen step status values ────────────────────────────────────────
REGEN_RAN_OK             = 'ran_ok'             # subprocess exited 0
REGEN_FAILED             = 'failed'             # subprocess exited non-zero
REGEN_SKIPPED            = 'skipped'            # --skip-regen flag
REGEN_SKIPPED_NO_CLAIMS  = 'skipped_no_claims'  # gate: new_claims == 0
REGEN_SKIPPED_MAP_FAILED = 'skipped_map_failed' # keynote skipped because map failed
REGEN_DRY_RUN            = 'dry_run'            # dry-run mode; would have run


def get_api_key() -> str:
    """API key from the environment (the SDK reads ANTHROPIC_API_KEY too)."""
    return os.environ.get('ANTHROPIC_API_KEY', '')


# ============================================================
# DB HELPERS
# ============================================================

def count_high_quality_claims() -> int:
    """Count signal+strong_signal, non-duplicate claims currently in the DB."""
    with db.connect() as conn:
        return db.query_one(conn,
            """SELECT COUNT(*) AS n FROM claims
               WHERE signal_strength IN ('signal','strong_signal')
                 AND duplicate_of IS NULL""")['n']


def count_failed_sources() -> int:
    """Count sources with last_run_status = 'failed' in source_state."""
    try:
        with db.connect() as conn:
            return db.query_one(conn,
                "SELECT COUNT(*) AS n FROM source_state WHERE last_run_status = 'failed'")['n']
    except Exception:
        return 0


# ============================================================
# NOTIFICATIONS
# ============================================================

def notify(title: str, message: str, urgency: str = 'info') -> None:
    """
    Send a macOS desktop notification.

    urgency: 'info' | 'warning' | 'critical'
             (reserved for future routing to ntfy.sh / email / Slack)

    Silently no-ops if osascript is unavailable (non-macOS, CI, etc.).
    """
    script = (
        f'display notification {json.dumps(message)} '
        f'with title {json.dumps(title)}'
    )
    try:
        subprocess.run(
            ['osascript', '-e', script],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        pass  # osascript not available


def _read_recent_token_entries(log_path: str, n: int = 5) -> list[dict]:
    """Return the last n entries from token_log.jsonl (oldest first)."""
    if not os.path.exists(log_path):
        return []
    entries = []
    with open(log_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries[-n:]


def check_escalation(
    *,
    errors: list[dict],
    new_claims: int,
    token_entry: dict | None,
    token_log_path: str,
    failed_sources: int,
    no_notify: bool = False,
    _notify_fn=None,     # injectable for tests; defaults to notify()
) -> list[str]:
    """
    Evaluate all escalation conditions.  Returns a list of triggered alert
    messages (empty = no escalation).  Sends one bundled notification unless
    no_notify is True.

    Conditions checked:
      1. Run cost exceeded COST_ALERT_THRESHOLD
      2. >PROCESS_FAIL_RATE_THRESHOLD of process_raw attempts failed
      3. >= FAILED_SOURCES_THRESHOLD sources in 'failed' state
      4. Zero new claims AND previous run also had zero new claims
      (Condition for run abort is handled upstream before this is called.)
    """
    _fn = _notify_fn or notify
    alerts: list[str] = []

    # ── Condition 1: cost overrun ────────────────────────────────
    if token_entry:
        cost = token_entry.get('total_cost_usd', 0.0)
        if cost > COST_ALERT_THRESHOLD:
            alerts.append(
                f"Run cost ${cost:.2f} exceeds threshold ${COST_ALERT_THRESHOLD:.2f}"
            )

    # ── Condition 2: high process_raw failure rate ───────────────
    process_errors = sum(1 for e in errors if e.get('stage') == 'process')
    files_ok = token_entry.get('total_files_processed', 0) if token_entry else 0
    total_attempted = files_ok + process_errors
    if total_attempted > 0:
        fail_rate = process_errors / total_attempted
        if fail_rate > PROCESS_FAIL_RATE_THRESHOLD:
            alerts.append(
                f"Process failure rate {fail_rate:.0%} "
                f"({process_errors}/{total_attempted} files failed)"
            )

    # ── Condition 3: too many failed sources ─────────────────────
    if failed_sources >= FAILED_SOURCES_THRESHOLD:
        alerts.append(
            f"{failed_sources} sources in 'failed' state "
            f"(threshold: {FAILED_SOURCES_THRESHOLD})"
        )

    # ── Condition 4: consecutive zero-claim runs ─────────────────
    if new_claims == 0:
        recent = _read_recent_token_entries(token_log_path, n=5)
        # The last entry is the current run; look at the one before it
        if len(recent) >= 2:
            prev_files = recent[-2].get('total_files_processed', -1)
            if prev_files == 0:
                alerts.append(
                    "Zero new claims this run AND previous run — "
                    "possible silent breakage"
                )

    # ── Send notification ────────────────────────────────────────
    if alerts and not no_notify:
        run_date = (
            token_entry.get('run_at', datetime.now().isoformat())[:10]
            if token_entry else datetime.now().strftime('%Y-%m-%d')
        )
        urgency = 'critical' if len(alerts) > 1 else 'warning'
        summary = '; '.join(alerts)
        message = f"Run {run_date}: {summary}\nCheck logs: {LOGS_DIR}"
        _fn(
            title='Serious Shift — Weekly Run Alert',
            message=message,
            urgency=urgency,
        )

    return alerts


# ============================================================
# ERROR LOG READER
# ============================================================

def read_last_token_entry_since(offset: int) -> dict | None:
    """
    Return the token log entry written during this run.
    Seeks past `offset` (recorded before the run) so historical entries
    from prior weeks are ignored.  Returns the last entry found, or None.
    """
    if not os.path.exists(TOKEN_LOG):
        return None
    with open(TOKEN_LOG, encoding='utf-8') as f:
        f.seek(offset)
        last = None
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                pass
    return last


def read_errors_since(offset: int) -> list[dict]:
    """
    Return all error entries appended to error_log.jsonl since byte offset.
    Using an offset (recorded before the run) ensures we only report THIS
    run's errors, not historical ones from previous weeks.
    """
    if not os.path.exists(ERROR_LOG):
        return []
    entries = []
    with open(ERROR_LOG, encoding='utf-8') as f:
        f.seek(offset)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


# ============================================================
# PIPELINE ERROR LOGGER
# ============================================================

def _log_pipeline_error(log_path: str, *, stage: str, message: str) -> None:
    """
    Append one structured error entry to error_log.jsonl for a failed
    orchestrator step (generate_map or generate_keynote).

    Format is consistent with ErrorLog entries written by scraper.py and
    process_raw.py so the end-of-run summary can render them uniformly.
    """
    entry = {
        'timestamp':      datetime.now().isoformat(),
        'stage':          stage,
        'error_class':    'SubprocessError',
        'error_message':  message,
        'thinker':        None,
        'retry_attempted': False,
    }
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')


# ============================================================
# STEP RUNNER
# ============================================================

def run_step(label: str, cmd: list, dry_run: bool = False,
             env: dict | None = None) -> int:
    """
    Run one pipeline step as a subprocess.
    Prints a labelled header, respects dry_run, returns exit code.
    Non-zero exit codes are reported but do NOT abort the pipeline —
    each step is isolated so a failure in step N doesn't skip N+1.
    """
    print(f"\n{'─'*60}")
    print(f"  {label}")
    if dry_run:
        print(f"  [dry-run] would run: {' '.join(str(c) for c in cmd)}")
        return 0
    result = subprocess.run(cmd, env=env)  # inherits cwd (repo root: config + raw_content)
    if result.returncode != 0:
        print(f"  ⚠  exited with code {result.returncode}")
    return result.returncode


# ============================================================
# REGEN STEPS (steps 3 & 4)
# ============================================================

def run_regen_steps(
    new_claims: int,
    skip_regen: bool,
    dry_run: bool,
    subprocess_env: dict | None,
    error_log_path: str,
) -> tuple[str, str]:
    """
    Execute Step 3 (generate_map_data) and Step 4 (generate_keynote)
    with proper gating and failure isolation.

    Gate: both steps are skipped if new_claims == 0 (and not dry-run).
    Failure isolation: if Step 3 fails, Step 4 is skipped and both failures
    are logged to error_log_path; the run still exits 0.

    Returns (map_status, keynote_status) where each is a REGEN_* constant.
    """

    # ── --skip-regen: skip both ──────────────────────────────────────
    if skip_regen:
        print(f"\n{'─'*60}")
        print("  STEP 3/4 — Map regen:     skipped (--skip-regen)")
        print(f"\n{'─'*60}")
        print("  STEP 4/4 — Keynote regen: skipped (--skip-regen)")
        return REGEN_SKIPPED, REGEN_SKIPPED

    # ── gate: no new claims (live run only) ─────────────────────────
    if new_claims == 0 and not dry_run:
        print(f"\n{'─'*60}")
        print("  STEP 3/4 — Map regen:     skipped (no new claims)")
        print(f"\n{'─'*60}")
        print("  STEP 4/4 — Keynote regen: skipped (no new claims)")
        return REGEN_SKIPPED_NO_CLAIMS, REGEN_SKIPPED_NO_CLAIMS

    # ── Step 3: rebuild map (→ documents['map']) ────────────────────
    if dry_run:
        print(f"\n{'─'*60}")
        print("  STEP 3/4 — Rebuild map (Claude API clustering)")
        print("  [dry-run] would run: -m serious_shift_pipeline.steps.generate_map_data  [gate: new_claims > 0]")
        map_status = REGEN_DRY_RUN
    else:
        rc3 = run_step(
            "STEP 3/4 — Rebuild map (Claude API clustering)",
            [PYTHON, '-m', f'{MOD}.steps.generate_map_data'],
            dry_run=False,
            env=subprocess_env,
        )
        if rc3 == 0:
            map_status = REGEN_RAN_OK
        else:
            map_status = REGEN_FAILED
            _log_pipeline_error(
                error_log_path,
                stage='generate_map',
                message=f"generate_map_data exited with code {rc3}",
            )

    # ── Step 4: rebuild keynote (→ documents['keynote']) ────────────
    if dry_run:
        print(f"\n{'─'*60}")
        print("  STEP 4/4 — Rebuild keynote (Claude API synthesis)")
        print("  [dry-run] would run: -m serious_shift_pipeline.steps.generate_keynote"
              "  [gate: new_claims > 0 and map succeeded]")
        keynote_status = REGEN_DRY_RUN
    elif map_status == REGEN_FAILED:
        print(f"\n{'─'*60}")
        print("  STEP 4/4 — Keynote regen: skipped (map step failed)")
        keynote_status = REGEN_SKIPPED_MAP_FAILED
    else:
        rc4 = run_step(
            "STEP 4/4 — Rebuild keynote (Claude API synthesis)",
            [PYTHON, '-m', f'{MOD}.steps.generate_keynote'],
            dry_run=False,
            env=subprocess_env,
        )
        if rc4 == 0:
            keynote_status = REGEN_RAN_OK
        else:
            keynote_status = REGEN_FAILED
            _log_pipeline_error(
                error_log_path,
                stage='generate_keynote',
                message=f"generate_keynote exited with code {rc4}",
            )

    return map_status, keynote_status


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Serious Shift weekly pipeline')
    parser.add_argument('--skip-scrape', action='store_true',
                        help='Skip fetch step (process existing raw files only)')
    parser.add_argument('--skip-regen',  action='store_true',
                        help='Skip map + keynote regeneration even if new claims exist')
    parser.add_argument('--dry-run',     action='store_true',
                        help='Print what would run without making any changes')
    parser.add_argument('--no-notify',   action='store_true',
                        help='Suppress desktop notifications (useful for manual runs)')
    parser.add_argument('--skip-migrate', action='store_true',
                        help='Skip the startup migration step (schema managed externally)')
    args = parser.parse_args()

    api_key = get_api_key()
    if not args.dry_run and not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Set env var or add to .env.local.")
        sys.exit(1)

    # Ensure the schema exists before any query. The weekly cron runs unattended
    # against the shared Postgres; bootstrapping here means a database that never
    # had `dbmate up` run against it still works (idempotent, dbmate-compatible).
    if not args.skip_migrate:
        from .core import migrate
        print("\n  Applying database migrations…")
        try:
            migrate.apply_pending()
        except Exception as e:  # noqa: BLE001 — surface a clear, actionable failure
            print(f"ERROR: could not apply database migrations: {e}")
            sys.exit(1)

    # Pass the key explicitly to subprocesses so they don't need to re-read .env.local
    subprocess_env = {**os.environ, 'ANTHROPIC_API_KEY': api_key} if api_key else None

    os.makedirs(LOGS_DIR, exist_ok=True)

    # Record log sizes before the run so we can isolate this run's entries
    error_log_offset = (
        os.path.getsize(ERROR_LOG) if os.path.exists(ERROR_LOG) else 0
    )
    token_log_offset = (
        os.path.getsize(TOKEN_LOG) if os.path.exists(TOKEN_LOG) else 0
    )

    run_start    = datetime.now()
    claims_before = count_high_quality_claims()

    print(f"\n{'='*60}")
    print("  SERIOUS SHIFT WEEKLY PIPELINE")
    print(f"  {run_start.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Claims in DB: {claims_before:,}")
    if args.dry_run:
        print("  [DRY-RUN MODE]")
    print(f"{'='*60}")

    # ── Step 1: Scrape ──────────────────────────────────────────────
    if not args.skip_scrape:
        run_step(
            "STEP 1/4 — Scrape (append-only, per-source watermark)",
            [PYTHON, '-m', f'{MOD}.steps.scraper', '--all'],
            dry_run=args.dry_run,
            env=subprocess_env,
        )
    else:
        print("\n  STEP 1/4 — Scrape: skipped (--skip-scrape)")

    # ── Step 2: Process raw files ───────────────────────────────────
    run_step(
        "STEP 2/4 — Process raw files (Claude API extraction)",
        [PYTHON, '-m', f'{MOD}.steps.process_raw'],
        dry_run=args.dry_run,
        env=subprocess_env,
    )

    # ── Step 2.5: Score claims (free; so new claims rank correctly) ──
    run_step(
        "STEP 2.5 — Score claims (source_depth, freshness, claim_weight)",
        [PYTHON, '-m', f'{MOD}.steps.scoring'],
        dry_run=args.dry_run,
        env=subprocess_env,
    )

    # ── Step 2.6: Deduplicate claims (free heuristic; marks duplicate_of) ──
    # Runs before the new-claims count so the gate counts net-new *unique* claims,
    # and before regen so the map/keynote exclude duplicates.
    run_step(
        "STEP 2.6 — Deduplicate claims (mark duplicate_of)",
        [PYTHON, '-m', f'{MOD}.steps.deduplicate', '--execute'],
        dry_run=args.dry_run,
        env=subprocess_env,
    )

    # ── Step 2.7: Evaluate predictions + recompute credibility (free, no API) ──
    # Updates prediction status/accuracy and thinker credibility_score, which the
    # map + keynote rank by — so it must run before regen.
    run_step(
        "STEP 2.7 — Evaluate predictions + thinker credibility",
        [PYTHON, '-m', f'{MOD}.steps.evaluate'],
        dry_run=args.dry_run,
        env=subprocess_env,
    )

    claims_after = count_high_quality_claims()
    new_claims   = claims_after - claims_before

    print(f"\n  New claims added this run: {new_claims:+,}")
    print(f"  Total claims in DB:        {claims_after:,}")

    # ── Steps 3–4: Regenerate outputs (gated on new claims) ────────
    map_status, keynote_status = run_regen_steps(
        new_claims=new_claims,
        skip_regen=args.skip_regen,
        dry_run=args.dry_run,
        subprocess_env=subprocess_env,
        error_log_path=ERROR_LOG,
    )

    # ── Run summary ─────────────────────────────────────────────────
    elapsed  = int((datetime.now() - run_start).total_seconds())
    errors   = read_errors_since(error_log_offset)

    def _regen_label(status: str) -> str:
        """Human-readable label for a REGEN_* status value."""
        labels = {
            REGEN_RAN_OK:             '✓ rebuilt',
            REGEN_FAILED:             '✗ FAILED',
            REGEN_SKIPPED:            'skipped (--skip-regen)',
            REGEN_SKIPPED_NO_CLAIMS:  'skipped (no new claims)',
            REGEN_SKIPPED_MAP_FAILED: 'skipped (map failed)',
            REGEN_DRY_RUN:            '[dry-run]',
        }
        return labels.get(status, status)

    print(f"\n{'='*60}")
    print(f"  RUN COMPLETE  —  {elapsed}s elapsed")
    print(f"  New claims:   {new_claims:+,}  |  Total: {claims_after:,}")

    token_entry = read_last_token_entry_since(token_log_offset)
    if token_entry:
        cost = token_entry.get('total_cost_usd', 0)
        inp  = token_entry.get('total_input_tokens', 0)
        out  = token_entry.get('total_output_tokens', 0)
        print(f"  API cost:     ${cost:.4f}  ({inp:,} in / {out:,} out)")
    else:
        print("  API cost:     $0.0000")

    print(f"  Map:          {_regen_label(map_status)}")
    print(f"  Keynote:      {_regen_label(keynote_status)}")

    if errors:
        print(f"\n  ── Errors this run ({len(errors)}) ──")
        for e in errors:
            stage   = e.get('stage', '?')
            thinker = e.get('thinker') or '—'
            cls     = e.get('error_class', '?')
            msg     = e.get('error_message', '')[:70]
            print(f"    [{stage}] {thinker} | {cls}: {msg}")
        print(f"\n  Full log: {ERROR_LOG}")
    else:
        print("  Errors:       0")

    print(f"{'='*60}\n")

    # ── Escalation checks ───────────────────────────────────────────
    if not args.dry_run:
        alerts = check_escalation(
            errors=errors,
            new_claims=new_claims,
            token_entry=token_entry,
            token_log_path=TOKEN_LOG,
            failed_sources=count_failed_sources(),
            no_notify=args.no_notify,
        )
        if alerts:
            print(f"  ⚠  {len(alerts)} escalation alert(s) sent:")
            for a in alerts:
                print(f"     · {a}")


if __name__ == '__main__':
    main()
