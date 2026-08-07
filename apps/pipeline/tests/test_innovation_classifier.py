"""The innovation→shift scorer.

DB-free, network-free, model-free. Everything the classifier actually decides is
in `core/matching.py`, and these pin the decisions that would be invisible in
production until a card showed up on the wrong page.
"""
from __future__ import annotations

import random

import pytest

from serious_shift_pipeline.core import matching as m


def shift(ref, name, to='', subtitle='', extra='', **kw):
    terms = m.weighted_terms([(name, 4), (subtitle, 3), (to, 2), (extra, 1)])
    return m.ShiftDoc(
        ref=ref, scope=ref.split(':')[0], slug=ref.split(':')[1], name=name,
        terms=terms, to_text=to, raw_lower=f'{name} {subtitle} {to} {extra}'.lower(), **kw
    )


def innovation(title, body='', tags=None, brands=()):
    return m.InnovationDoc(
        id=1,
        terms=m.weighted_terms([(title, 3), (body, 1), (' '.join(brands), 2)]),
        tags=tags or {},
        brand_phrases=[b.lower() for b in brands if ' ' in b],
    )


def no_sector(_):
    return ''


# ── Normalisation ───────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw, want', [
    ('Agents', ['agent']),
    ('verifying', ['verify']),
    ('Groceries', ['grocery']),
    # The domain stoplist: every shift says these, so they carry no signal.
    ('AI and the future of technology', []),
    ('Café', ['cafe']),
    ('a an the of', []),
])
def test_normalize(raw, want):
    assert m.normalize(raw) == want


# ── IDF is what makes this discriminate at all ──────────────────────────────

def test_idf_suppresses_terms_every_shift_shares():
    """Every shift on the site is about the same subject. A term present in all
    of them tells you nothing about which one an innovation belongs to."""
    shifts = [shift(f'key_trend:s{i}', f'Agentic Commerce {i}') for i in range(20)]
    corpus = m.Corpus(shifts)
    assert corpus.idf['agentic'] < 1.1
    assert corpus.idf['commerce'] < 1.1


def test_a_distinctive_term_outranks_a_universal_one():
    shifts = [
        shift('key_trend:wallets', 'Agentic Wallets', to='Software does the shopping'),
        shift('key_trend:erosion', 'Agentic Erosion', to='Reasoning atrophies from disuse'),
    ] + [shift(f'key_trend:f{i}', f'Agentic Filler {i}') for i in range(10)]
    corpus = m.Corpus(shifts)
    ranked = m.score_all(corpus, innovation('An assistant that does your shopping'), no_sector)
    assert ranked[0].ref == 'key_trend:wallets'


# ── The thresholds ──────────────────────────────────────────────────────────

def test_confidence_is_monotonic_and_bounded():
    rng = random.Random(7)
    values = sorted(rng.random() for _ in range(60))
    confs = [m.confidence(v) for v in values]
    assert confs == sorted(confs)
    assert all(0.0 <= c <= 1.0 for c in confs)


def test_scoring_is_deterministic():
    shifts = [shift('key_trend:a', 'Proof Premium', to='Verified human becomes the luxury label')]
    corpus = m.Corpus(shifts)
    inn = innovation('A verification badge for human-made goods')
    first = m.score_all(corpus, inn, no_sector)
    second = m.score_all(corpus, inn, no_sector)
    assert [(s.ref, s.confidence) for s in first] == [(s.ref, s.confidence) for s in second]


def test_topic_overlap_alone_does_not_clear_the_floor():
    """A food brand shipping loyalty software is not evidence of a shift that
    merely mentions food. This is the failure mode the whole design is aimed at:
    a plausible-looking card on the wrong page."""
    shifts = [shift(
        'key_trend:slow', 'Slow Craft',
        to='Handmade production becomes a premium signal in food and drink',
    )]
    corpus = m.Corpus(shifts)
    inn = innovation('Loyalty app rebuild', body='A beverage company shipped a new points program.')
    assert m.score_all(corpus, inn, no_sector)[0].confidence < m.FLOOR


def test_a_textbook_example_clears_accept():
    shifts = [
        shift('key_trend:wallets', 'Agentic Wallets',
              subtitle='Your agent does the shopping',
              to='Brands sell to software with a human sponsor',
              extra='delegated purchasing standing instruction machine readable catalogue'),
        shift('key_trend:proof', 'Proof Premium', to='Verified human becomes the luxury label'),
    ]
    corpus = m.Corpus(shifts)
    inn = innovation(
        'Agent-driven shopping with standing instructions',
        body='A delegated purchasing agent buys on a shopper behalf from a machine readable catalogue.',
    )
    top = m.score_all(corpus, inn, no_sector)[0]
    assert top.ref == 'key_trend:wallets'
    assert top.confidence >= m.ACCEPT


