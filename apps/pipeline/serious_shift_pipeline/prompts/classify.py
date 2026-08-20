"""Innovation → shift matching, for the ambiguous cases the arithmetic can't call.

No VOICE block. Voice governs copy a reader sees; this returns a ranking and a
twenty-word internal note. The other two judgement prompts — thinker attribution
and interrelatedness — omit it for the same reason.
"""
from __future__ import annotations

import json

#: Haiku. The deterministic pass has already narrowed this to a shortlist of at
#: most eight, so the model is breaking a tie rather than searching a catalogue.
from ..core.config import CLASSIFY_MODEL  # noqa: F401 — re-exported
from ._loader import load_and_render


def fmt_shift_catalogue(shifts: list[dict]) -> str:
    """JSON Lines, one shift per line — the house format `fmt_claims_block` uses.

    Compact enough that eight candidates cost a few hundred tokens, and each
    line keeps its own `ref` beside the text it describes, so the model cannot
    mis-attribute a framing to the wrong shift.
    """
    return '\n'.join(
        json.dumps({
            'ref': s['ref'],
            'domain': s.get('domain', ''),
            'name': s.get('name', ''),
            'framing': (s.get('framing') or '')[:220],
            'from': (s.get('from') or '')[:220],
            'to': (s.get('to') or '')[:220],
        }, ensure_ascii=False, separators=(',', ':'))
        for s in shifts
    )


def classify_prompt(innovation: dict, shifts: list[dict]) -> str:
    tags = ', '.join(
        f'{facet}:{slug}'
        # Geography does not discriminate between shifts that are all global,
        # and offering it invites the model to match on country.
        for facet, slugs in (innovation.get('tags') or {}).items()
        if facet not in ('region', 'country', 'season')
        for slug in slugs
    )
    summary = innovation.get('trendbite') or (innovation.get('body') or '')[:600]
    # Keyword arguments, not a dict: `load_and_render` takes the template name
    # positionally and every token as a keyword. Passing a dict raised TypeError
    # on the first escalation, which is only reached once the lexical scorer is
    # undecided — so the step's happy path never touched it and the failure only
    # showed on a real corpus.
    return load_and_render(
        'classify/innovation_shift.txt',
        title=innovation.get('title', ''),
        brands=', '.join(innovation.get('brands_list') or []) or '—',
        tags=tags or '—',
        summary=summary or '—',
        shift_count=str(len(shifts)),
        catalogue=fmt_shift_catalogue(shifts),
    )
