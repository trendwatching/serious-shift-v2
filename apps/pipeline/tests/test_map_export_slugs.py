"""The published slug rules, tested without a database.

`test_map_export_golden.py` covers the exported document, but it skips unless
`DATABASE_URL` is populated — so on an ordinary CI run nothing exercised slug
assignment at all. These do, because the rules here are the ones the publication
gate refuses a whole run over.
"""
from __future__ import annotations

from serious_shift_pipeline.mapgen.export import assign_sub_tails


def _sub(sid, name, kt_id=1):
    return {'id': sid, 'name': name, 'kt_id': kt_id}


def test_a_tail_is_unique_across_the_whole_map_not_just_under_its_parent():
    """validation.duplicate_sub_shift_slug compares tails globally. Deduplicating
    per parent is what let the exporter build a document the gate always
    refused — after every paid phase had already run."""
    tails, suffixed = assign_sub_tails(
        [_sub(1, 'Provenance Premium', kt_id=1),
         _sub(2, 'Provenance Premium', kt_id=2)], {})
    assert sorted(tails.values()) == ['provenance-premium', 'provenance-premium-2']
    assert suffixed == ['provenance-premium-2']


def test_a_tail_never_shadows_a_key_shift_slug():
    """validation.sub_shift_shadows_shift is unrepairable, so this has to hold
    by construction rather than by rejection."""
    tails, _ = assign_sub_tails([_sub(1, 'Silent Commerce')],
                                {10: 'silent-commerce'})
    assert tails[1] == 'silent-commerce-2'


def test_distinct_names_are_left_alone():
    tails, suffixed = assign_sub_tails(
        [_sub(1, 'Charm Arithmetic'), _sub(2, 'Intent Plumbing')], {})
    assert tails == {1: 'charm-arithmetic', 2: 'intent-plumbing'}
    assert suffixed == []


def test_every_suffix_is_reported():
    """A numeric suffix in a live URL is a name nobody chose. It used to be
    applied silently."""
    _, suffixed = assign_sub_tails(
        [_sub(i, 'Same Name') for i in range(1, 4)], {})
    assert suffixed == ['same-name-2', 'same-name-3']


def test_assignment_is_stable_for_the_same_input():
    """The caller passes rows ORDER BY kt_id, sort_order, so a rerun over an
    unchanged database must produce byte-identical URLs — that is what makes
    --export-only a safe recovery path."""
    rows = [_sub(1, 'Same Name', 1), _sub(2, 'Same Name', 2), _sub(3, 'Other', 3)]
    assert assign_sub_tails(rows, {}) == assign_sub_tails(list(rows), {})


def test_every_row_gets_exactly_one_tail():
    rows = [_sub(i, n) for i, n in enumerate(['A', 'B', 'A', 'C', 'B'], start=1)]
    tails, _ = assign_sub_tails(rows, {})
    assert len(tails) == len(rows)
    assert len(set(tails.values())) == len(rows)
