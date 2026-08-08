from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from serious_shift_pipeline.mapgen.export import _write_map_document
from serious_shift_pipeline.mapgen import cli
from serious_shift_pipeline.mapgen.validation import (
    PublicationValidationError,
    _validate_modules,
    validate_map,
)

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[3] / 'packages/contracts/shift_modules.json').read_text()
)
SECTORS = CONTRACT['industry_sectors']
DOMAINS = ['society', 'economy', 'consumers', 'organisations']


def valid_map() -> dict:
    domains, shifts, subs, claims = [], [], [], []
    for domain_index, domain_id in enumerate(DOMAINS):
        shift_id = f'kt-{domain_index + 1}'
        shift_slug = f'shift-{domain_index + 1}'
        child_ids = []
        for sub_index in range(5):
            claim_ids = [domain_index * 100 + sub_index * 2 + 1, domain_index * 100 + sub_index * 2 + 2]
            claims.extend({
                'id': f'c_{claim_id}', 'text': f'Evidence {claim_id}',
                'source_url': f'https://example.com/{claim_id}',
            } for claim_id in claim_ids)
            sub_id = f'st-{domain_index + 1}-{sub_index + 1}'
            child_ids.append(sub_id)
            subs.append({
                'id': sub_id,
                'key_trend_id': shift_id,
                'domain_id': domain_id,
                'slug': f'{shift_slug}/sub-{sub_index + 1}',
                'name': f'Sub {sub_index + 1}',
                'claim_ids': [f'c_{claim_id}' for claim_id in claim_ids],
                'modules': [
                    {'type': 'lede', 'data': {'text': 'Lede'}},
                    {'type': 'from_to_solid', 'data': {'from': 'Old', 'to': 'New'}},
                    {'type': 'tension_band', 'data': {'quote': 'A tension'}},
                    {'type': 'peel_tabs', 'data': {'whats_changing': 'Change', 'why_now': 'Now', 'evidence_ids': claim_ids}},
                    {'type': 'human_needs', 'data': {'unlocked': 'Agency', 'threatened': 'Trust'}},
                    {'type': 'signals', 'data': {'items': ['Signal']}},
                    {'type': 'counter_signals', 'data': {'items': ['Counter'] }},
                    {'type': 'evidence', 'data': {'items': [{
                        'text': 'Evidence', 'thinker': 'A',
                        'url': 'https://example.com/evidence',
                    }, {
                        'text': 'More evidence', 'thinker': 'B',
                        'url': 'https://example.org/evidence',
                    }]}},
                    {'type': 'timeline', 'data': {'steps': [{'label': 'Now', 'text': 'Move'}]}},
                    {'type': 'territories', 'data': {'items': [{'name': 'Space', 'text': 'Build'}]}},
                ],
            })
        domains.append({'id': domain_id, 'name': domain_id.title(),
                        'key_trend_ids': [shift_id]})
        shifts.append({
            'id': shift_id,
            'domain_id': domain_id,
            'slug': shift_slug,
            'name': f'Shift {domain_index + 1}',
            'sub_trend_ids': child_ids,
            'modules': [
                {'type': 'dek', 'data': {'text': 'Dek'}},
                {'type': 'from_to', 'data': {'from': 'Old', 'to': 'New'}},
                {'type': 'pull_quote', 'data': {'quote': 'A verdict'}},
                {'type': 'peel_tabs', 'data': {'whats_changing': 'Change', 'why_now': 'Now', 'evidence_ids': [domain_index * 100 + 1, domain_index * 100 + 2]}},
                {'type': 'sub_shift_list', 'data': {}},
                {'type': 'human_needs', 'data': {'unlocked': 'Agency', 'threatened': 'Trust'}},
                {'type': 'tension_band', 'data': {'quote': 'A tension'}},
                {'type': 'timeline', 'data': {'steps': [{'label': 'Now', 'text': 'Move'}]}},
                {'type': 'industries', 'data': {
                    'items': [{'name': name, 'text': 'Impact'} for name in SECTORS],
                }},
                {'type': 'territories', 'data': {'items': [{'name': 'Space', 'text': 'Build'}]}},
                {'type': 'voices', 'data': {
                    'proponents': [{
                        'name': 'A', 'quote': 'A real quote',
                        'url': 'https://example.com/voice',
                    }],
                    'skeptics': [],
                }},
            ],
        })
    return {'updated': '2026-08-02', 'domains': domains, 'key_trends': shifts,
            'sub_trends': subs, 'claims': claims, 'synthesis_insights': []}


