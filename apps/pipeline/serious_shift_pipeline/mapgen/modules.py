"""Build the `{type, data}` module lists that make up a shift page.

A page's composition is data, not code — these functions turn one editorial
response into the contract's module objects, and `_module` drops any module
whose required fields are missing so a page never renders a half-empty section.
See packages/contracts/shift_modules.json.
"""
from __future__ import annotations

import json
import re

# Phases 3 and 4 name and cluster; this writes the prose the reader sees on the
# shift and sub-shift pages (From→To, what's changing / why now, human needs,
# the tension, horizon, industries, opportunity territories).
#
# Kept as its own phase, one call per Key Trend, for two reasons: a long
# editorial answer can never truncate the taxonomy it hangs off, and a parse
# failure here leaves the shift intact — the page just falls back to hero + dek,
# because the front end renders each section only when its field is present.
# ---------------------------------------------------------------------------

#: The horizon steps and the labels the page prints, in order.
#:
#: The first step is `today`, not `now`: the page already has a WHY NOW tab
#: immediately above this module, and two sections competing for the word read
#: as the same section twice.
_TIMELINE_STEPS = (('today', 'Today'), ('next', 'Next'), ('beyond', 'Beyond'))


def _as_steps(timeline) -> list | None:
    """Normalise a {today,next,beyond} object into the [{label,text}] the map
    document carries. Tolerates a model that already returned a list."""
    if isinstance(timeline, list):
        return [t for t in timeline if isinstance(t, dict) and t.get('text')] or None
    if isinstance(timeline, dict):
        steps = []
        for key, label in _TIMELINE_STEPS:
            # `now` is the pre-August-2026 key. Accept it rather than drop a
            # third of the module when a cached or retried response predates the
            # rename; the label is ours either way.
            text = timeline.get(key) or (timeline.get('now') if key == 'today' else None)
            if text:
                steps.append({'label': label, 'text': text})
        return steps or None
    return None


def _as_pairs(items) -> list | None:
    """Normalise [{name,text}] lists (industries, opportunities, territories)."""
    if not isinstance(items, list):
        return None
    out = [{'name': i.get('name', ''), 'text': i.get('text', '')}
           for i in items if isinstance(i, dict) and i.get('name')]
    return out or None


def _as_strings(items) -> list | None:
    """Normalise a list of plain strings (signals, counter-signals)."""
    if not isinstance(items, list):
        return None
    out = [s.strip() for s in items if isinstance(s, str) and s.strip()]
    return out or None


#: A leading display figure: 200 · 25% · 3× · 2:1 · $4.2bn · 18-34.
_FIGURE_RE = re.compile(
    r'^[$€£]?\d[\d,.]*(?:\s?[-–]\s?\d[\d,.]*)?'          # 200 · 4.2 · 18-34
    r'(?:\s?(?:%|×|x\b|:\s?\d+))?'                        # % · × · :1
    r'(?:\s?(?:million|billion|trillion|bn|m|k))?',       # 4.2bn · 16 million
    re.IGNORECASE,
)


#: Database identifiers a model copied out of the evidence block into prose.
#:
#: The evidence records carry an `id` so the model can cite it in `evidence_ids`
#: and `claim_id`. Some runs put it in the sentence instead, and two such strings
#: reached production: "Jack Clark, import AI newsletter (cred:54)" and
#: "Jakob Nielsen (id:38735)". The prompts now forbid it, but published copy goes
#: out under a real person's name, so the same reasoning as
#: `parse_thinker_attribution` applies: "the model was told not to" is not a
#: guarantee, and this is cheap to enforce.
_LEAKED_PAREN = re.compile(
    r'\s*[\(\[]\s*(?:id|ids|claim|claim_id|evidence_id|cred|credibility|'
    r'conf|confidence|score|weight|specificity)\s*[:=]\s*[^)\]]{0,40}[\)\]]',
    re.IGNORECASE,
)
#: The lookbehind keeps a URL's query string intact: "example.com/a?id=7" is a
#: link the copy legitimately carries, not a leaked identifier.
_LEAKED_BARE = re.compile(
    r'(?<![?&/=])\b(?:id|claim_id|evidence_id|cred|credibility|specificity)\s*[:=]\s*\d+\b',
    re.IGNORECASE,
)
_LEAKED_CREF = re.compile(r'\bc_\d{2,}\b')


def strip_identifiers(text) -> str:
    """Remove database identifiers a model copied into reader-facing prose.

    Deliberately narrow: it only matches a known field name joined to a value by
    `:` or `=`. A ratio ("a 2:1 split") and a plain year ("the 2026 id card
    scheme") have to survive, because they are things the copy legitimately says.
    """
    out = str(text or '')
    for pattern in (_LEAKED_PAREN, _LEAKED_BARE, _LEAKED_CREF):
        out = pattern.sub('', out)
    out = re.sub(r'\s{2,}', ' ', out)
    return re.sub(r'\s+([,.;:!?])', r'\1', out).strip().rstrip(',;:')


