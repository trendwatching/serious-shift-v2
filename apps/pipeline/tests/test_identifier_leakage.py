"""Database identifiers must never reach reader-facing copy.

Two strings shipped to production before this existed:

    "Jack Clark, import AI newsletter (cred:54)"
    "Jakob Nielsen (id:38735)"

They were model output, not composed by any code we own — the evidence block
hands the model an `id` so it can cite claims, and some runs put it in the
sentence instead. The prompts now forbid it, but published copy carries a real
person's name, so "the model was told not to" is not the guarantee we need.

Three layers are tested here: the scrubber removes it, the export applies the
scrubber to already-stored modules (which is what cleans copy published before
the fix, for free, on an --export-only run), and validation refuses to publish
a document that still contains one.

DB-free and network-free.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from serious_shift_pipeline.mapgen import modules as gm
from serious_shift_pipeline.mapgen import validation as gv


def _repo_file(*parts: str) -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent.joinpath(*parts)
        if candidate.is_file():
            return candidate
    return None


# ── The scrubber ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, want", [
    # The two that actually shipped.
    ("Jack Clark, import AI newsletter (cred:54)", "Jack Clark, import AI newsletter"),
    ("Jakob Nielsen (id:38735)", "Jakob Nielsen"),
    # Neighbouring shapes the same mistake takes.
    ("Ethan Mollick [id: 12]", "Ethan Mollick"),
    ("A claim (confidence: 0.9) about agents", "A claim about agents"),
    ("Sourced from c_38735 and c_991", "Sourced from and"),
    ("Nielsen (credibility=54) argues", "Nielsen argues"),
    ("specificity:4 was recorded", "was recorded"),
])
def test_leaked_identifiers_are_removed(raw, want):
    assert gm.strip_identifiers(raw) == want


@pytest.mark.parametrize("raw", [
    # Ratios, years and ordinary prose have to survive untouched. A scrubber
    # that eats "2:1" is worse than the leak it prevents.
    "Support runs 2:1 against the proposal",
    "The 2026 id card scheme was withdrawn",
    "Section 3: what changed",
    "Revenue grew 24% in 18 months",
    "Read more at https://example.com/a?id=7",
    "",
])
def test_ordinary_copy_survives(raw):
    assert gm.strip_identifiers(raw) == raw.strip()


def test_the_scrub_walks_a_whole_module_tree_but_leaves_urls_alone():
    """The leak lands wherever the model put it — a stat band's source, an
    evidence item's text, a voices quote. So the walk is structural, not a list
    of named fields. URLs are exempt: they are machine strings by definition."""
    tree = [{
        "type": "evidence",
        "data": {
            "items": [{
                "text": "Reasoning degrades under delegation (id:99)",
                "thinker": "Nielsen (cred:54)",
                "url": "https://example.com/paper?id=99&cred=54",
            }],
        },
    }]
    scrubbed = gm.scrub_module_tree(tree)
    item = scrubbed[0]["data"]["items"][0]
    assert item["text"] == "Reasoning degrades under delegation"
    assert item["thinker"] == "Nielsen"
    assert item["url"] == "https://example.com/paper?id=99&cred=54"


def test_clamp_words_scrubs_before_it_measures():
    """Every prose field passes through clamp_words, so the scrub is applied on
    the way in. A stripped identifier must not cost the copy a word of its
    allowance either."""
    assert gm.clamp_words("one two three (id:7)", 3) == "one two three"


# ── Validation refuses to publish one ───────────────────────────────────────

def test_a_module_with_a_leaked_identifier_fails_validation():
    modules = [{"type": "dek", "data": {"text": "A shift, per Nielsen (id:38735)."}}]
    issues = gv._validate_modules(modules, "key_trend", "key_trends.x", _contract())
    codes = {i.code for i in issues}
    assert "leaked_identifier" in codes, sorted(codes)


def test_a_clean_module_raises_no_leak_issue():
    modules = [{"type": "dek", "data": {"text": "A shift, per Nielsen."}}]
    issues = gv._validate_modules(modules, "key_trend", "key_trends.x", _contract())
    assert "leaked_identifier" not in {i.code for i in issues}


def _contract() -> dict:
    path = _repo_file("packages", "contracts", "shift_modules.json")
    if path is None:
        pytest.skip("canonical packages/contracts not present (installed/sdist build)")
    return json.loads(path.read_text())


# ── The source of the temptation ────────────────────────────────────────────

def test_the_evidence_block_no_longer_offers_a_credibility_score():
    """The SQL already ranks by credibility before a claim reaches the prompt, so
    handing the number to the model buys nothing and is how "(cred:54)" got into
    a sentence."""
    from serious_shift_pipeline.prompts.map_data import fmt_claims_block

    block = fmt_claims_block([{
        "id": 1, "claim_text": "x", "thinker": "Nielsen", "credibility_score": 54,
    }])
    assert "thinker_credibility" not in block
    assert "54" not in block


@pytest.mark.parametrize("name", ["kt_editorial.txt", "st_editorial.txt"])
def test_the_prompts_forbid_identifiers_in_prose(name):
    """Guards an accidental revert of the prompt rule — the cheapest of the three
    layers, and the only one that stops the mistake being made at all."""
    path = _repo_file("packages", "prompts", "map", name)
    if path is None:
        pytest.skip("canonical packages/prompts not present")
    text = path.read_text()
    assert "It must never appear in prose" in text
    assert "(id:38735)" in text


# ── The reason the scrub lives at export ────────────────────────────────────

def test_the_scrub_is_applied_at_export_not_only_at_generation():
    """The offending strings are baked into domain_key_trends.modules from runs
    that predate the fix. Scrubbing where every list passes through on the way
    out is what lets a free --export-only run clean the live pages; scrubbing
    only at generation would need a paid --editorial-only pass."""
    source = _repo_file("apps", "pipeline", "serious_shift_pipeline", "mapgen", "export.py")
    assert source is not None
    text = source.read_text()
    assert "scrub_module_tree" in text
    # It has to sit inside the ordering helper, which is the single choke point
    # every list reaches after its derived modules have been inserted.
    ordered = re.search(r"def _ordered\(.*?\n(?:.*\n)*?        \)", text)
    assert ordered and "scrub_module_tree" in ordered.group(0)
