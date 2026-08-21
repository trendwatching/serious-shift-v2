"""A duplicate name must not be able to reach the reader OR fail the run.

Before this, a collision surviving three re-asks printed "publication will
reject them" and the gate killed the whole run — after every paid phase had
been paid for. The ask ladder is a quality mechanism and is kept; these pin the
deterministic tier underneath it, which cannot fail because it chooses among
candidates the model already returned rather than asking for new ones.
"""
from __future__ import annotations

from serious_shift_pipeline.mapgen.naming import (
    NAME_FAMILY_CAP, breaches_family_cap, choose_unique, family_counter,
    family_keys, name_key)


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


# ── Name families ────────────────────────────────────────────────────────────
# The 2026-08-19 content review counted nine "…Blindspot"s and seven
# "…Premium"s — every one legal by exact-slug uniqueness, together a monotone.


def test_blind_spot_and_blindspot_are_one_family():
    assert family_keys('Deflation Blind Spot') & family_keys('Proxy Blindspot')
    assert family_keys('Liability Blind Spot') & family_keys('Deflation Blindspot')


def test_short_and_stop_words_never_form_a_family():
    # "AI" (2 chars) and "of" must not register; nothing here collides
    assert not (family_keys('AI Shift') & family_keys('AI Premium'))


def test_no_stemming_blindness_is_not_blindspot():
    assert not (family_keys('Proxy Blindness') & family_keys('Proxy Blindspot') - {'proxy'})


def test_the_third_family_member_is_walked_past():
    families = family_counter(['Evaluation Premium', 'Collapse Premium'])
    assert breaches_family_cap('Toil Premium', families)
    kept, dropped = choose_unique(
        [_sub('Toil Premium'), _sub('Craft Amnesia')], 1, set(), families=families)
    assert [k['name'] for k in kept] == ['Craft Amnesia']
    assert dropped == ['Toil Premium']


def test_kept_names_count_toward_the_cap():
    families = family_counter(['Origin Debt'])
    kept, dropped = choose_unique(
        [_sub('Privacy Debt'), _sub('Graph Debt'), _sub('Verification Gap')],
        3, set(), families=families)
    # second "Debt" fills the cap; the third is rejected
    assert [k['name'] for k in kept] == ['Privacy Debt', 'Verification Gap']
    assert dropped == ['Graph Debt']


def test_head_words_form_families_too():
    families = family_counter(['Context Capture', 'Context Ransom'])
    assert breaches_family_cap('Context Prerequisite', families)


def test_families_none_preserves_old_behavior():
    claimed: set = set()
    kept, dropped = choose_unique(
        [_sub('Evaluation Premium'), _sub('Collapse Premium'), _sub('Toil Premium')],
        3, claimed)
    assert len(kept) == 3 and dropped == []


def test_the_cap_is_two():
    assert NAME_FAMILY_CAP == 2, "the review's finding: a pair rhymes, three is a tic"


def test_the_family_cap_yields_to_the_sub_count_floor():
    """2026-08-19: with ~200 names claimed, every candidate of a late family
    echoed something and the strict walk left shifts 0-2 children against a
    gate of 3. Family-breaching spares are re-admitted up to min_want; exact
    twins never are."""
    families = family_counter(['Evaluation Premium', 'Collapse Premium',
                               'Origin Debt', 'Privacy Debt'])
    claimed = {name_key('Toil Premium')}
    kept, dropped = choose_unique(
        [_sub('Toil Premium'),      # exact collision — stays out even at the floor
         _sub('Slippage Premium'),  # family breach — re-admitted at the floor
         _sub('Graph Debt'),        # family breach — re-admitted at the floor
         _sub('Craft Amnesia')],    # clean — kept strictly
        5, claimed, families=families, min_want=3)
    assert [k['name'] for k in kept] == ['Craft Amnesia', 'Slippage Premium', 'Graph Debt']
    assert dropped == ['Toil Premium']


def test_the_floor_never_readmits_when_the_strict_walk_suffices():
    families = family_counter(['Evaluation Premium', 'Collapse Premium'])
    kept, dropped = choose_unique(
        [_sub('Craft Amnesia'), _sub('Vernacular Suspicion'), _sub('Gut Veto'),
         _sub('Toil Premium')],
        3, set(), families=families, min_want=3)
    assert [k['name'] for k in kept] == ['Craft Amnesia', 'Vernacular Suspicion', 'Gut Veto']
    assert dropped == []  # never visited: want was satisfied before its turn
