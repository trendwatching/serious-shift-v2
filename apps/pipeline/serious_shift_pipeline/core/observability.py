"""
Run history, structured errors and cost tracking — all persisted to Postgres.

These used to be append-only JSONL files under ./logs. The pipeline runs as a
Railway cron job on an ephemeral filesystem, so the log died with the container
at exactly the moment it mattered: a failed run left an alert saying something
broke and nothing at all saying what. Postgres is already the only durable
shared state in the system, so `pipeline_runs` and `pipeline_errors` live there.

Two consequences worth knowing:

  * Writes are best-effort. Recording an error must never be able to fail the
    run it is describing, so a database problem here degrades to stderr rather
    than raising. The same applies to the run record.
  * Everything is also printed. Railway keeps container logs, so stdout stays
    the live view; Postgres is the durable one you can query afterwards.
"""
from __future__ import annotations

import os
import sys
import threading
import traceback as tb
import uuid
from datetime import datetime, timezone

import psycopg
from psycopg.types.json import Json

from . import db
from .config import cost_of

# How long run history is kept. Long enough to compare against the same week
# last quarter, short enough that the tables stay small without any operator
# involvement. prune() is called at the end of each run.
RETENTION_DAYS = int(os.environ.get("SS_RUN_RETENTION_DAYS", "180"))


def new_run_id(stage: str) -> str:
    """A run id that sorts chronologically and is unique across concurrent runs."""
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{stage}-{uuid.uuid4().hex[:6]}"


def _write(sql: str, params: tuple) -> None:
    """Execute one statement on its own short-lived connection, never raising.

    Its own connection because callers are worker threads and the run's main
    connection is not shareable across them; never raising because this is
    telemetry, and telemetry that can break the job is worse than no telemetry.
    """
    try:
        with psycopg.connect(db.get_dsn(), autocommit=True) as conn:
            conn.execute(sql, params)
    except Exception as e:  # noqa: BLE001 — see docstring
        print(f"[observability] could not persist: {e}", file=sys.stderr, flush=True)


class ErrorLog:
    """Structured pipeline errors, written to `pipeline_errors`.

    One row per failure, attributed to the run and the step that raised it.
    `record()` is called from worker threads, so the counter is lock-guarded;
    the insert itself needs no lock because each call uses its own connection.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._count = 0
        self._lock = threading.Lock()

    def record(self, *, step: str, thinker, exc, retry_attempted: bool,
               outcome: str = "skipped", **extra) -> None:
        print(
            f"  ✗ [{step}] {thinker or '—'}: {type(exc).__name__}: {str(exc)[:120]}",
            flush=True,
        )
        _write(
            """INSERT INTO pipeline_errors
                 (run_id, step, thinker, error_class, error_message,
                  traceback, retry_attempted, outcome, detail)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                self.run_id, step, thinker, type(exc).__name__, str(exc)[:2000],
                tb.format_exc()[:20000], retry_attempted, outcome,
                Json({k: str(v)[:500] for k, v in extra.items()}) if extra else None,
            ),
        )
        with self._lock:
            self._count += 1

    @property
    def count(self) -> int:
        return self._count


