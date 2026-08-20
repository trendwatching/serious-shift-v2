"""Pre-publication validation for the routed Serious Shift map."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from ..core.text import url_slug as slugify
from .config import (DOMAINS, MAX_KTS_PER_DOM, MAX_SUB_TRENDS,
                     MIN_KTS_PER_DOM, MIN_SUB_TRENDS, load_gates)
from .modules import (_LEAKED_BARE, _LEAKED_CREF, _LEAKED_PAREN, NOT_PROSE,
                      FIELD_WORD_LIMITS, LIST_ITEM_WORD_LIMITS, PAIR_TEXT_WORD_LIMITS,
                      STEP_TEXT_WORD_LIMIT, UNAUTHORED_MODULE_TYPES, count_words,
                      figure_echoes, stat_claim_key)
from .naming import NAME_FAMILY_CAP, family_keys
from .phases.hero_stats import stat_matches_shift

#: A stat band displays a statistic, and a statistic contains a number.
_HAS_DIGIT = re.compile(r'\d')


def _leaked_identifiers(value, path: str) -> list[tuple[str, str]]:
    """Every (path, match) where a database identifier reached reader-facing copy.

    Walks module data rather than checking named fields, because the leak lands
    wherever the model happened to put it: it has appeared in a stat band's
    `source`, an evidence item's `text`, and a voices quote.
    """
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in NOT_PROSE:
                continue
            found += _leaked_identifiers(nested, f'{path}.{key}')
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found += _leaked_identifiers(nested, f'{path}[{index}]')
    elif isinstance(value, str):
        for pattern in (_LEAKED_PAREN, _LEAKED_BARE, _LEAKED_CREF):
            match = pattern.search(value)
            if match:
                found.append((path, match.group(0).strip()))
                break
    return found


REQUIRED_MODULES = {
    'key_trend': {
        'dek', 'from_to', 'pull_quote', 'peel_tabs', 'human_needs',
        'tension_band', 'timeline', 'industries', 'territories', 'sub_shift_list',
    },
    'sub_trend': {
        'lede', 'from_to_solid', 'tension_band', 'peel_tabs', 'human_needs',
        'signals', 'counter_signals', 'evidence', 'timeline', 'territories',
    },
}

#: Imported, not restated. Every one of these caps has a clamp on the writing
#: side that must satisfy it, and two copies of a number drift.
WORD_LIMITS = FIELD_WORD_LIMITS
ITEM_WORD_LIMITS = LIST_ITEM_WORD_LIMITS


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str
    repairable: bool = False


class PublicationValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__(f"candidate map failed validation with {len(issues)} issue(s)")

    def detail(self) -> dict:
        return {"validation": {"issue_count": len(self.issues),
                               "issues": [asdict(issue) for issue in self.issues]}}


def _http_url(value) -> bool:
    try:
        parsed = urlparse(str(value or '').strip())
        return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)
    except ValueError:
        return False


def _load_contract() -> dict:
    from ..paths import contracts_dir

    return json.loads((contracts_dir() / 'shift_modules.json').read_text(encoding='utf-8'))


def _name_key(value) -> str:
    """Names compared the way URLs compare them.

    Two names that slugify the same ARE one page as far as a reader, a link and
    every slug-keyed manifest are concerned, so "Proof Premium", "proof premium"
    and "Proof  Premium" must not be three distinct names here.
    """
    return slugify(str(value or '')) or ''


def _duplicates(values) -> set:
    seen, dupes = set(), set()
    for value in values:
        if value in seen:
            dupes.add(value)
        seen.add(value)
    return dupes


def _missing(value) -> bool:
    return value is None or value == '' or value == [] or value == {}


#: The gate and the write-time clamp must agree on what a word is, or a field
#: can be trimmed to the limit and still be rejected for exceeding it. One
#: definition, in modules.py, next to the clamp that has to satisfy it.
_words = count_words


def _claim_number(value) -> int | None:
    try:
        return int(str(value).removeprefix('c_'))
    except (TypeError, ValueError):
        return None


def _editorial_citations(row: dict) -> set[int]:
    for module in row.get('modules') or []:
        if module.get('type') == 'peel_tabs':
            return {
                number for value in (module.get('data') or {}).get('evidence_ids') or []
                if (number := _claim_number(value)) is not None
            }
    return set()


def _validate_modules(modules, scope: str, path: str, contract: dict) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(modules, list):
        return [ValidationIssue('modules_type', f'{path}.modules', 'modules must be a list', True)]

    declared = contract.get('types') or {}
    order = (contract.get('order') or {}).get(scope) or []
    ranks, last_rank = {name: i for i, name in enumerate(order)}, -1
    industry_modules = 0
    present: list[str] = []
    for index, module in enumerate(modules):
        module_path = f'{path}.modules[{index}]'
        if not isinstance(module, dict):
            issues.append(ValidationIssue('module_type', module_path, 'module must be an object', True))
            continue
        type_ = module.get('type')
        if type_ not in declared:
            issues.append(ValidationIssue('unknown_module', f'{module_path}.type',
                                          f'unknown module type {type_!r}', True))
            continue
        present.append(str(type_))
        rank = ranks.get(type_, len(order))
        if rank < last_rank:
            issues.append(ValidationIssue('module_order', module_path,
                                          f'{type_!r} is outside canonical {scope} order', True))
        last_rank = max(last_rank, rank)
        data = module.get('data')
        if not isinstance(data, dict):
            issues.append(ValidationIssue('module_data', f'{module_path}.data',
                                          'module data must be an object', True))
            continue
        for field in declared[type_].get('required') or []:
            if _missing(data.get(field)):
                issues.append(ValidationIssue('required_module_field', f'{module_path}.data.{field}',
                                              f'{type_} requires {field}', True))
        for (limited_type, field), limit in WORD_LIMITS.items():
            if type_ == limited_type and _words(data.get(field)) > limit:
                issues.append(ValidationIssue(
                    'editorial_length', f'{module_path}.data.{field}',
                    f'{field} exceeds {limit} words', True,
                ))

        # from_to, from_to_solid and human_needs used to be checked again here,
        # by hand. They are entries in FIELD_WORD_LIMITS now, so the loop above
        # covers them and a second check only reported each overrun twice.
        if type_ == 'timeline':
            for item_index, item in enumerate(data.get('steps') or []):
                if isinstance(item, dict) and _words(item.get('text')) > STEP_TEXT_WORD_LIMIT:
                    issues.append(ValidationIssue(
                        'editorial_length', f'{module_path}.data.steps[{item_index}].text',
                        f'timeline step exceeds {STEP_TEXT_WORD_LIMIT} words', True,
                    ))
        if type_ in ITEM_WORD_LIMITS:
            limit = ITEM_WORD_LIMITS[type_]
            for item_index, item in enumerate(data.get('items') or []):
                if _words(item) > limit:
                    issues.append(ValidationIssue(
                        'editorial_length', f'{module_path}.data.items[{item_index}]',
                        f'{type_} item exceeds {limit} words', True,
                    ))

        if type_ == 'industries':
            industry_modules += 1
            names = [item.get('name') for item in data.get('items') or [] if isinstance(item, dict)]
            expected = contract.get('industry_sectors') or []
            if names != expected:
                issues.append(ValidationIssue(
                    'industries_contract', f'{module_path}.data.items',
                    f'industries must contain all {len(expected)} canonical sectors '
                    'exactly once and in order', True,
                ))

        if type_ in {'evidence', 'voices'}:
            buckets = [data.get('items') or []] if type_ == 'evidence' else [
                data.get('proponents') or [], data.get('skeptics') or [],
            ]
            for bucket in buckets:
                for item_index, item in enumerate(bucket):
                    if not isinstance(item, dict) or not _http_url(item.get('url')):
                        issues.append(ValidationIssue(
                            'source_url', f'{module_path}.data[{item_index}].url',
                            f'every published {type_} item requires a valid HTTP(S) source URL', True,
                        ))
        if type_ == 'evidence' and len(data.get('items') or []) < 2:
            issues.append(ValidationIssue(
                'evidence_coverage', f'{module_path}.data.items',
                'every sub-shift requires at least two independently routed evidence items', True,
            ))
        if type_ == 'stat_band' and not _http_url(data.get('url')):
            issues.append(ValidationIssue(
                'source_url', f'{module_path}.data.url',
                'a published statistic requires a valid HTTP(S) source URL', True,
            ))
        # The band sets `value` at ~99px as the page's headline statistic, so it
        # has to be a statistic. "multi-hop" shipped once because the reducer only
        # checked length.
        if type_ == 'stat_band' and not _HAS_DIGIT.search(str(data.get('value') or '')):
            issues.append(ValidationIssue(
                'stat_band_numeral', f'{module_path}.data.value',
                'a stat band must display a figure containing a numeral', True,
            ))
        # Belt and braces on strip_identifiers: the prompts forbid it, clamp_words
        # removes it, and this makes a leak unpublishable rather than merely
        # unlikely. Published copy carries a real person's name.
        for leaf_path, leaked in _leaked_identifiers(data, f'{module_path}.data'):
            issues.append(ValidationIssue(
                'leaked_identifier', leaf_path,
                f'published copy contains a database identifier ({leaked!r})', True,
            ))
        if type_ in {'industries', 'territories'}:
            for item_index, item in enumerate(data.get('items') or []):
                if isinstance(item, dict) and _words(item.get('text')) > PAIR_TEXT_WORD_LIMITS[type_]:
                    issues.append(ValidationIssue(
                        'editorial_length', f'{module_path}.data.items[{item_index}].text',
                        f'{type_} text is too long', True,
                    ))
    for missing_type in sorted(REQUIRED_MODULES.get(scope, set()) - set(present)):
        issues.append(ValidationIssue(
            'required_module', f'{path}.modules',
            f'{scope} is missing required module {missing_type!r}', True,
        ))
    if scope == 'key_trend' and industry_modules != 1:
        issues.append(ValidationIssue(
            'industries_contract', f'{path}.modules',
            f'expected exactly one industries module, found {industry_modules}', True,
        ))
    return issues


#: British spellings the content spec forbids. Matched LOWERCASE only, because
#: the capitalised forms are almost always proper nouns we must not rewrite —
#: "Centre for AI Safety", "Ministry of Defence", "the Labour Party".
#:
#: `voice.txt` has said "US spelling only" all along; it is instruction, and
#: instruction is not a gate. The 2026-08-09 crawl found "catalogued" and
#: "organisation" sitting in published copy. It does not help that the prompt
#: files are themselves written in British English — "synthesising",
#: "recognise" — two lines above the rule telling the model not to.
#: The suffixes are spelled out rather than left as `\w*`, because the greedy
#: version fails on correct US English: `optimis\w*` matches "optimism" and
#: "optimistic", `realis\w*` matches "realistic", `cancell\w*` matches
#: "cancellation", and `organis\w*` matches "organism". Running it over the live
#: map produced 26 hits of which 20 were false — a gate that rejects correct copy
#: gets switched off. "analyses" is deliberately absent: it is both a British
#: verb and the universal plural of "analysis", and there is no way to tell them
#: apart here.
_BRITISH = re.compile(
    r'\b('
    r'organis(?:e|es|ed|ing|ation|ations|ational)|'
    r'catalogu(?:e|es|ed|ing)|behaviour(?:s|al|ally)?|programme(?:s)?|'
    # NOT programmed: that is the standard US past tense of "program"
    # (Merriam-Webster's primary form), and the `d` alternative failed
    # three correct sentences on the 18 Aug 2026 run. The trailing \b
    # already keeps `programme` from matching inside it.
    r'centre[sd]?|recognis(?:e|es|ed|ing|able)|'
    r'optimis(?:e|es|ed|ing|ation|ations)|realis(?:e|es|ed|ing|ation)|'
    r'utilis(?:e|es|ed|ing|ation)|analys(?:e|ed|ing)|'
    r'favourite?s?|colour(?:s|ed|ing|ful)?|labour(?:s|ed|ing)?|'
    r'defence|offence|licence[sd]?|practis(?:e|es|ed|ing)|'
    r'travell(?:ed|ing|er|ers)|modell(?:ed|ing)|cancell(?:ed|ing)|'
    r'apologis(?:e|es|ed|ing)|prioritis(?:e|es|ed|ing|ation)'
    r')\b'
)

#: A slug loose in prose. THREE segments minimum, and that bound is the whole
#: design: a two-segment slug is indistinguishable from ordinary hyphenated
#: English. Run over the live map, the two-segment version produced 54 hits and
#: essentially all of them were real writing — "switching-cost", "vendor-lock",
#: "fact-flooding" — that only matched because a shift happens to carry that
#: name. It would have rejected correct copy on almost every page.
#:
#: Three segments is rare enough in natural prose to be a signal:
#: `labor-displacement-gradient` and `demographic-weaponization` are what a
#: leaked identifier actually looks like. Digits allowed, because real slugs
#: carry them — `moat-migration-2` was a published URL.
_SLUGGISH = re.compile(r'\b[a-z0-9]+(?:-[a-z0-9]+){2,}\b')

#: Fields that quote a human being. Their spelling is THEIRS: "correcting"
#: labour to labor inside a quotation misquotes the person who said it.
_QUOTED = frozenset({'quote'})

#: Module types whose text is scraped source material or code-derived data,
#: not authored editorial. A lint that fires on a source author's em dash asks
#: the repair pass to rewrite a quotation it must never touch — the issue can
#: only loop. One definition, in modules.py, shared with the dash-conform pass
#: so the writer and the gate agree on what "authored" means.
_UNAUTHORED_TYPES = UNAUTHORED_MODULE_TYPES

#: An em dash, or a spaced en dash doing an em dash's job. The voice file has
#: banned them since the redesign ("No em dashes; use a period or a comma") and
#: the ban was advisory — nothing rejected one. A bare en dash stays legal:
#: "1–3 years" and "ages 18–34" are ranges, not rhetoric.
_EM_DASH = re.compile(r'—|\s–\s')

#: Vocabulary that reads as generated rather than written. Deliberately tiny —
#: the `_BRITISH` calibration lesson applies with force here, since half the
#: internet now writes like this on purpose. Each entry is a phrase the voice
#: file already bans or a word ("delve") with no innocent use in this corpus;
#: anything broader must be calibrated against the live map before it ships.
_AI_TELL = re.compile(
    r'\b(delv(?:e|es|ed|ing)|'
    r"it(?:\s+is|['’]s)\s+worth\s+noting|"
    r'at the end of the day|it goes without saying|'
    r"in today['’]s rapidly|rapidly evolving landscape|"
    r'is a testament to)\b', re.IGNORECASE)

#: A counter-signal that audits the study instead of the world. Scoped to
#: counter_signals items ONLY, and deliberately four patterns: "survey" and
#: "peer-reviewed" are unsafe ("MIT reported adoption stalling in a
#: peer-reviewed study" is a legitimate counter-signal), so the lint catches
#: the flagrant methods-appendix register and the rewritten prompt spec does
#: the rest.
_METHODS_AUDIT = re.compile(
    r'\b(sample size|self-reported|methodolog\w*|generalizab\w*)\b',
    re.IGNORECASE)


# ── Content gates (2026-08-10) ────────────────────────────────────────────────
#
# Everything above validates FORM; the checks below validate CONTENT. Each one
# encodes a defect class the 2026-08-10 audit found in the published map, so
# that class of document can never promote again. Population-level checks
# (counts, distributions, cross-page frequency) engage only when the document
# is map-sized — the unit-test fixtures are four shifts and would trip them
# meaninglessly.

# Threshold VALUES live in packages/contracts/gates.json so every change is a
# reviewed diff; the rationale for each number stays here, beside its consumer.
_GATES = load_gates()

#: Below this many key shifts, population-level gates stay quiet.
FULL_MAP_MIN_SHIFTS = int(_GATES.get('full_map_min_shifts', 10))

#: A velocity distribution where one bucket holds more than this share of
#: shifts is prompt-anchoring, not grading ("accelerating" × 51).
VELOCITY_MAX_SHARE = float(_GATES.get('velocity_max_share', 0.8))

#: At least this share of key shifts must carry a stat_band.
#:
#: Lowered from 0.6 on the 18 Aug 2026 review, when the key-shift ceiling rose to
#: 15. Hero statistics are assigned EXCLUSIVELY — one claim fronts one shift —
#: from the claims routed to that shift's own children, so the number of shifts
#: that can carry one is bounded by topically-matched supply, not by effort. A
#: 36-shift map reached 19/36 = 53% and failed this gate; a 60-shift map needs
#: 36 distinct on-topic statistics to clear 0.6. The claim budget rising to 350
#: per domain is what actually improves coverage; this floor stops the gate
#: failing a map for a shortage the generator cannot invent its way out of.
STAT_COVERAGE_FLOOR = float(_GATES.get('stat_coverage_floor', 0.45))

#: A proper-noun bigram may headline at most this many shift FAMILIES ("Adam
#: Raine" carried ~12); a bare figure gets more slack (different 40%s exist).
#: The unit is the family — a parent and its five children legitimately share
#: their own evidence (Loudoun County on the Compute shift and two of its
#: sub-shifts is cohesion); the same number fronting unrelated shifts is the
#: crutch the audit found.
#: These are ABSOLUTE counts of families, so they tighten as the map grows: at
#: 36 families a recurring name had 36 chances to exceed 4, at 60 it has 60.
#: Scaled with the ceiling so the rule keeps meaning "a handful of pages", not
#: "a progressively smaller fraction".
CRUTCH_ENTITY_PAGE_LIMIT = int(_GATES.get('crutch_entity_page_limit', 6))
CRUTCH_FIGURE_PAGE_LIMIT = int(_GATES.get('crutch_figure_page_limit', 9))

#: How many sub-shifts one claim may anchor, as a share of the map's sub-shifts.
#: At 180 sub-shifts this reproduces the historical cap of 3; at 300 it gives 5.
EVIDENCE_REUSE_SHARE = float(_GATES.get('evidence_reuse_share', 3 / 180))

#: Everyday bigrams/figures that legitimately recur across an AGI map.
#: Frontier-model names are domain vocabulary here, like "AI" itself.
#: Thinker names are exempted dynamically in validate_map — attributing
#: evidence to its (prolific) author is citation, not anecdote recycling;
#: "Adam Raine" and "GrandChef" stay caught because they are subjects of
#: claims, not authors of them.
CRUTCH_WHITELIST = frozenset({
    'artificial intelligence', 'united states', 'serious shift', 'new york',
    'silicon valley', 'san francisco',
    'claude opus', 'claude sonnet', 'claude haiku', 'chat gpt',
})

#: Centerpiece fields per module type: the prose that headlines a page. Body
#: fields (signals, industries, timeline) may legitimately share supporting
#: facts; centerpieces may not.
_CENTERPIECE_FIELDS = {
    'dek': ('text',), 'lede': ('text',), 'pull_quote': ('quote',),
    'tension_band': ('quote',), 'stat_band': ('value', 'text'),
    'peel_tabs': ('whats_changing', 'why_now'),
}

#: Internal vocabulary that must never reach a reader. "sub-trend" is the
#: pipeline's name; published surfaces say "sub-shift". One published lede
#: opened "The two allowed evidence records for this sub-trend cover…".
#: Calibrated against the 2026-08-09 live map: "prompt injection" and a
#: litigation sentence about "isolated evidence records" are legitimate AI/legal
#: prose, so the patterns match the self-referential phrasings, not the nouns.
_META_LANGUAGE = re.compile(
    r'\b(sub-?trends?|allowed evidence|assigned evidence|'
    r'evidence records? for|evidence blocks?|'
    r'claim pool|routed (?:claims?|to sibling)|word (?:limit|cap)s?|'
    r'editorial body|this dataset)\b', re.IGNORECASE)

#: Sector notes that say "this page has nothing for you" in a paid product.
#: An EMPTY note is legal (the canonical fill) and the reading view skips it;
#: prose that names its own irrelevance is filler wearing content's clothes.
_INDUSTRY_FILLER = re.compile(
    r'^\s*(?:peripheral|not directly|minimal(?:ly)?|'
    r'limited (?:direct )?(?:impact|relevance)|largely (?:unaffected|peripheral))',
    re.IGNORECASE)

_FIGURE_TOKEN = re.compile(r'[$€£]?\d[\d,]*(?:\.\d+)?%?')
_PROPER_BIGRAM = re.compile(r'\b([A-Z][a-z]+ [A-Z][a-z]+)\b')


def _norm_prose(value) -> str:
    return ' '.join(re.findall(r'[a-z0-9]+', str(value or '').lower()))


def _centerpiece_text(row: dict) -> str:
    parts = []
    hero = row.get('hero_stat')
    if isinstance(hero, dict):
        parts += [str(hero.get('value') or ''), str(hero.get('text') or '')]
    for module in row.get('modules') or []:
        if not isinstance(module, dict):
            continue
        fields = _CENTERPIECE_FIELDS.get(str(module.get('type') or ''))
        if not fields:
            continue
        data = module.get('data') or {}
        parts += [str(data.get(field) or '') for field in fields]
    # Newline-joined so a bigram can never straddle two fields — "Change" at
    # the end of one field and "Now" at the start of the next is not an entity.
    return '\n'.join(parts)


def _crutch_signatures(text: str) -> set[str]:
    """The distinctive tokens a page's centerpiece leans on."""
    signatures: set[str] = set()
    for match in _PROPER_BIGRAM.finditer(text):
        bigram = match.group(1).lower()
        if bigram not in CRUTCH_WHITELIST:
            signatures.add(f'entity:{bigram}')
    for token in _FIGURE_TOKEN.findall(text):
        token = token.rstrip(',.')
        bare = token.strip('$€£')
        digits = re.sub(r'\D', '', token)
        # A signature figure must carry a UNIT — %, currency, a decimal, or a
        # thousands separator — or be 5+ digits. Bare small integers ("30",
        # "88") collide across unrelated pages by coincidence, and bare years
        # are just evidence dating; calibrated on the 2026-08-09 live map,
        # where "2026," alone produced 42 false hits.
        distinctive = ('%' in token or token[0] in '$€£' or '.' in bare
                       or (',' in bare and len(digits) >= 4) or len(digits) >= 5)
        if not distinctive or re.fullmatch(r'(19|20)\d\d', digits):
            continue
        signatures.add(f'figure:{token.lower()}')
    return signatures