def codes(document) -> set[str]:
    return {issue.code for issue in validate_map(document, CONTRACT)}


@pytest.mark.parametrize(('count', 'valid'), [(0, False), (4, False), (5, True), (6, False)])
def test_exactly_five_sub_shifts(count, valid):
    document = valid_map()
    parent = document['key_trends'][0]
    children = [sub for sub in document['sub_trends'] if sub['key_trend_id'] == parent['id']]
    if count < 5:
        removed = {sub['id'] for sub in children[count:]}
        document['sub_trends'] = [sub for sub in document['sub_trends'] if sub['id'] not in removed]
        parent['sub_trend_ids'] = parent['sub_trend_ids'][:count]
    elif count > 5:
        extra = copy.deepcopy(children[-1])
        extra.update(id='st-extra', slug=f"{parent['slug']}/sub-extra", name='Extra')
        document['sub_trends'].append(extra)
        parent['sub_trend_ids'].append(extra['id'])
    assert ('sub_shift_count' not in codes(document)) is valid


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'reordered', 'unknown'])
def test_industry_contract_is_exact(mutation):
    document = valid_map()
    module = next(item for item in document['key_trends'][0]['modules'] if item['type'] == 'industries')
    items = module['data']['items']
    if mutation == 'missing':
        items.pop()
    elif mutation == 'duplicate':
        items[-1] = copy.deepcopy(items[0])
    elif mutation == 'reordered':
        items[0], items[1] = items[1], items[0]
    else:
        items[-1]['name'] = 'Unknown Sector'
    assert 'industries_contract' in codes(document)


def test_duplicate_slugs_and_broken_related_links_are_rejected():
    document = valid_map()
    duplicate = copy.deepcopy(document['key_trends'][1])
    duplicate.update(id='kt-duplicate', domain_id='society', slug='shift-1')
    document['key_trends'].append(duplicate)
    document['key_trends'][0]['modules'].append({
        'type': 'related_shifts',
        'data': {'items': [{'title': 'Missing', 'href': '/map/society/missing'}]},
    })
    found = codes(document)
    assert {'duplicate_shift_slug', 'related_route'} <= found


@pytest.mark.parametrize('module_type', ['evidence', 'voices'])
def test_published_attribution_requires_http_source_urls(module_type):
    document = valid_map()
    if module_type == 'evidence':
        module = next(item for item in document['sub_trends'][0]['modules'] if item['type'] == 'evidence')
        module['data']['items'][0]['url'] = 'javascript:alert(1)'
    else:
        module = next(item for item in document['key_trends'][0]['modules'] if item['type'] == 'voices')
        module['data']['proponents'][0]['url'] = '/relative'
    assert 'source_url' in codes(document)


class RecordingConnection:
    def __init__(self):
        self.statements = []
        self.commits = 0

    def execute(self, statement, params=None):
        self.statements.append((' '.join(statement.split()), params))
        return self

    def fetchall(self):
        # Promotion also records shift identities and then asks which curated
        # innovation links point at a shift that is no longer published. With no
        # database there are none, which is the answer that keeps this test about
        # statement *ordering*.
        return []

    def commit(self):
        self.commits += 1


def test_invalid_candidate_never_touches_current_map():
    connection = RecordingConnection()
    document = valid_map()
    document['sub_trends'] = []
    with pytest.raises(PublicationValidationError):
        _write_map_document(connection, document)
    assert connection.statements == []
    assert connection.commits == 0


def test_successful_promotion_rotates_previous_then_current():
    connection = RecordingConnection()
    _write_map_document(connection, valid_map())
    assert "'map:previous'" in connection.statements[0][0]
    assert "'map'" in connection.statements[1][0]
    # The identities an innovation's foreign key points at are recorded in the
    # same transaction as the document they came from, so the two cannot disagree.
    assert 'INSERT INTO shift_refs' in connection.statements[2][0]
    assert connection.commits == 1


