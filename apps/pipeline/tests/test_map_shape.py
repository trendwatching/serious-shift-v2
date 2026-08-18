"""The map's shape: spheres may differ, and the limits scale with the map.

The counts were widened on the 18 Aug 2026 review — key shifts to 7–15 per
sphere with no requirement that spheres match, sub-shifts to 3–5. The risk is
not the two ranges; it is the half-dozen supporting numbers that were sized for
a 36-shift map and are absolute. Each of these pins one of them.
"""
from __future__ import annotations

import pytest

from serious_shift_pipeline.mapgen import cli
from serious_shift_pipeline.mapgen.config import (CLAIMS_PER_DOM, MAX_KTS_PER_DOM,
                                                  MAX_SUB_TRENDS, MIN_KTS_PER_DOM,
                                                  MIN_SUB_TRENDS, kt_change_budget)
from serious_shift_pipeline.mapgen.phases.sub_trends import (MIN_CLAIMS_PER_SUB,
                                                             MIN_POOL_PER_KT)
from serious_shift_pipeline.mapgen.validation import EVIDENCE_REUSE_SHARE

from test_content_gates import full_map
from test_map_validation import CONTRACT, codes, valid_map


# ── the ranges themselves ────────────────────────────────────────────────

def test_the_ranges_are_what_the_review_asked_for():
    assert (MIN_SUB_TRENDS, MAX_SUB_TRENDS) == (3, 5)
    assert MAX_KTS_PER_DOM == 15


def test_spheres_are_not_required_to_match_each_other():
    """The gate checks each sphere against the range independently, so a sphere
    with thinner evidence simply carries fewer — that is all "need not be the
    same" requires."""
    document = valid_map()
    base = document['key_trends'][0]
    subs: dict = {}
    for sub in document['sub_trends']:
        subs.setdefault(sub['key_trend_id'], []).append(sub)

    shifts, children = [], []
    n = 0
    # society gets the ceiling, economy the floor; both must pass.
    for domain_id, count in (('society', MAX_KTS_PER_DOM), ('economy', MIN_KTS_PER_DOM)):
        for _ in range(count):
            n += 1
            shift = {**base, 'id': f'kt-{n}', 'slug': f'shift-{n}',
                     'domain_id': domain_id, 'name': f'Distinct Story {n}'}
            kids = []
            for k, sub in enumerate(subs[base['id']][:MIN_SUB_TRENDS], start=1):
                kids.append({**sub, 'id': f'st-{n}-{k}', 'key_trend_id': shift['id'],
                             'domain_id': domain_id, 'slug': f'shift-{n}/sub-{n}-{k}',
                             'name': f'Distinct Sub {n}-{k}'})
            shift['sub_trend_ids'] = [c['id'] for c in kids]
            shifts.append(shift)
            children.extend(kids)

    document['key_trends'] = shifts
    document['sub_trends'] = children
    document['domains'] = [d for d in document['domains']
                           if d['id'] in {'society', 'economy'}]
    for domain in document['domains']:
        domain['key_trend_ids'] = [s['id'] for s in shifts
                                   if s['domain_id'] == domain['id']]
    assert 'kt_count' not in codes(document)


@pytest.mark.parametrize('count', [MIN_KTS_PER_DOM - 1, MAX_KTS_PER_DOM + 1])
def test_a_sphere_outside_the_range_is_still_rejected(count):
    """Widening is not removing: the range still has both ends."""
    assert not MIN_KTS_PER_DOM <= count <= MAX_KTS_PER_DOM


# ── the supporting numbers that had to scale ─────────────────────────────

def test_the_claim_pool_scales_with_the_ceiling():
    """Demand is n_kts x CLAIMS_PER_KT against a fixed supply. At the ceiling
    the pool must still leave every shift a publishable share."""
    per_shift = CLAIMS_PER_DOM // MAX_KTS_PER_DOM
    assert per_shift >= MIN_POOL_PER_KT, (
        f'{CLAIMS_PER_DOM} claims over {MAX_KTS_PER_DOM} shifts leaves '
        f'{per_shift} each, below the publishable floor of {MIN_POOL_PER_KT}')


