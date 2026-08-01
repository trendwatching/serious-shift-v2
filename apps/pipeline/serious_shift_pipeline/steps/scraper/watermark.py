"""
Per-source fetch watermarks (`source_state`).

This decides what the next run fetches, and both ways of getting it wrong are
invisible from the outside: advance it when a fetch failed and a week of
sources is skipped in silence; let it regress and everything behind it is
re-fetched and re-extracted at cost. tests/test_watermark.py pins the
invariants.
"""
from __future__ import annotations

from datetime import datetime

from ...core import db

# Default lookback when a source has no source_state entry yet. A source that
# has never been fetched must start from its back catalogue, not from today.
FALLBACK_SINCE = '2023-01-01'


def get_thinker_id(conn, name):
    """Look up thinker.id by name (fuzzy match). Returns None if not found."""
    r = db.query_one(conn, "SELECT id FROM thinkers WHERE name ILIKE %s", (f"%{name}%",))
    return r['id'] if r else None

def get_since_for_source(conn, thinker_id, platform, source_url, fallback):
    """
    Return the since-date (YYYY-MM-DD string) to use for this specific source.
    Uses last_item_date from source_state, or fallback if no entry exists.
    """
    r = db.query_one(
        conn,
        """SELECT last_item_date FROM source_state
           WHERE thinker_id = %s AND platform = %s AND source_url = %s""",
        (thinker_id, platform, source_url),
    )
    if r and r['last_item_date']:
        # Postgres returns a date object; keep the string contract downstream.
        d = r['last_item_date']
        return d.isoformat() if hasattr(d, 'isoformat') else str(d)
    return fallback

def update_source_state(conn, thinker_id, platform, source_url,
                        newest_date, items_fetched, status):
    """
    Upsert source_state for one source after a fetch attempt.

    Invariant: last_item_date only moves forward — it never regresses.
    If newest_date is None (nothing fetched), last_item_date is unchanged.
    (Postgres: SQLite's 2-arg MAX(a,b) becomes GREATEST(a,b).)
    """
    db.execute(
        conn,
        """INSERT INTO source_state
               (thinker_id, platform, source_url,
                last_fetched_at, last_item_date, last_run_status, items_last_run)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT(thinker_id, platform, source_url) DO UPDATE SET
               last_fetched_at = excluded.last_fetched_at,
               last_item_date  = CASE
                   WHEN excluded.last_item_date IS NOT NULL
                   THEN GREATEST(COALESCE(source_state.last_item_date, '2000-01-01'::date),
                                 excluded.last_item_date)
                   ELSE source_state.last_item_date
               END,
               last_run_status = excluded.last_run_status,
               items_last_run  = excluded.items_last_run
        """,
        (
            thinker_id, platform, source_url,
            datetime.now().isoformat(),
            newest_date,
            status,
            items_fetched,
        ),
    )
    conn.commit()