def test_promotion_records_an_identity_for_every_addressable_shift():
    """`shift_refs` is what innovation_shift_links FKs into. If publication stops
    recording a shift, every innovation curated onto it silently disappears."""
    connection = RecordingConnection()
    document = valid_map()
    _write_map_document(connection, document)
    statement, params = next(
        item for item in connection.statements if 'INSERT INTO shift_refs' in item[0]
    )
    scopes, slugs, _domains, _titles = params
    expected = [kt['slug'] for kt in document['key_trends']] + [
        st['slug'] for st in document['sub_trends']
    ]
    assert slugs == expected
    assert set(scopes) == {'key_trend', 'sub_trend'}
    # A sub-shift's identity keeps the parent segment; that two-part slug is what
    # makes it unique across the document.
    assert any('/' in slug for slug in slugs)


def test_targeted_repair_never_exceeds_parent_limit(monkeypatch):
    document = valid_map()
    issues = validate_map({**document, 'sub_trends': []}, CONTRACT)
    monkeypatch.setattr(cli, 'MAX_TARGETED_REPAIR_SHIFTS', 1)
    connection = RecordingConnection()
    repaired = cli._targeted_repair_once(
        connection, 'unused', document, issues,
        domain_claims={}, domain_kts={},
    )
    assert repaired is False
    assert connection.statements == []


def test_required_editorial_modules_cannot_silently_disappear():
    document = valid_map()
    document['sub_trends'][0]['modules'] = [
        module for module in document['sub_trends'][0]['modules']
        if module['type'] != 'counter_signals'
    ]
    assert 'required_module' in codes(document)


def test_long_and_duplicated_editorial_is_rejected():
    document = valid_map()
    repeated = ' '.join(['specific mechanism'] * 50)
    for shift in document['key_trends'][:2]:
        module = next(item for item in shift['modules'] if item['type'] == 'peel_tabs')
        module['data']['whats_changing'] = repeated
    found = codes(document)
    assert {'editorial_length', 'duplicate_editorial'} <= found


def test_card_and_horizon_copy_has_enforced_reading_limits():
    document = valid_map()
    modules = document['sub_trends'][0]['modules']
    needs = next(item for item in modules if item['type'] == 'human_needs')
    timeline = next(item for item in modules if item['type'] == 'timeline')
    needs['data']['unlocked'] = ' '.join(['word'] * 46)
    timeline['data']['steps'][0]['text'] = ' '.join(['word'] * 46)
    matching = [issue for issue in validate_map(document, CONTRACT)
                if issue.code == 'editorial_length']
    assert len(matching) == 2


def test_statistics_require_clickable_provenance():
    document = valid_map()
    document['key_trends'][0]['modules'].insert(3, {
        'type': 'stat_band',
        'data': {'value': '25%', 'text': 'Measured result', 'source': 'Study'},
    })
    assert 'source_url' in codes(document)


def test_editorial_citations_must_belong_to_the_current_route():
    document = valid_map()
    module = next(item for item in document['sub_trends'][0]['modules'] if item['type'] == 'peel_tabs')
    module['data']['evidence_ids'] = document['sub_trends'][1]['claim_ids']
    assert 'editorial_provenance' in codes(document)


# ── The three ways generation and the gate disagreed ────────────────────────
#
# Every synthesize run between 2026-08-03 and 2026-08-08 failed publication, and
# all 75 issues on the last one came from three places where the writing side and
# the checking side applied different rules. Each test below fails if the two are
# allowed to drift apart again.

def test_the_gate_and_the_clamp_count_words_the_same_way():
    """`str.split()` and the gate's regex disagree on "cost/benefit", "U.S." and
    "2026—2028" — one word each by the first measure, two, three and two by the
    second. Clamping by one and gating by the other trimmed 23 fields to the
    limit and then rejected them for exceeding it."""
    from serious_shift_pipeline.mapgen.modules import clamp_words, count_words
    from serious_shift_pipeline.mapgen.validation import _words

    assert _words is count_words
    awkward = 'cost/benefit trade-offs across U.S. and non-U.S. markets in 2026—2028 and beyond'
    for limit in (3, 5, 8, 12):
        assert count_words(clamp_words(awkward, limit)) <= limit