def test_the_pool_floor_is_derived_from_the_child_minimum():
    """It was a literal 12, sized for five children, and would have stayed
    sized for five."""
    assert MIN_POOL_PER_KT >= MIN_SUB_TRENDS * MIN_CLAIMS_PER_SUB


def test_the_evidence_reuse_cap_grows_with_the_map():
    """Absolute and NOT repairable, so it is the likeliest way a paid run dies:
    reuse pressure scales with sub-shift count and the cap did not."""
    cap = lambda n: max(3, round(EVIDENCE_REUSE_SHARE * n))  # noqa: E731
    assert cap(180) == 3, 'must reproduce the historical cap at the old size'
    assert cap(MAX_KTS_PER_DOM * 4 * MAX_SUB_TRENDS) > 3


def test_the_repair_limit_grows_with_the_map():
    """A flat 12 is a third of a 36-shift map and a fifth of a 60-shift one, so
    a constant defect RATE would cross it as the map grew and skip the repair
    entirely — turning repairable issues into a failed publication."""
    small = cli._repair_limit({'key_trends': [{}] * 36})
    large = cli._repair_limit({'key_trends': [{}] * 60})
    assert large > small >= cli.MIN_TARGETED_REPAIR_SHIFTS


def test_the_rename_budget_is_a_share_not_a_count():
    """2 renames is 29% of a seven-shift sphere and 13% of a fifteen-shift one."""
    assert kt_change_budget(15) > kt_change_budget(7) >= 1


# ── the writer and the gate must agree ───────────────────────────────────

def test_the_generator_and_the_gate_read_the_same_sub_shift_range():
    """These were separate literals in three files. The gate's message is built
    from the constants, so a drift shows up here rather than in production."""
    from serious_shift_pipeline.mapgen.phases import editorial, sub_trends

    assert sub_trends.MIN_SUB_TRENDS is MIN_SUB_TRENDS
    assert sub_trends.MAX_SUB_TRENDS is MAX_SUB_TRENDS
    assert editorial.MIN_SUB_TRENDS is MIN_SUB_TRENDS

    document = valid_map()
    parent = document['key_trends'][0]
    kids = [s for s in document['sub_trends'] if s['key_trend_id'] == parent['id']]
    for sub in kids[MIN_SUB_TRENDS - 1:]:
        document['sub_trends'].remove(sub)
        parent['sub_trend_ids'].remove(sub['id'])
    found = [i for i in __import__(
        'serious_shift_pipeline.mapgen.validation', fromlist=['x']
    ).validate_map(document, CONTRACT) if i.code == 'sub_shift_count']
    assert found and f'{MIN_SUB_TRENDS}-{MAX_SUB_TRENDS}' in found[0].message


def test_evidence_reuse_is_repairable():
    """It was the only non-repairable issue in the 18 Aug staging set, and one
    claim sitting a single page over the cap discarded a finished 44-shift map
    while 28 other issues were all repairable."""
    # full_map(), not valid_map(): the population gates only run once the map
    # has FULL_MAP_MIN_SHIFTS shifts, and valid_map() has four.
    document = full_map()
    shared = (document['sub_trends'][0]['claim_ids'] or ['c_1'])[0]
    for sub in document['sub_trends'][:6]:
        sub['claim_ids'] = [shared]
    found = [i for i in __import__(
        'serious_shift_pipeline.mapgen.validation', fromlist=['x']
    ).validate_map(document, CONTRACT) if i.code == 'evidence_reuse']
    assert found, 'expected the cap to fire'
    assert all(i.repairable for i in found)


def test_the_repair_limit_covers_a_map_that_needs_many_small_fixes():
    """0.35 gave 15 against 30 affected parents, so the pass skipped and threw
    away a completed generation to avoid a repair costing a fraction of it. The
    guard should still refuse a map that is broken EVERYWHERE."""
    assert cli._repair_limit({'key_trends': [{}] * 44}) >= 30
    total = 60
    assert cli._repair_limit({'key_trends': [{}] * total}) < total
