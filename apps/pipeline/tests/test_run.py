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


def test_ingest_stage_is_retired():
    """2026-08-20 pivot: content is researched inside synthesize; nothing
    schedules the scraper. `run ingest` still exits cleanly (stale crons must
    not red-flag a deploy) but carries no steps."""
    assert run.STAGES == ('synthesize',)
    assert run.steps_for('ingest', only=None, discover=False) == []


def test_only_the_map_regen_is_gated():
    """The gate exists for one reason: mapgen is expensive whether or not the
    input changed, so it is skipped when no new claims landed.

    `scan` is deliberately NOT gated — it is what PRODUCES the new claims the
    gate then measures. `classify` is not gated either: an innovation can
    arrive in a week with no new claims at all, and it still needs its shift
    links; it is free when there is nothing to do."""
    synth = {s.name: s.gated for s in run.steps_for('synthesize', only=None, discover=False)}
    assert synth['mapgen'] is True
    assert synth['scan'] is False
    assert synth['classify'] is False


# ── Stage selection ───────────────────────────────────────────────────────────

def test_only_selects_a_single_step():
    steps = run.steps_for('synthesize', only='scan', discover=False)
    assert [s.name for s in steps] == ['scan']


def test_only_rejects_an_unknown_step():
    # Asking for a retired step is an operator error and must fail loudly
    # rather than silently running nothing.
    with pytest.raises(SystemExit):
        run.steps_for('synthesize', only='scrape', discover=False)


def test_scan_feeds_scoring_feeds_generation():
    """Research writes the claims; weights must be current before dedup uses
    them to pick primaries and before mapgen routes on them."""
    names = [s.name for s in run.steps_for('synthesize', only=None, discover=False)]
    assert (names.index('scan') < names.index('score')
            < names.index('dedupe') < names.index('mapgen')
            < names.index('classify'))


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


def test_blocked_sources_without_proxy_alert(monkeypatch):
    """A whole platform IP-blocked with no proxy credential must escalate —
    the console-only line let all 11 YouTube sources stay dark for weeks."""
    monkeypatch.delenv('YOUTUBE_PROXY_URL', raising=False)
    monkeypatch.delenv('WEBSHARE_PROXY_USERNAME', raising=False)
    alerts, sent = _alerts(blocked_sources=11)
    assert any('no proxy configured' in a for a in alerts)
    assert len(sent) == 1


def test_blocked_sources_with_proxy_is_quiet(monkeypatch):
    """Once a credential exists the block is being worked; no standing alarm."""
    monkeypatch.setenv('WEBSHARE_PROXY_USERNAME', 'user')
    alerts, _ = _alerts(blocked_sources=11)
    assert alerts == []


def test_high_extraction_failure_rate_alerts():
    errors = [{'step': 'extract'}] * 9
    alerts, _ = _alerts(errors=errors, run_row={'run_id': 'r', 'files_processed': 1})
    assert any('failure rate' in a for a in alerts)


def test_two_consecutive_empty_synthesize_runs_alert():
    """Since the pivot, synthesize is the stage that ADDS claims (the sphere
    scan researches the live web) — two runs producing none is the new shape
    of silent breakage."""
    alerts, _ = _alerts(
        new_claims=0,
        run_row={'run_id': 'r', 'stage': 'synthesize', 'files_processed': 0},
        previous_runs=[{'stage': 'synthesize', 'files_processed': 0}])
    assert any('silent breakage' in a for a in alerts)


def test_one_empty_run_after_a_productive_one_is_quiet():
    alerts, _ = _alerts(
        new_claims=0,
        run_row={'run_id': 'r', 'stage': 'synthesize', 'files_processed': 0},
        previous_runs=[{'stage': 'synthesize', 'files_processed': 40}])
    assert alerts == []


def test_legacy_ingest_rows_are_not_judged():
    """Historical ingest run rows predate the pivot; the retired stage must
    not be measured for silent breakage."""
    alerts, _ = _alerts(
        new_claims=0,
        run_row={'run_id': 'r', 'stage': 'ingest', 'files_processed': 0},
        previous_runs=[{'stage': 'ingest', 'files_processed': 0}])
    assert alerts == []


def test_an_empty_synthesize_is_not_excused_by_an_intervening_legacy_row():
    """The previous *synthesize* is the comparison, whatever else ran since."""
    alerts, _ = _alerts(
        new_claims=0,
        run_row={'run_id': 'r', 'stage': 'synthesize', 'files_processed': 0},
        previous_runs=[{'stage': 'ingest', 'files_processed': 40},
                       {'stage': 'synthesize', 'files_processed': 0}])
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
