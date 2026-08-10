"""The content gates: every defect class the 2026-08-10 audit found in the
published map, encoded so that class of document can never promote again.

Population-level gates (kt_count, velocity_distribution, stat_coverage,
crutch_frequency, evidence_reuse) engage only at FULL_MAP_MIN_SHIFTS, so the
small structural fixtures elsewhere stay quiet; `full_map()` here scales the
shared fixture up to a realistic 7-per-domain document.
"""
from __future__ import annotations

import copy

from serious_shift_pipeline.mapgen import validation
from serious_shift_pipeline.mapgen.validation import validate_map

from test_map_validation import CONTRACT, DOMAINS, valid_map


def codes(document) -> set[str]:
    return {issue.code for issue in validate_map(document, CONTRACT)}


def _issues(document, code):
    return [i for i in validate_map(document, CONTRACT) if i.code == code]


def _hero(value, text, url='https://example.com/1'):
    return {'value': value, 'text': text, 'thinker': 'T', 'source': 'T, 2026',
            'year': '2026', 'url': url}


def full_map() -> dict:
    """valid_map() scaled to 7 shifts per domain with velocities spread and
    on-topic heroes — a document every gate should wave through."""
    document = valid_map()
    base_shifts = {s['domain_id']: s for s in document['key_trends']}
    base_subs: dict = {}
    for sub in document['sub_trends']:
        base_subs.setdefault(sub['key_trend_id'], []).append(sub)

    shifts, subs, claims = [], [], list(document['claims'])
    velocities = ['breakout', 'accelerating', 'rising', 'steady',
                  'accelerating', 'rising', 'steady']
    n = 0
    for domain_id in DOMAINS:
        for copy_index in range(7):
            n += 1
            shift = copy.deepcopy(base_shifts[domain_id])
            children = copy.deepcopy(base_subs[shift['id']])
            shift['id'] = f'kt-{n}'
            shift['slug'] = f'shift-{n}'
            shift['name'] = f'Distinct Story {n}'
            shift['subtitle'] = f'How pattern number {n} moves markets'
            shift['velocity'] = velocities[copy_index]
            shift['sub_trend_ids'] = []
            # Give every page a unique claim set and centerpiece so no gate
            # sees accidental repetition.
            for sub_index, sub in enumerate(children):
                sub_claims = [n * 1000 + sub_index * 2 + 1, n * 1000 + sub_index * 2 + 2]
                claims.extend({'id': f'c_{cid}', 'text': f'Evidence {cid}',
                               'source_url': f'https://example.com/{cid}'}
                              for cid in sub_claims)
                sub['id'] = f'st-{n}-{sub_index}'
                sub['key_trend_id'] = shift['id']
                sub['slug'] = f"{shift['slug']}/sub-{n}-{sub_index}"
                sub['name'] = f'Sub {n}-{sub_index}'
                sub['claim_ids'] = [f'c_{cid}' for cid in sub_claims]
                for module in sub['modules']:
                    if module['type'] == 'peel_tabs':
                        module['data']['evidence_ids'] = sub_claims
                    if module['type'] == 'lede':
                        module['data']['text'] = f'Story {n} sub {sub_index} lede.'
                shift['sub_trend_ids'].append(sub['id'])
                subs.append(sub)
            for module in shift['modules']:
                if module['type'] == 'peel_tabs':
                    module['data']['evidence_ids'] = [n * 1000 + 1, n * 1000 + 2]
                if module['type'] == 'dek':
                    module['data']['text'] = f'Why story {n} lands now.'
            # On-topic hero: shares "story"/"pattern" vocabulary with the name,
            # sourced from the shift's own subtree.
            shift['hero_stat'] = _hero(
                f'{40 + n}% story adoption', f'Pattern {n} story adoption measured',
                url=f'https://example.com/{n * 1000 + 1}')
            shift['modules'].insert(3, {'type': 'stat_band', 'data': {
                'value': f'{40 + n}%', 'text': f'Pattern {n} story adoption measured',
                'source': 'T, 2026', 'url': f'https://example.com/{n * 1000 + 1}'}})
            shifts.append(shift)
    by_domain: dict = {}
    for shift in shifts:
        by_domain.setdefault(shift['domain_id'], []).append(shift['id'])
    domains = [{'id': d, 'name': d.title(), 'key_trend_ids': by_domain[d]}
               for d in DOMAINS]
    return {'updated': '2026-08-10', 'domains': domains, 'key_trends': shifts,
            'sub_trends': subs, 'claims': claims, 'synthesis_insights': []}


def test_the_full_fixture_is_clean():
    assert codes(full_map()) == set()


# ── hero stats ────────────────────────────────────────────────────────────────

def test_duplicate_hero_claim_is_rejected():
    document = full_map()
    document['key_trends'][1]['hero_stat'] = dict(document['key_trends'][0]['hero_stat'])
    assert 'duplicate_hero_claim' in codes(document)


def test_off_topic_hero_is_rejected():
    document = full_map()
    shift = document['key_trends'][0]
    shift['hero_stat'] = _hero('ChatGPT mentioned suicide 6x more frequently',
                               'A teen suicide lawsuit revealed chatbot transcripts',
                               url=shift['hero_stat']['url'])
    assert 'hero_topicality' in codes(document)


