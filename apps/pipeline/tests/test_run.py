"""
Orchestrator tests — step table, stage selection, escalation. No DB, no network.

The step table is data, so these assert the properties that matter rather than
the literal list: stages partition the steps, every step is runnable as
`python -m`, and the two stages can genuinely be run on their own.
"""
import pytest

from serious_shift_pipeline import run


# ── Step table ────────────────────────────────────────────────────────────────

def test_every_step_belongs_to_a_known_stage():
    for step in run.STEPS:
        assert step.stage in run.STAGES, f"{step.name} has stage {step.stage!r}"


def test_both_stages_are_non_empty():
    """The whole point of the split is that each stage does something on its own."""
    for stage in run.STAGES:
        assert run.steps_for(stage, only=None, discover=False), f"{stage} has no steps"


def test_step_names_are_unique():
    names = [s.name for s in run.STEPS]
    assert len(names) == len(set(names))


def test_commands_invoke_the_package_as_a_module():
    for step in run.STEPS:
        cmd = step.command()
        assert cmd[1] == '-m'
        assert cmd[2].startswith('serious_shift_pipeline.')


def test_ingest_and_synthesize_do_not_overlap():
    ingest = {s.name for s in run.steps_for('ingest', only=None, discover=True)}
    synth = {s.name for s in run.steps_for('synthesize', only=None, discover=True)}
    assert not (ingest & synth)


def test_only_the_map_regen_is_gated():
    """The gate exists for one reason: mapgen is a flat ~$5 whether or not the
    input changed, so it is skipped when no new claims landed.

    `classify` deliberately is NOT gated. An innovation can arrive in a week
    with no new claims at all, and it still needs its shift links — gating it
    behind the claim counter would leave those cards missing until the next week
    that happened to produce claims. It is free when there is nothing to do: the
    sweep query returns zero rows."""
    synth = {s.name: s.gated for s in run.steps_for('synthesize', only=None, discover=False)}
    assert synth['mapgen'] is True
    assert synth['classify'] is False
    assert not any(s.gated for s in run.steps_for('ingest', only=None, discover=False))


# ── Stage selection ───────────────────────────────────────────────────────────

def test_discovery_is_opt_in():
    without = [s.name for s in run.steps_for('ingest', only=None, discover=False)]
    with_ = [s.name for s in run.steps_for('ingest', only=None, discover=True)]
    assert 'discover' not in without
    assert 'discover' in with_


def test_discovery_runs_before_scraping():
    """It emits raw files that the scrape/extract steps then consume."""
    names = [s.name for s in run.steps_for('ingest', only=None, discover=True)]
    assert names.index('discover') < names.index('scrape')


def test_only_selects_a_single_step():
    steps = run.steps_for('ingest', only='scrape', discover=False)
    assert [s.name for s in steps] == ['scrape']


def test_only_rejects_a_step_from_another_stage():
    # mapgen is a synthesize step; asking for it under ingest is an operator
    # error and must fail loudly rather than silently running nothing.
    with pytest.raises(SystemExit):
        run.steps_for('ingest', only='mapgen', discover=False)


def test_extract_follows_scrape():
    names = [s.name for s in run.steps_for('ingest', only=None, discover=False)]
    assert names.index('scrape') < names.index('extract')


def test_scoring_precedes_dedupe_and_evaluate():
    """Ranking inputs must be current before duplicates and credibility use them."""
    names = [s.name for s in run.steps_for('ingest', only=None, discover=False)]
    assert names.index('score') < names.index('dedupe') < names.index('evaluate')


# ── Escalation ────────────────────────────────────────────────────────────────

def _alerts(**kw):
    sent = []
    defaults = dict(
        errors=[], new_claims=10, run_row=None, previous_runs=[],
        failed_sources=0, _notify_fn=lambda **k: sent.append(k),
    )
    return run.check_escalation(**{**defaults, **kw}), sent


def test_quiet_run_raises_nothing():
    alerts, sent = _alerts()
    assert alerts == [] and sent == []


def test_cost_overrun_alerts():
    alerts, sent = _alerts(
        run_row={'run_id': 'r1', 'cost_usd': run.COST_ALERT_THRESHOLD + 1,
                 'files_processed': 10})
    assert any('exceeds threshold' in a for a in alerts)
    assert len(sent) == 1


def test_failed_sources_alert_at_threshold():
    alerts, _ = _alerts(failed_sources=run.FAILED_SOURCES_THRESHOLD)
    assert any('failed' in a for a in alerts)


def test_failed_sources_below_threshold_is_quiet():
    alerts, _ = _alerts(failed_sources=run.FAILED_SOURCES_THRESHOLD - 1)
    assert alerts == []


def test_high_extraction_failure_rate_alerts():
    errors = [{'step': 'extract'}] * 9
    alerts, _ = _alerts(errors=errors, run_row={'run_id': 'r', 'files_processed': 1})
    assert any('failure rate' in a for a in alerts)


def test_two_consecutive_empty_ingest_runs_alert():
    alerts, _ = _alerts(
        new_claims=0,
        run_row={'run_id': 'r', 'stage': 'ingest', 'files_processed': 0},
        previous_runs=[{'stage': 'ingest', 'files_processed': 0}])
    assert any('silent breakage' in a for a in alerts)


def test_one_empty_run_after_a_productive_one_is_quiet():
    alerts, _ = _alerts(
        new_claims=0,
        run_row={'run_id': 'r', 'stage': 'ingest', 'files_processed': 0},
        previous_runs=[{'stage': 'ingest', 'files_processed': 40}])
    assert alerts == []


def test_back_to_back_synthesis_is_not_reported_as_silent_breakage():
    """Synthesis adds no claims and processes no files by definition, so judging
    it on those counters made every second `synthesize` cry wolf."""
    alerts, _ = _alerts(
        new_claims=0,
        run_row={'run_id': 'r', 'stage': 'synthesize', 'files_processed': 0},
        previous_runs=[{'stage': 'synthesize', 'files_processed': 0}])
    assert alerts == []


def test_an_empty_ingest_is_not_excused_by_an_intervening_synthesis():
    """The previous *ingest* is the comparison, even when a synthesize ran since."""
    alerts, _ = _alerts(
        new_claims=0,
        run_row={'run_id': 'r', 'stage': 'ingest', 'files_processed': 0},
        previous_runs=[{'stage': 'synthesize', 'files_processed': 0},
                       {'stage': 'ingest', 'files_processed': 0}])
    assert any('silent breakage' in a for a in alerts)


def test_multiple_conditions_escalate_to_critical():
    _, sent = _alerts(
        failed_sources=run.FAILED_SOURCES_THRESHOLD,
        run_row={'run_id': 'r', 'cost_usd': run.COST_ALERT_THRESHOLD + 1,
                 'files_processed': 10},
    )
    assert sent[0]['urgency'] == 'critical'


def test_no_notify_suppresses_delivery_but_not_detection():
    alerts, sent = _alerts(failed_sources=run.FAILED_SOURCES_THRESHOLD, no_notify=True)
    assert alerts and sent == []


# ── CLI ───────────────────────────────────────────────────────────────────────

def test_stage_defaults_to_all():
    assert run.build_parser().parse_args([]).stage == 'all'


def test_each_stage_is_selectable_on_its_own():
    for stage in run.STAGES:
        assert run.build_parser().parse_args([stage]).stage == stage


def test_unknown_stage_is_rejected():
    with pytest.raises(SystemExit):
        run.build_parser().parse_args(['scrape-everything'])
