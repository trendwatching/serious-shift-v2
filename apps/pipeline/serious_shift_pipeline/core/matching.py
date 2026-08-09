"""Score how well an innovation matches a shift.

Pure: no database, no network, no model. Everything here is a function of its
arguments, which is what lets the interesting decisions — the weights, the
thresholds, the stoplist — be tested directly instead of inferred from a run.

The problem this solves is narrower than it looks. Every shift on the site is
about AI, so a naive bag-of-words match scores everything against everything at
roughly the same warmth. The discrimination comes from computing IDF **over the
shift corpus itself**: a term that appears in all 52 shifts carries no
information about which one an innovation belongs to, and is driven to zero
automatically rather than by maintaining a blocklist of this year's buzzwords.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

# ── Weights and thresholds ──────────────────────────────────────────────────
#
# Tunable at runtime via SS_CLASSIFY_* so a threshold can be moved without a
# deploy; these are the defaults.

W_LEX, W_FACET, W_BRAND = 0.55, 0.30, 0.15

#: Sigmoid midpoint and steepness mapping a raw score to a confidence.
#: raw .24 → .19 | .32 → .43 | .34 → .50 | .41 → .72 | .45 → .83 | .55 → .95
SIG_MID, SIG_K = 0.34, 0.07

#: Link it. This is `confidence(SIG_MID)` exactly — the midpoint the scorer was
#: centred on, three lines above, in code written before any of the evidence
#: below existed. "Link at or above your own calibration centre" is the whole
#: justification, and it does not depend on any particular corpus.
#:
#: It was 0.72, and 0.72 was an artifact. It is the value that makes
#: `test_a_textbook_example_clears_accept` pass on a TWO-shift corpus where the
#: innovation restates the shift almost verbatim: with n=2 the IDF is flat and
#: the cosine is enormous. Across 306 AI-about-AI shifts an IDF-weighted cosine
#: between two ~200-word documents structurally lives at 0.1–0.4, so 0.72 could
#: not be reached by a real match and the classifier linked nothing at all.
#:
#: Measured on staging's real corpus, the best genuine match scored 0.536
#: (a multilingual public-services chatbot → "Institutional Collapse") with the
#: runner-up at 0.426; the clearest non-match topped out at 0.237. So the usable
#: band is (0.426, 0.536]: above it the good match stops linking, at or below it
#: a second, weaker shift joins. 0.50 sits inside with room either side.
#: `tests/test_classifier_calibration.py` derives that band from the recorded
#: scores and fails if this constant leaves it.
#:
#: Do NOT pair this with a margin/gap rule: measured, the non-match had the
#: LARGER gap to its runner-up (0.176 vs 0.110), because a gap measures the
#: runner-up's weakness, not the winner's strength. On a corpus of overlapping
#: shifts a near-tie is evidence the scorer is working.
ACCEPT = 0.50
FLOOR = 0.45        # below this, never link — not even the model's pick
TIE_MARGIN = 0.06   # three candidates this close is a tie, not a ranking
MAX_KEY_LINKS, MAX_SUB_LINKS = 2, 2
SHORTLIST = 8       # candidates offered to the model when escalating

#: Facets and what they are matched against. Geography carries weight 0 and is
#: absent: every innovation has a region and a country, and neither
#: discriminates between shifts that are all global. Including them added noise
#: to every score and signal to none.
FACET_WEIGHTS = {
    'industry': 0.6,
    'subindustry': 0.4,
    'basic-human-need': 0.8,
    'innovation-type': 0.6,
    'audience': 0.4,
}

#: Minimum summed IDF of the terms shared with a facet's target text before it
#: counts as a hit. A single common word overlapping is not a match.
FACET_HIT_IDF = 4.0

STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be because been
before being below between both but by can cannot did do does doing down during each
few for from further had has have having her here hers him his how i if in into is it
its itself just me more most my no nor not now of off on once only or other our out
over own same she should so some such than that the their them then there these they
this those through to too under until up very was we were what when where which while
who whom why will with would you your
""".split())

#: Terms every shift shares. IDF would flatten most of these anyway; dropping
#: them first keeps the vectors small and makes the scores easier to read when
#: debugging a bad match.
DOMAIN_STOPWORDS = frozenset("""
ai agi artificial intelligence shift shifts consumer consumers brand brands new model
models data technology tech digital platform platforms company companies world people
future work business market markets product products service services
""".split())

_WORD = re.compile(r'[^a-z0-9]+')
_SUFFIXES = (('ies', 'y'), ('sses', 'ss'), ('ing', ''), ('ed', ''), ('es', ''), ('s', ''))


def _stem(token: str) -> str:
    """Six deterministic suffix rules. Not linguistics — just enough that
    "agents"/"agent" and "verifying"/"verified" land on the same key."""
    for suffix, replacement in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) + len(replacement) >= 4:
            return token[: len(token) - len(suffix)] + replacement
    return token


