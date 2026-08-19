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
DOMAINS = ['society', 'economy', 'consumers', 'organizations']


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
                # Unique across the WHOLE document, not just beneath the parent.
                # These used to be sub-1..sub-5 under every shift, which is
                # exactly the shape that put six "Provenance Premium" pages and
                # seven "Governance Gap" pages on the live site.
                'slug': f'{shift_slug}/sub-{domain_index + 1}-{sub_index + 1}',
                'name': f'Sub {domain_index + 1}-{sub_index + 1}',
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
                # Last, not after peel_tabs — the 12 Aug 2026 review's placement.
                {'type': 'sub_shift_list', 'data': {}},
            ],
        })
    return {'updated': '2026-08-02', 'domains': domains, 'key_trends': shifts,
            'sub_trends': subs, 'claims': claims, 'synthesis_insights': []}


def codes(document) -> set[str]:
    return {issue.code for issue in validate_map(document, CONTRACT)}


@pytest.mark.parametrize(('count', 'valid'),
                         [(0, False), (2, False), (3, True), (4, True), (5, True), (6, False)])
def test_sub_shift_count_range(count, valid):
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

    # psycopg's `connection.execute()` hands back a cursor, and promotion reads
    # `rowcount` off the reconciliation DELETE to report how many stale
    # identities it pruned. Zero is the honest answer with no database behind
    # this, and it keeps the test about statement *ordering*.
    rowcount = 0

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
    monkeypatch.setattr(cli, 'MIN_TARGETED_REPAIR_SHIFTS', 1)
    monkeypatch.setattr(cli, 'REPAIR_SHIFT_SHARE', 0.0)
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


def test_a_name_used_twice_anywhere_fails_publication():
    """The crawl of 2026-08-09 found 22 names spread over 58 pages: "Provenance
    Premium" was a key shift AND a sub-shift under six different parents, so
    seven pages carried one name. Nothing rejected it, because the slug checks
    were grouped — shifts by sphere, sub-shifts by parent — so each duplicate
    landed in its own bucket and `_duplicates` never saw a pair.

    Export then HID the collision rather than surfacing it: a second identically
    named key shift is silently disambiguated to `-2`, which is how
    `/organisations/moat-migration-2` reached production."""
    from serious_shift_pipeline.mapgen.validation import validate_map

    def codes(mutate):
        document = valid_map()
        mutate(document)
        return {issue.code for issue in validate_map(document, CONTRACT)}

    # Two key shifts in DIFFERENT spheres sharing a slug.
    def same_shift_slug(document):
        document['key_trends'][1]['slug'] = document['key_trends'][0]['slug']
    assert 'duplicate_shift_slug' in codes(same_shift_slug)

    # Two sub-shifts under DIFFERENT parents sharing a name.
    def same_sub_slug(document):
        first = document['sub_trends'][0]['slug'].rsplit('/', 1)[-1]
        other = next(s for s in document['sub_trends']
                     if s['key_trend_id'] != document['sub_trends'][0]['key_trend_id'])
        other['slug'] = f"{other['slug'].rsplit('/', 1)[0]}/{first}"
    assert 'duplicate_sub_shift_slug' in codes(same_sub_slug)

    # A sub-shift wearing a key shift's name — the "Provenance Premium" shape.
    def sub_shadows_shift(document):
        shift_slug = document['key_trends'][0]['slug']
        sub = document['sub_trends'][-1]
        sub['slug'] = f"{sub['slug'].rsplit('/', 1)[0]}/{shift_slug}"
    assert 'sub_shift_shadows_shift' in codes(sub_shadows_shift)

    # …and the fixture itself is clean, or none of the above proves anything.
    assert validate_map(valid_map(), CONTRACT) == []


