"""
The threshold, pinned to the evidence that chose it.

`ACCEPT` decides whether any innovation reaches any page, and it was wrong for a
year without failing a single test: 0.72 was the value that made
`test_a_textbook_example_clears_accept` pass on a *two-shift* corpus where the
innovation restates the shift almost verbatim. Against the real 306-shift corpus
nothing could reach it, the classifier linked nothing, and it reported
`0 model call(s), $0.0000` while doing so — which reads as health.

That is the failure this file exists to make impossible to repeat. The fixture is
real scores from the real corpus (`tools/calibrate_classifier --record`); the
durable half replays them through the real `choose()` and asserts the DECISIONS.
Move `ACCEPT` without re-reading the evidence and this goes red.

Split durable/volatile the way `test_map_export_golden.py` argues for: shape and
decisions are asserted always and need no database; anything that drifts with the
weekly content is checked only when a `DATABASE_URL` is present, and loosely.
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest

from serious_shift_pipeline.core import matching as m

FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'classifier_calibration.json'

#: The one match a human would call obvious in the recorded corpus: a
#: multilingual public-services chatbot, against a shift about public
#: institutions failing.
OBVIOUS = ('South Africa', 'key_trend:institutional-collapse')
#: And the one that must not link: a clothing-resale programme is not an AI shift.
NOT_A_MATCH = 'Patagonia'


def _entries():
    if not FIXTURE.is_file():
        pytest.skip('no calibration fixture — record one with '
                    '`python -m serious_shift_pipeline.tools.calibrate_classifier --record`')
    return json.loads(FIXTURE.read_text())['innovations']


def _decide(entry, accept):
    from serious_shift_pipeline.tools.calibrate_classifier import decisions
    return decisions(entry, accept)


def _find(entries, needle):
    return next(e for e in entries if needle.lower() in e['title'].lower())


def test_the_obvious_match_links_at_the_shipped_threshold():
    entries = _entries()
    title, expected = OBVIOUS
    assert _decide(_find(entries, title), m.ACCEPT) == [expected]


def test_the_clear_non_match_links_nothing_at_the_shipped_threshold():
    assert _decide(_find(_entries(), NOT_A_MATCH), m.ACCEPT) == []


def test_the_threshold_sits_inside_the_band_the_evidence_supports():
    """`ACCEPT` must separate the obvious match from the clear non-match.

    The band is derived from the fixture rather than written down, because a
    hardcoded band goes stale the moment the corpus moves and then asserts
    something nobody measured. Its upper edge is the obvious match's own score —
    above that it stops linking; its lower edge is the runner-up's, below which a
    second, weaker shift joins it.

    Concretely, in the recorded corpus: the winner is 0.536 above a cliff to a
    0.41–0.43 plateau, so the usable band is roughly [0.427, 0.536]. It is real
    and it is narrow, which is exactly why the number deserves a test rather than
    a comment.
    """
    entries = _entries()
    title, expected = OBVIOUS
    obvious, non_match = _find(entries, title), _find(entries, NOT_A_MATCH)

    keys = [s for s in obvious['scored'] if s['scope'] == 'key_trend']
    top, runner_up = keys[0]['conf'], keys[1]['conf']
    non_match_top = max(s['conf'] for s in non_match['scored'])

    # Anything in the open band decides both cases correctly.
    for accept in (round(runner_up + 0.001, 3), m.ACCEPT, top):
        assert _decide(obvious, accept) == [expected], f'at {accept}'
        assert _decide(non_match, accept) == [], f'at {accept}'

    assert runner_up < m.ACCEPT <= top, (
        f'ACCEPT is {m.ACCEPT}; the recorded evidence supports '
        f'({runner_up}, {top}]. Above {top} the obvious match stops linking; '
        f'at or below {runner_up} a second, weaker shift joins it. If a move is '
        f'deliberate, run `tools.calibrate_classifier` and re-record first.'
    )
    assert non_match_top < m.ACCEPT, (
        f'the clear non-match tops out at {non_match_top}, which ACCEPT '
        f'({m.ACCEPT}) no longer clears'
    )


def test_the_old_threshold_would_link_nothing():
    """Guards the reason for the change, not just its result.

    Without this, someone restoring 0.72 sees every other test still pass — the
    classifier would simply go quiet again, which is exactly how it stayed broken
    for a year.
    """
    entries = _entries()
    assert all(_decide(e, 0.72) == [] for e in entries)


def test_accept_stays_above_the_never_link_floor():
    """`FLOOR` is the independent pre-evidence assertion. If `ACCEPT` ever slid
    below it the escalation band would invert and the floor would stop meaning
    anything."""
    assert m.FLOOR < m.ACCEPT


@pytest.mark.skipif(not os.environ.get('DATABASE_URL'), reason='needs a live corpus')
def test_live_corpus_links_something_but_not_everything():
    """Smoke only — never a digest.

    Content drifts weekly, so the assertions are the two failure modes worth
    waking up for: linking nothing at all (the bug we just fixed) and linking
    almost everything (a threshold set too low). Anything tighter than this would
    fail every Monday for no reason.
    """
    from serious_shift_pipeline.core import db
    from serious_shift_pipeline.tools.calibrate_classifier import collect

    with db.connect() as conn:
        _meta, entries = collect(conn, top=3, only=None)
    if not entries:
        pytest.skip('no active innovations in this database')

    linked = [e for e in entries if _decide(e, m.ACCEPT)]
    assert linked, 'the live corpus links nothing at all — the exact regression this suite exists for'
    assert len(linked) / len(entries) < 0.6, 'more than 60% linked; the threshold looks too low'
