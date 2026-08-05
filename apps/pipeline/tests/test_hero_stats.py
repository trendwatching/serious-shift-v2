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


# ── Word clamping ─────────────────────────────────────────────────────────────
#
# The publication contract caps each editorial field because the design has a
# fixed amount of room for it. The model overruns some of them routinely, and
# a whole-body retry cannot fix that: a shift carries sixteen sector notes, so
# judging the body on its longest note failed 46 of 49 shifts and still 41
# after three attempts. Trimming per field is what makes the gate reachable.

def test_text_within_the_limit_is_returned_untouched():
    from serious_shift_pipeline.mapgen.modules import clamp_words
    assert clamp_words("a short note", 40) == "a short note"


def test_overlong_text_is_cut_to_the_limit():
    from serious_shift_pipeline.mapgen.modules import clamp_words
    out = clamp_words("word " * 60, 40)
    assert len(out.split()) == 40


def test_a_sentence_boundary_is_preferred_when_it_keeps_most_of_the_allowance():
    from serious_shift_pipeline.mapgen.modules import clamp_words
    text = ("Agents now negotiate prices directly with suppliers on the buyer's "
            "behalf. That leaves the brand with no surface to advertise against.")
    out = clamp_words(text, 16)
    assert out.endswith('.'), out
    assert 'That leaves' not in out


def test_a_cut_with_no_usable_sentence_break_is_elided_not_left_dangling():
    from serious_shift_pipeline.mapgen.modules import clamp_words
    out = clamp_words("one two three four five six seven eight nine ten", 4)
    assert out == "one two three four…"


def test_missing_text_clamps_to_empty_rather_than_the_string_none():
    from serious_shift_pipeline.mapgen.modules import clamp_words
    assert clamp_words(None, 10) == ""
    assert clamp_words("", 10) == ""


def test_list_items_are_clamped_individually_not_dropped():
    """One long sector note must not cost the other fifteen."""
    from serious_shift_pipeline.mapgen.modules import _clamp_items
    items = [{'name': 'Retail & Commerce', 'text': 'word ' * 60},
             {'name': 'Financial Services', 'text': 'short note'}]
    out = _clamp_items(items, 40)
    assert len(out) == 2
    assert len(out[0]['text'].split()) == 40
    assert out[1]['text'] == 'short note'
    assert [i['name'] for i in out] == ['Retail & Commerce', 'Financial Services']