def normalize(text) -> list[str]:
    """Text → comparable terms. NFKD-folded, lowercased, stopped and stemmed."""
    folded = unicodedata.normalize('NFKD', str(text or ''))
    ascii_only = ''.join(c for c in folded if not unicodedata.combining(c)).lower()
    out = []
    for raw in _WORD.split(ascii_only):
        if len(raw) < 3 or raw in STOPWORDS or raw in DOMAIN_STOPWORDS:
            continue
        stem = _stem(raw)
        if len(stem) >= 3 and stem not in STOPWORDS and stem not in DOMAIN_STOPWORDS:
            out.append(stem)
    return out


def weighted_terms(parts: list[tuple[object, int]]) -> Counter:
    """Term counts from (text, multiplicity) pairs. Multiplicity is how much a
    field is worth: a shift's name says far more about what it is about than a
    sentence buried in its narrative panel."""
    counts: Counter = Counter()
    for text, weight in parts:
        if not text or weight <= 0:
            continue
        for term in normalize(text):
            counts[term] += weight
    return counts


@dataclass
class ShiftDoc:
    """One candidate. `ref` is `"<scope>:<slug>"`, the key the links table uses."""
    ref: str
    scope: str
    slug: str
    domain_id: str = ''
    name: str = ''
    parent_ref: str | None = None
    terms: Counter = field(default_factory=Counter)
    #: Sector name → that sector's note, for the facet channel.
    sector_text: dict = field(default_factory=dict)
    needs_text: str = ''
    territories_text: str = ''
    #: The from→to pair, which the escalation prompt calls the shift's spine.
    #: `from_text` existed nowhere, so the catalogue sent to the model hardcoded
    #: `'from': ''` — the prompt asked whether an innovation sits on the `to`
    #: side rather than merely illustrating the `from`, and then withheld the
    #: `from`.
    from_text: str = ''
    to_text: str = ''
    audience_text: str = ''
    raw_lower: str = ''
    vector: dict = field(default_factory=dict)


@dataclass
class InnovationDoc:
    id: int
    terms: Counter = field(default_factory=Counter)
    #: facet → [slug]
    tags: dict = field(default_factory=dict)
    #: Multi-word brand names, lowercased, for the exact-phrase channel.
    brand_phrases: list = field(default_factory=list)


def _l2(vec: dict) -> dict:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    return {k: v / norm for k, v in vec.items()} if norm else {}


class Corpus:
    """The shift set, with IDF computed across it."""

    def __init__(self, shifts: list[ShiftDoc]):
        self.shifts = shifts
        n = len(shifts)
        df: Counter = Counter()
        for shift in shifts:
            df.update(set(shift.terms))
        self.idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
        # A term the corpus has never seen is maximally distinctive, not
        # unknown — an innovation naming a brand no shift mentions should not be
        # penalised for it.
        self.idf_max = math.log(n + 1) + 1 if n else 1.0
        for shift in shifts:
            shift.vector = _l2({t: c * self.idf.get(t, self.idf_max) for t, c in shift.terms.items()})

    def lexical(self, innovation: InnovationDoc, shift: ShiftDoc) -> float:
        vec = _l2({t: c * self.idf.get(t, self.idf_max) for t, c in innovation.terms.items()})
        return sum(v * shift.vector.get(t, 0.0) for t, v in vec.items())

    def idf_overlap(self, terms, text) -> float:
        target = set(normalize(text))
        return sum(self.idf.get(t, self.idf_max) for t in set(terms) & target)


def facet(corpus: Corpus, innovation: InnovationDoc, shift: ShiftDoc, sector_of) -> float:
    """How well the innovation's structured tags line up with this shift.

    Only facets the innovation actually carries contribute to the denominator,
    so an innovation tagged with nothing but a region scores 0 rather than being
    punished for the tags it lacks.
    """
    hits = weight = 0.0
    terms = set(innovation.terms)
    for name, w in FACET_WEIGHTS.items():
        slugs = innovation.tags.get(name) or []
        if not slugs:
            continue
        weight += w
        if name in ('industry', 'subindustry'):
            sectors = [sector_of(s) for s in slugs]
            target = ' '.join(shift.sector_text.get(s, '') for s in sectors if s)
        elif name == 'basic-human-need':
            target = shift.needs_text
        elif name == 'innovation-type':
            target = f'{shift.territories_text} {shift.to_text}'
        else:
            target = shift.audience_text
        if target and corpus.idf_overlap(terms, target) >= FACET_HIT_IDF:
            hits += w
    return hits / weight if weight else 0.0


