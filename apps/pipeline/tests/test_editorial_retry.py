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