def _copy_strings(row: dict, path: str):
    """The three published fields no check has ever looked at, plus module prose.

    `sub_trends[].description` is the meta description seo.rs publishes verbatim,
    and until now nothing validated it at all.
    """
    for field in ('name', 'subtitle', 'description'):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            yield f'{path}.{field}', value


def _prose_strings(value, path: str, skip=frozenset()):
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in NOT_PROSE or key in skip:
                continue
            yield from _prose_strings(nested, f'{path}.{key}', skip)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _prose_strings(nested, f'{path}[{index}]', skip)
    elif isinstance(value, str):
        yield path, value


def _authored_strings(row: dict, base: str, skip=frozenset()):
    """Module prose the editorial phase actually WROTE — the only text a
    repairable prose lint may fire on, because it is the only text a repair
    regen can change. Skips `_UNAUTHORED_TYPES` wholesale; key-level skips
    (`_QUOTED`, 'source', 'label') are the caller's to choose."""
    for index, module in enumerate(row.get('modules') or []):
        if not isinstance(module, dict) or module.get('type') in _UNAUTHORED_TYPES:
            continue
        yield from _prose_strings(module.get('data') or {},
                                  f'{base}.modules[{index}].data', skip)


def validate_map(document: dict, contract: dict | None = None) -> list[ValidationIssue]:
    """Return every publication issue; an empty list is safe to promote."""
    contract = contract or _load_contract()
    issues: list[ValidationIssue] = []
    prose_seen: dict[str, str] = {}
    domains = document.get('domains') or []
    shifts = document.get('key_trends') or []
    subs = document.get('sub_trends') or []
    claims = document.get('claims') or []
    claim_sources = {
        number: claim.get('source_url')
        for claim in claims if isinstance(claim, dict)
        if (number := _claim_number(claim.get('id'))) is not None
    }

    domain_ids = [domain.get('id') for domain in domains if isinstance(domain, dict)]
    canonical_domains = [domain['id'] for domain in DOMAINS]
    if domain_ids != canonical_domains:
        issues.append(ValidationIssue('domains_contract', 'domains',
                                      f'domains must be unique and ordered as {canonical_domains}'))
    for duplicate in sorted(_duplicates(domain_ids)):
        issues.append(ValidationIssue('duplicate_domain', 'domains', f'duplicate domain id {duplicate!r}'))

    shift_ids = [shift.get('id') for shift in shifts if isinstance(shift, dict)]
    shift_by_id = {shift.get('id'): shift for shift in shifts if isinstance(shift, dict)}
    for duplicate in sorted(_duplicates(shift_ids)):
        issues.append(ValidationIssue('duplicate_shift_id', 'key_trends', f'duplicate shift id {duplicate!r}'))
    shift_routes = {
        f"/{shift.get('domain_id')}/{shift.get('slug')}"
        for shift in shifts if isinstance(shift, dict)
    }
    # GLOBAL, not grouped by sphere. Grouping was the hole: two spheres each
    # naming a shift "Moat Migration" produced no issue here, and export.py
    # quietly disambiguated the second one to `moat-migration-2` — a machine
    # slug in a published URL that nobody chose.
    for duplicate in sorted(_duplicates([shift.get('slug') for shift in shifts
                                         if isinstance(shift, dict)])):
        issues.append(ValidationIssue('duplicate_shift_slug', 'key_trends',
                                      f'duplicate shift slug {duplicate!r}'))

    # The check the slug check could never be. export.py disambiguates before
    # the gate sees the document, so `duplicate_shift_slug` above is an export
    # invariant that can only fire on an exporter regression — by the time it
    # runs, the second "Moat Migration" is already `moat-migration-2` and looks
    # unique. Nothing anywhere compared the NAMES, so two spheres could publish
    # the same shift name indefinitely, one of them at a URL nobody chose.
    for duplicate in sorted(_duplicates([_name_key(shift.get('name')) for shift in shifts
                                         if isinstance(shift, dict)])):
        if duplicate:
            issues.append(ValidationIssue('duplicate_shift_name', 'key_trends',
                                          f'two key shifts are named {duplicate!r}'))

    subs_by_parent: dict[str, list[dict]] = {}
    for index, sub in enumerate(subs):
        if not isinstance(sub, dict):
            issues.append(ValidationIssue('sub_type', f'sub_trends[{index}]', 'sub-shift must be an object'))
            continue
        subs_by_parent.setdefault(str(sub.get('key_trend_id') or ''), []).append(sub)

    for index, shift in enumerate(shifts):
        path = f'key_trends[{index}]'
        if not isinstance(shift, dict):
            issues.append(ValidationIssue('shift_type', path, 'shift must be an object'))
            continue
        if shift.get('domain_id') not in domain_ids:
            issues.append(ValidationIssue('shift_domain', f'{path}.domain_id', 'unknown parent domain'))
        children = subs_by_parent.get(str(shift.get('id') or ''), [])
        # MAX is the generation target; anything down to MIN publishes. Fewer
        # was legal from the 11 Aug 2026 review onward because an editor may
        # merge near-duplicate siblings (tutor-paradox absorbed
        # scaffold-dependency), and the floor dropped to MIN_SUB_TRENDS on
        # 18 Aug so a shift with genuinely three distinct sub-patterns is not
        # padded to five with a near-twin. Imported, never restated here: this
        # literal and the generator's disagreed for as long as both existed.
        if not MIN_SUB_TRENDS <= len(children) <= MAX_SUB_TRENDS:
            issues.append(ValidationIssue(
                'sub_shift_count', f'{path}.sub_trend_ids',
                f'expected {MIN_SUB_TRENDS}-{MAX_SUB_TRENDS} sub-shifts, '
                f'found {len(children)}', True))
        declared_children = shift.get('sub_trend_ids') or []
        actual_children = [sub.get('id') for sub in children]
        if declared_children != actual_children:
            issues.append(ValidationIssue('sub_shift_references', f'{path}.sub_trend_ids',
                                          'sub-shift references do not match ordered children'))
        issues.extend(_validate_modules(shift.get('modules'), 'key_trend', path, contract))

    # Also global. Grouping by parent meant six sub-shifts called "Provenance
    # Premium" under six different key shifts produced six disjoint lists and no
    # issue at all — seven pages carrying one name, since the key shift had it
    # too. A sub-shift's URL is unique beneath its parent, so this does not break
    # routing; it breaks the reader's ability to tell two pages apart.
    for duplicate in sorted(_duplicates([str(sub.get('slug') or '').rsplit('/', 1)[-1]
                                         for sub in subs if isinstance(sub, dict)])):
        issues.append(ValidationIssue('duplicate_sub_shift_slug', 'sub_trends',
                                      f'duplicate sub-shift slug {duplicate!r}'))

    # Names, not just slugs — same reason as duplicate_shift_name above.
    #
    # Not repairable, and deliberately so. naming.choose_unique makes this
    # impossible at the point of writing: a colliding candidate is replaced by
    # the next spare the model returned, and a shift publishes four children
    # rather than a twin. So reaching here means the writer regressed, and the
    # repair pass has nothing to offer — it re-runs editorial, which never
    # renames anything. Failing loudly beats spending a call to change nothing.
    for duplicate in sorted(_duplicates([_name_key(sub.get('name')) for sub in subs
                                         if isinstance(sub, dict)])):
        if duplicate:
            issues.append(ValidationIssue(
                'duplicate_sub_shift_name', 'sub_trends',
                f'two sub-shifts are named {duplicate!r} — one name, one page'))

    shift_name_keys = {_name_key(shift.get('name')) for shift in shifts
                       if isinstance(shift, dict)} - {''}
    for sub in subs:
        if not isinstance(sub, dict):
            continue
        sub_name_key = _name_key(sub.get('name'))
        if sub_name_key and sub_name_key in shift_name_keys:
            issues.append(ValidationIssue(
                'sub_shift_shadows_shift_name', f'sub_trends.{sub_name_key}',
                f'sub-shift {sub_name_key!r} is named after a key shift'))

    # And across the two levels: a sub-shift must not wear a key shift's name.
    shift_slugs = {str(shift.get('slug') or '') for shift in shifts if isinstance(shift, dict)}
    for sub in subs:
        if not isinstance(sub, dict):
            continue
        tail = str(sub.get('slug') or '').rsplit('/', 1)[-1]
        if tail and tail in shift_slugs:
            issues.append(ValidationIssue('sub_shift_shadows_shift', f'sub_trends.{tail}',
                                          f'sub-shift {tail!r} has the same name as a key shift'))

    for parent_id, children in subs_by_parent.items():
        parent = shift_by_id.get(parent_id)
        for index, sub in enumerate(children):
            path = f'sub_trends[{sub.get("id", index)}]'
            if parent is None:
                issues.append(ValidationIssue('sub_shift_parent', f'{path}.key_trend_id',
                                              'unknown parent shift'))
            elif sub.get('domain_id') != parent.get('domain_id'):
                issues.append(ValidationIssue('sub_shift_domain', f'{path}.domain_id',
                                              'sub-shift domain does not match parent'))
            expected_prefix = f"{parent.get('slug')}/" if parent else ''
            if expected_prefix and not str(sub.get('slug') or '').startswith(expected_prefix):
                issues.append(ValidationIssue('sub_shift_slug', f'{path}.slug',
                                              'sub-shift slug is not scoped to its parent'))
            issues.extend(_validate_modules(sub.get('modules'), 'sub_trend', path, contract))

            allowed = {
                number for value in sub.get('claim_ids') or []
                if (number := _claim_number(value)) is not None
            }
            cited = _editorial_citations(sub)
            if not 2 <= len(cited) <= 6 or not cited <= allowed:
                issues.append(ValidationIssue(
                    'editorial_provenance', f'{path}.modules.peel_tabs.data.evidence_ids',
                    'sub-shift editorial requires 2–6 citations from its own routed claims', True,
                ))
            for claim_id in cited:
                if not _http_url(claim_sources.get(claim_id)):
                    issues.append(ValidationIssue(
                        'editorial_provenance', f'{path}.modules.peel_tabs.data.evidence_ids',
                        f'cited claim c_{claim_id} has no publishable source URL', True,
                    ))

    for shift_index, shift in enumerate(shifts):
        children = subs_by_parent.get(str(shift.get('id') or ''), [])
        allowed = {
            number for child in children for value in child.get('claim_ids') or []
            if (number := _claim_number(value)) is not None
        }
        cited = _editorial_citations(shift)
        if not 2 <= len(cited) <= 6 or not cited <= allowed:
            issues.append(ValidationIssue(
                'editorial_provenance', f'key_trends[{shift_index}].modules.peel_tabs.data.evidence_ids',
                'key-shift editorial requires 2–6 citations from its routed child evidence', True,
            ))
        for claim_id in cited:
            if not _http_url(claim_sources.get(claim_id)):
                issues.append(ValidationIssue(
                    'editorial_provenance', f'key_trends[{shift_index}].modules.peel_tabs.data.evidence_ids',
                    f'cited claim c_{claim_id} has no publishable source URL', True,
                ))

    # Exact long-form editorial reuse is almost always evidence leakage between
    # routes. Source claims and quotes are excluded because one verified source
    # may legitimately support more than one higher-level synthesis.
    for scope_name, rows in (('key_trends', shifts), ('sub_trends', subs)):
        for row_index, row in enumerate(rows):
            for module_index, module in enumerate((row or {}).get('modules') or []):
                type_ = module.get('type')
                if type_ in _UNAUTHORED_TYPES:
                    continue
                data = module.get('data') or {}
                values = []
                if type_ == 'peel_tabs':
                    values = [data.get('whats_changing'), data.get('why_now')]
                elif type_ in {'lede', 'dek', 'pull_quote', 'tension_band', 'rich_text'}:
                    values = [data.get('text'), data.get('quote'), data.get('body')]
                for value in values:
                    normalized = ' '.join(re.findall(r'[a-z0-9]+', str(value or '').lower()))
                    if len(normalized) < 80:
                        continue
                    here = f'{scope_name}[{row_index}].modules[{module_index}]'
                    if normalized in prose_seen:
                        issues.append(ValidationIssue(
                            'duplicate_editorial', here,
                            f'editorial text duplicates {prose_seen[normalized]}', True,
                        ))
                    else:
                        prose_seen[normalized] = here

    valid_routes = shift_routes | {
        f"/{sub.get('domain_id')}/{sub.get('slug')}"
        for sub in subs if isinstance(sub, dict)
    }
    for shift_index, shift in enumerate(shifts):
        for module_index, module in enumerate(shift.get('modules') or []):
            if module.get('type') != 'related_shifts':
                continue
            for item_index, item in enumerate((module.get('data') or {}).get('items') or []):
                href = item.get('href') if isinstance(item, dict) else None
                if href not in valid_routes:
                    issues.append(ValidationIssue(
                        'related_route',
                        f'key_trends[{shift_index}].modules[{module_index}].data.items[{item_index}].href',
                        f'unknown related route {href!r}',
                    ))

    # ── Copy: US spelling, and no slug wearing the clothes of a word ──────
    known_slugs = {str(shift.get('slug') or '') for shift in shifts if isinstance(shift, dict)}
    known_slugs |= {str(sub.get('slug') or '').rsplit('/', 1)[-1]
                    for sub in subs if isinstance(sub, dict)}
    known_slugs.discard('')

    for label, rows in (('key_trends', shifts), ('sub_trends', subs)):
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            base = f'{label}[{index}]'
            ours = list(_copy_strings(row, base))
            ours += list(_prose_strings(row.get('modules') or [], f'{base}.modules', _QUOTED))
            everything = list(_copy_strings(row, base))
            everything += list(_prose_strings(row.get('modules') or [], f'{base}.modules'))
            for path, text in ours:
                british = _BRITISH.search(text)
                if british:
                    issues.append(ValidationIssue(
                        'british_spelling', path,
                        f'{british.group(0)!r} is British spelling; the content spec is US', True))
            for path, text in everything:
                for match in _SLUGGISH.finditer(text):
                    if match.group(0) in known_slugs:
                        issues.append(ValidationIssue(
                            'slug_in_prose', path,
                            f'{match.group(0)!r} is a URL slug, not a name', True))
                        break
            # Authored module prose only, quoted fields exempt: an em dash or
            # an AI-tell in a name/subtitle/description is real but the repair
            # pass cannot rewrite phase-3/4 copy, so those are reported by
            # `advisory_issues` instead of blocking here.
            for path, text in _authored_strings(row, base,
                                                _QUOTED | {'source', 'label'}):
                dash = _EM_DASH.search(text)
                if dash:
                    issues.append(ValidationIssue(
                        'em_dash', path,
                        'em dash in editorial prose; the voice spec is a period '
                        'or a comma', True))
                tell = _AI_TELL.search(text)
                if tell:
                    issues.append(ValidationIssue(
                        'ai_tell', path,
                        f'{tell.group(0)!r} reads as generated boilerplate; say '
                        f'the specific thing instead', True))

    # ── Content gates: what the 2026-08-10 audit found, made unpublishable ──

    # Hero statistics: exclusive across shifts, and about the shift they front.
    hero_seen: dict[tuple, str] = {}
    subtree_urls: dict[str, set] = {}
    for parent_id, children in subs_by_parent.items():
        urls = set()
        for child in children:
            for value in child.get('claim_ids') or []:
                number = _claim_number(value)
                url = claim_sources.get(number) if number is not None else None
                # NB _http_url here is a validity predicate (bool), not a
                # normalizer like export.py's namesake — compare raw strings.
                if url and _http_url(url):
                    urls.add(str(url))
        subtree_urls[parent_id] = urls

    for index, shift in enumerate(shifts):
        if not isinstance(shift, dict):
            continue
        hero = shift.get('hero_stat')
        if not isinstance(hero, dict) or not hero.get('value'):
            continue
        path = f'key_trends[{index}].hero_stat'
        # Keyed on the reduced figure, not the raw prose: the hero carries the
        # claim's long-form sentence here while a sub band carries its
        # _short_figure reduction, and the raw-prose key let both front the
        # same claim (the 1,337 petition figure, 2026-08-12).
        key = stat_claim_key(hero.get('value'), hero.get('url'))
        if key in hero_seen:
            issues.append(ValidationIssue(
                'duplicate_hero_claim', path,
                f'hero statistic already fronts {hero_seen[key]} — one claim, one shift', True))
        else:
            hero_seen[key] = f'key_trends[{shifts.index(shift)}]'
        hero_url = str(hero.get('url') or '')
        if hero_url and _http_url(hero_url) \
                and hero_url not in subtree_urls.get(str(shift.get('id') or ''), set()):
            issues.append(ValidationIssue(
                'hero_topicality', path,
                'hero statistic cites a source none of this shift\'s own claims carry', True))
        if not stat_matches_shift(shift.get('name'), shift.get('subtitle'),
                                  hero.get('value'), hero.get('text')):
            issues.append(ValidationIssue(
                'hero_topicality', path,
                'hero statistic shares no topical vocabulary with the shift it fronts', True))
        # Backstop for the dated-candidates filter in phase 8: an undated
        # figure fronting a page gives the reader no way to tell last month
        # from 2019. Repairable — the hero re-run only offers dated claims.
        if not str(hero.get('year') or '').strip():
            issues.append(ValidationIssue(
                'hero_stat_undated', path,
                'hero statistic carries no year — undated figures cannot front a page', True))

    # Sub-shift stat bands join the same exclusivity registry as the heroes,
    # so a child fronting its parent's headline — or another family's — is
    # caught on the same (value, url) key. st-pacing-schism shipped Governance
    # Void's 1,337 hero byte-for-byte before this covered sub_trends.
    for index, sub in enumerate(subs):
        if not isinstance(sub, dict):
            continue
        for module in sub.get('modules') or []:
            if not isinstance(module, dict) or module.get('type') != 'stat_band':
                continue
            data = module.get('data') or {}
            value = data.get('value')
            if not value:
                continue
            key = stat_claim_key(value, data.get('url'))
            path = f'sub_trends[{index}].modules.stat_band'
            if key in hero_seen:
                issues.append(ValidationIssue(
                    'duplicate_hero_claim', path,
                    f'stat band already fronts {hero_seen[key]} — one claim, one page', True))
            else:
                hero_seen[key] = f'sub_trends[{index}]'

    # dek must be its own sentence, not the subtitle republished.
    for index, shift in enumerate(shifts):
        if not isinstance(shift, dict):
            continue
        subtitle = _norm_prose(shift.get('subtitle'))
        for module in shift.get('modules') or []:
            if isinstance(module, dict) and module.get('type') == 'dek':
                dek = _norm_prose((module.get('data') or {}).get('text'))
                if dek and subtitle and dek == subtitle:
                    issues.append(ValidationIssue(
                        'dek_recycles_subtitle', f'key_trends[{index}].modules.dek',
                        'dek is the subtitle verbatim — the page says one sentence twice', True))

    # A page must not restate the figure it fronts. Phase 8 avoids picking such
    # heroes, editorial retries reject such bodies, and export drops the band
    # when the fixed copy carries the figure — so on a fresh publish both codes
    # are invariants, like `evidence_reuse` below. `stat_echo` names authored
    # prose the repair pass CAN rewrite; `stat_echo_subtitle` names phase-3/4
    # copy it cannot, and its remedy is the free phase-8 re-run
    # (cli.HERO_REPAIR_CODES) followed by export's reconcile_self_echo.
    for label, rows in (('key_trends', shifts), ('sub_trends', subs)):
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            base = f'{label}[{index}]'
            if label == 'key_trends':
                hero = row.get('hero_stat')
                fronted = hero.get('value') if isinstance(hero, dict) else None
            else:
                fronted = next(
                    ((m.get('data') or {}).get('value')
                     for m in row.get('modules') or []
                     if isinstance(m, dict) and m.get('type') == 'stat_band'),
                    None)
            if not fronted:
                continue
            for path, figure in figure_echoes(
                    fronted, _authored_strings(row, base, {'source', 'label'})):
                issues.append(ValidationIssue(
                    'stat_echo', path,
                    f'restates the fronted figure {figure!r} — the stat band '
                    f'already displays it', True))
            for path, figure in figure_echoes(fronted, _copy_strings(row, base)):
                issues.append(ValidationIssue(
                    'stat_echo_subtitle', path,
                    f'the fronted figure {figure!r} already sits in this fixed '
                    f'copy; the statistic must cede (re-run phase 8 / export)', True))

    # No amputated prose, no internal vocabulary, no self-declared filler.
    for label, rows in (('key_trends', shifts), ('sub_trends', subs)):
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            base = f'{label}[{index}]'
            for path, text in _prose_strings(row.get('modules') or [],
                                             f'{base}.modules',
                                             _QUOTED | {'source', 'label'}):
                stripped = text.rstrip()
                if stripped.endswith('…') or stripped.endswith('...'):
                    issues.append(ValidationIssue(
                        'ellipsis_truncation', path,
                        'prose ends mid-sentence with an ellipsis', True))
            for path, text in _prose_strings(row.get('modules') or [],
                                             f'{base}.modules', _QUOTED):
                meta = _META_LANGUAGE.search(text)
                if meta:
                    issues.append(ValidationIssue(
                        'meta_language', path,
                        f'{meta.group(0)!r} is pipeline vocabulary in reader-facing copy', True))
            for module_index, module in enumerate(row.get('modules') or []):
                if not isinstance(module, dict) or module.get('type') not in ('industries', 'territories'):
                    continue
                for item_index, item in enumerate((module.get('data') or {}).get('items') or []):
                    text = item.get('text') if isinstance(item, dict) else None
                    if text and _INDUSTRY_FILLER.search(str(text)):
                        issues.append(ValidationIssue(
                            'industries_filler',
                            f'{base}.modules[{module_index}].data.items[{item_index}]',
                            'sector note declares its own irrelevance — leave it empty instead', True))
            for module_index, module in enumerate(row.get('modules') or []):
                if not isinstance(module, dict) or module.get('type') != 'counter_signals':
                    continue
                for item_index, item in enumerate((module.get('data') or {}).get('items') or []):
                    audit = _METHODS_AUDIT.search(str(item or ''))
                    if audit:
                        issues.append(ValidationIssue(
                            'counter_signal_meta',
                            f'{base}.modules[{module_index}].data.items[{item_index}]',
                            f'{audit.group(0)!r} audits the evidence, not the world — '
                            f'a counter-signal is market evidence against the shift', True))

    # Population-level gates: only meaningful on a full-sized map.
    if len(shifts) >= FULL_MAP_MIN_SHIFTS:
        per_domain: dict[str, int] = {}
        for shift in shifts:
            if isinstance(shift, dict):
                per_domain[str(shift.get('domain_id'))] = per_domain.get(str(shift.get('domain_id')), 0) + 1
        for domain_id, count in sorted(per_domain.items()):
            if not MIN_KTS_PER_DOM <= count <= MAX_KTS_PER_DOM:
                issues.append(ValidationIssue(
                    'kt_count', f'key_trends.{domain_id}',
                    f'{domain_id} carries {count} key shifts; the contract is '
                    f'{MIN_KTS_PER_DOM}–{MAX_KTS_PER_DOM} per domain'))

        velocities = [str(shift.get('velocity') or '') for shift in shifts if isinstance(shift, dict)]
        if velocities:
            top = max(set(velocities), key=velocities.count)
            share = velocities.count(top) / len(velocities)
            if share > VELOCITY_MAX_SHARE:
                issues.append(ValidationIssue(
                    'velocity_distribution', 'key_trends',
                    f'{velocities.count(top)}/{len(velocities)} shifts share velocity '
                    f'{top!r} — a single-bucket grading carries no signal'))

        with_stat = sum(
            1 for shift in shifts if isinstance(shift, dict)
            and any(isinstance(m, dict) and m.get('type') == 'stat_band'
                    for m in shift.get('modules') or []))
        if with_stat / len(shifts) < STAT_COVERAGE_FLOOR:
            issues.append(ValidationIssue(
                'stat_coverage', 'key_trends',
                f'only {with_stat}/{len(shifts)} key shifts carry a stat_band; '
                f'the floor is {STAT_COVERAGE_FLOOR:.0%}', True))

        # Crutch content: one centerpiece may not carry the map. Pages beyond
        # the per-signature allowance are flagged individually so the repair
        # pass regenerates exactly those pages with the avoid-list in hand.
        # Corpus thinkers are exempt as entity signatures: citing the author
        # of the evidence is attribution, not a recycled anecdote.
        thinker_names = {
            _norm_prose(claim.get('thinker'))
            for claim in claims if isinstance(claim, dict) and claim.get('thinker')
        }
        pages: list[tuple[str, str, set]] = []  # (path, family, signatures)
        for label, rows in (('key_trends', shifts), ('sub_trends', subs)):
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                family = str(row.get('key_trend_id') or row.get('id') or '')
                signatures = {
                    s for s in _crutch_signatures(_centerpiece_text(row))
                    if not (s.startswith('entity:') and s[7:] in thinker_names)
                }
                pages.append((f'{label}[{index}]', family, signatures))
        family_holders: dict[str, dict[str, list[str]]] = {}
        for path, family, signatures in pages:
            for signature in signatures:
                family_holders.setdefault(signature, {}).setdefault(family, []).append(path)
        for signature, families in sorted(family_holders.items()):
            limit = (CRUTCH_ENTITY_PAGE_LIMIT if signature.startswith('entity:')
                     else CRUTCH_FIGURE_PAGE_LIMIT)
            for family in sorted(families)[limit:]:
                for path in families[family]:
                    issues.append(ValidationIssue(
                        'crutch_frequency', f'{path}.modules',
                        f'centerpiece leans on {signature.split(":", 1)[1]!r}, already '
                        f'headlining {limit}+ other shift families', True))

        reuse: dict[int, list[str]] = {}
        for index, sub in enumerate(subs):
            if not isinstance(sub, dict):
                continue
            for value in sub.get('claim_ids') or []:
                number = _claim_number(value)
                if number is not None:
                    reuse.setdefault(number, []).append(f'sub_trends[{index}]')
        # Cap 3, not 2: routing deliberately offers some claims to two domains
        # (secondary_claim_domains), so three holders is reachable by design —
        # one per domain assignment plus one top-up. Four is the filler-dump
        # pattern the audit found (one claim padding unrelated pages).
        #
        # ABSOLUTE, and NOT repairable, which makes it the likeliest single way a
        # paid run dies as the map grows: reuse pressure scales with sub-shift
        # count while the cap does not. 180 sub-shifts need ~360 claim slots,
        # 300 need ~600, from a pool that grew only to 350 per domain. The cap
        # therefore scales with the map, keeping the RULE ("a claim may anchor a
        # few pages, not a dozen") while dropping the pretence that a fixed
        # number expresses it at every size.
        reuse_cap = max(3, round(EVIDENCE_REUSE_SHARE * len(subs)))
        # Repairable in name only, and the 18 Aug 2026 run proved it: the
        # targeted repair rewrites editorial prose and never re-routes claims,
        # so it fixed all four of this issue's neighbours and re-published the
        # identical claim_ids. Routing is settled deterministically at export
        # now (export.reconcile_evidence_reuse), which is why this should no
        # longer fire on a generated map; it stays here as the check on that.
        for number, holders in sorted(reuse.items()):
            if len(holders) > reuse_cap:
                issues.append(ValidationIssue(
                    'evidence_reuse', holders[reuse_cap],
                    f'claim c_{number} is routed to {len(holders)} sub-shifts; '
                    f'the same evidence cannot anchor more than {reuse_cap} pages',
                    True))

    return issues


