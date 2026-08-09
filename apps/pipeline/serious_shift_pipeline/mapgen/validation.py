"""Pre-publication validation for the routed Serious Shift map."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from .config import DOMAINS
from .modules import (_LEAKED_BARE, _LEAKED_CREF, _LEAKED_PAREN, NOT_PROSE,
                      FIELD_WORD_LIMITS, LIST_ITEM_WORD_LIMITS, PAIR_TEXT_WORD_LIMITS,
                      STEP_TEXT_WORD_LIMIT, count_words)

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
                    'industries must contain all 16 canonical sectors exactly once and in order', True,
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
_BRITISH = re.compile(
    r'\b('
    r'organis\w*|catalogu\w*|behaviour\w*|programme\w*|centre[sd]?|'
    r'recognis\w*|optimis\w*|realis\w*|utilis\w*|analys(?:e|ed|es|ing)|'
    r'favourite\w*|colour\w*|labour\w*|defence|offence|licence|practis\w*|'
    r'travell\w*|modell\w*|cancell\w*|marvell\w*|apologis\w*|prioritis\w*'
    r')\b'
)

#: A lowercase hyphenated token, i.e. slug-shaped. Digits are allowed because
#: real slugs carry them — `moat-migration-2` is a published URL.
#:
#: Only reported when it matches a slug that actually exists in this document.
#: Plenty of legitimate copy is hyphenated ("entry-level", "AI-assisted"), and
#: only a token that IS a slug reads as a machine identifier loose in prose.
_SLUGGISH = re.compile(r'\b[a-z0-9]+(?:-[a-z0-9]+)+\b')


def _copy_strings(row: dict, path: str):
    """The three published fields no check has ever looked at, plus module prose.

    `sub_trends[].description` is the meta description seo.rs publishes verbatim,
    and until now nothing validated it at all.
    """
    for field in ('name', 'subtitle', 'description'):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            yield f'{path}.{field}', value


def _prose_strings(value, path: str):
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in NOT_PROSE:
                continue
            yield from _prose_strings(nested, f'{path}.{key}')
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _prose_strings(nested, f'{path}[{index}]')
    elif isinstance(value, str):
        yield path, value


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
        if len(children) != 5:
            issues.append(ValidationIssue('sub_shift_count', f'{path}.sub_trend_ids',
                                          f'expected exactly 5 sub-shifts, found {len(children)}', True))
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
                if type_ in {'evidence', 'voices', 'stat_band', 'related_shifts'}:
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
            texts = list(_copy_strings(row, base))
            texts += list(_prose_strings(row.get('modules') or [], f'{base}.modules'))
            for path, text in texts:
                british = _BRITISH.search(text)
                if british:
                    issues.append(ValidationIssue(
                        'british_spelling', path,
                        f'{british.group(0)!r} is British spelling; the content spec is US', True))
                for match in _SLUGGISH.finditer(text):
                    if match.group(0) in known_slugs:
                        issues.append(ValidationIssue(
                            'slug_in_prose', path,
                            f'{match.group(0)!r} is a URL slug, not a name', True))
                        break
    return issues


def require_valid_map(document: dict, contract: dict | None = None) -> None:
    issues = validate_map(document, contract)
    if issues:
        raise PublicationValidationError(issues)