def test_copy_must_be_us_spelling_and_free_of_slugs():
    """Neither of these had any gate at all. `voice.txt` says "US spelling only"
    and the prompt files are themselves written in British English two lines
    above the rule; the 2026-08-09 crawl duly found "catalogued" and
    "organisation" in published copy, and `pilot-plateau` used as an adjective
    in three different pages' prose.

    `sub_trends[].description` is the worst of it: seo.rs publishes it verbatim
    as the meta description, and until now nothing validated it."""
    from serious_shift_pipeline.mapgen.validation import validate_map

    def codes(mutate):
        document = valid_map()
        mutate(document)
        return {issue.code for issue in validate_map(document, CONTRACT)}

    def british_description(document):
        document['sub_trends'][0]['description'] = (
            'Firms catalogued their models. The organisation pays for it later.')
    assert 'british_spelling' in codes(british_description)

    def slug_in_prose(document):
        # Three segments — see the note on _SLUGGISH. A two-segment slug cannot
        # be told apart from ordinary hyphenated English.
        document['sub_trends'][1]['slug'] = 'shift-1/labor-displacement-gradient'
        document['sub_trends'][1]['name'] = 'Labor Displacement Gradient'
        document['key_trends'][0]['subtitle'] = (
            'The labor-displacement-gradient firms move first.')
    assert 'slug_in_prose' in codes(slug_in_prose)

    # A two-segment slug in prose is just English and must NOT be flagged:
    # "switching-cost", "vendor-lock" and "fact-flooding" are all real shift
    # names AND ordinary compounds. Flagging them produced 54 false positives
    # on the live map.
    def two_segment_compound(document):
        document['sub_trends'][1]['slug'] = 'shift-1/switching-cost'
        document['sub_trends'][1]['name'] = 'Switching Cost'
        document['key_trends'][0]['subtitle'] = 'A switching-cost problem, in prose.'
    assert 'slug_in_prose' not in codes(two_segment_compound)

    # A thinker's own words keep their own spelling. Americanising a quotation
    # misquotes the person who said it.
    def british_inside_a_quote(document):
        document['key_trends'][0]['modules'].append(
            {'type': 'pull_quote', 'data': {'quote': 'The labour market centre shifted.'}})
    assert 'british_spelling' not in codes(british_inside_a_quote)

    # A capitalised British-looking word is a proper noun and must survive:
    # "Centre for AI Safety" is an organisation's name, not a spelling error.
    def proper_noun(document):
        document['sub_trends'][0]['description'] = (
            'The Centre for AI Safety published it. Labour markets shifted.')
    assert 'british_spelling' not in codes(proper_noun)

    # Correct US English that LOOKS British to a greedy pattern. Running the
    # first version of this over the live map produced 26 hits of which 20 were
    # these — and a gate that rejects correct copy gets switched off.
    def us_lookalikes(document):
        document['sub_trends'][0]['description'] = (
            'Optimism about the organism was realistic. The analyses drove '
            'cancellation of the center program.')
    assert 'british_spelling' not in codes(us_lookalikes)

    # Ordinary hyphenated copy is not a slug.
    def ordinary_hyphens(document):
        document['sub_trends'][0]['description'] = (
            'Entry-level and AI-assisted work diverged. Brands must re-plan.')
    assert 'slug_in_prose' not in codes(ordinary_hyphens)


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
        {'id': 48, 'domain_id': 'organizations', 'name': 'Moat Migration'},
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