def advisory_issues(document: dict) -> list[ValidationIssue]:
    """Report-only findings — printed beside the gate, never raised by it.

    Everything here is real but unrepairable-by-machine: name-family monotony
    needs an editor to rename (the repair pass never renames — see the
    duplicate_sub_shift_name note above), and an em dash or AI-tell inside a
    name/subtitle/description is phase-3/4 copy the repair cannot rewrite. A
    blocking gate whose issues nothing can fix strands every publish; a report
    tells the operator without holding the map hostage. The live 2026-08-19
    map violates the family cap nine times over, which is also why this must
    not block: the first publish after the rule would otherwise be impossible.
    """
    issues: list[ValidationIssue] = []
    shifts = document.get('key_trends') or []
    subs = document.get('sub_trends') or []

    holders: dict[str, list[tuple[str, str]]] = {}
    for label, rows in (('key_trends', shifts), ('sub_trends', subs)):
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or not row.get('name'):
                continue
            for key in family_keys(row['name']):
                holders.setdefault(key, []).append(
                    (f'{label}[{index}]', str(row['name'])))
    for key, pages in sorted(holders.items()):
        if len(pages) > NAME_FAMILY_CAP:
            names = ', '.join(sorted({name for _, name in pages}))
            issues.append(ValidationIssue(
                'name_family_repeat', pages[NAME_FAMILY_CAP][0],
                f'{len(pages)} pages share the name family {key!r}: {names}'))

    for label, rows in (('key_trends', shifts), ('sub_trends', subs)):
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            for path, text in _copy_strings(row, f'{label}[{index}]'):
                if _EM_DASH.search(text):
                    issues.append(ValidationIssue(
                        'em_dash_fixed_copy', path,
                        'em dash in name/subtitle/description — regeneration or '
                        'a hand edit, the repair pass cannot rewrite this'))
                tell = _AI_TELL.search(text)
                if tell:
                    issues.append(ValidationIssue(
                        'ai_tell_fixed_copy', path,
                        f'{tell.group(0)!r} in name/subtitle/description'))
    return issues


def skipped_issue_codes() -> set[str]:
    """Remediation valve: issue codes listed under `skip_issue_codes` in
    packages/contracts/gates.json are reported but never block.

    Exists for the first publish after a new lint lands, when the live map may
    violate it more widely than one repair pass can absorb. This replaced the
    SS_SKIP_ISSUE_CODES env var: every silent gate loosening in the August
    audit traced back to valves that left no diff, so the list now lives in a
    versioned file and changing it is a reviewed edit. Read at call time, not
    import time, so a remediation branch can carry the list and the next
    deploy drops it. Honored by `require_valid_map` — the write-time gate —
    and by the CLI's publish path, so the two can never disagree about what
    blocks. Empty on main; keep it that way.
    """
    from . import config as _config  # attribute lookup at call time, not import
    return {str(code).strip()
            for code in _config.load_gates().get('skip_issue_codes') or []
            if str(code).strip()}


def require_valid_map(document: dict, contract: dict | None = None) -> None:
    skipped = skipped_issue_codes()
    issues = [issue for issue in validate_map(document, contract)
              if issue.code not in skipped]
    if issues:
        raise PublicationValidationError(issues)
