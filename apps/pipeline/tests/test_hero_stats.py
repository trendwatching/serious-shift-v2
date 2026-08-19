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


def test_a_cut_never_ships_an_ellipsis():
    """37 visibly amputated sentences shipped on the 2026-08-09 map."""
    from serious_shift_pipeline.mapgen.modules import clamp_words
    out = clamp_words("one two three four five six seven eight nine ten", 4)
    assert out == "one two three four."
    assert not out.endswith("…") and not out.endswith("...")


def test_a_clause_break_is_preferred_over_a_bare_word_cut():
    from serious_shift_pipeline.mapgen.modules import clamp_words
    text = ("Agents negotiate the price, the terms, the warranty and the "
            "delivery window for every purchase a household makes")
    out = clamp_words(text, 8)
    assert out == "Agents negotiate the price, the terms."


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


# ── Exclusive, topical hero assignment ───────────────────────────────────────
#
# The 2026-08-09 map had ~6 distinct hero stats across 51 shifts — a per-KT
# argmax over shared pools with no topical check put a teen-suicide statistic
# atop ten pages including shopping and pricing.

def _cand(claim_id, statistic, text, score):
    return {'claim_id': claim_id, 'statistic': statistic, 'claim_text': text,
            'thinker': 'A. Thinker', 'source': 'A Post', 'pub_date': '2026-08-01',
            'url': 'https://example.com/post', 'score': score}


def test_stat_matches_shift_rejects_category_errors():
    from serious_shift_pipeline.mapgen.phases.hero_stats import stat_matches_shift
    assert not stat_matches_shift(
        'Delegated Discovery', 'AI shopping agents replace brand websites',
        'ChatGPT mentioned suicide 6x more frequently',
        "Adam Raine's ChatGPT interactions included the AI mentioning suicide")


def test_stat_matches_shift_accepts_on_topic_stats():
    from serious_shift_pipeline.mapgen.phases.hero_stats import stat_matches_shift
    assert stat_matches_shift(
        'Delegated Discovery', 'AI shopping agents replace brand websites',
        '41% prefer AI-assisted shopping over brand websites',
        'Consumers now choose AI-assisted shopping over going to brand sites')


def test_one_claim_heroes_exactly_one_shift():
    from serious_shift_pipeline.mapgen.phases.hero_stats import assign_heroes
    shared = _cand(1, '41% choose agent shopping', 'agent shopping beats brand sites', 9.0)
    kts = [{'id': 10, 'name': 'Delegated Discovery', 'subtitle': 'agent shopping replaces brand sites'},
           {'id': 11, 'name': 'Agent Shopping Anxiety', 'subtitle': 'shoppers distrust agent shopping'}]
    by_kt = {10: [shared, _cand(2, '3.5x conversion via shopping assistants',
                                'shopping assistants convert 3.5x better', 5.0)],
             11: [shared]}
    heroes = assign_heroes(kts, by_kt)
    # KT 11 has one candidate (scarcest, picks first) and takes the shared claim;
    # KT 10 falls back to its next-ranked candidate.
    values = [heroes[10]['value'], heroes[11]['value']]
    assert values.count('41% choose agent shopping') == 1
    assert heroes[10] is not None and heroes[11] is not None


def test_a_shift_with_only_off_topic_candidates_gets_none():
    from serious_shift_pipeline.mapgen.phases.hero_stats import assign_heroes
    kts = [{'id': 20, 'name': 'Provenance Premium', 'subtitle': 'human-made goods command a premium'}]
    by_kt = {20: [_cand(3, '10,000 GPU cluster operating', 'Tencent runs a GPU training cluster', 9.9)]}
    assert assign_heroes(kts, by_kt) == {20: None}


def test_a_hero_never_restates_the_subtitle_figure():
    """The subtitle is phase-3 copy no later pass rewrites, so a hero echoing
    it puts the same number on the page twice, forever — 32 pages on the
    2026-08-19 live map. The next-ranked non-echoing candidate wins instead."""
    from serious_shift_pipeline.mapgen.phases.hero_stats import assign_heroes
    kts = [{'id': 50, 'name': 'Silent Commerce',
            'subtitle': 'Amazon voice shopping converts at 3.5x the rate of keyword search'}]
    echoing = _cand(1, '3.5x conversion rate for voice shopping',
                    'Amazon voice shopping assistants convert shoppers', 9.0)
    clean = _cand(2, '75% of adults use AI shopping tools',
                  'AI shopping tools reach mainstream adoption at Amazon', 5.0)
    picked = assign_heroes(kts, {50: [echoing, clean]})[50]
    assert picked is not None and picked['value'].startswith('75%')
    # when every on-topic candidate echoes, the shift goes without a statistic
    assert assign_heroes(kts, {50: [echoing]})[50] is None


