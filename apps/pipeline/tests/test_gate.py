"""Reputability gate — pure-function tests (no DB, no network)."""
from serious_shift_pipeline.steps import gate


def test_venue_tier_lookup():
    assert gate.venue_tier("NeurIPS") == 1
    assert gate.venue_tier("Nature") == 1
    assert gate.venue_tier("arXiv") == 3
    assert gate.venue_tier("Some Random Newsletter") == 4
    assert gate.venue_tier(None) == 5
    # explicit overrides win over defaults
    assert gate.venue_tier("arXiv", {"arXiv": 1}) == 1


def test_citation_component_scales():
    assert gate.citation_component(None) is None
    assert gate.citation_component(0) == 0.0
    assert gate.citation_component(1000) == 1.0
    assert 0.0 < gate.citation_component(30) < 1.0


def test_compute_authority_prefers_reputable():
    top = gate.compute_authority(citation_count=1000, tier=1)
    weak = gate.compute_authority(citation_count=0, tier=5)
    assert top == 1.0
    assert weak < 0.35
    # arXiv preprint with no citations is still mid-tier, not junk
    assert gate.compute_authority(citation_count=None, tier=3) >= 0.5


def test_is_reputable_decisions():
    top = {"authors": ["X"], "venue": "Nature", "citation_count": 40}
    junk = {"authors": ["Y"], "venue": "Random Blog", "citation_count": 0}
    ok, auth = gate.is_reputable(top, min_citations=5, min_authority=0.4)
    assert ok and auth > 0.4
    bad, _ = gate.is_reputable(junk, min_citations=5, min_authority=0.4)
    assert not bad


def test_allowlist_always_passes():
    junk = {"authors": ["Jane Roster"], "venue": "Random Blog", "citation_count": 0}
    ok, auth = gate.is_reputable(junk, allowlist={"Jane Roster"}, min_authority=0.4)
    assert ok and auth >= 0.6
