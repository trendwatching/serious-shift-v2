"""Per-KT claim pools must be topical and mutually exclusive.

The old top-up padded every Key Trend's pool from the head of the same
domain-wide list, so every KT in a domain saw the same ~80 top-weighted claims
— the root cause of the map's recycled hero stats and crutch anecdotes.
"""

from serious_shift_pipeline.mapgen.phases.sub_trends import (
    MIN_POOL_PER_KT,
    _pool_idf,
    _topical_top_up,
)


def _claim(cid: int, text: str) -> dict:
    return {'id': cid, 'claim_text': text}


POOL = [
    _claim(1, 'AI shopping assistants now filter and rank products before consumers arrive'),
    _claim(2, 'Retail brands compete for algorithmic favor in agent-mediated commerce'),
    _claim(3, 'Data centers in Virginia counties generate record property tax revenue'),
    _claim(4, 'Municipal budgets increasingly depend on data center infrastructure levies'),
    _claim(5, 'Teen suicide lawsuit reveals chatbot safety failures in consumer products'),
    _claim(6, 'Employment for young workers dropped sharply in AI-exposed occupations'),
    _claim(7, 'Shopping agents evaluate net value and ignore psychological pricing tricks'),
    _claim(8, 'Compute clusters and GPU production expand under national industrial policy'),
]

SHOPPING_KT = {'name': 'Delegated Discovery',
               'subtitle': 'AI shopping agents replace brand websites as the consumer discovery layer'}
DATACENTER_KT = {'name': 'Compute Capitalism',
                 'subtitle': 'Data centers become the tax base and infrastructure spine of local budgets'}


def test_top_up_is_topical_not_positional():
    idf = _pool_idf(POOL)
    ledger: set[int] = set()
    chosen = _topical_top_up(SHOPPING_KT, POOL, set(), ledger, remaining=3, idf=idf)
    ids = [c['id'] for c in chosen]
    # Shopping claims outrank the list-head data-center claims.
    assert set(ids) <= {1, 2, 7}
    assert 3 not in ids and 5 not in ids


def test_siblings_never_share_top_up_claims():
    idf = _pool_idf(POOL)
    ledger: set[int] = set()
    first = _topical_top_up(SHOPPING_KT, POOL, set(), ledger, remaining=3, idf=idf)
    second = _topical_top_up(DATACENTER_KT, POOL, set(), ledger, remaining=3, idf=idf)
    assert not {c['id'] for c in first} & {c['id'] for c in second}


def test_phase3_assignments_are_never_stolen():
    idf = _pool_idf(POOL)
    ledger: set[int] = set()
    chosen = _topical_top_up(SHOPPING_KT, POOL, preferred_ids={1, 2},
                             ledger=ledger, remaining=3, idf=idf)
    assert {c['id'] for c in chosen}.isdisjoint({1, 2})


def test_zero_overlap_fallback_reaches_the_floor():
    idf = _pool_idf(POOL)
    ledger: set[int] = set()
    off_topic_kt = {'name': 'Quantum Basketry', 'subtitle': 'Weaving with entangled reeds'}
    chosen = _topical_top_up(off_topic_kt, POOL, set(), ledger,
                             remaining=len(POOL), idf=idf)
    # Nothing overlaps, but the pool still reaches the publishable floor.
    assert len(chosen) == min(MIN_POOL_PER_KT, len(POOL))


def test_deterministic_across_invocations():
    idf = _pool_idf(POOL)
    a = _topical_top_up(SHOPPING_KT, POOL, set(), set(), remaining=4, idf=idf)
    b = _topical_top_up(SHOPPING_KT, POOL, set(), set(), remaining=4, idf=idf)
    assert [c['id'] for c in a] == [c['id'] for c in b]