#: Keys whose values are machine strings, not prose. A URL is full of things that
#: look like `id=…` by definition, and `evidence_ids` is a list of the very
#: numbers the scrubber is looking for.
NOT_PROSE = frozenset({'url', 'href', 'image', 'evidence_ids'})


def scrub_module_tree(value):
    """`value` with database identifiers removed from every prose leaf.

    Applied at export rather than only at generation, which is what makes the fix
    free: the offending strings are already baked into `domain_key_trends.modules`
    from earlier runs, so an `--export-only` pass cleans the live pages without
    paying to regenerate them.
    """
    if isinstance(value, dict):
        return {k: v if k in NOT_PROSE else scrub_module_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_module_tree(v) for v in value]
    if isinstance(value, str):
        return strip_identifiers(value)
    return value


def clamp_words(text, limit: int) -> str:
    """Trim prose to `limit` words, preferring a sentence boundary.

    The publication contract caps each editorial field because the design has a
    fixed amount of room for it; a body that overruns fails the gate. The model
    overruns some of these routinely — 53 of one run's 144 length failures were
    a single sector note running past 40 words — and asking again is a poor
    remedy, because a shift carries sixteen sector notes and any one of them
    being long would discard the other fifteen.

    So the cap is applied here instead, where it is one item's problem. Cutting
    at the last full sentence inside the limit keeps the note readable; only when
    there is no sentence break do we fall back to a word cut with an ellipsis.
    """
    # Scrub before measuring: a stripped identifier should not cost the copy a
    # word of its allowance, and every prose field already passes through here.
    cleaned = strip_identifiers(text)
    words = cleaned.split()
    if len(words) <= limit:
        return cleaned
    head = ' '.join(words[:limit])
    # Prefer the last sentence end, but only if it keeps most of the allowance —
    # cutting a 40-word note down to 6 to land on a full stop loses more than the
    # ellipsis does.
    cut = max(head.rfind('. '), head.rfind('! '), head.rfind('? '))
    if cut > 0 and len(head[:cut].split()) >= limit * 0.6:
        return head[:cut + 1]
    return head.rstrip(' ,;:—-') + '…'


def _clamp_items(items, limit: int) -> list | None:
    """Clamp the `text` of each {name, text} pair. One long sector note is that
    note's problem, not the whole list's."""
    if not items:
        return None
    return [{**item, 'text': clamp_words(item.get('text'), limit)} for item in items]


def _clamp_steps(steps, limit: int) -> list | None:
    """Clamp each timeline step's prose."""
    if not steps:
        return None
    return [{**step, 'text': clamp_words(step.get('text'), limit)} for step in steps]


def _clamp_strings(items, limit: int) -> list | None:
    """Clamp each entry of a plain string list (signals, counter-signals)."""
    if not items:
        return None
    return [clamp_words(item, limit) for item in items]


#: A stat band displays a statistic, and a statistic contains a number.
_HAS_DIGIT = re.compile(r'\d')


def _short_figure(text, limit: int = 14) -> str | None:
    """A numeral fit for the stat band, or None.

    `hero_stat.value` is prose lifted from a claim ("200 years of encyclical
    history, first time dedicated entirely to technology"), but the band renders
    it at ~99px on desktop, so only a short figure works. Take a leading figure
    if there is one and give up otherwise — an overflowing band is worse than no
    band, and the module is dropped when this returns nothing.
    """
    if not text:
        return None
    t = ' '.join(str(text).split())
    # A short string is only a figure if it contains one. Without the digit
    # check a ten-character phrase like "multi-hop" passed straight through and
    # rendered as the page's headline statistic at ~99px.
    if len(t) <= limit and _HAS_DIGIT.search(t):
        return t
    m = _FIGURE_RE.match(t)
    if m:
        figure = m.group(0).strip().rstrip('.,;:')
        if figure and len(figure) <= limit:
            return figure
    return None


def _jsonb(value) -> str | None:
    """Serialise for a `%s::jsonb` placeholder; empty/None stays SQL NULL so the
    front end treats the section as absent."""
    return json.dumps(value) if value else None


# ── The module template ─────────────────────────────────────────────────────
#
# A shift page is an ordered list of {type, data} modules. These two functions
# ARE the template: the order below is the order the reader sees, and a module is
# omitted when the model gave us nothing for it (the page then simply doesn't
# have that section). To add, drop or reorder a section for every shift at once,
# edit these lists — no frontend change is needed as long as the type is
# registered in apps/frontend/src/shift/modules.jsx.
#
# Canonical type list + data shapes: packages/contracts/shift_modules.json.

def _module(type_: str, data, required: tuple = ()) -> dict | None:
    """A module, or None when it has nothing to render.

    `required` names the keys the module cannot render without. A stat band with
    prose but no numeral, or a tension band with a label but no quote, is not a
    section — it is an empty box. With no `required` given the module survives as
    long as any one value is set, which is what peel_tabs wants: its two panes
    are behind a tab, so one of them being absent costs the reader nothing.
    Mirrors the `required` lists in packages/contracts/shift_modules.json.
    """
    if not data:
        return None
    if isinstance(data, dict):
        if required:
            if any(not data.get(k) for k in required):
                return None
        elif not any(v for v in data.values()):
            return None
    return {'type': type_, 'data': data}


