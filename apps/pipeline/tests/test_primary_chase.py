"""Primary-source chasing: a laundered statistic gains primary_source_id only
when the origin URL was already in the passage AND the fetched document
verifiably contains the number. The model points; deterministic checks decide."""
from serious_shift_pipeline.prompts import primary_origin_prompt
from serious_shift_pipeline.steps.primary_chase import (
    CONTEXT_CHARS, _context_window, _plausible_origin_url)

PASSAGE = (
    "Nielsen, reporting on a Propeller Insights survey "
    "(https://www.propellerinsights.com/ai-shopping-2026) of 4,040 US and UK "
    "adults, documented an 18-point swing in one year."
)


def test_context_window_prefers_anchored_span():
    full = ("x" * 5000) + PASSAGE + ("y" * 5000)
    claim = {"quote_start": 5000, "quote_end": 5000 + len(PASSAGE),
             "statistic": "4,040 adults"}
    window = _context_window(claim, full)
    assert PASSAGE in window
    assert len(window) <= len(PASSAGE) + 2 * CONTEXT_CHARS


def test_context_window_falls_back_to_statistic_position():
    full = ("x" * 5000) + PASSAGE + ("y" * 5000)
    claim = {"quote_start": None, "quote_end": None, "statistic": "4,040 adults"}
    assert "4,040" in _context_window(claim, full)


def test_context_window_defaults_to_document_head():
    claim = {"quote_start": None, "quote_end": None, "statistic": "no digits here"}
    assert _context_window(claim, PASSAGE) == PASSAGE[:2 * CONTEXT_CHARS]


def test_origin_url_must_appear_verbatim_in_passage():
    ok = "https://www.propellerinsights.com/ai-shopping-2026"
    assert _plausible_origin_url(ok, "https://nngroup.com/post", PASSAGE)
    # Invented / completed URLs are refused even when plausible-looking.
    assert not _plausible_origin_url(
        "https://www.propellerinsights.com/ai-shopping-2026/full-report",
        "https://nngroup.com/post", PASSAGE)


def test_origin_url_may_not_be_the_commentary_itself():
    passage = PASSAGE + " See https://nngroup.com/other-post for more."
    assert not _plausible_origin_url(
        "https://nngroup.com/other-post", "https://nngroup.com/post", passage)


def test_origin_url_rejects_non_http_and_empty():
    assert not _plausible_origin_url(None, "https://a.com", PASSAGE)
    assert not _plausible_origin_url("ftp://x.com/f", "https://a.com",
                                     PASSAGE + " ftp://x.com/f")


def test_prompt_renders_with_all_fields():
    prompt = primary_origin_prompt("Consumers swung to AI shopping.",
                                   "18-point swing", PASSAGE)
    assert "18-point swing" in prompt
    assert PASSAGE in prompt
    assert "NEVER invent" in prompt
