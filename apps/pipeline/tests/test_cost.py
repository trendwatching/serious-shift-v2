"""Cost accounting + budget enforcement.

These guard the two failure modes that cost real money: pricing every call at a
single model's rate (which under-reported the bill by ~3x), and a ceiling that
only notifies instead of stopping.
"""
import pytest

from serious_shift_pipeline.core.config import Budget, BudgetExceeded, cost_of, rates_for
from serious_shift_pipeline.core.observability import CostTracker


def test_rates_are_per_model_not_global():
    assert rates_for("claude-haiku-4-5") == (1.0 / 1e6, 5.0 / 1e6)
    assert rates_for("claude-sonnet-4-6") == (3.0 / 1e6, 15.0 / 1e6)
    assert rates_for("claude-opus-4-7") == (5.0 / 1e6, 25.0 / 1e6)


def test_dated_model_ids_resolve_to_the_alias_rate():
    # The SDK echoes back dated ids; they must not fall through to the default.
    assert rates_for("claude-haiku-4-5-20251001") == rates_for("claude-haiku-4-5")


def test_unknown_model_does_not_price_as_free():
    # Silently costing an unrecognised model at zero would hide real spend.
    inp, out = rates_for("claude-something-new")
    assert inp > 0 and out > 0


def test_every_model_a_stage_can_be_pointed_at_is_priced_explicitly():
    """EXTRACTION_MODEL and INSIGHTS_MODEL are env-overridable, so upgrading a
    stage must not fall through to the Sonnet fallback — that under-reports an
    Opus-tier run by 1.7x and a Fable-tier one by 3.3x."""
    fallback = rates_for("claude-definitely-not-a-model")
    for model, expected in (
        ("claude-sonnet-5", (3.0, 15.0)),
        ("claude-opus-5", (5.0, 25.0)),
        ("claude-fable-5", (10.0, 50.0)),
    ):
        rate = rates_for(model)
        assert rate == (expected[0] / 1e6, expected[1] / 1e6), model
        if expected != (3.0, 15.0):
            assert rate != fallback, f"{model} is priced by the fallback, not its own row"


def test_cost_of_prices_a_call():
    usage = {"model": "claude-sonnet-4-6", "input_tokens": 1_000_000, "output_tokens": 0}
    assert cost_of(usage) == pytest.approx(3.0)


def test_batch_is_half_price():
    usage = {"model": "claude-sonnet-4-6", "input_tokens": 1_000_000, "output_tokens": 0}
    assert cost_of({**usage, "batch": True}) == pytest.approx(1.5)


def test_cache_reads_are_a_tenth_of_input():
    usage = {"model": "claude-sonnet-4-6", "cache_read_input_tokens": 1_000_000}
    assert cost_of(usage) == pytest.approx(0.3)


def test_tracker_sums_mixed_models_correctly():
    t = CostTracker()
    t.add({"model": "claude-haiku-4-5", "input_tokens": 1_000_000, "output_tokens": 0})
    t.add({"model": "claude-opus-4-7", "input_tokens": 1_000_000, "output_tokens": 0})
    # 1.00 + 5.00 — not 2x the Haiku rate, which is what the old tracker reported.
    assert t.cost == pytest.approx(6.0)
    assert t.calls == 2


def test_budget_raises_when_the_run_ceiling_is_passed():
    b = Budget(total_usd=1.0)
    b.charge("map", 0.6)
    with pytest.raises(BudgetExceeded, match="run spend"):
        b.charge("map", 0.6)


def test_budget_raises_on_a_per_phase_cap():
    b = Budget(total_usd=100.0, per_phase_usd={"map": 1.0})
    with pytest.raises(BudgetExceeded, match="phase 'map'"):
        b.charge("map", 1.5)


def test_tracker_enforces_its_budget():
    t = CostTracker(budget=Budget(total_usd=0.5), phase="extract")
    with pytest.raises(BudgetExceeded):
        t.add({"model": "claude-opus-4-7", "input_tokens": 1_000_000, "output_tokens": 0})
