"""
Per-source health, and the signal for a source that has quietly stopped.

The run summary reported run-wide totals only. In one real run that meant:
three sources produced 74 of 115 fetch failures, 70 files were discarded as
too small, and the console said `Errors: 72` beside a query that returned 173.
Every one of those facts was already in the database. None of them was in the
thing anyone reads.

So the table here is *derived*, never tallied in parallel — a second counter is
exactly how the console and the record came to disagree in the first place.
"""
import pytest

from serious_shift_pipeline.run import (
    check_escalation,
    silent_sources,
    source_health,
)


def run_row(by_source, stage='ingest'):
    return {'stage': stage, 'detail': {'scrape': {'by_source': by_source}}}


def test_health_joins_scrape_counters_errors_and_claims():
    rows = source_health(
        run_row([
            {'thinker': 'Ethan Mollick', 'platform': 'blog', 'found': 9, 'fetched': 8, 'failed': 1},
            {'thinker': 'OpenAI', 'platform': 'blog', 'found': 30, 'fetched': 6, 'failed': 24},
        ]),
        errors=[
            {'step': 'scrape', 'thinker': 'OpenAI'},
            {'step': 'size_filter', 'thinker': 'Ethan Mollick'},
            {'step': 'size_filter', 'thinker': 'Ethan Mollick'},
            # Not attributable to a source, and not a fetch or extract failure —
            # must not land on anybody's row as one.
            {'step': 'publish', 'thinker': None},
        ],
        claims_by_thinker={'Ethan Mollick': 41},
    )
    by = {r['thinker']: r for r in rows}

    assert by['OpenAI']['found'] == 30
    assert by['OpenAI']['fetched'] == 6
    assert by['OpenAI']['failed'] == 25       # 24 from scrape counters + 1 error row
    assert by['OpenAI']['claims'] == 0
    assert by['Ethan Mollick']['too_small'] == 2
    assert by['Ethan Mollick']['claims'] == 41
    assert by['Ethan Mollick']['failed'] == 1
    # A publication error belongs to the run, not to a source. It must not
    # invent a row — an unattributable failure listed under "—" reads as a
    # broken source and sends someone looking for one that does not exist.
    assert set(by) == {'Ethan Mollick', 'OpenAI'}

    # Worst first — the top of the list is the list of things to look at.
    assert rows[0]['thinker'] == 'OpenAI'


def test_too_small_is_counted_apart_from_failure():
    """A 900-byte file is usually a nav shell and sometimes a genuinely short
    post. Folding it into `failed` would make the 1500-byte threshold
    untunable, because nobody could see what it was costing."""
    rows = source_health(
        run_row([{'thinker': 'A', 'platform': 'blog', 'found': 5, 'fetched': 5, 'failed': 0}]),
        errors=[{'step': 'size_filter', 'thinker': 'A'} for _ in range(70)],
        claims_by_thinker={},
    )
    assert rows[0]['too_small'] == 70
    assert rows[0]['failed'] == 0


def test_a_source_silent_twice_is_reported_but_one_quiet_week_is_not():
    current = [
        {'thinker': 'Dead Feed', 'fetched': 0, 'claims': 0, 'failed': 0, 'too_small': 0, 'found': 0},
        {'thinker': 'Quiet Week', 'fetched': 0, 'claims': 0, 'failed': 0, 'too_small': 0, 'found': 0},
        {'thinker': 'Healthy', 'fetched': 4, 'claims': 9, 'failed': 0, 'too_small': 0, 'found': 4},
    ]
    previous = [run_row([
        {'thinker': 'Dead Feed', 'fetched': 0},
        {'thinker': 'Quiet Week', 'fetched': 3},
        {'thinker': 'Healthy', 'fetched': 5},
    ])]

    assert silent_sources(current, previous, 'ingest') == ['Dead Feed']


def test_a_source_not_attempted_last_run_is_not_called_silent():
    """Absent from the previous run's buckets means it was not tried, which is
    not the same as having produced nothing — a newly-added source would
    otherwise alert on its first empty run."""
    current = [{'thinker': 'Brand New', 'fetched': 0, 'claims': 0}]
    previous = [run_row([{'thinker': 'Someone Else', 'fetched': 2}])]
    assert silent_sources(current, previous, 'ingest') == []


def test_synthesis_is_never_judged_on_source_silence():
    """Synthesis fetches nothing, so every source looks silent to it. This is
    the same trap the run-wide check already fell into once."""
    current = [{'thinker': 'Anyone', 'fetched': 0, 'claims': 0}]
    previous = [run_row([{'thinker': 'Anyone', 'fetched': 0}], stage='synthesize')]
    assert silent_sources(current, previous, 'synthesize') == []


def test_no_previous_run_means_no_verdict():
    current = [{'thinker': 'Anyone', 'fetched': 0, 'claims': 0}]
    assert silent_sources(current, [], 'ingest') == []


@pytest.mark.parametrize('quiet,expected_alert', [([], False), (['A', 'B'], True)])
def test_quiet_sources_escalate(quiet, expected_alert):
    sent = []
    alerts = check_escalation(
        errors=[],
        new_claims=500,
        run_row={'stage': 'ingest', 'run_id': 'r1', 'cost_usd': 0, 'files_processed': 10},
        previous_runs=[],
        failed_sources=0,
        quiet_sources=quiet,
        _notify_fn=lambda **kw: sent.append(kw),
    )
    fired = any('silent' in a or 'produced nothing' in a for a in alerts)
    assert fired is expected_alert


def test_quiet_sources_defaults_to_off_for_existing_callers():
    """The parameter is optional so nothing that already calls this breaks."""
    alerts = check_escalation(
        errors=[], new_claims=1,
        run_row={'stage': 'ingest', 'run_id': 'r', 'cost_usd': 0, 'files_processed': 1},
        previous_runs=[], failed_sources=0, no_notify=True,
    )
    assert alerts == []
