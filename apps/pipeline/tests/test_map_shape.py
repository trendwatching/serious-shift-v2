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
from serious_shift_pipeline.mapgen.validation import validate_map

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


# ── one claim, one page: settled at export, not asked of the writers ─────

def _shift(slug, value, url):
    return {'slug': slug, 'hero_stat': {'value': value, 'url': url},
            'modules': [{'type': 'dek', 'data': {'text': 'x'}},
                        {'type': 'stat_band', 'data': {'value': value, 'url': url}}]}


def _sub(value, url):
    return {'modules': [{'type': 'stat_band', 'data': {'value': value, 'url': url}},
                        {'type': 'dek', 'data': {'text': 'x'}}]}


def test_a_child_cedes_its_stat_band_to_its_parent():
    """The gate registers key shifts first and blames the SUB, so the writer has
    to resolve it the same way round. The band is dropped, not blanked — a band
    without a figure is not a band."""
    from serious_shift_pipeline.mapgen.export import reconcile_fronted_stats

    # Long-form on the parent, the _short_figure reduction on the child: the
    # two forms that keyed differently before 2026-08-12.
    shifts = [_shift('governance-void',
                     '~1,337 employees across major Western AI labs signed', 'u1')]
    subs = [_sub('1,337', 'u1'), _sub('72%', 'u2')]
    report = reconcile_fronted_stats(shifts, subs)

    assert report['sub_bands_ceded'] == 1
    assert [m['type'] for m in subs[0]['modules']] == ['dek']
    assert shifts[0]['hero_stat'] is not None, 'the parent keeps its figure'
    assert [m['type'] for m in subs[1]['modules']] == ['stat_band', 'dek']


def test_two_parents_on_one_figure_leaves_the_later_shift_without_one():
    """Exclusive assignment is by claim id, but the key is (figure, source) —
    two claim rows quoting the same figure from the same article collide anyway,
    and there is no second place to put a hero."""
    from serious_shift_pipeline.mapgen.export import reconcile_fronted_stats

    shifts = [_shift('first', '41% choose agent shopping', 'u1'),
              _shift('second', '41% choose agent shopping', 'u1')]
    report = reconcile_fronted_stats(shifts, [])

    assert report['shift_heroes_dropped'] == ['second']
    assert shifts[1]['hero_stat'] is None
    assert 'stat_band' not in [m['type'] for m in shifts[1]['modules']]
    assert 'stat_band' in [m['type'] for m in shifts[0]['modules']]


def test_reconciliation_leaves_the_gate_nothing_to_find():
    """The point of doing it at export: whatever this returns must pass the
    very gate that used to reject it."""
    from serious_shift_pipeline.mapgen.export import reconcile_fronted_stats

    document = full_map()
    shared = {'value': '41% choose agent shopping', 'url': 'https://e.com/a'}
    for shift in document['key_trends'][:3]:
        shift['hero_stat'] = dict(shared)
    for sub in document['sub_trends'][:4]:
        sub['modules'] = [{'type': 'stat_band', 'data': dict(shared)}] + [
            m for m in sub.get('modules') or [] if m.get('type') != 'stat_band']

    assert 'duplicate_hero_claim' in codes(document), 'fixture must trip the gate'
    reconcile_fronted_stats(document['key_trends'], document['sub_trends'])
    assert 'duplicate_hero_claim' not in codes(document)


def test_the_us_spelling_of_programmed_is_not_flagged_as_british():
    """`programme(?:s|d)?` matched "programmed", which is the US past tense of
    "program" — three correct sentences failed the 18 Aug 2026 run on it. The
    British noun must still be caught."""
    from serious_shift_pipeline.mapgen.validation import _BRITISH

    assert not _BRITISH.search('the model was programmed to refuse')
    assert _BRITISH.search('a government programme')
    assert _BRITISH.search('two funding programmes')
    assert _BRITISH.search('they catalogued the results')


# ── claim over-reach: routing, so prose regeneration cannot touch it ─────

def test_the_page_with_the_most_to_stand_on_is_the_one_that_cedes():
    from serious_shift_pipeline.mapgen.export import reconcile_evidence_reuse

    subs = [{'claim_ids': ['c_1', 'c_2', 'c_3', 'c_4', 'c_5']},   # richest
            {'claim_ids': ['c_1', 'c_9']},
            {'claim_ids': ['c_1', 'c_7', 'c_8']},
            {'claim_ids': ['c_1', 'c_6', 'c_7', 'c_8']}]
    report = reconcile_evidence_reuse(subs)

    assert report['claims_trimmed'] == 1
    assert 'c_1' not in subs[0]['claim_ids'], 'the five-claim page gives it up'
    assert all('c_1' in subs[i]['claim_ids'] for i in (1, 2, 3))


