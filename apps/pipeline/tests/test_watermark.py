"""
Scrape watermark invariants — the least-tested, highest-consequence logic in
the pipeline.

`source_state.last_item_date` decides what the next run fetches. If it advances
when it should not, a week of sources is skipped silently: no error, no missing
row, just less content than there should have been. If it regresses, the run
re-fetches and re-extracts everything behind it, which costs real money.

Neither failure is visible from the outside, which is why these exist.

The DB tests are gated like the other destructive integration tests; the date
helpers are pure and always run.
"""
import os
from datetime import date

import pytest

from serious_shift_pipeline.core import db
from serious_shift_pipeline.steps import scraper


# ── Pure helpers (no DB) ──────────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("https://x.com/2025/04/15/a-post", "2025-04-15"),
    ("https://x.com/2025/04/a-post", "2025-04-01"),
    ("https://x.com/blog/2025-04-15-a-post", "2025-04-15"),
    ("https://x.com/p/20250415-thing", "2025-04-15"),
    ("https://x.com/no-date-here", None),
    # A long digit run is an id, not a date.
    ("https://x.com/p/123456789012", None),
    # Implausible years are rejected rather than silently accepted.
    ("https://x.com/1899/04/15/old", None),
])
def test_date_extraction_from_url(url, expected):
    assert scraper.extract_date_from_url(url) == expected


def test_in_range_is_inclusive_at_both_ends():
    assert scraper.in_range("2025-01-01", "2025-01-01", "2025-12-31")
    assert scraper.in_range("2025-12-31", "2025-01-01", "2025-12-31")
    assert not scraper.in_range("2024-12-31", "2025-01-01", "2025-12-31")
    assert not scraper.in_range("2026-01-01", "2025-01-01", "2025-12-31")


def test_undated_items_are_kept_not_dropped():
    """A missing date must not silently exclude an item from the window —
    better to extract something twice than to lose it."""
    assert scraper.in_range(None, "2025-01-01", "2025-12-31")


# ── Watermark against a real source_state ─────────────────────────────────────

PLATFORM = "test_platform"
URL = "https://example.invalid/watermark-test"


@pytest.fixture
def source(request):
    """A throwaway thinker plus a clean source_state row, torn down after.

    Gating lives here rather than in a module-level `pytestmark` so the pure
    helper tests above still run without a database — they cover the date
    parsing that decides which items are even considered for the window.
    """
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    if os.environ.get("SS_ALLOW_DESTRUCTIVE_TESTS", "") not in ("1", "true", "yes"):
        pytest.skip("writes source_state; set SS_ALLOW_DESTRUCTIVE_TESTS=1 "
                    "on a disposable database")

    with db.connect() as conn:
        tid = db.insert_returning_id(
            conn, "INSERT INTO thinkers (name) VALUES (%s) RETURNING id",
            (f"Watermark Test {request.node.name}",))
        conn.commit()
        yield conn, tid
        db.execute(conn, "DELETE FROM source_state WHERE thinker_id = %s", (tid,))
        db.execute(conn, "DELETE FROM thinkers WHERE id = %s", (tid,))
        conn.commit()


def _since(conn, tid, fallback="2023-01-01"):
    return scraper.get_since_for_source(conn, tid, PLATFORM, URL, fallback)


def _update(conn, tid, newest, items=1, status="ok"):
    scraper.update_source_state(conn, tid, PLATFORM, URL, newest, items, status)


def test_first_run_uses_the_fallback(source):
    """A source with no state has never been fetched — start from the fallback,
    not from today, or its whole back catalogue is skipped on the first run."""
    conn, tid = source
    assert _since(conn, tid, "2023-01-01") == "2023-01-01"


def test_watermark_advances_after_a_successful_fetch(source):
    conn, tid = source
    _update(conn, tid, date(2025, 6, 1))
    assert _since(conn, tid) == "2025-06-01"


def test_watermark_never_regresses(source):
    """The core invariant. An older newest-date must not pull the watermark
    back — that would re-fetch and re-extract everything in between, at cost."""
    conn, tid = source
    _update(conn, tid, date(2025, 6, 1))
    _update(conn, tid, date(2025, 1, 1))
    assert _since(conn, tid) == "2025-06-01"


def test_a_fetch_with_no_items_leaves_the_watermark_alone(source):
    """A quiet week (or a broken feed) must not move the mark in either
    direction — the next run has to cover the same window again."""
    conn, tid = source
    _update(conn, tid, date(2025, 6, 1))
    _update(conn, tid, None, items=0, status="ok")
    assert _since(conn, tid) == "2025-06-01"


def test_a_failed_fetch_leaves_the_watermark_alone(source):
    """This is the one that would silently lose a week: if a failed run
    advanced the mark, the content it failed to fetch is never looked for
    again."""
    conn, tid = source
    _update(conn, tid, date(2025, 6, 1))
    _update(conn, tid, None, items=0, status="failed")
    assert _since(conn, tid) == "2025-06-01"

    row = db.query_one(
        conn,
        """SELECT last_run_status, items_last_run FROM source_state
           WHERE thinker_id = %s AND platform = %s AND source_url = %s""",
        (tid, PLATFORM, URL))
    assert row["last_run_status"] == "failed"
    assert row["items_last_run"] == 0


def test_status_and_count_are_recorded_for_the_operator(source):
    """`source_state` is what the failed-source alert counts; the status has to
    reflect the most recent attempt, not the last successful one."""
    conn, tid = source
    _update(conn, tid, date(2025, 6, 1), items=7, status="ok")
    row = db.query_one(
        conn,
        """SELECT last_run_status, items_last_run, last_fetched_at FROM source_state
           WHERE thinker_id = %s AND platform = %s AND source_url = %s""",
        (tid, PLATFORM, URL))
    assert row["last_run_status"] == "ok"
    assert row["items_last_run"] == 7
    assert row["last_fetched_at"] is not None


def test_each_source_carries_its_own_watermark(source):
    """Sources advance independently — one thinker's working feed must not
    move the mark on their broken one."""
    conn, tid = source
    _update(conn, tid, date(2025, 6, 1))
    other = "https://example.invalid/second-source"
    scraper.update_source_state(conn, tid, PLATFORM, other, date(2024, 1, 1), 1, "ok")
    assert _since(conn, tid) == "2025-06-01"
    assert scraper.get_since_for_source(conn, tid, PLATFORM, other, "2023-01-01") == "2024-01-01"