def test_a_stat_figure_cannot_be_wider_than_the_band():
    """The band renders its value at ~52–58px in a 349px-wide strip, and the
    value is set not to shrink, so an over-long figure scrolls the whole PAGE
    sideways. "$54.2 million" is 13 characters — inside the old 14-character
    limit — and 353px of Suez One. It broke three published sub-shifts.

    Scale words compress rather than the module being dropped: the number is
    what the reader came for."""
    from serious_shift_pipeline.mapgen.modules import _short_figure, conform_modules

    assert _short_figure('$54.2 million') == '$54.2M'
    assert _short_figure('1.2 billion') == '1.2B'
    assert _short_figure('72%') == '72%'
    assert _short_figure('10,874') == '10,874'
    # No numeral is not a statistic, whatever its length.
    assert _short_figure('multi-hop') is None

    # And the export re-reduces a value already written under the older limit.
    conformed = conform_modules([
        {'type': 'stat_band', 'data': {'value': '$54.2 million', 'text': 'x', 'source': 's',
                                       'url': 'https://example.com/stat'}},
    ])
    assert conformed[0]['data']['value'] == '$54.2M'
    # A band whose value cannot be reduced to a figure is dropped, not shipped.
    assert conform_modules([{'type': 'stat_band',
                             'data': {'value': 'a long phrase',
                                      'url': 'https://example.com/stat'}}]) == []
    # As is a band without clickable provenance (contract v6: url required).
    assert conform_modules([{'type': 'stat_band', 'data': {'value': '72%'}}]) == []


def test_two_key_shifts_may_not_share_a_name():
    """The check `duplicate_shift_slug` could never be. export.py disambiguates
    before the gate runs, so by then the second "Moat Migration" is already
    `moat-migration-2` and looks unique — a machine slug in a published URL that
    nobody chose, and no issue raised anywhere."""
    document = valid_map()
    document['key_trends'][1]['name'] = document['key_trends'][0]['name']
    assert 'duplicate_shift_name' in codes(document)


def test_names_that_slugify_alike_are_one_name():
    """Two names that produce the same URL are one page to a reader, a link and
    every slug-keyed art manifest."""
    document = valid_map()
    document['key_trends'][0]['name'] = 'Proof Premium'
    document['key_trends'][1]['name'] = 'proof  premium'
    assert 'duplicate_shift_name' in codes(document)


def test_two_sub_shifts_may_not_share_a_name():
    document = valid_map()
    document['sub_trends'][1]['name'] = document['sub_trends'][0]['name']
    assert 'duplicate_sub_shift_name' in codes(document)


def test_a_sub_shift_may_not_be_named_after_a_key_shift():
    """Seven pages carried one name on the live site because the key shift had
    it too, and nothing compared the two levels by name."""
    document = valid_map()
    document['sub_trends'][0]['name'] = document['key_trends'][0]['name']
    assert 'sub_shift_shadows_shift_name' in codes(document)


def test_a_clean_map_raises_none_of_the_name_gates():
    assert not ({'duplicate_shift_name', 'duplicate_sub_shift_name',
                 'sub_shift_shadows_shift_name'} & codes(valid_map()))


# ── 2026-08-19 content review: figure echoes, em dashes, AI tells ─────────────


def _with_hero(document, value='72% of consumers switched', subtitle='A subtitle'):
    shift = document['key_trends'][0]
    shift['hero_stat'] = {'value': value, 'text': 'measured by Example Research',
                          'url': 'https://example.com/1'}
    shift['subtitle'] = subtitle
    return shift


def test_a_body_restating_the_fronted_figure_is_repairable():
    document = valid_map()
    shift = _with_hero(document)
    shift['modules'][0]['data']['text'] = 'Fully 72% of consumers now switch.'
    found = [i for i in validate_map(document, CONTRACT) if i.code == 'stat_echo']
    assert found and all(i.repairable for i in found)
    assert found[0].path.startswith('key_trends[0].modules[0]'), 'names the dek module'


def test_a_subtitle_carrying_the_fronted_figure_is_a_hero_problem():
    document = valid_map()
    _with_hero(document, subtitle='After 72 percent of consumers switched, brands noticed.')
    found = [i for i in validate_map(document, CONTRACT)
             if i.code == 'stat_echo_subtitle']
    assert found and all(i.repairable for i in found)
    assert 'stat_echo_subtitle' in cli.HERO_REPAIR_CODES, \
        'the remedy is the free phase-8 re-run, not editorial regen'