class RunLog:
    """The `pipeline_runs` row for one stage invocation.

    Opened at the start of a run and closed at the end, so an interrupted run
    leaves a row with status 'running' and a NULL finished_at — which is itself
    the signal that the container died mid-flight. That was previously invisible.
    """

    def __init__(self, run_id: str, stage: str):
        self.run_id = run_id
        self.stage = stage

    def start(self, *, claims_before: int | None = None) -> None:
        _write(
            """INSERT INTO pipeline_runs (run_id, stage, claims_before)
               VALUES (%s, %s, %s)
               ON CONFLICT (run_id) DO NOTHING""",
            (self.run_id, self.stage, claims_before),
        )

    def add_usage(self, *, files_processed: int = 0,
                  cost: "CostTracker | None" = None, detail: dict | None = None) -> None:
        """Accumulate one step's spend onto the run row.

        Additive, not assignment: a single orchestrated run has several steps
        that each spend, and the orchestrator closes the row afterwards. If this
        overwrote, whichever wrote last would erase the others.
        """
        _write(
            """UPDATE pipeline_runs SET
                 files_processed = files_processed + %s,
                 api_calls       = api_calls + %s,
                 input_tokens    = input_tokens + %s,
                 output_tokens   = output_tokens + %s,
                 cost_usd        = cost_usd + %s,
                 detail          = COALESCE(detail, '{}'::jsonb) || %s::jsonb
               WHERE run_id = %s""",
            (
                files_processed,
                cost.calls if cost else 0,
                cost.input_tokens if cost else 0,
                cost.output_tokens if cost else 0,
                round(cost.cost, 6) if cost else 0,
                Json(detail or {}),
                self.run_id,
            ),
        )

    def finish(self, *, status: str, claims_after: int | None = None,
               detail: dict | None = None) -> None:
        """Close the run. Spend is whatever add_usage() accumulated."""
        _write(
            """UPDATE pipeline_runs SET
                 finished_at = now(), status = %s,
                 claims_after = COALESCE(%s, claims_after),
                 detail = COALESCE(detail, '{}'::jsonb) || %s::jsonb
               WHERE run_id = %s""",
            (status, claims_after, Json(detail or {}), self.run_id),
        )

    def prune(self) -> None:
        """Drop history past the retention window. Cheap, and keeps the tables
        from being a slow leak nobody remembers to empty."""
        for table, column in (
            ("pipeline_errors", "occurred_at"),
            ("pipeline_runs", "started_at"),
        ):
            _write(
                f"DELETE FROM {table} WHERE {column} < now() - %s::interval",
                (f"{RETENTION_DAYS} days",),
            )


def errors_for_run(conn, run_id: str) -> list[dict]:
    """This run's errors, oldest first — for the end-of-run summary."""
    return db.query(
        conn,
        """SELECT step, thinker, error_class, error_message, outcome
           FROM pipeline_errors WHERE run_id = %s ORDER BY occurred_at""",
        (run_id,),
    )


def recent_runs(conn, stage: str | None = None, limit: int = 5) -> list[dict]:
    """Most recent completed runs, newest first."""
    return db.query(
        conn,
        """SELECT run_id, stage, started_at, finished_at, status,
                  claims_before, claims_after, files_processed, cost_usd
           FROM pipeline_runs
           WHERE (%s::text IS NULL OR stage = %s)
           ORDER BY started_at DESC LIMIT %s""",
        (stage, stage, limit),
    )


class CostTracker:
    """Accumulates spend across calls.

    Cost is priced per call from the usage dict's own model id, not from a single
    global rate — a run mixes Haiku, Sonnet and Opus, and pricing it all at the
    Haiku rate under-reported the bill by roughly a factor of three.

    Pass a `budget` to make overspend raise instead of merely being logged.
    """

    def __init__(self, budget=None, phase: str = "pipeline"):
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self.cost = 0.0
        self.by_thinker: dict = {}
        self.budget = budget
        self.phase = phase
        self._lock = threading.Lock()   # add() is called from worker threads

    def add(self, usage: dict, thinker_name: str = "unknown") -> None:
        inp = usage.get("input_tokens", 0) or 0
        out = usage.get("output_tokens", 0) or 0
        usd = cost_of(usage)
        with self._lock:
            self.input_tokens += inp
            self.output_tokens += out
            self.calls += 1
            self.cost += usd
            t = self.by_thinker.setdefault(
                thinker_name, {"input_tokens": 0, "output_tokens": 0, "calls": 0, "cost_usd": 0.0})
            t["input_tokens"] += inp
            t["output_tokens"] += out
            t["calls"] += 1
            t["cost_usd"] += usd
        # Charged outside the lock: Budget has its own, and raising here must not
        # leave this tracker's lock held.
        if self.budget is not None:
            self.budget.charge(self.phase, usd)

    def thinker_cost(self, name: str) -> float:
        return self.by_thinker.get(name, {}).get("cost_usd", 0.0)

    def by_thinker_serializable(self) -> dict:
        return {
            name: {**data, "cost_usd": round(data["cost_usd"], 6)}
            for name, data in self.by_thinker.items()
        }

    def report(self) -> None:
        print(f"\n  API Calls:     {self.calls}")
        print(f"  Input tokens:  {self.input_tokens:,}")
        print(f"  Output tokens: {self.output_tokens:,}")
        print(f"  Estimated cost: ${self.cost:.4f}")


__all__ = [
    "CostTracker", "ErrorLog", "RunLog",
    "new_run_id", "errors_for_run", "recent_runs",
]
