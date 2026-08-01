"""
Apply pending database migrations at pipeline startup.

The schema is owned by `packages/db` (dbmate), located via `paths.migrations_dir()`.
This applier is **dbmate compatible** — same `schema_migrations` table, same
version scheme (the leading digits of the filename) — so a manual `dbmate up`
and this runner can be used interchangeably and idempotently.

Why the pipeline applies migrations: the weekly cron is the system's primary
writer and runs unattended. Without this, a database that never had `dbmate up`
run against it fails on the very first query (`relation "claims" does not
exist`). Bootstrapping here makes the cron self-sufficient.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import psycopg

from ..paths import migrations_dir
from . import db

# Versions recorded by the pre-squash sequential migrations (0001-0008). A
# database still carrying them has not been reconciled with the squashed
# baseline, and applying the baseline on top would try to CREATE existing
# tables. Fail loudly with the fix instead. Remove after one release cycle.
_LEGACY_VERSIONS = {f"{n:04d}" for n in range(1, 9)}
_BASELINE_VERSION = "20250101000000"


def _version(filename: str) -> str:
    """dbmate version = the leading digits of the filename (e.g. 0001_x.sql → 0001)."""
    m = re.match(r"(\d+)", os.path.basename(filename))
    return m.group(1) if m else os.path.basename(filename)


def _up_sql(text: str) -> str:
    """Extract the `-- migrate:up` … `-- migrate:down` section of a dbmate file."""
    up = text.split("-- migrate:down", 1)[0]
    up = re.sub(r"(?m)^\s*--\s*migrate:up.*$", "", up, count=1)
    return up.strip()


def apply_pending(verbose: bool = True) -> int:
    """Apply every migration not yet recorded in schema_migrations. Returns the
    number applied. Raises if the migrations tree cannot be found — a silent
    skip would run the pipeline against an unmigrated schema."""
    mdir = migrations_dir()
    files = sorted(f for f in os.listdir(mdir) if f.endswith(".sql"))
    applied = 0
    # autocommit so the bookkeeping DDL/SELECT run outside a transaction and each
    # migration gets its own explicit transaction (atomic per file).
    with psycopg.connect(db.get_dsn(), autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version varchar(255) NOT NULL, PRIMARY KEY (version))"
        )
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}

        if done & _LEGACY_VERSIONS and _BASELINE_VERSION not in done:
            raise RuntimeError(
                "Database still has pre-squash migration rows "
                f"({sorted(done & _LEGACY_VERSIONS)}). Run the reconciliation in "
                "packages/db/README.md#baseline-squash before deploying this build."
            )

        for f in files:
            version = _version(f)
            if version in done:
                continue
            sql = _up_sql(Path(mdir, f).read_text())
            if not sql:
                continue
            # Multi-statement SQL with no parameters runs via the simple query
            # protocol; the version insert is a separate parameterised statement.
            with conn.transaction():
                conn.execute(sql)
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied += 1
            if verbose:
                print(f"  migrate: applied {f}")

    if verbose:
        msg = f"{applied} applied" if applied else "already up to date"
        print(f"  migrate: schema {msg} ({len(files)} migrations total).")
    return applied


if __name__ == "__main__":  # pragma: no cover — operational entrypoint
    # `python -m serious_shift_pipeline.core.migrate` applies pending migrations
    # and exits. The weekly run does this on startup anyway; having it standalone
    # means a schema change can be rolled out without waiting for (or paying for)
    # a full pipeline run — e.g. `railway run --service pipeline python -m
    # serious_shift_pipeline.core.migrate`.
    apply_pending()
