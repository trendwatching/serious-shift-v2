"""Targeted-repair parent resolution — pure-function tests (no DB, no API).

The validator writes ARRAY INDICES into issue paths ('sub_trends[39]…'),
while `_issue_shift_ids` only looked the segment up in an id-keyed map
('st-140' → parent) — so every sub-anchored issue resolved to no parent and a
repair pass regenerated almost nothing. Observed on staging 2026-08-12: 14
issues produced a 1-request batch. These pin the fix: index first, id as the
fallback, and out-of-range/unknown segments are dropped rather than crashing.
"""
from dataclasses import dataclass

from serious_shift_pipeline.mapgen.cli import _issue_shift_ids


@dataclass
class _Issue:
    path: str


DOC = {
    'key_trends': [
        {'id': 'kt-1'},
        {'id': 'kt-2'},
    ],
    'sub_trends': [
        {'id': 'st-10', 'key_trend_id': 'kt-1'},
        {'id': 'st-11', 'key_trend_id': 'kt-1'},
        {'id': 'st-20', 'key_trend_id': 'kt-2'},
    ],
}


def test_sub_issue_paths_resolve_by_index():
    issues = [_Issue('sub_trends[2].modules.stat_band'),
              _Issue('sub_trends[0].modules[3].data.whats_changing')]
    assert _issue_shift_ids(DOC, issues) == {'kt-1', 'kt-2'}


def test_kt_issue_paths_resolve_by_index():
    assert _issue_shift_ids(DOC, [_Issue('key_trends[1].modules[7].data')]) == {'kt-2'}


def test_id_shaped_segments_still_resolve():
    # The id-keyed lookup stays as the fallback for any path that carries one.
    assert _issue_shift_ids(DOC, [_Issue('sub_trends[st-20].modules')]) == {'kt-2'}


def test_unresolvable_segments_are_dropped_not_fatal():
    issues = [_Issue('sub_trends[99].modules'),   # out of range
              _Issue('sub_trends[st-nope].x'),    # unknown id
              _Issue('claims[3].text')]           # different subtree entirely
    assert _issue_shift_ids(DOC, issues) == set()
