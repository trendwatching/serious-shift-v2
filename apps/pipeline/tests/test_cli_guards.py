"""The failure paths, which are the ones nobody exercises until they fire.

Each of these was a way a run either died with a traceback instead of a usable
message, or — worse — carried on and produced output indistinguishable from a
good run.
"""
from __future__ import annotations

import serious_shift_pipeline.mapgen.cli as cli
import serious_shift_pipeline.run as run_mod


# ── the repair pass must survive an id it cannot parse ───────────────────

def test_an_unparseable_shift_id_is_skipped_not_raised():
    """`int(...removeprefix('kt-'))` raised from INSIDE the repair pass, which
    turned a recoverable gate failure into a traceback — destroying the message
    that says the map is intact and re-publishable for free."""
    assert cli._db_id('kt-42') == 42
    for bad in ('kt-abc', '', None, 'st-7x', 'kt-'):
        assert cli._db_id(bad) is None


# ── a failed mapgen must not let classify run on last week's map ─────────

def test_mapgen_aborts_the_synthesize_stage():
    mapgen = next(s for s in run_mod.STEPS if s.name == 'mapgen')
    assert mapgen.aborts_stage is True


def test_ingest_steps_stay_independent():
    """Deliberately unchanged: one dead source must not stop the others."""
    assert not any(s.aborts_stage for s in run_mod.STEPS if s.stage == 'ingest')


def test_a_failing_abort_step_skips_the_rest_of_its_stage(monkeypatch):
    monkeypatch.setattr(run_mod, 'run_step', lambda step, dry_run, env: 1)
    monkeypatch.setattr(run_mod, 'gate_reason', lambda stage, dry_run=False: None)

    class _Args:
        only = None
        discover = False
        dry_run = False
        force = True

    class _Log:
        def record(self, **kwargs):
            pass

    outcomes = run_mod.run_stage(
        'synthesize', args=_Args(), error_log=_Log(), subprocess_env=None)
    assert outcomes['mapgen'].startswith('FAILED')
    # classify reads the map mapgen just failed to publish. Running it anyway
    # recorded last week's classification as this week's.
    assert outcomes['classify'] == 'skipped (mapgen failed)'


def test_a_succeeding_stage_still_runs_every_step(monkeypatch):
    monkeypatch.setattr(run_mod, 'run_step', lambda step, dry_run, env: 0)
    monkeypatch.setattr(run_mod, 'gate_reason', lambda stage, dry_run=False: None)

    class _Args:
        only = None
        discover = False
        dry_run = False
        force = True

    class _Log:
        def record(self, **kwargs):
            pass

    outcomes = run_mod.run_stage(
        'synthesize', args=_Args(), error_log=_Log(), subprocess_env=None)
    assert outcomes == {'scan': 'ok', 'score': 'ok', 'dedupe': 'ok',
                        'mapgen': 'ok', 'classify': 'ok'}


# ── the orchestrator's run row is not mapgen's to close ──────────────────

def test_a_gate_failure_does_not_close_an_orchestrated_run_row(monkeypatch):
    """`finish()` matches on run_id alone, so stamping it here set finished_at
    and status='failed' while later steps had yet to run — the exact double-close
    `_open_export_run` documents avoiding."""
    monkeypatch.setenv('SS_RUN_ID', 'run-owned-by-the-orchestrator')
    calls: list[str] = []

    class _Run:
        def __init__(self, run_id, stage):
            pass

        def start(self):
            calls.append('start')

        def finish(self, **kwargs):
            calls.append('finish')

        def add_usage(self, **kwargs):
            calls.append('add_usage')

    monkeypatch.setattr(cli, 'RunLog', _Run)
    cli._record_validation_failure(
        cli.PublicationValidationError([]))
    assert calls == ['add_usage']


def test_a_standalone_gate_failure_still_opens_and_closes_its_own_row(monkeypatch):
    monkeypatch.delenv('SS_RUN_ID', raising=False)
    calls: list[str] = []

    class _Run:
        def __init__(self, run_id, stage):
            pass

        def start(self):
            calls.append('start')

        def finish(self, **kwargs):
            calls.append('finish')

        def add_usage(self, **kwargs):
            calls.append('add_usage')

    monkeypatch.setattr(cli, 'RunLog', _Run)
    cli._record_validation_failure(cli.PublicationValidationError([]))
    # add_usage carries the spend the failed generation already incurred; the
    # lifecycle this test guards is still open-first, close-last.
    assert calls == ['start', 'add_usage', 'finish']