def test_a_claim_a_child_already_fronts_is_a_last_resort_not_a_veto():
    """This used to be a hard exclusion, and it inverted the gate.

    validate_map registers key shifts FIRST and blames the sub-shift for
    re-fronting, so treating a child's persisted band as senior prior art cost
    the parent its figure and left the collision standing. It also made
    stat_coverage unsatisfiable from both ends — 17/36 in Aug 2026, 16/44 on the
    18 Aug run. Now: prefer a clean claim, fall back to a contested one, and let
    export cede the child's band to its parent.
    """
    from serious_shift_pipeline.mapgen.modules import stat_claim_key
    from serious_shift_pipeline.mapgen.phases.hero_stats import assign_heroes
    kts = [{'id': 40, 'name': 'Governance Void',
            'subtitle': 'labs sign a restraint petition'}]
    cand = _cand(5, '~1,337 employees across major Western AI labs signed',
                 'employees signed a restraint petition', 8.0)
    clean = _cand(6, '62% of labs signed a petition on restraint',
                  'a majority of labs signed the restraint petition', 4.0)
    fronted = {stat_claim_key('1,337', cand['url'])}   # a child's band, short form

    # Given a choice, the contested claim loses even though it ranks higher.
    both = assign_heroes(kts, {40: [cand, clean]}, fronted)[40]
    assert both is not None and '62%' in both['value']

    # Given no choice, the shift still gets its figure rather than nothing.
    only = assign_heroes(kts, {40: [cand]}, fronted)[40]
    assert only is not None and '1,337' in only['value']


def test_a_hero_that_cannot_render_a_band_is_never_picked():
    """kt_modules drops the stat_band when _short_figure returns None, so a
    hero picked from figure-less prose reports coverage the page does not have
    — and burns the claim exclusively on the way. 30/44 heroes rendered 16/44
    bands on the 18 Aug staging run, failing stat_coverage.
    """
    from serious_shift_pipeline.mapgen.modules import _short_figure
    from serious_shift_pipeline.mapgen.phases.hero_stats import assign_heroes
    kts = [{'id': 41, 'name': 'Provenance Premium',
            'subtitle': 'human-made goods command a premium'}]
    prose = _cand(7, 'a premium for goods made by human hands, without machines',
                  'shoppers pay a premium for human-made goods', 9.9)
    figure = _cand(8, '31% premium for human-made goods',
                   'shoppers pay a premium for human-made goods', 1.0)
    assert _short_figure(prose['statistic']) is None

    assert assign_heroes(kts, {41: [prose]})[41] is None
    picked = assign_heroes(kts, {41: [prose, figure]})[41]
    assert picked is not None and _short_figure(picked['value']) is not None


def test_hero_json_carries_no_claim_id():
    from serious_shift_pipeline.mapgen.phases.hero_stats import assign_heroes
    kts = [{'id': 30, 'name': 'Compute Capitalism', 'subtitle': 'data centers as the local tax base'}]
    by_kt = {30: [_cand(4, '$1.3B county tax revenue', 'data centers pay record county tax', 2.0)]}
    hero = assign_heroes(kts, by_kt)[30]
    assert hero is not None and 'claim_id' not in hero


def test_short_figure_no_longer_garbles_scale_suffixes():
    from serious_shift_pipeline.mapgen.modules import _short_figure
    assert _short_figure('10 major open problems solved') != '10 m'
    assert _short_figure('10 major open problems solved') == '10'
    assert _short_figure('16 million users') == '16M'


def test_short_figure_finds_a_figure_past_a_leading_word():
    from serious_shift_pipeline.mapgen.modules import _short_figure
    assert _short_figure('Approximately 79.44% of sampled pairs') == '79.44%'
    assert _short_figure('roughly $54.2 million in claims') == '$54.2M'
