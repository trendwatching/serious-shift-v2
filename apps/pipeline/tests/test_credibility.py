"""Pure-function tests for the credibility formula — no database needed."""
from serious_shift_pipeline.steps.evaluate import score_thinker


def test_no_evaluable_predictions_defaults_to_neutral():
    # All pending → accuracy defaults to 0.5; consensus 0.5 → outlier 0.75.
    s = score_thinker([("pending", 0.5), ("pending", 0.5)])
    assert s["accuracy"] == 0.5
    assert s["outlier"] == 0.75
    # (0.5*0.85 + 0.75*0.15)*100 = 53.75 -> 53.8
    assert s["credibility"] == 53.8
    assert s["evaluable"] == 0 and s["total"] == 2


def test_all_true_high_consensus():
    s = score_thinker([("true", 1.0), ("true", 1.0)])
    assert s["accuracy"] == 1.0
    assert s["outlier"] == 1.0
    assert s["credibility"] == 100.0


def test_mixed_statuses_average():
    # true(1.0) + false(0.0) + partially_true(0.5) over 3 evaluable = 0.5
    s = score_thinker([("true", 0.2), ("false", 0.2), ("partially_true", 0.2)])
    assert s["accuracy"] == 0.5
    # avg consensus 0.2 -> outlier 0.6
    assert s["outlier"] == 0.6
    assert s["evaluable"] == 3


def test_none_consensus_treated_as_zero():
    s = score_thinker([("true", None)])
    assert s["outlier"] == 0.5  # avg consensus 0.0 -> 0.5 + 0