def kt_modules(kt_row: dict, editorial: dict) -> list:
    """Module list for a key shift, in the design's reading order."""
    e = editorial or {}
    # Bound before the isinstance check so the narrowing actually applies —
    # `x.get(k) if isinstance(x.get(k), dict)` calls get() twice and narrows
    # neither.
    raw_needs = e.get('human_needs')
    needs: dict = raw_needs if isinstance(raw_needs, dict) else {}
    hero: dict = kt_row.get('hero_stat') or {}

    candidates = [
        _module('dek', {'text': clamp_words(kt_row.get('subtitle'), 45)}, ('text',)),
        _module('from_to', {'from': clamp_words(e.get('from'), 30),
                            'to': clamp_words(e.get('to'), 30)}, ('from', 'to')),
        _module('pull_quote', {'quote': clamp_words(e.get('pull_quote'), 18)}, ('quote',)),
        _module('stat_band', {
            # The model is asked for a display figure; hero_stat.value is a
            # fallback and is usually prose, so it has to be reduced first.
            'value': _short_figure(hero.get('value')) or '',
            'text': hero.get('text') or hero.get('value') or '',
            'source': hero.get('source') or hero.get('thinker') or '',
            'url': hero.get('url') or '',
        }, ('value',)),
        _module('peel_tabs', {
            'whats_changing': clamp_words(e.get('whats_changing'), 90),
            'why_now': clamp_words(e.get('why_now'), 70),
            'evidence_ids': e.get('evidence_ids') or [],
        }),
        # Resolved from the shift's sub-shifts at render time, so it carries no
        # data of its own — but it still has to sit in the order.
        {'type': 'sub_shift_list', 'data': {}},
        # Both sides or neither. A card pair with one half filled is not a
        # section, and the design shows them side by side rather than as an
        # accordion, so the empty half has nowhere to hide.
        _module('human_needs', {
            'unlocked': clamp_words(needs.get('unlocked'), 45),
            'threatened': clamp_words(needs.get('threatened'), 45),
        }, ('unlocked', 'threatened')),
        # `consumer_tension` is the pre-August-2026 key, kept so a retried or
        # cached response still lands. The label is always ours: the module is
        # "The tension" on every sphere, not only Consumers.
        _module('tension_band', {
            'quote': clamp_words(e.get('tension') or e.get('consumer_tension'), 38),
            'label': 'The tension',
        }, ('quote',)),
        _module('timeline', {'steps': _clamp_steps(_as_steps(e.get('timeline')), 45)}, ('steps',)),
        _module('industries', {'items': _clamp_items(_as_pairs(e.get('industries')), 40)}, ('items',)),
        _module('territories', {'items': _clamp_items(_as_pairs(e.get('opportunities')), 50)}, ('items',)),
    ]
    return [m for m in candidates if m]


def st_modules(st_row: dict, editorial: dict) -> list:
    """Module list for a sub-shift, in the design's reading order."""
    e = editorial or {}
    raw_needs, raw_stat = e.get('human_needs'), e.get('stat')
    needs: dict = raw_needs if isinstance(raw_needs, dict) else {}
    stat: dict = raw_stat if isinstance(raw_stat, dict) else {}

    candidates = [
        _module('lede', {'text': clamp_words(e.get('lede') or st_row.get('description'), 40)}, ('text',)),
        _module('from_to_solid', {'from': clamp_words(e.get('from'), 30),
                                  'to': clamp_words(e.get('to'), 30)}, ('from', 'to')),
        _module('tension_band', {'quote': clamp_words(e.get('quote'), 38),
                                 'label': 'The tension'}, ('quote',)),
        _module('stat_band', {
            # Same reduction as the key shift's band, and for the same reason:
            # the value is set at ~99px, and it has to be a figure. A sub-shift
            # whose evidence carries no number simply has no stat band.
            'value': _short_figure(stat.get('value')) or '',
            'text': stat.get('text') or '',
            'source': stat.get('source') or '',
            'url': stat.get('url') or '',
        }, ('value',)),
        _module('peel_tabs', {
            'whats_changing': clamp_words(e.get('whats_changing'), 90),
            'why_now': clamp_words(e.get('why_now'), 70),
            'evidence_ids': e.get('evidence_ids') or [],
        }),
        _module('human_needs', {
            'unlocked': clamp_words(needs.get('unlocked'), 45),
            'threatened': clamp_words(needs.get('threatened'), 45),
        }, ('unlocked', 'threatened')),
        _module('signals', {'items': _clamp_strings(_as_strings(e.get('signals')), 35)}, ('items',)),
        _module('counter_signals',
                {'items': _clamp_strings(_as_strings(e.get('counter_signals')), 35)}, ('items',)),
        _module('timeline', {'steps': _clamp_steps(_as_steps(e.get('timeline')), 45)}, ('steps',)),
        _module('territories', {'items': _clamp_items(_as_pairs(e.get('territories')), 50)}, ('items',)),
    ]
    return [m for m in candidates if m]