def brand(innovation: InnovationDoc, shift: ShiftDoc) -> float:
    """1.0 when a shift names one of the innovation's brands outright. Rare, and
    close to decisive when it happens."""
    return 1.0 if any(p in shift.raw_lower for p in innovation.brand_phrases) else 0.0


def confidence(raw: float) -> float:
    return round(1 / (1 + math.exp(-(raw - SIG_MID) / SIG_K)), 3)


@dataclass
class Scored:
    ref: str
    scope: str
    parent_ref: str | None
    confidence: float
    lexical: float
    facet: float
    brand: float

    @property
    def note(self) -> str:
        """Stored on the link, so a curator can see why the machine proposed it.

        Carries the threshold in force, because that number has moved once and
        will move again: without it, a row written at 0.50 is indistinguishable
        from one written at 0.72 and nobody can answer "why is this card here"
        six months later.
        """
        return f'auto@{ACCEPT:.2f}: lex {self.lexical:.2f} facet {self.facet:.2f}'


def available_weight(innovation: InnovationDoc) -> float:
    """Total weight of the channels this innovation can actually be judged on.

    An innovation with no tags and no multi-word brand can only be scored
    lexically. Dividing its lexical score by the full 1.0 would cap it at 0.55
    however perfect the match is, so a textbook example would never clear
    `ACCEPT` — which is precisely the bug this function exists to prevent.

    Note the distinction: a channel is *unavailable* when the innovation has no
    input for it, not when the input scored zero. An innovation that does carry
    tags and matches none of the shift's is genuinely a poor match, and that
    zero must count against it.
    """
    weight = W_LEX
    if any(innovation.tags.get(f) for f in FACET_WEIGHTS):
        weight += W_FACET
    if innovation.brand_phrases:
        weight += W_BRAND
    return weight


def score_all(corpus: Corpus, innovation: InnovationDoc, sector_of, *, exclude=()) -> list[Scored]:
    """Every candidate, best first. `exclude` drops refs an editor already owns."""
    out = []
    scale = available_weight(innovation)
    for shift in corpus.shifts:
        if shift.ref in exclude:
            continue
        lex = corpus.lexical(innovation, shift)
        fac = facet(corpus, innovation, shift, sector_of)
        bra = brand(innovation, shift)
        raw = (W_LEX * lex + W_FACET * fac + W_BRAND * bra) / scale
        out.append(Scored(shift.ref, shift.scope, shift.parent_ref, confidence(raw), lex, fac, bra))
    out.sort(key=lambda s: (-s.confidence, s.ref))
    return out


def is_ambiguous(keys: list[Scored], *, accept=ACCEPT, floor=FLOOR, margin=TIE_MARGIN) -> bool:
    """Whether this innovation is worth a model call.

    Two shapes qualify: a best guess that is plausible but not convincing, and a
    photo finish between three or more. Everything else the arithmetic already
    answers, and paying for a second opinion on an obvious case is waste.

    Since `ACCEPT` moved to 0.50 the first branch spans only [0.45, 0.50) and
    rarely fires. That is deliberate, and it leaves escalation the job it is
    better at: the tie. "Which of these three" is a judgement a model can make;
    "is 0.61 good enough" is arithmetic that does not need one.
    """
    if not keys:
        return False
    top = keys[0].confidence
    if floor <= top < accept:
        return True
    return len(keys) >= 3 and top >= accept and keys[2].confidence >= top - margin


def choose(scored: list[Scored], *, key_budget=MAX_KEY_LINKS, sub_budget=MAX_SUB_LINKS,
           accept=ACCEPT, owned_parents=()) -> list[Scored]:
    """The deterministic pick: accepted key shifts, plus sub-shifts *beneath an
    accepted parent only*.

    That parent rule is the one that keeps the pages coherent. Without it an
    innovation can surface on a child page whose parent page does not show it,
    which reads to a reader as a bug in the site rather than a judgement call.

    `owned_parents` are key-shift refs a curator or the upstream has ALREADY
    linked and that are still published. They satisfy the parent rule just as
    well as a pick made in this pass — the parent page does show the innovation,
    it simply shows it because a human said so. Without them, an innovation whose
    key shift is curated could never gain a sub-shift link: its `key_budget` is
    spent, so `keys` is empty, so `parents` is empty, so every child is rejected
    however well it scores.

    Note `key_budget` must not be negative. `keys[:-1]` drops the last accepted
    shift and keeps the others, which is the opposite of "no room"; callers clamp
    at zero.
    """
    keys = [s for s in scored if s.scope == 'key_trend' and s.confidence >= accept][:key_budget]
    parents = {s.ref for s in keys} | set(owned_parents)
    subs = [
        s for s in scored
        if s.scope == 'sub_trend' and s.parent_ref in parents and s.confidence >= accept
    ][:sub_budget]
    return keys + subs
