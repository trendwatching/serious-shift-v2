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
# consumer tension, horizon, industries, opportunity territories).
#
# Kept as its own phase, one call per Key Trend, for two reasons: a long
# editorial answer can never truncate the taxonomy it hangs off, and a parse
# failure here leaves the shift intact — the page just falls back to hero + dek,
# because the front end renders each section only when its field is present.
# ---------------------------------------------------------------------------

def _as_steps(timeline) -> list | None:
    """Normalise a {now,next,beyond} object into the [{label,text}] the map
    document carries. Tolerates a model that already returned a list."""
    if isinstance(timeline, list):
        return [t for t in timeline if isinstance(t, dict) and t.get('text')] or None
    if isinstance(timeline, dict):
        steps = [{'label': k.capitalize(), 'text': timeline[k]}
                 for k in ('now', 'next', 'beyond') if timeline.get(k)]
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
    if len(t) <= limit:
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
    long as any one value is set, which is what peel_tabs and human_needs want
    (both render happily with only one side filled). Mirrors the `required` lists
    in packages/contracts/shift_modules.json.
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
        _module('dek', {'text': kt_row.get('subtitle') or ''}, ('text',)),
        _module('from_to', {'from': e.get('from') or '', 'to': e.get('to') or ''}, ('from', 'to')),
        _module('pull_quote', {'quote': e.get('pull_quote') or ''}, ('quote',)),
        _module('stat_band', {
            # The model is asked for a display figure; hero_stat.value is a
            # fallback and is usually prose, so it has to be reduced first.
            'value': (e.get('stat_value') or '').strip() or _short_figure(hero.get('value')) or '',
            'text': e.get('stat_text') or hero.get('value') or '',
            'source': hero.get('source') or hero.get('thinker') or '',
        }, ('value',)),
        _module('peel_tabs', {
            'whats_changing': e.get('whats_changing') or '',
            'why_now': e.get('why_now') or '',
        }),
        # Resolved from the shift's sub-shifts at render time, so it carries no
        # data of its own — but it still has to sit in the order.
        {'type': 'sub_shift_list', 'data': {}},
        _module('human_needs', {
            'unlocked': needs.get('unlocked') or '',
            'threatened': needs.get('threatened') or '',
        }),
        _module('tension_band', {'quote': e.get('consumer_tension') or ''}, ('quote',)),
        _module('timeline', {'steps': _as_steps(e.get('timeline')) or []}, ('steps',)),
        _module('industries', {'items': _as_pairs(e.get('industries')) or []}, ('items',)),
        _module('territories', {'items': _as_pairs(e.get('opportunities')) or []}, ('items',)),
    ]
    return [m for m in candidates if m]


def st_modules(st_row: dict, editorial: dict) -> list:
    """Module list for a sub-shift, in the design's reading order."""
    e = editorial or {}
    raw_needs, raw_stat = e.get('human_needs'), e.get('stat')
    needs: dict = raw_needs if isinstance(raw_needs, dict) else {}
    stat: dict = raw_stat if isinstance(raw_stat, dict) else {}

    candidates = [
        _module('lede', {'text': e.get('lede') or st_row.get('description') or ''}, ('text',)),
        _module('from_to_solid', {'from': e.get('from') or '', 'to': e.get('to') or ''}, ('from', 'to')),
        _module('tension_band', {'quote': e.get('quote') or '', 'label': 'The tension'}, ('quote',)),
        _module('stat_band', {
            'value': stat.get('value') or '',
            'text': stat.get('text') or '',
            'source': stat.get('source') or '',
        }, ('value',)),
        _module('peel_tabs', {
            'whats_changing': e.get('whats_changing') or '',
            'why_now': e.get('why_now') or '',
        }),
        _module('human_needs', {
            'unlocked': needs.get('unlocked') or '',
            'threatened': needs.get('threatened') or '',
        }),
        _module('signals', {'items': _as_strings(e.get('signals')) or []}, ('items',)),
        _module('counter_signals', {'items': _as_strings(e.get('counter_signals')) or []}, ('items',)),
        _module('timeline', {'steps': _as_steps(e.get('timeline')) or []}, ('steps',)),
        _module('territories', {'items': _as_pairs(e.get('territories')) or []}, ('items',)),
    ]
    return [m for m in candidates if m]