def test_hero_from_outside_the_subtree_is_rejected():
    document = full_map()
    shift = document['key_trends'][0]
    shift['hero_stat'] = dict(shift['hero_stat'], url='https://elsewhere.com/other')
    assert 'hero_topicality' in codes(document)


def test_stat_coverage_floor():
    document = full_map()
    for shift in document['key_trends'][: int(len(document['key_trends']) * 0.5)]:
        shift['hero_stat'] = None
        shift['modules'] = [m for m in shift['modules'] if m['type'] != 'stat_band']
    assert 'stat_coverage' in codes(document)


# ── prose hygiene ─────────────────────────────────────────────────────────────

def test_ellipsis_truncation_is_rejected():
    document = full_map()
    document['key_trends'][0]['modules'][0]['data']['text'] = 'The shift is about…'
    assert 'ellipsis_truncation' in codes(document)


def test_quotes_and_attributions_may_carry_ellipses():
    document = full_map()
    for module in document['key_trends'][0]['modules']:
        if module['type'] == 'stat_band':
            module['data']['source'] = 'A Very Long Newsletter Title That Was…'
        if module['type'] == 'tension_band':
            module['data']['quote'] = 'I keep wondering where this goes…'
    assert 'ellipsis_truncation' not in codes(document)


def test_meta_language_is_rejected():
    document = full_map()
    document['sub_trends'][0]['modules'][0]['data']['text'] = (
        'The two allowed evidence records for this sub-trend cover positioning.')
    assert 'meta_language' in codes(document)


def test_industries_filler_is_rejected_but_empty_is_legal():
    document = full_map()
    for module in document['key_trends'][0]['modules']:
        if module['type'] == 'industries':
            module['data']['items'][0]['text'] = 'Peripheral to this shift; residual stake only.'
            module['data']['items'][1]['text'] = ''
    issues = _issues(document, 'industries_filler')
    assert len(issues) == 1
    assert 'items[0]' in issues[0].path


def test_dek_may_not_recycle_the_subtitle():
    document = full_map()
    shift = document['key_trends'][0]
    for module in shift['modules']:
        if module['type'] == 'dek':
            module['data']['text'] = shift['subtitle']
    assert 'dek_recycles_subtitle' in codes(document)


# ── population-level gates ────────────────────────────────────────────────────

def test_kt_count_range_is_enforced():
    document = full_map()
    extra = copy.deepcopy(document['key_trends'][0])
    dropped = document['key_trends'][-1]
    document['key_trends'] = [s for s in document['key_trends'] if s is not dropped]
    for _ in range(3):  # push one domain over MAX
        clone = copy.deepcopy(extra)
        clone['id'] = f"kt-x{_}"
        clone['slug'] = f"shift-x{_}"
        clone['name'] = f"Extra Story {_}"
        clone['hero_stat'] = None
        clone['modules'] = [m for m in clone['modules'] if m['type'] != 'stat_band']
        clone['sub_trend_ids'] = []
        document['key_trends'].append(clone)
    assert 'kt_count' in codes(document)


def test_single_bucket_velocity_is_rejected():
    document = full_map()
    for shift in document['key_trends']:
        shift['velocity'] = 'accelerating'
    assert 'velocity_distribution' in codes(document)


def test_crutch_entity_beyond_the_page_limit_is_rejected():
    document = full_map()
    for shift in document['key_trends'][:6]:
        for module in shift['modules']:
            if module['type'] == 'dek':
                module['data']['text'] = 'Adam Raine went looking and the map answered.'
    issues = _issues(document, 'crutch_frequency')
    # 6 pages carrying one entity, allowance 4 → the 2 over the limit flag.
    assert len(issues) == 2
    assert 'adam raine' in issues[0].message


def test_evidence_reuse_across_three_subshifts_is_rejected():
    document = full_map()
    shared = document['sub_trends'][0]['claim_ids'][0]
    for sub in document['sub_trends'][1:3]:
        sub['claim_ids'] = [shared] + sub['claim_ids'][1:]
    assert 'evidence_reuse' in codes(document)


def test_small_structural_fixtures_do_not_trip_population_gates():
    assert codes(valid_map()) & {
        'kt_count', 'velocity_distribution', 'stat_coverage',
        'crutch_frequency', 'evidence_reuse'} == set()


# ── repair routing ────────────────────────────────────────────────────────────

def test_hero_issue_triggers_a_free_phase8_rerun(monkeypatch):
    from serious_shift_pipeline.mapgen import cli
    ran = []
    monkeypatch.setattr(cli, 'phase8_hero_stats', lambda conn: ran.append(True))
    monkeypatch.setattr(cli, 'phase4b_editorial',
                        lambda conn, key, claims, kts: ran.append('editorial'))
    issue = validation.ValidationIssue(
        'duplicate_hero_claim', 'key_trends[0].hero_stat', 'dup', True)
    document = full_map()
    changed = cli._targeted_repair_once(
        conn=None, api_key='k', out=document, issues=[issue],
        domain_claims={}, domain_kts={})
    assert ran[0] is True          # phase 8 ran first, before any paid regen
    assert changed is True