def test_a_page_is_never_hollowed_out_to_pass_the_gate():
    """If every over-cap holder is at the floor, the claim stays over the cap
    and the gate rejects it — better a visible failure than four thin pages."""
    from serious_shift_pipeline.mapgen.export import reconcile_evidence_reuse

    subs = [{'claim_ids': ['c_1', 'c_2']} for _ in range(4)]
    assert reconcile_evidence_reuse(subs)['claims_trimmed'] == 0
    assert all(len(s['claim_ids']) == 2 for s in subs)


def test_a_claim_the_page_actually_cites_is_never_un_routed():
    """The first version trimmed on routing alone. It cleared evidence_reuse and
    broke editorial_provenance on two pages, because the prose was left citing a
    claim no longer routed to it — the point made, its source deleted."""
    from serious_shift_pipeline.mapgen.export import reconcile_evidence_reuse

    def page(extra):
        return {'claim_ids': ['c_1', *extra],
                'modules': [{'type': 'peel_tabs', 'data': {'evidence_ids': [1, *[
                    int(c.split('_')[1]) for c in extra]]}}]}

    subs = [page(['c_2', 'c_3', 'c_4']), page(['c_5']), page(['c_6']), page(['c_7'])]
    assert reconcile_evidence_reuse(subs)['claims_trimmed'] == 0
    assert all('c_1' in s['claim_ids'] for s in subs)


def test_trimming_leaves_the_gate_nothing_to_find():
    from serious_shift_pipeline.mapgen.export import reconcile_evidence_reuse

    document = full_map()
    subs = document['sub_trends']
    # c_1001 is routed to six pages and cited by none of them — the filler-dump
    # the cap exists to catch, and the only shape that is safe to trim.
    for n, sub in enumerate(subs[:6]):
        sub['claim_ids'] = ['c_1001', 'c_1002', f'c_{9000 + n}']
        for module in sub['modules']:
            if module.get('type') == 'peel_tabs':
                module['data']['evidence_ids'] = [1002, 9000 + n]

    def reuse_of(claim):
        return [i for i in validate_map(document, CONTRACT)
                if i.code == 'evidence_reuse' and claim in i.message]

    # By claim, not by code: full_map() trips evidence_reuse on its own, and a
    # bare `code in codes()` assertion passed whether or not the trim worked.
    assert reuse_of('c_1001'), 'fixture must trip the gate on this claim'
    provenance_before = [i for i in validate_map(document, CONTRACT)
                         if i.code == 'editorial_provenance']
    reconcile_evidence_reuse(subs)
    assert not reuse_of('c_1001')
    assert [i.path for i in validate_map(document, CONTRACT)
            if i.code == 'editorial_provenance'] == [i.path for i in provenance_before], \
        'the trim must not orphan a citation'


# ── the batch queue is not worth the wait for a handful of requests ──────

def test_a_small_submission_skips_the_batch_queue(monkeypatch):
    """A one-request retry sat in the batch queue for 58 minutes on the 18 Aug
    2026 run, protecting a discount worth under a cent."""
    from serious_shift_pipeline.core import llm

    monkeypatch.setattr(llm, 'call', lambda req: (f'body:{req.custom_id}', {'in': 1}))
    monkeypatch.setattr(llm, 'client',
                        lambda: pytest.fail('the batch API must not be reached'))

    reqs = [llm.Req(user=f'p{n}', custom_id=f'kt-{n}')
            for n in range(llm.SYNC_AT_OR_BELOW)]
    out = llm.call_batch(reqs)

    assert sorted(out) == sorted(r.custom_id for r in reqs)
    assert out['kt-0'][0] == 'body:kt-0'
    # NOT marked batch: these are billed at full price and the report must say so.
    assert not out['kt-0'][1].get('batch')


def test_one_failure_does_not_lose_the_others():
    """Same contract as the batch path — callers filter on a None body."""
    from serious_shift_pipeline.core import llm

    def flaky(req):
        if req.custom_id == 'kt-1':
            raise RuntimeError('overloaded')
        return ('body', {'in': 1})

    original = llm.call
    llm.call = flaky
    try:
        out = llm.call_batch([llm.Req(user='p', custom_id=f'kt-{n}') for n in range(2)])
    finally:
        llm.call = original

    assert out['kt-0'][0] == 'body'
    assert out['kt-1'][0] is None
    assert out['kt-1'][1]['error'] == 'RuntimeError'


def test_a_real_batch_still_goes_to_the_batch_api():
    """The discount is the whole point above the threshold."""
    from serious_shift_pipeline.core import llm

    assert llm.SYNC_AT_OR_BELOW < 44, 'a full map must never bypass the discount'
