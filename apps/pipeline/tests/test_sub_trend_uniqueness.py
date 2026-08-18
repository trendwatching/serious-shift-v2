"""A duplicate name must not be able to reach the reader OR fail the run.

Before this, a collision surviving three re-asks printed "publication will
reject them" and the gate killed the whole run — after every paid phase had
been paid for. The ask ladder is a quality mechanism and is kept; these pin the
deterministic tier underneath it, which cannot fail because it chooses among
candidates the model already returned rather than asking for new ones.
"""
from __future__ import annotations

from serious_shift_pipeline.mapgen.naming import choose_unique, name_key


def _sub(name):
    return {'name': name, 'subtitle': f'{name} subtitle', 'description': 'd'}


def test_a_collider_is_replaced_by_the_next_candidate():
    claimed = {name_key('Provenance Premium')}
    kept, dropped = choose_unique(
        [_sub('Provenance Premium'), _sub('Charm Arithmetic'), _sub('Intent Plumbing')],
        2, claimed)
    assert [k['name'] for k in kept] == ['Charm Arithmetic', 'Intent Plumbing']
    assert dropped == ['Provenance Premium']


def test_a_sub_shift_can_never_wear_its_parents_name():
    """Seeded with the key-shift names, so `sub_shift_shadows_shift` — which is
    unrepairable — becomes impossible rather than merely detected."""
    claimed = {name_key('Silent Commerce')}
    kept, dropped = choose_unique(
        [_sub('Silent Commerce'), _sub('Charm Arithmetic')], 5, claimed)
    assert [k['name'] for k in kept] == ['Charm Arithmetic']
    assert dropped == ['Silent Commerce']


def test_no_machine_name_is_ever_minted():
    """The alternative fix — suffixing a collider — puts a name no editor wrote
    into a public URL. Dropping is preferred over inventing."""
    claimed: set = set()
    kept, _ = choose_unique([_sub('Same Name')] * 4, 4, claimed)
    assert [k['name'] for k in kept] == ['Same Name']
    assert not any(k['name'].endswith(('-2', '-3', '-4')) for k in kept)


def test_four_real_names_beat_five_with_a_twin():
    """The gate accepts 4..5 children precisely so an editor can merge two."""
    claimed: set = set()
    kept, _ = choose_unique(
        [_sub('A'), _sub('B'), _sub('C'), _sub('D'), _sub('A')], 5, claimed)
    assert len(kept) == 4


def test_spares_are_used_before_the_list_is_truncated():
    """Truncating to five first discarded the very candidate that would have
    replaced the collider — which is how a duplicate reached the gate."""
    claimed = {name_key('B')}
    kept, _ = choose_unique(
        [_sub('A'), _sub('B'), _sub('C'), _sub('D'), _sub('E'), _sub('F')], 5, claimed)
    assert [k['name'] for k in kept] == ['A', 'C', 'D', 'E', 'F']


def test_claimed_accumulates_so_later_shifts_see_earlier_ones():
    claimed: set = set()
    choose_unique([_sub('Shared')], 5, claimed)
    kept, dropped = choose_unique([_sub('Shared'), _sub('Distinct')], 5, claimed)
    assert [k['name'] for k in kept] == ['Distinct']
    assert dropped == ['Shared']


def test_names_are_compared_the_way_the_url_compares_them():
    """Looser than url_slug and the writer disagrees with the gate again."""
    claimed = {name_key('Proof Premium')}
    kept, _ = choose_unique([_sub('proof  premium'), _sub('Other')], 5, claimed)
    assert [k['name'] for k in kept] == ['Other']


def test_a_nameless_candidate_is_skipped_without_being_reported():
    claimed: set = set()
    kept, dropped = choose_unique([{'name': '  '}, _sub('Real')], 5, claimed)
    assert [k['name'] for k in kept] == ['Real']
    assert dropped == []
