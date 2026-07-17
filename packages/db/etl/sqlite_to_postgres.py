#!/usr/bin/env python3
"""
One-off ETL: copy serious-shift.db (SQLite) into the Postgres schema created by
packages/db/migrations/0001_initial_schema.sql.

Design:
  * Rows are copied table-by-table in FK-safe order, preserving primary keys so
    every existing reference (source_id, thinker_id, claim_id, …) stays valid.
  * claims.duplicate_of is a self-referential FK; it is loaded NULL first, then
    back-filled in a second pass so row order can't violate the constraint.
  * After load, identity sequences are advanced past MAX(id) so the pipeline's
    subsequent inserts don't collide with migrated ids.
  * Column lists are introspected from SQLite (PRAGMA table_info) so this script
    needs no hard-coded schema and stays in sync with the source.

Usage:
  pip install "psycopg[binary]"
  export DATABASE_URL=postgres://user:pass@localhost:5432/serious_shift
  python sqlite_to_postgres.py --sqlite ../../serious-shift.db --truncate

Verify afterwards with packages/db/etl/verify_parity.py.
"""
import argparse
import datetime
import os
import re
import sqlite3
import sys

import psycopg

# Optional one-off import of legacy SQLite data into the current schema. Only the
# tables that still exist in Postgres are copied (copy_table skips the rest), and
# only the columns both sides share — so this stays valid as the schema evolves.
# FK-safe load order: every table appears after all tables it references.
LOAD_ORDER = [
    "thinkers",
    "sources",
    "claims",                 # duplicate_of loaded NULL, back-filled later
    "predictions",
    "concepts",
    "tensions",
    "claim_concepts",
    "concept_thinkers",
    "thinker_disagreements",
    "source_state",
    "domains_v2",
    "domain_key_trends",
    "domain_sub_trends",
    "domain_sub_trend_claims",
    "domain_synthesis_insights",
    "domain_synthesis_insight_claims",
    "domain_links",
    "domain_flows",
]

# schema_migrations is owned by the migration tool (dbmate), not copied.
SKIP_TABLES = {"schema_migrations"}

# (table, column) pairs that are BOOLEAN in Postgres but 0/1 in SQLite.
BOOLEAN_COLUMNS = {("predictions", "falsifiable")}

BATCH = 1000


def sqlite_columns(scur, table):
    """Return (column names, set of columns declared DATE in SQLite)."""
    scur.execute(f"PRAGMA table_info({table})")
    rows = scur.fetchall()
    cols = [r[1] for r in rows]
    date_cols = {r[1] for r in rows if (r[2] or "").upper() == "DATE"}
    return cols, date_cols


def normalize_date(value):
    """Coerce a SQLite date value into a Postgres-castable 'YYYY-MM-DD' or None.

    SQLite is dynamically typed: date columns hold a mix of full dates, bare
    year integers (1995), year-only strings, datetimes, and malformed values
    like '2001-00-00' or '2026-02-30'. Postgres DATE rejects all of those, so
    we parse leniently (missing/zero/out-of-range month or day fall back to 1)
    and validate against the real calendar, returning None if unsalvageable.
    """
    if value is None:
        return None
    s = str(value).strip()
    m = re.match(r"(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", s)
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2)) if m.group(2) else 1
    day = int(m.group(3)) if m.group(3) else 1
    if not 1 <= month <= 12:
        month = 1
    if not 1 <= day <= 31:
        day = 1
    for d in (day, 1):  # e.g. Feb 30 -> fall back to the 1st
        try:
            return datetime.date(year, month, d).isoformat()
        except ValueError:
            continue
    return None


def coerce(table, col, value, is_date):
    if value is not None and (table, col) in BOOLEAN_COLUMNS:
        return bool(value)
    if is_date:
        return normalize_date(value)
    return value


