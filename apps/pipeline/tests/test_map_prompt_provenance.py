from serious_shift_pipeline.prompts.map_data import fmt_claims_block, prompt_st_editorial


def claim(claim_id: int, title: str) -> dict:
    return {
        'id': claim_id,
        'claim_text': f'Claim {claim_id}',
        'claim_type': 'fact',
        'signal_strength': 'strong_signal',
        'specificity': 4,
        'thinker': 'Researcher',
        'credibility_score': 91,
        'consumer_implication': 'Implication',
        'quote': 'Verbatim words',
        'has_statistic': True,
        'statistic': '25%',
        'source_title': title,
        'date_published': '2026-07-21',
        'source_url': f'https://example.com/{claim_id}',
        'source_type': 'article',
        'source_confidence': 'data_backed',
    }


def test_claim_prompt_keeps_provenance_and_evidence_type_together():
    block = fmt_claims_block([claim(7, 'Primary source')])
    assert '"id":7' in block
    assert '"source_title":"Primary source"' in block
    assert '"source_date":"2026-07-21"' in block
    assert '"source_url":"https://example.com/7"' in block
    assert '"quote":"Verbatim words"' in block
    assert '"source_confidence":"data_backed"' in block


def test_sub_shift_prompt_scopes_each_claim_to_one_named_child():
    subs = [
        {'id': 1, 'name': 'First', 'subtitle': 'First framing'},
        {'id': 2, 'name': 'Second', 'subtitle': 'Second framing'},
    ]
    prompt = prompt_st_editorial(
        'Parent', 'Framing', subs,
        {1: [claim(11, 'First source')], 2: [claim(22, 'Second source')]},
    )
    first = prompt.index('SUB-TREND: First')
    second = prompt.index('SUB-TREND: Second')
    assert prompt.index('https://example.com/11', first, second) > first
    assert prompt.index('https://example.com/22', second) > second


def test_prompts_carry_the_2026_08_19_review_rules():
    """The content review's fixes live in the prompt files; a rewrite that
    drops one of these lines silently reverts the review."""
    from serious_shift_pipeline.prompts._loader import load

    key_trends = load('map/key_trends.txt')
    assert 'ARENA SPREAD' in key_trends
    assert 'Autarky' in key_trends, 'economist-jargon name blacklist'

    sub_trends = load('map/sub_trends.txt')
    assert 'Kaldor' in sub_trends, 'sub-shift names had no jargon blacklist at all'
    assert 'Canary Cohort' in sub_trends, 'the opaque-coinage example'

    st_editorial = load('map/st_editorial.txt')
    assert 'never commentary about the evidence' in st_editorial, \
        'counter-signals must be market evidence, not source audits'
    assert 'at most 30 words' not in st_editorial, \
        'prompt caps must match modules.LIST_ITEM_WORD_LIMITS (35)'

    voice = load('voice.txt')
    assert 'plain-English gloss' in voice, 'the plain-language rule'
