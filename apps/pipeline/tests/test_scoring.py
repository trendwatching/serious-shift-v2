"""Pure-function tests for the scoring formulas — no database needed."""
from datetime import date

from serious_shift_pipeline.steps.scoring import base_freshness, depth_from_chars


def test_depth_from_chars():
    assert depth_from_chars(60_000) == 5
    assert depth_from_chars(30_000) == 4
    assert depth_from_chars(12_000) == 3
    assert depth_from_chars(3_000) == 2
    assert depth_from_chars(100) == 1


def test_base_freshness_tiers():
    today = date(2026, 6, 4)
    assert base_freshness("2026-06-01", today) == 1.0   # 3 days
    assert base_freshness("2026-03-01", today) == 0.8    # ~95 days -> 3-6mo tier
    assert base_freshness("2025-09-01", today) == 0.6    # 6-12mo
    assert base_freshness("2025-01-01", today) == 0.4    # 1-2y
    assert base_freshness("2024-01-01", today) == 0.2    # 2-3y
    assert base_freshness("2020-01-01", today) == 0.1    # older
    assert base_freshness("2099-01-01", today) == 1.0    # future-dated edge case


def test_base_freshness_unknown():
    today = date(2026, 6, 4)
    assert base_freshness(None, today) == 0.4
    assert base_freshness("not a date", today) == 0.4
