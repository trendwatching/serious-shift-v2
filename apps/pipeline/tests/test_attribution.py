"""
"Who is saying this" must only ever print words the person actually said.

The panel renders `quote` inside quotation marks under a real person's name.
It used to be fed our extractor's paraphrases — `claim_text` — because
`routing.py` never selected `claims.quote`, and the prompt asked for "a direct
quote or close paraphrase". The live site therefore attributed sentences to
Satya Nadella and Peter Diamandis that they did not say.

The prompt now demands verbatim, but a prompt is a request. These tests pin the
*check*: the parser accepts an entry only when the quote matches one of that
thinker's actual spans, so a paraphrase cannot reach the page even if the model
returns one.
"""
import pytest

from serious_shift_pipeline.mapgen.parsers import (
    _collect_by_thinker,
    parse_thinker_attribution,
)

REAL = "Expedia reported gaining an extra $12 million a year after deleting 1 optional field."
GROUPS = {
    "Jakob Nielsen": [
        {"claim_text": "Removing form fields materially lifts conversion.", "quote": REAL},
    ],
    "Satya Nadella": [
        # A thinker present in the evidence but with no verbatim span.
        {"claim_text": "GrandChef achieved a 31% conversion increase.", "quote": ""},
    ],
}


def _one(name, quote, bucket="proponents"):
    return parse_thinker_attribution({bucket: [{"name": name, "quote": quote}]}, GROUPS)


# ── The failure that shipped ──────────────────────────────────────────────────

def test_a_paraphrase_is_rejected():
    """The exact shape of the live bug: a claim_text returned as a quote."""
    out = _one("Satya Nadella", "GrandChef achieved a 31% conversion increase.")
    assert out["proponents"] == []


def test_a_thinker_with_no_verbatim_span_is_dropped_entirely():
    out = _one("Satya Nadella", REAL)  # not HIS quote
    assert out["proponents"] == []


def test_an_invented_quote_is_rejected():
    out = _one("Jakob Nielsen", "Something he never said about anything at all.")
    assert out["proponents"] == []


def test_a_thinker_not_in_the_evidence_is_rejected():
    out = _one("Someone Else Entirely", REAL)
    assert out["proponents"] == []


# ── What must still get through ───────────────────────────────────────────────

def test_a_real_quote_is_kept():
    out = _one("Jakob Nielsen", REAL)
    assert out["proponents"] == [{"name": "Jakob Nielsen", "quote": REAL}]


def test_skeptics_are_verified_the_same_way():
    ok = _one("Jakob Nielsen", REAL, bucket="skeptics")
    bad = _one("Jakob Nielsen", "invented", bucket="skeptics")
    assert ok["skeptics"] and not bad["skeptics"]


@pytest.mark.parametrize("variant", [
    REAL.replace("$12", "$12 "),                      # re-wrapped whitespace
    REAL.replace("'", "’"),                      # smart apostrophe
    "  " + REAL + "  ",                               # padding
    REAL.upper(),                                     # case drift
])
def test_cosmetic_drift_does_not_reject_a_true_quote(variant):
    """Models re-wrap and swap glyphs while copying faithfully. That is not
    misattribution and must not cost us a real quote."""
    out = _one("Jakob Nielsen", variant)
    assert len(out["proponents"]) == 1


def test_the_stored_quote_is_ours_not_the_models():
    """Whatever cosmetic form came back, the page shows the source text."""
    out = _one("Jakob Nielsen", REAL.upper())
    assert out["proponents"][0]["quote"] == REAL


# ── Fail closed ───────────────────────────────────────────────────────────────

def test_without_evidence_nothing_is_trusted():
    """No groups means nothing can be verified — drop rather than pass through."""
    out = parse_thinker_attribution({"proponents": [{"name": "X", "quote": "Y"}]})
    assert out == {"proponents": [], "skeptics": []}


@pytest.mark.parametrize("raw", [None, [], "text", {}, {"proponents": None}])
def test_malformed_responses_yield_an_empty_result(raw):
    assert parse_thinker_attribution(raw, GROUPS) == {"proponents": [], "skeptics": []}


def test_bare_name_strings_no_longer_pass_through():
    """The old back-compat path admitted names with no quote at all."""
    out = parse_thinker_attribution({"proponents": ["Jakob Nielsen"]}, GROUPS)
    assert out["proponents"] == []


# ── Roster scoping ────────────────────────────────────────────────────────────

CLAIMS = [
    {"thinker": "Jakob Nielsen", "thinker_discovered": False, "quote": REAL},
    {"thinker": "Li Wang", "thinker_discovered": True, "quote": "A paper sentence."},
]


def test_discovered_authors_are_excluded_from_the_panel():
    """Auto-created paper co-authors are not authorities we can name."""
    assert set(_collect_by_thinker(CLAIMS, curated_only=True)) == {"Jakob Nielsen"}


def test_other_phases_still_see_every_thinker():
    """Only the attribution panel is scoped; routing and evidence are not."""
    assert set(_collect_by_thinker(CLAIMS)) == {"Jakob Nielsen", "Li Wang"}
