"""A quote or statistic the source never said must not enter the corpus.

core/claim_integrity.py is the verifier both steps/process_raw.py (at insert)
and tools/backfill_claim_integrity.py (retroactively) run. Failure is a
downgrade, never a rejection — the claim survives, the fabricated field dies.
"""

from serious_shift_pipeline.core.claim_integrity import (
    _normalize_with_map,
    locate_quote,
    normalize_text,
    quote_verifies,
    statistic_verifies,
    verify_at_offset,
    verify_claim_against_source,
)

SOURCE = (
    "In a wide-ranging interview, Dr. Webb argued that shopping habits have "
    "already turned: “34% of US consumers used an AI tool to shortlist a "
    "purchase in the first quarter of 2025 — and they didn’t go back.” "
    "She added that adoption among younger users grew six times faster than "
    "forecast, while roughly 1,540 retailers now expose structured product "
    "feeds. The host asked whether brands should panic; Webb laughed."
)


class TestQuote:
    def test_verbatim_span_passes(self):
        assert quote_verifies("34% of US consumers used an AI tool", SOURCE)

    def test_smart_quotes_and_case_are_tolerated(self):
        assert quote_verifies(
            'they didn’t go back', SOURCE.replace('’', "'"))
        assert quote_verifies("THEY DIDN'T GO BACK", SOURCE)

    def test_light_transcript_cleanup_passes(self):
        # One small word changed inside an otherwise verbatim span.
        assert quote_verifies(
            "adoption among younger users grew six times faster than forecasts",
            SOURCE)

    def test_paraphrase_fails(self):
        assert not quote_verifies(
            "consumers now prefer AI assistants to brand websites for most "
            "purchases and will never return to direct search", SOURCE)

    def test_composed_quote_fails(self):
        # Both halves appear in the source, far apart — stitching them is
        # fabrication even though every word is "real".
        assert not quote_verifies(
            "shopping habits have already turned; Webb laughed at whether "
            "brands should panic about structured product feeds", SOURCE)

    def test_empty_quote_passes(self):
        assert quote_verifies("", SOURCE)

    def test_empty_source_fails_nonempty_quote(self):
        assert not quote_verifies("34% of US consumers", "")


class TestStatistic:
    def test_number_present_passes(self):
        assert statistic_verifies("34% of US consumers, Q1 2025 (Webb)", SOURCE)

    def test_thousands_separator_matches(self):
        assert statistic_verifies("1,540 retailers with structured feeds", SOURCE)

    def test_spelled_out_small_number_passes(self):
        assert statistic_verifies("6x faster adoption among younger users", SOURCE)

    def test_absent_number_fails(self):
        assert not statistic_verifies(
            "Approximately 1,337 employees signed the letter (2026)", SOURCE)

    def test_number_free_statistic_fails(self):
        assert not statistic_verifies("a complete reversal from last year", SOURCE)

    def test_empty_statistic_passes(self):
        assert statistic_verifies("", SOURCE)


class TestDowngrade:
    def test_bad_fields_are_downgraded_in_place(self):
        claim = {
            "claim_text": "Consumers prefer AI shopping.",
            "quote": "brands are dead and everyone knows it",
            "has_statistic": True,
            "statistic": "$200 billion in debt financing (Valar)",
        }
        _, drops = verify_claim_against_source(claim, SOURCE)
        assert sorted(drops) == ["quote", "statistic"]
        assert claim["quote"] == ""
        assert claim["has_statistic"] is False
        assert claim["statistic"] == ""

    def test_good_claim_is_untouched(self):
        claim = {
            "claim_text": "Adoption turned in 2025.",
            "quote": "34% of US consumers used an AI tool to shortlist a purchase",
            "has_statistic": True,
            "statistic": "34% of US consumers, Q1 2025 (Webb)",
        }
        _, drops = verify_claim_against_source(claim, SOURCE)
        assert drops == []
        assert claim["has_statistic"] is True

    def test_empty_source_downgrades_gracefully(self):
        claim = {"quote": "anything", "has_statistic": True, "statistic": "34%"}
        _, drops = verify_claim_against_source(claim, "")
        assert sorted(drops) == ["quote", "statistic"]


class TestSpanAnchor:
    """locate_quote/verify_at_offset — the exact-slice tier claims.quote_start/
    quote_end store, so 'does the source say this' never needs a search again."""

    def test_raw_exact_match_span(self):
        quote = "34% of US consumers used an AI tool"
        span = locate_quote(quote, SOURCE)
        assert span is not None
        start, end = span
        assert SOURCE[start:end] == quote
        assert verify_at_offset(quote, SOURCE, start, end)

    def test_smart_punctuation_maps_back_to_raw_span(self):
        # Straight-quote claim text against the curly-quote source.
        quote = "they didn't go back"
        span = locate_quote(quote, SOURCE)
        assert span is not None
        start, end = span
        assert normalize_text(SOURCE[start:end]) == normalize_text(quote)
        assert verify_at_offset(quote, SOURCE, start, end)

    def test_whitespace_collapse_still_locates(self):
        source = "adoption\n  turned   sharply\nin 2025, she said"
        span = locate_quote("adoption turned sharply in 2025", source)
        assert span is not None
        assert verify_at_offset("adoption turned sharply in 2025", source, *span)

    def test_absent_quote_has_no_span(self):
        assert locate_quote("brands are dead and everyone knows it", SOURCE) is None
        assert locate_quote("", SOURCE) is None

    def test_wrong_or_out_of_bounds_span_fails(self):
        assert not verify_at_offset("34% of US consumers", SOURCE, 0, 19)
        assert not verify_at_offset("anything", SOURCE, None, None)
        assert not verify_at_offset("anything", SOURCE, 5, len(SOURCE) + 40)

    def test_normalize_with_map_agrees_with_normalize_text(self):
        for text in (SOURCE, "…ellipsis — and nbsp “x”", "  padded  ", ""):
            norm, idx = _normalize_with_map(text)
            assert norm == normalize_text(text)
            assert len(idx) == len(norm)