# ── Escalation ──────────────────────────────────────────────────────────────

def scored(*confs, scope='key_trend'):
    return [m.Scored(f'{scope}:s{i}', scope, None, c, 0, 0, 0) for i, c in enumerate(confs)]


def test_a_confident_single_winner_is_not_escalated():
    assert not m.is_ambiguous(scored(0.91, 0.30, 0.20))


def test_a_plausible_but_unconvincing_top_pick_is_escalated():
    assert m.is_ambiguous(scored(0.55, 0.30))


def test_three_candidates_within_the_margin_is_a_tie_not_a_ranking():
    assert m.is_ambiguous(scored(0.80, 0.78, 0.76))
    # Two close and a distant third is still a ranking.
    assert not m.is_ambiguous(scored(0.80, 0.78, 0.40))


def test_a_hopeless_top_pick_is_not_worth_a_model_call():
    assert not m.is_ambiguous(scored(0.20, 0.10))


# ── Link budget and the parent rule ─────────────────────────────────────────

def test_a_sub_shift_link_requires_an_accepted_parent():
    """An innovation must never surface on a child page whose parent page does
    not show it — to a reader that reads as a broken site, not a judgement."""
    picks = m.choose([
        m.Scored('key_trend:parent', 'key_trend', None, 0.90, 0, 0, 0),
        m.Scored('sub_trend:child', 'sub_trend', 'key_trend:parent', 0.88, 0, 0, 0),
        m.Scored('sub_trend:orphan', 'sub_trend', 'key_trend:elsewhere', 0.95, 0, 0, 0),
    ])
    refs = [p.ref for p in picks]
    assert 'sub_trend:child' in refs
    assert 'sub_trend:orphan' not in refs


def test_the_link_budget_is_respected():
    many = [m.Scored(f'key_trend:s{i}', 'key_trend', None, 0.95, 0, 0, 0) for i in range(6)]
    assert len(m.choose(many)) == m.MAX_KEY_LINKS
    assert len(m.choose(many, key_budget=1)) == 1


def test_nothing_below_accept_is_ever_linked():
    assert m.choose([m.Scored('key_trend:a', 'key_trend', None, m.ACCEPT - 0.01, 0, 0, 0)]) == []


# ── Facets ──────────────────────────────────────────────────────────────────

def test_geography_facets_carry_no_weight():
    """Every innovation has a region and a country, and every shift is global.
    Including them added noise to every score and signal to none."""
    assert 'region' not in m.FACET_WEIGHTS
    assert 'country' not in m.FACET_WEIGHTS


def test_a_facet_the_innovation_lacks_does_not_penalise_it():
    """Only facets actually present contribute to the denominator, so a sparsely
    tagged innovation scores 0 on the channel rather than being marked down."""
    corpus = m.Corpus([shift('key_trend:a', 'Anything')])
    bare = innovation('Something', tags={})
    assert m.facet(corpus, bare, corpus.shifts[0], no_sector) == 0.0


def test_a_brand_named_by_the_shift_is_decisive():
    s = shift('key_trend:a', 'Delegated Desire', extra='Acme Retail already does this')
    inn = innovation('A launch', brands=['Acme Retail'])
    assert m.brand(inn, s) == 1.0
    assert m.brand(innovation('A launch', brands=['Other Co']), s) == 0.0


def test_an_untagged_innovation_is_judged_on_what_it_has():
    """Regression: the channel weights used to be divided by a fixed 1.0, so an
    innovation with no tags and no brand could score at most 0.55 raw and never
    cleared ACCEPT however good the text match was."""
    assert m.available_weight(innovation('x')) == pytest.approx(m.W_LEX)
    tagged = innovation('x', tags={'industry': ['retail']})
    assert m.available_weight(tagged) == pytest.approx(m.W_LEX + m.W_FACET)
    branded = innovation('x', brands=['Acme Retail'])
    assert m.available_weight(branded) == pytest.approx(m.W_LEX + m.W_BRAND)


def test_a_tagged_innovation_that_matches_no_facet_is_marked_down():
    """The other half of the rule: a zero that comes from a real input has to
    count against the score, or tags would only ever help."""
    shifts = [shift('key_trend:a', 'Delegated Desire', to='Software does the shopping')]
    corpus = m.Corpus(shifts)
    text = 'An agent that does the shopping for you'
    bare = m.score_all(corpus, innovation(text), no_sector)[0].confidence
    mismatched = m.score_all(
        corpus, innovation(text, tags={'basic-human-need': ['nutrition']}), no_sector,
    )[0].confidence
    assert mismatched < bare