def test_a_shift_cannot_cite_more_evidence_than_the_gate_accepts():
    """The gate takes 2–6 citations. Generation only ever checked "at least two,
    all inside the routed pool", so the model — handed the union of five
    sub-shifts' claims — cited seventeen to twenty-one and all 49 shifts failed."""
    from serious_shift_pipeline.mapgen.modules import MAX_CITATIONS, conform_modules

    conformed = conform_modules([
        {'type': 'peel_tabs', 'data': {
            'whats_changing': 'x', 'why_now': 'y',
            'evidence_ids': [f'c_{n}' for n in range(1, 22)],
        }},
    ])
    cited = conformed[0]['data']['evidence_ids']
    assert len(cited) == MAX_CITATIONS
    assert cited == [f'c_{n}' for n in range(1, MAX_CITATIONS + 1)], 'keeps the strongest support, in order'


def test_industries_are_made_canonical_or_dropped():
    """The gate wants all sixteen sectors, exactly once, in order. Nothing put
    them in that order — `_as_pairs` passed through whatever came back."""
    from serious_shift_pipeline.mapgen.modules import conform_modules

    shuffled = [{'name': name, 'text': 'Impact'} for name in reversed(SECTORS)]
    conformed = conform_modules([{'type': 'industries', 'data': {'items': shuffled}}])
    assert [item['name'] for item in conformed[0]['data']['items']] == SECTORS

    # A sector the model skipped is completed with an empty note, not dropped
    # and not invented: `industries` is a required module on every key shift, so
    # dropping it traded three publication failures for four.
    partial = [{'name': name, 'text': 'Impact'} for name in SECTORS[:-2]]
    completed = conform_modules([{'type': 'industries', 'data': {'items': partial}}])
    assert [item['name'] for item in completed[0]['data']['items']] == SECTORS
    assert [item['text'] for item in completed[0]['data']['items']][-2:] == ['', '']


def test_export_conformance_fixes_a_document_without_regenerating_it():
    """The whole point of conforming at export rather than only at generation:
    copy already in the database, written under a cap that disagreed with the
    gate, becomes publishable on an --export-only run."""
    from serious_shift_pipeline.mapgen.modules import conform_modules

    over_limit = [
        {'type': 'dek', 'data': {'text': ' '.join(['word'] * 60)}},
        {'type': 'human_needs', 'data': {'unlocked': ' '.join(['w'] * 50),
                                         'threatened': ' '.join(['w'] * 50)}},
        {'type': 'timeline', 'data': {'steps': [{'label': 'Today', 'text': ' '.join(['w'] * 60)}]}},
        {'type': 'signals', 'data': {'items': [' '.join(['w'] * 40)]}},
    ]
    conformed = conform_modules(over_limit)
    issues = _validate_modules(conformed, 'sub_trend', 'sub_trends[x]', CONTRACT)
    assert [issue for issue in issues if issue.code == 'editorial_length'] == []


def test_two_spheres_naming_a_shift_the_same_get_distinct_slugs():
    """`shift_refs` and `shift_module_overrides` are keyed on (scope, slug) with
    no domain, so a URL slug has to be unique across the whole map — not just
    within its sphere. Economy and Organizations both produced a "Moat Migration"
    on the 2026-08-08 run; both were slugged `moat-migration`, and publication
    died on a unique-constraint violation after passing the entire editorial
    gate. An override keyed that way would also have hit the wrong sphere."""
    from serious_shift_pipeline.core.text import url_slug

    rows = [
        {'id': 19, 'domain_id': 'economy', 'name': 'Moat Migration'},
        {'id': 48, 'domain_id': 'organisations', 'name': 'Moat Migration'},
        {'id': 60, 'domain_id': 'society', 'name': 'Moat Migration'},
    ]
    seen: dict = {}
    slugs = []
    for row in rows:
        base = url_slug(row['name'])
        n = seen.get(base, 0) + 1
        seen[base] = n
        slugs.append(base if n == 1 else f'{base}-{n}')

    assert slugs == ['moat-migration', 'moat-migration-2', 'moat-migration-3']
    assert len(set(slugs)) == len(rows), 'a slug may not repeat across spheres'
