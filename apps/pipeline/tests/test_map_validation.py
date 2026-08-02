from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from serious_shift_pipeline.mapgen.export import _write_map_document
from serious_shift_pipeline.mapgen import cli
from serious_shift_pipeline.mapgen.validation import (
    PublicationValidationError,
    validate_map,
)

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[3] / 'packages/contracts/shift_modules.json').read_text()
)
SECTORS = CONTRACT['industry_sectors']
DOMAINS = ['society', 'economy', 'consumers', 'organisations']


def valid_map() -> dict:
    domains, shifts, subs = [], [], []
    for domain_index, domain_id in enumerate(DOMAINS):
        shift_id = f'kt-{domain_index + 1}'
        shift_slug = f'shift-{domain_index + 1}'
        child_ids = []
        for sub_index in range(5):
            sub_id = f'st-{domain_index + 1}-{sub_index + 1}'
            child_ids.append(sub_id)
            subs.append({
                'id': sub_id,
                'key_trend_id': shift_id,
                'domain_id': domain_id,
                'slug': f'{shift_slug}/sub-{sub_index + 1}',
                'name': f'Sub {sub_index + 1}',
                'modules': [
                    {'type': 'lede', 'data': {'text': 'Lede'}},
                    {'type': 'evidence', 'data': {'items': [{
                        'text': 'Evidence', 'thinker': 'A',
                        'url': 'https://example.com/evidence',
                    }]}},
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
                {'type': 'industries', 'data': {
                    'items': [{'name': name, 'text': 'Impact'} for name in SECTORS],
                }},
                {'type': 'voices', 'data': {
                    'proponents': [{
                        'name': 'A', 'quote': 'A real quote',
                        'url': 'https://example.com/voice',
                    }],
                    'skeptics': [],
                }},
                {'type': 'sub_shift_list', 'data': {}},
            ],
        })
    return {'updated': '2026-08-02', 'domains': domains, 'key_trends': shifts,
            'sub_trends': subs, 'synthesis_insights': []}


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
    items = document['key_trends'][0]['modules'][1]['data']['items']
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
        document['sub_trends'][0]['modules'][1]['data']['items'][0]['url'] = 'javascript:alert(1)'
    else:
        document['key_trends'][0]['modules'][2]['data']['proponents'][0]['url'] = '/relative'
    assert 'source_url' in codes(document)


class RecordingConnection:
    def __init__(self):
        self.statements = []
        self.commits = 0

    def execute(self, statement, params=None):
        self.statements.append((' '.join(statement.split()), params))
        return self

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
    assert connection.commits == 1


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