def pg_columns(pcur, table):
    """Columns the Postgres target table actually has (empty set if it doesn't exist)."""
    pcur.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s""",
        (table,),
    )
    return {r[0] for r in pcur.fetchall()}


def copy_table(scur, pcur, table):
    cols, date_cols = sqlite_columns(scur, table)
    if not cols:
        print(f"  · {table}: not present in SQLite, skipping")
        return 0

    # Only copy into columns the Postgres schema still has. The schema is owned
    # by packages/db migrations and has since diverged from the legacy SQLite —
    # e.g. the scenario layer was removed (domain_scenarios dropped,
    # domain_key_trends.scenario_id dropped). Skip dropped tables/columns rather
    # than fail.
    target = pg_columns(pcur, table)
    if not target:
        print(f"  · {table}: not present in Postgres, skipping")
        return 0

    load_cols = [c for c in cols if c in target]
    if table == "claims":
        # First pass: omit the self-referential FK.
        load_cols = [c for c in load_cols if c != "duplicate_of"]

    collist = ", ".join(load_cols)
    placeholders = ", ".join(["%s"] * len(load_cols))
    insert = f"INSERT INTO {table} ({collist}) VALUES ({placeholders})"

    scur.execute(f"SELECT {', '.join(cols)} FROM {table}")
    idx = {c: i for i, c in enumerate(cols)}

    total = 0
    batch = []
    for row in scur:
        values = [coerce(table, c, row[idx[c]], c in date_cols) for c in load_cols]
        batch.append(values)
        if len(batch) >= BATCH:
            pcur.executemany(insert, batch)
            total += len(batch)
            batch = []
    if batch:
        pcur.executemany(insert, batch)
        total += len(batch)

    print(f"  ✓ {table}: {total} rows")
    return total


def backfill_claim_duplicates(scur, pcur):
    scur.execute(
        "SELECT id, duplicate_of FROM claims WHERE duplicate_of IS NOT NULL"
    )
    pairs = scur.fetchall()
    if not pairs:
        return 0
    pcur.executemany(
        "UPDATE claims SET duplicate_of = %s WHERE id = %s",
        [(dup, cid) for (cid, dup) in pairs],
    )
    print(f"  ✓ claims.duplicate_of back-filled: {len(pairs)} rows")
    return len(pairs)


def bump_sequences(pcur):
    """Advance identity sequences past the migrated MAX(id).

    Only tables with an `id` column are considered — junction tables
    (claim_concepts, …) have composite PKs and no id, and pg_get_serial_sequence
    raises on a missing column rather than returning NULL.
    """
    pcur.execute(
        """SELECT table_name FROM information_schema.columns
           WHERE table_schema = 'public' AND column_name = 'id'"""
    )
    have_id = {r[0] for r in pcur.fetchall()}
    bumped = 0
    for table in LOAD_ORDER:
        if table not in have_id:
            continue
        pcur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
        seq = pcur.fetchone()[0]
        if not seq:
            continue  # natural/text PK (domains_v2, key_trend_meta, …)
        pcur.execute(
            f"SELECT setval(%s, COALESCE((SELECT MAX(id) FROM {table}), 1))",
            (seq,),
        )
        bumped += 1
    print(f"  ✓ advanced {bumped} identity sequences")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True, help="path to serious-shift.db")
    ap.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Postgres URL (or set DATABASE_URL)",
    )
    ap.add_argument(
        "--truncate",
        action="store_true",
        help="TRUNCATE all target tables before load (idempotent re-runs)",
    )
    args = ap.parse_args()

    if not args.database_url:
        sys.exit("error: --database-url or DATABASE_URL is required")
    if not os.path.exists(args.sqlite):
        sys.exit(f"error: sqlite db not found: {args.sqlite}")

    sconn = sqlite3.connect(args.sqlite)
    scur = sconn.cursor()

    with psycopg.connect(args.database_url) as pconn:
        with pconn.cursor() as pcur:
            if args.truncate:
                targets = ", ".join(t for t in LOAD_ORDER)
                print(f"Truncating {len(LOAD_ORDER)} tables…")
                pcur.execute(f"TRUNCATE {targets} RESTART IDENTITY CASCADE")

            print("Loading tables…")
            grand_total = 0
            for table in LOAD_ORDER:
                if table in SKIP_TABLES:
                    continue
                grand_total += copy_table(scur, pcur, table)

            print("Post-processing…")
            backfill_claim_duplicates(scur, pcur)
            bump_sequences(pcur)

        pconn.commit()
        print(f"\nDone. {grand_total} rows committed to Postgres.")

    sconn.close()


if __name__ == "__main__":
    main()
