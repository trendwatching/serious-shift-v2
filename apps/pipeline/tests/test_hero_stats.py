"""
Hero-stat attribution.

The stat band renders `source` as a small credit line under a large figure.
It was being fed `sources.title` verbatim, and one live shift page carried
200 characters of pipe-separated newsletter headlines under its hero number —
a roundup post's title is a table of contents, not a citation.
"""
from serious_shift_pipeline.mapgen.phases.hero_stats import MAX_ATTRIBUTION, _attribution

ROUNDUP = ("UX Roundup: Web Design for AI Agents | AI Assistants Beat Brand Websites | "
           "Ship, Learn, Iterate | AI as Business Strategist | AI-Assisted Creativity "
           "for Children | Infinite Canvas | Scott McCloud")


def test_named_thinker_wins_over_the_article_title():
    assert _attribution("Ethan Mollick", ROUNDUP, "2026") == "Ethan Mollick, 2026"


def test_title_is_the_fallback_when_there_is_no_thinker():
    assert _attribution("", "The Intelligence Curse", "2025") == "The Intelligence Curse, 2025"


def test_long_titles_are_truncated():
    out = _attribution("", ROUNDUP, "2026")
    assert len(out) <= MAX_ATTRIBUTION + len("…, 2026")
    assert out.endswith("…, 2026")


def test_truncation_breaks_on_a_word_not_mid_word():
    out = _attribution("", ROUNDUP, "")
    assert "  " not in out
    # The character before the ellipsis must not be a dangling separator.
    assert out.rstrip("…")[-1] not in " ,;:|-"


def test_missing_year_is_omitted_rather_than_rendered_empty():
    assert _attribution("Ethan Mollick", ROUNDUP, "") == "Ethan Mollick"
    assert not _attribution("Ethan Mollick", "", "").endswith(",")


def test_no_attribution_at_all_yields_empty_string():
    # The frontend hides the line when it is falsy; a stray comma would show.
    assert _attribution("", "", "") == ""


def test_whitespace_only_thinker_falls_through_to_the_title():
    assert _attribution("   ", "Some Paper", "2026") == "Some Paper, 2026"