def test_indistinct_figures_never_count_as_echoes():
    document = valid_map()
    # bare small integer and a year: coincidence, not repetition
    _with_hero(document, value='30 labs signed in 2026',
               subtitle='All 30 labs signed the 2026 accord')
    assert not {'stat_echo', 'stat_echo_subtitle'} & codes(document)


def test_a_sub_band_echoed_by_its_own_signals_is_flagged():
    document = valid_map()
    sub = document['sub_trends'][0]
    sub['modules'].insert(3, {'type': 'stat_band', 'data': {
        'value': '660,000', 'text': 'smuggled units', 'url': 'https://example.com/2'}})
    sub['modules'][5]['data']['whats_changing'] = 'An estimated 660,000 units moved.'
    found = [i for i in validate_map(document, CONTRACT) if i.code == 'stat_echo']
    assert found and 'sub_trends[0]' in found[0].path


def test_em_dash_in_authored_prose_is_repairable():
    document = valid_map()
    document['key_trends'][0]['modules'][0]['data']['text'] = 'A claim — and a dash.'
    found = [i for i in validate_map(document, CONTRACT) if i.code == 'em_dash']
    assert found and all(i.repairable for i in found)


def test_em_dash_in_quotes_evidence_and_ranges_is_not_flagged():
    document = valid_map()
    # a quoted human's dash is theirs; evidence text is scraped source material
    document['key_trends'][0]['modules'][2]['data']['quote'] = 'Their words — verbatim.'
    document['sub_trends'][0]['modules'][7]['data']['items'][0]['text'] = 'Source — dash.'
    # a bare en dash is a range, not rhetoric
    document['key_trends'][0]['modules'][0]['data']['text'] = 'Adoption grew 1–3 years out.'
    assert 'em_dash' not in codes(document)


def test_ai_tells_are_rejected_in_authored_prose():
    document = valid_map()
    document['key_trends'][0]['modules'][3]['data']['why_now'] = \
        "It's worth noting that brands will delve into this."
    found = [i for i in validate_map(document, CONTRACT) if i.code == 'ai_tell']
    assert found and all(i.repairable for i in found)


def test_counter_signal_meta_catches_methods_audits_only():
    document = valid_map()
    sub = document['sub_trends'][0]
    sub['modules'][6]['data']['items'] = [
        'The sample size is small and self-reported, limiting generalizability.']
    found = [i for i in validate_map(document, CONTRACT)
             if i.code == 'counter_signal_meta']
    assert found and all(i.repairable for i in found)
    # a real market counter-signal citing a study is NOT a methods audit
    sub['modules'][6]['data']['items'] = [
        'MIT reported adoption stalling among enterprise buyers in a peer-reviewed study.']
    assert 'counter_signal_meta' not in codes(document)


def test_name_families_are_advisory_never_blocking():
    from serious_shift_pipeline.mapgen.validation import advisory_issues
    document = valid_map()
    for index, name in enumerate(['Proxy Blindspot', 'Deflation Blind Spot',
                                  'Visibility Blindspot']):
        document['sub_trends'][index]['name'] = name
    advisory = {issue.code for issue in advisory_issues(document)}
    assert 'name_family_repeat' in advisory
    assert 'name_family_repeat' not in codes(document), \
        'the live map violates the cap 9x over; blocking would strand every publish'


def test_skip_valve_unblocks_only_the_named_codes(monkeypatch):
    from serious_shift_pipeline.mapgen.validation import require_valid_map
    document = valid_map()
    document['key_trends'][0]['modules'][0]['data']['text'] = 'A claim — and a dash.'
    with pytest.raises(PublicationValidationError):
        require_valid_map(document, CONTRACT)
    monkeypatch.setenv('SS_SKIP_ISSUE_CODES', 'em_dash')
    require_valid_map(document, CONTRACT)   # must not raise
    monkeypatch.setenv('SS_SKIP_ISSUE_CODES', 'ai_tell')
    with pytest.raises(PublicationValidationError):
        require_valid_map(document, CONTRACT)
