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
  * The scrape manifest is preserved across the load. `scrape_sources` does not
    exist in SQLite, but it references `thinkers(id)`, so `TRUNCATE thinkers …
    CASCADE` used to delete all 120 seeded rows with nothing to restore them —
    leaving the weekly cron with nothing to fetch, silently and permanently.
    It is now snapshotted by *thinker name* before the truncate and re-keyed to
    the loaded thinker ids afterwards. `source_state` (the per-source watermark)
    gets the same treatment for any row the SQLite load does not supply.

Usage:
  pip install "psycopg[binary]"
  export DATABASE_URL=postgres://user:pass@localhost:5432/serious_shift
  python sqlite_to_postgres.py --sqlite ../../serious-shift.db --truncate

Verify afterwards with packages/db/etl/verify_parity.py.
"""
import argparse
import datetime
import json
import os
import re
import sqlite3
import sys

import psycopg
from psycopg.types.json import Json

# Optional one-off import of legacy SQLite data into the current schema. Only the
# tables that still exist in Postgres are copied (copy_table skips the rest), and
# only the columns both sides share — so this stays valid as the schema evolves.
# FK-safe load order: every table appears after all tables it references.
LOAD_ORDER = [
    "thinkers",
    "sources",
    "claims",                 # duplicate_of loaded NULL, back-filled later
    "predictions",
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


def coerce(value, *, is_date, is_bool):
    """Adapt one SQLite value to what the Postgres column will accept."""
    if is_bool:
        # SQLite has no boolean type; these arrive as 0/1 integers, which
        # Postgres rejects outright for a boolean column.
        return None if value is None else bool(value)
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


def pg_bool_columns(pcur, table):
    """Columns declared boolean in Postgres.

    Read from the live schema rather than a hand-maintained list: the list had
    exactly one entry, and any boolean column added to the schema later would
    have failed the import with a type error nobody would connect to this file.
    """
    pcur.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s
             AND data_type = 'boolean'""",
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
    bool_cols = pg_bool_columns(pcur, table)

    collist = ", ".join(load_cols)
    placeholders = ", ".join(["%s"] * len(load_cols))
    insert = f"INSERT INTO {table} ({collist}) VALUES ({placeholders})"

    scur.execute(f"SELECT {', '.join(cols)} FROM {table}")
    idx = {c: i for i, c in enumerate(cols)}

    total = 0
    batch = []
    for row in scur:
        values = [
            coerce(row[idx[c]], is_date=c in date_cols, is_bool=c in bool_cols)
            for c in load_cols
        ]
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


# ── Scrape-manifest preservation ──────────────────────────────────────────────
#
# `scrape_sources` and `source_state` are seeded by the migration and maintained
# by the pipeline; neither is present in the legacy SQLite. Both reference
# `thinkers(id)`, so the CASCADE on the truncate takes them out. Thinker ids are
# reassigned by the load (SQLite carries 70 thinkers, the seed 87), so the rows
# have to be re-keyed on the one stable identifier both sides share: the name.

# Tables to carry across the truncate. `id` is deliberately excluded: the rows
# are re-inserted with fresh identities against the reloaded thinker ids.
PRESERVE = {
    "scrape_sources": ["platform", "method", "url", "rss", "channel_url",
                       "handle", "note", "params"],
    "source_state": ["platform", "source_url", "last_fetched_at", "last_item_date",
                     "last_run_status", "items_last_run"],
}

# The key that decides whether a snapshotted row is already present after the
# load. `None` means "the whole row" — scrape_sources has no unique constraint
# and two rows can legitimately share (thinker, platform, url) while differing
# only in `params`: arXiv is seeded twice against the same endpoint, once for
# the cs.* categories and once for econ.GN. Keying on anything narrower silently
# drops one of them, which is the same class of bug as the CASCADE itself.
# source_state does have a unique constraint, and there the row the SQLite load
# supplied is the more recent watermark and must win.
PRESERVE_KEY = {
    "scrape_sources": None,
    "source_state": ["thinker_id", "platform", "source_url"],
}


def _keyrepr(value):
    """Stable, hashable rendering of a column value for row-identity compares.

    jsonb arrives as an unhashable dict whose key order Postgres does not
    preserve, so sort the keys and render to text.
    """
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return value


def snapshot_manifest(pcur):
    """Read scrape_sources / source_state keyed by thinker NAME, before truncate.

    Returns {table: (columns, [(thinker_name, *values), …])}. Missing tables are
    skipped so this stays valid if the schema drops one.
    """
    out = {}
    for table, cols in PRESERVE.items():
        present = pg_columns(pcur, table)
        if not present:
            continue
        cols = [c for c in cols if c in present]
        pcur.execute(
            f"""SELECT t.name, {', '.join('s.' + c for c in cols)}
                FROM {table} s JOIN thinkers t ON t.id = s.thinker_id"""
        )
        rows = pcur.fetchall()
        out[table] = (cols, rows)
        print(f"  · snapshot {table}: {len(rows)} rows")
    return out


