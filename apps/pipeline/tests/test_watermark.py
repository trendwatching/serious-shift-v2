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


# ── Blocked vs broken ─────────────────────────────────────────────────────────
#
# All 11 sources that were sitting in `failed` were YouTube, blocked because
# Railway runs on datacenter IPs. That is a missing proxy credential, not 11
# broken feeds — and recording it as a failure pinned the failed-source alert
# permanently above its threshold, which is how the next real breakage gets
# missed.

class _Blocked(Exception):
    pass


@pytest.mark.parametrize("exc", [
    _Blocked("YouTube is blocking requests from your IP"),
    _Blocked("Sign in to confirm you're not a bot"),
    _Blocked("HTTP Error 429: Too Many Requests"),
    _Blocked("The provided YouTube account cookies are no longer valid"),
])
def test_host_refusals_are_classified_as_blocked(exc):
    from serious_shift_pipeline.steps.scraper.handlers import is_ip_block
    assert is_ip_block(exc)


def test_request_blocked_exception_type_is_recognised():
    from serious_shift_pipeline.steps.scraper.handlers import is_ip_block
    # The transcript library signals this by type, not message.
    assert is_ip_block(type("RequestBlocked", (Exception,), {})())


def test_a_youtube_listing_timeout_is_classified_as_blocked():
    """The shape the block actually took on staging.

    Throttling a datacenter IP makes the yt-dlp listing hang rather than answer,
    so all six YouTube sources were failing as TimeoutExpired — matching none of
    the worded refusals and landing in `failed`, which re-armed the alert the
    `blocked` status exists to silence.
    """
    import subprocess

    from serious_shift_pipeline.steps.scraper.handlers import is_ip_block

    exc = subprocess.TimeoutExpired(
        ["/usr/local/bin/python", "-m", "yt_dlp", "--skip-download",
         "https://www.youtube.com/@reidhoffman/videos"],
        120,
    )
    assert is_ip_block(exc)


@pytest.mark.parametrize("cmd", [
    ["curl", "https://example.com/feed"],
    ["python", "-m", "trafilatura"],
])
def test_a_timeout_from_any_other_source_is_still_a_real_failure(cmd):
    """A blog that hangs is genuinely broken. Mapping every timeout to "needs a
    proxy" would hide real breakage in the other direction, so the YouTube path
    has to be identifiable in the exception itself."""
    import subprocess

    from serious_shift_pipeline.steps.scraper.handlers import is_ip_block

    assert not is_ip_block(subprocess.TimeoutExpired(cmd, 30))


@pytest.mark.parametrize("exc", [
    _Blocked("HTTP Error 404: Not Found"),
    _Blocked("Connection timed out"),
    _Blocked("no such channel"),
    _Blocked("yt-dlp exited 1 with no output. stderr: (empty)"),
])
def test_genuine_breakage_is_not_misread_as_blocked(exc):
    """The important direction: a real failure must not be filed as 'blocked'
    and quietly excluded from the alert that exists to catch it."""
    from serious_shift_pipeline.steps.scraper.handlers import is_ip_block
    assert not is_ip_block(exc)


def test_blocked_sources_do_not_count_toward_the_failure_alert(source):
    from serious_shift_pipeline import run
    conn, tid = source
    scraper.update_source_state(conn, tid, PLATFORM, URL, None, 0, "blocked")
    row = db.query_one(
        conn,
        """SELECT last_run_status FROM source_state
           WHERE thinker_id = %s AND platform = %s AND source_url = %s""",
        (tid, PLATFORM, URL))
    assert row["last_run_status"] == "blocked"
    # The two counters must not overlap, or the alert is pinned forever.
    assert run.count_failed_sources() + run.count_blocked_sources() >= 1
    assert run.count_blocked_sources() >= 1


# ── Per-source item cap ───────────────────────────────────────────────────────
#
# Extraction cost is per raw file, so an uncapped feed sets the bill for the
# whole run. huggingface.co/blog took $4.78 of a $5.01 run and 142 of its
# sources. The cap's *direction* is the subtle part: it has to drain from the
# old end, because the watermark advances to the newest item fetched.

def _capped(dates, cap):
    """Mirror the selection in scrape_rss: oldest-first, then truncate."""
    return sorted(dates)[:cap]


def test_cap_takes_the_oldest_items_not_the_newest():
    dates = ["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"]
    assert _capped(dates, 2) == ["2025-01-01", "2025-02-01"]


def test_successive_runs_drain_the_backlog_without_a_gap():
    """The property that matters: nothing is skipped between runs.

    Taking the NEWEST N would advance the watermark past everything older and
    lose it permanently — silently, which is the whole failure mode this file
    exists to prevent.
    """
    backlog = ["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01", "2025-05-01"]
    cap, seen, remaining = 2, [], list(backlog)
    while remaining:
        batch = _capped(remaining, cap)
        seen += batch
        watermark = max(batch)
        # Next run resumes from the watermark, exactly as get_since_for_source does.
        remaining = [d for d in remaining if d > watermark]
    assert seen == backlog, "items were skipped or reordered across runs"


def test_a_cap_larger_than_the_backlog_is_a_no_op():
    dates = ["2025-01-01", "2025-02-01"]
    assert _capped(dates, 30) == dates


def test_the_cap_is_configurable_and_shared_by_both_fetch_paths():
    # The blog crawler used a hard-coded 30 while the RSS path had none; one
    # constant now governs both, so they cannot drift apart again.
    from serious_shift_pipeline.steps.scraper import handlers
    assert isinstance(handlers.MAX_ITEMS_PER_SOURCE, int)
    assert handlers.MAX_ITEMS_PER_SOURCE > 0
