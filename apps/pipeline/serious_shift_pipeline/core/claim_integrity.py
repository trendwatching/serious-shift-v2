"""Verify extracted claim fields against the source text they came from.

Extraction output is model-authored; `quote` and `statistic` are the two fields
downstream code treats as ground truth (hero stats rank on `has_statistic`,
`voices` and evidence render `quote`). Anything published as a number or a
quotation must therefore be provably present in the source — the 2026-08-10
audit shipped "1,337 employees" and a "$200 billion" financing round that no
source ever said.

The check runs against `sources.full_text`, which is a superset of the slice the
extraction prompt saw, so a pass here never contradicts the model's own input.
Failure is always a downgrade, never a rejection: a bad quote is emptied, a bad
statistic clears `has_statistic` — the claim itself survives.
"""

from __future__ import annotations

import difflib
import re

QUOTE_MATCH_RATIO = 0.9

_SMART_CHARS = str.maketrans({
    '‘': "'", '’': "'", '‚': "'", '‛': "'",
    '“': '"', '”': '"', '„': '"',
    '–': '-', '—': '-', '−': '-',
    ' ': ' ', '…': '...',
})

# Statistics quote figures the source may spell out ("six times" → "6x").
_SPELLED_NUMBERS = {
    1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six',
    7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten', 11: 'eleven', 12: 'twelve',
    13: 'thirteen', 14: 'fourteen', 15: 'fifteen', 16: 'sixteen',
    17: 'seventeen', 18: 'eighteen', 19: 'nineteen', 20: 'twenty',
}

# A numeric token with its immediate letter prefix, so "Q1 2025" yields
# ("q", "1") and ("", "2025") rather than a bare "1" that no prose contains.
_NUMERIC_TOKEN = re.compile(r'([a-z]*)(\d[\d,]*(?:\.\d+)?)')

_QUARTERS = {'q1': 'first quarter', 'q2': 'second quarter',
             'q3': 'third quarter', 'q4': 'fourth quarter'}


def normalize_text(text: str) -> str:
    """Lowercase, ASCII-fold quotes/dashes, collapse whitespace."""
    return ' '.join(str(text or '').translate(_SMART_CHARS).lower().split())


def _anchor_windows(quote: str, source: str) -> list[str]:
    """Candidate source windows found by exact word-run anchors from the quote.

    A contiguous fuzzy match must share *some* exact run of words with the
    source; scanning only around those runs keeps the check fast enough for a
    45k-claim backfill.
    """
    words = quote.split()
    if not words:
        return []
    anchors = []
    for start in (0, max(0, len(words) // 2 - 2), max(0, len(words) - 4)):
        anchor = ' '.join(words[start:start + 4])
        if len(anchor) >= 8:
            anchors.append(anchor)
    windows = []
    span = len(quote) + 40
    for anchor in anchors:
        pos = source.find(anchor)
        while pos != -1:
            lo = max(0, pos - span)
            windows.append(source[lo:pos + span])
            if len(windows) >= 24:  # pathological repetition guard
                return windows
            pos = source.find(anchor, pos + 1)
    return windows


def quote_verifies(quote: str, source_text: str,
                   threshold: float = QUOTE_MATCH_RATIO) -> bool:
    """True when `quote` appears as a contiguous (fuzzy) span of `source_text`.

    Empty quotes pass — there is nothing to misattribute. Scattered fragments
    that only match piecewise (a composed quote) fail: matching is anchored on
    exact word runs and scored per candidate window, not over the whole text.
    """
    q = normalize_text(quote)
    if not q:
        return True
    s = normalize_text(source_text)
    if not s:
        return False
    if q in s:
        return True
    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq2(q)
    for window in _anchor_windows(q, s):
        matcher.set_seq1(window)
        # Coverage of the quote inside this one window. The window is barely
        # longer than the quote, so piecewise matches scattered across the
        # source (a composed quote) can never assemble a passing score here.
        covered = sum(b.size for b in matcher.get_matching_blocks())
        if covered / len(q) >= threshold:
            return True
    return False


def statistic_verifies(statistic: str, source_text: str) -> bool:
    """True when every numeric token in `statistic` appears in `source_text`.

    Digit strings are compared with separators stripped, so "1,337" only
    passes when the source contains 1337 in some punctuation. Small integers
    also accept their spelled-out form ("6x" ↔ "six times"). Attribution
    prose around the numbers is not checked — numbers are the payload.
    """
    stat = normalize_text(statistic)
    if not stat:
        return True
    source = normalize_text(source_text)
    if not source:
        return False
    source_digits = re.sub(r'(?<=\d),(?=\d)', '', source)
    tokens = _NUMERIC_TOKEN.findall(stat)
    if not tokens:
        # A "statistic" with no number in it is not a statistic.
        return False
    for prefix, token in tokens:
        bare = token.replace(',', '')
        compound = prefix + bare
        if prefix:
            # "q1", "fy26", "h2": the compound is the fact, not the digit.
            if compound in source_digits:
                continue
            spelled = _QUARTERS.get(compound)
            if spelled and spelled in source:
                continue
            # A letter-prefixed digit is period/label shorthand, not a
            # standalone figure — don't fail the statistic over its absence.
            continue
        if re.search(rf'(?<![\d.]){re.escape(bare)}(?![\d])', source_digits):
            continue
        try:
            value = int(bare) if '.' not in bare else None
        except ValueError:
            value = None
        if value is not None and value in _SPELLED_NUMBERS \
                and re.search(rf'\b{_SPELLED_NUMBERS[value]}\b', source):
            continue
        return False
    return True


def verify_claim_against_source(claim: dict, source_text: str) -> tuple[dict, list[str]]:
    """Downgrade unverifiable fields in an extracted claim dict.

    Returns (claim, downgrades) where downgrades names what was dropped:
    'quote' and/or 'statistic'. The claim dict is modified in place.
    """
    downgrades: list[str] = []
    if claim.get('quote') and not quote_verifies(claim['quote'], source_text):
        claim['quote'] = ''
        downgrades.append('quote')
    if claim.get('has_statistic'):
        if not statistic_verifies(claim.get('statistic') or '', source_text):
            claim['has_statistic'] = False
            claim['statistic'] = ''
            downgrades.append('statistic')
    return claim, downgrades