def restore_manifest(pcur, snapshot):
    """Re-insert the snapshotted manifest, re-keyed to the loaded thinker ids.

    A thinker named in the manifest but absent after the load is recreated with
    just its name — dropping the source instead would silently shrink what the
    weekly cron fetches, which is the failure this whole function exists to
    prevent. Rows already restored by the SQLite load (matched on the table's
    natural key) are not duplicated.
    """
    if not snapshot:
        return

    for table, (cols, rows) in snapshot.items():
        if not rows:
            continue

        # Recreate any thinker the manifest needs but the load did not provide.
        names = {r[0] for r in rows}
        pcur.execute("SELECT name, id FROM thinkers WHERE name = ANY(%s)", (list(names),))
        ids = dict(pcur.fetchall())
        for missing in sorted(names - set(ids)):
            pcur.execute(
                "INSERT INTO thinkers (name) VALUES (%s) RETURNING id", (missing,)
            )
            ids[missing] = pcur.fetchone()[0]
            print(f"  · recreated thinker for manifest: {missing}")

        insert_cols = ["thinker_id"] + cols
        key_cols = PRESERVE_KEY.get(table) or insert_cols
        pcur.execute(f"SELECT {', '.join(key_cols)} FROM {table}")
        # Compared as text: jsonb round-trips to dict (unhashable) and Postgres
        # may reorder its keys, so the rendered form is the only stable identity.
        existing = {tuple(map(_keyrepr, r)) for r in pcur.fetchall()}

        placeholders = ", ".join(["%s"] * len(insert_cols))
        stmt = f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({placeholders})"

        batch = []
        for name, *values in rows:
            row = [ids[name]] + list(values)
            key = tuple(_keyrepr(row[insert_cols.index(c)]) for c in key_cols)
            if key in existing:
                continue
            existing.add(key)
            # jsonb comes back from psycopg as dict/list; it has to go back as
            # Json() or the driver has no placeholder adapter for it.
            batch.append([Json(v) if isinstance(v, (dict, list)) else v for v in row])

        if batch:
            pcur.executemany(stmt, batch)
        skipped = len(rows) - len(batch)
        note = f" ({skipped} already present)" if skipped else ""
        print(f"  ✓ {table} restored: {len(batch)} rows{note}")


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


def main_with_args(*, sqlite: str, database_url: str, truncate: bool = False) -> int:
    """Run the import. Returns the number of rows loaded.

    Separate from `main()` so the regression test can drive it directly instead
    of going through argparse and sys.exit.
    """
    sconn = sqlite3.connect(sqlite)
    scur = sconn.cursor()

    with psycopg.connect(database_url) as pconn:
        with pconn.cursor() as pcur:
            snapshot = {}
            if truncate:
                # The CASCADE reaches scrape_sources and source_state through
                # thinkers, and neither exists in SQLite to be reloaded. Capture
                # them first, keyed by thinker name, and put them back after.
                print("Snapshotting the scrape manifest…")
                snapshot = snapshot_manifest(pcur)

                # Only truncate tables that still exist. copy_table already skips
                # missing ones; without the same filter here a dropped table makes
                # the whole import abort before it starts.
                pcur.execute(
                    """SELECT table_name FROM information_schema.tables
                       WHERE table_schema = 'public'"""
                )
                existing = {r[0] for r in pcur.fetchall()}
                targets = [t for t in LOAD_ORDER if t in existing]
                print(f"Truncating {len(targets)} tables…")
                pcur.execute(f"TRUNCATE {', '.join(targets)} RESTART IDENTITY CASCADE")

            print("Loading tables…")
            grand_total = 0
            for table in LOAD_ORDER:
                if table in SKIP_TABLES:
                    continue
                grand_total += copy_table(scur, pcur, table)

            print("Post-processing…")
            backfill_claim_duplicates(scur, pcur)
            # Before the restore: it inserts without explicit ids, so the
            # identity sequences must already be past the ids the load supplied.
            bump_sequences(pcur)
            restore_manifest(pcur, snapshot)

        pconn.commit()
        print(f"\nDone. {grand_total} rows committed to Postgres.")

    sconn.close()
    return grand_total


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

    main_with_args(
        sqlite=args.sqlite,
        database_url=args.database_url,
        truncate=args.truncate,
    )


if __name__ == "__main__":
    main()
