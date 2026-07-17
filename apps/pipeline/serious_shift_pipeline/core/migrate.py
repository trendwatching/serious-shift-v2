"""
Apply pending database migrations at pipeline startup.

The schema is owned by `packages/db` (dbmate). A copy of the migrations is
vendored into this package (`serious_shift_pipeline/migrations/*.sql`) so they
ship inside the image without needing a repo-root Docker build context; a test
(`tests/test_migrate.py`) asserts the vendored copy stays byte-identical to
`packages/db/migrations`. This applier is **dbmate compatible** — it uses the
same `schema_migrations` table and the same version scheme (the leading digits
of the filename) — so a manual `dbmate up` and this runner can be used
interchangeably and idempotently against the same database.

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

from . import db

# The copy vendored into this package (always present; ships in the image).
_PKG_MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def _repo_migrations() -> Path | None:
    """Canonical packages/db/migrations, when run from a source checkout.

    Walk up from this file looking for `packages/db/migrations` rather than
    indexing a fixed parent depth — in the installed/container layout there are
    fewer parent directories, and a hard index raises IndexError."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "packages" / "db" / "migrations"
        if candidate.is_dir():
            return candidate
    return None


# Migration directory lookup, in priority order. SS_MIGRATIONS_DIR wins; then the
# vendored package copy (ships in the image); then the canonical repo copy.
_REPO_MIGRATIONS = _repo_migrations()
_CANDIDATES = (
    os.environ.get("SS_MIGRATIONS_DIR"),
    str(_PKG_MIGRATIONS),
    str(_REPO_MIGRATIONS) if _REPO_MIGRATIONS else None,
)


def _migrations_dir() -> str | None:
    for c in _CANDIDATES:
        if c and os.path.isdir(c):
            return c
    return None


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
    number applied. No-op (with a note) if no migrations directory is found."""
    mdir = _migrations_dir()
    if not mdir:
        if verbose:
            print("  migrate: no migrations directory found — assuming the schema "
                  "is managed externally; skipping.")
        return 0

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
