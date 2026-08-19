"""Editorial retries must carry feedback naming exactly what failed.

Re-sending the identical prompt converged on the identical mistake; the
2026-08-09 map shipped 101 clamped mid-sentence strings because overruns were
never named to the model, only trimmed after the fact.
"""

from serious_shift_pipeline.mapgen.phases import editorial as ed


def test_overlong_fields_are_named_with_their_caps():
    body = {
        'dek': 'word ' * 50,                       # cap 45
        'why_now': 'fine.',
        'human_needs': {'unlocked': 'ok', 'threatened': 'word ' * 50},  # cap 45
        'industries': [{'name': 'Retail & Commerce', 'text': 'word ' * 45}],  # cap 40
        'signals': ['short', 'word ' * 40],        # cap 35
    }
    over = ed._overlong_fields(body)
    joined = ' | '.join(over)
    assert 'dek (50 words, max 45)' in joined
    assert 'human_needs.threatened' in joined
    assert 'Retail & Commerce' in joined
    assert 'signals[2]' in joined
    assert not any('why_now' in entry for entry in over)


def test_feedback_block_names_missing_and_overlong():
    block = ed._feedback_block(['pull_quote'], ['dek (50 words, max 45)'])
    assert 'MISSING or empty: pull_quote' in block
    assert 'OVER THE WORD CAP: dek' in block


def test_retry_prompt_carries_the_feedback(monkeypatch):
    calls = []

    def fake_generate_json(items, prompt_of, default=dict, describe=None):
        calls.append([prompt_of(item) for item in items])
        if len(calls) == 1:
            return [{'a': ''}]          # first pass fails
        return [{'a': 'filled'}]        # retry succeeds

    monkeypatch.setattr(ed, 'generate_json', fake_generate_json)
    results = ed._generate_until_complete(
        ['item-1'],
        lambda item: f'PROMPT for {item}',
        lambda item, r: bool(isinstance(r, dict) and r.get('a')),
        describe=lambda item: str(item), label='test',
        diagnose=lambda item, r: ['a'],
    )
    assert results == [{'a': 'filled'}]
    assert 'PROMPT for item-1' in calls[0][0]
    assert 'YOUR PREVIOUS RESPONSE WAS REJECTED' in calls[1][0]
    assert 'MISSING or empty: a' in calls[1][0]


def test_an_echoing_body_is_reasked_with_the_field_named(monkeypatch):
    """kt_editorial has forbidden restating the hero since contract v7 and is
    ignored on 12 of the live map's 44 shift pages. Naming the offending field
    is what makes attempt two different from attempt one."""
    calls = []
    echoing = {'a': 'ok', 'dek': 'Amazon converts at 3.5x the rate of search'}
    fixed = {'a': 'ok', 'dek': 'The agent displaced the brand website'}

    def fake_generate_json(items, prompt_of, default=dict, describe=None):
        calls.append([prompt_of(item) for item in items])
        return [echoing] if len(calls) == 1 else [fixed]

    monkeypatch.setattr(ed, 'generate_json', fake_generate_json)
    results = ed._generate_until_complete(
        ['item-1'], lambda item: 'P',
        lambda item, r: bool(isinstance(r, dict) and r.get('a')),
        describe=lambda item: str(item), label='test',
        echoes_of=lambda item, r: ed._echoing_fields('3.5x conversion rate', r),
    )
    assert results == [fixed]
    assert 'REPEATS THE HEADLINE STATISTIC: dek (restates 3.5x)' in calls[1][0]


def test_echoing_fields_share_the_gates_definition_of_a_figure():
    body = {'dek': 'Half of labs — 72 percent by revenue — now gate access',
            'why_now': 'Access rules hardened in 2026',
            'signals': ['A lab shipped a 72% gated tier this quarter']}
    named = ed._echoing_fields('72% of frontier labs', body)
    assert any(entry.startswith('dek') for entry in named)
    assert any(entry.startswith('signals[1]') for entry in named)
    # bare years are dating, not statistics
    assert not ed._echoing_fields('the 2026 cohort', body)


def test_a_verified_stat_ceding_to_page_copy_returns_none():
    """A sub-shift stat whose figure sits in the page's own name/subtitle/body
    is refused at attach time — the stat is optional, the copy is not."""
    claims = [{'id': 7, 'statistic': '660,000 H100-equivalents smuggled',
               'has_statistic': True, 'claim_text': 'smuggling estimate',
               'thinker': 'Epoch AI', 'source_title': 't',
               'date_published': '2026-06-01', 'source_url': 'https://e.com/x'}]
    editorial = {'stat': {'claim_id': 7}}
    echoing_page = [('subtitle', 'An estimated 660,000 units reached China')]
    clean_page = [('subtitle', 'Export controls are failing at the border')]
    assert ed._verified_stat(editorial, claims, page_texts=echoing_page) is None
    kept = ed._verified_stat(editorial, claims, page_texts=clean_page)
    assert kept is not None and kept['value'] == '660,000'


def test_a_complete_body_is_never_replaced_by_a_worse_retry(monkeypatch):
    """Overlong-but-complete keeps its body unless the retry is no longer."""
    complete_but_long = {'a': 'word ' * 60}

    def fake_generate_json(items, prompt_of, default=dict, describe=None):
        if not fake_generate_json.called:
            fake_generate_json.called = True
            return [complete_but_long]
        return [{'a': ''}]              # retry comes back broken
    fake_generate_json.called = False

    monkeypatch.setattr(ed, 'generate_json', fake_generate_json)
    monkeypatch.setattr(ed, '_overlong_fields',
                        lambda r: ['a (60 words, max 45)'] if r.get('a') else [])
    results = ed._generate_until_complete(
        ['item-1'], lambda item: 'P',
        lambda item, r: bool(isinstance(r, dict) and r.get('a')),
        describe=lambda item: str(item), label='test',
    )
    assert results == [complete_but_long]
