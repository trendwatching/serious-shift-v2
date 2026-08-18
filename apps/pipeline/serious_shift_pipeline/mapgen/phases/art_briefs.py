"""Write one image brief per shift and sub-shift, and remember them.

Runs after the gate passes, against the FINAL document, because the brief is
keyed by published slug and slugs are only final at export.

The briefs live in `shift_art_briefs`, not in the v2 tables. That is the single
most expensive decision available here: the v2 tables are truncated every week,
so a brief stored there would be rewritten every week, changing every image
prompt, invalidating every prompt hash, and re-paying for all ~250 images every
Monday. Keyed durably and hashed on the editorial inputs it was written from, an
unchanged shift costs nothing at all.
"""
from __future__ import annotations

import hashlib
import json

from ...prompts import SYNTHESIS_MODEL, prompt_art_brief
from ..art import store
from ..llm import generate_json


def _context(shift: dict) -> str:
    """The editorial the brief is allowed to see: the arc and the dek.

    Deliberately narrow. Handing over the whole module tree buries the thesis in
    industry notes and evidence, and the brief then describes the page instead of
    the shift.
    """
    parts: list[str] = []
    for module in shift.get('modules') or []:
        if not isinstance(module, dict):
            continue
        data = module.get('data') or {}
        if module.get('type') in {'from_to', 'from_to_solid'}:
            arc_from, arc_to = data.get('from'), data.get('to')
            if arc_from and arc_to:
                parts.append(f'The world is moving from {arc_from} to {arc_to}.')
        elif module.get('type') in {'dek', 'lede'} and data.get('text'):
            parts.append(str(data['text']))
    return ' '.join(parts)[:900]


def brief_inputs_sha256(shift: dict, subs: list[dict]) -> str:
    """What the brief was written from. Unchanged inputs, unchanged brief.

    Ordered and explicit rather than a hash of the whole row: a `db_id` that is
    recycled weekly, or a module reordering that changes nothing a reader sees,
    would otherwise re-pay for every image on the page.
    """
    payload = json.dumps({
        'name': shift.get('name'), 'subtitle': shift.get('subtitle'),
        'context': _context(shift),
        'subs': [[s.get('name'), s.get('subtitle') or s.get('description')]
                 for s in subs],
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def phase10_art_briefs(conn, out: dict) -> dict[tuple[str, str], str]:
    """Returns {(scope, slug): brief}. Never raises — the caller publishes anyway."""
    subs_by_parent: dict[str, list[dict]] = {}
    for sub in out.get('sub_trends') or []:
        parent = str(sub.get('slug') or '').rsplit('/', 1)[0]
        if parent:
            subs_by_parent.setdefault(parent, []).append(sub)

    stored = store.load_briefs(conn)
    briefs: dict[tuple[str, str], str] = {}
    work: list[tuple[dict, list[dict], str]] = []

    for shift in out.get('key_trends') or []:
        slug = str(shift.get('slug') or '')
        if not slug:
            continue
        subs = subs_by_parent.get(slug, [])
        digest = brief_inputs_sha256(shift, subs)
        current = stored.get(('key_trend', slug))
        if current and current['input_sha256'] == digest:
            briefs[('key_trend', slug)] = current['brief']
            for sub in subs:
                held = stored.get(('sub_trend', str(sub.get('slug'))))
                if held:
                    briefs[('sub_trend', str(sub.get('slug')))] = held['brief']
            continue
        work.append((shift, subs, digest))

    if not work:
        print(f'  art briefs: all {len(briefs)} current, nothing to write')
        return briefs

    print(f'  art briefs: writing {len(work)} shift family/families '
          f'({len(briefs)} already current)…')
    results = generate_json(
        work,
        lambda item: prompt_art_brief(item[0].get('name', ''),
                                      item[0].get('subtitle', ''),
                                      _context(item[0]), item[1]),
        default=lambda: {},
        describe=lambda item: str(item[0].get('name', ''))[:30],
    )

    rows: list[dict] = []
    for (shift, subs, digest), result in zip(work, results):
        slug = str(shift.get('slug') or '')
        shift_brief = str(((result or {}).get('shift') or {}).get('brief') or '').strip()
        if not shift_brief:
            # No brief means no art for this family this week; the existing rows
            # (if any) stay, and _jobs simply skips it.
            continue
        briefs[('key_trend', slug)] = shift_brief
        rows.append({'scope': 'key_trend', 'slug': slug, 'brief': shift_brief[:4000],
                     'input_sha256': digest, 'model': SYNTHESIS_MODEL})
        # Matched on name, like the editorial phase, because the model is asked
        # to echo the name verbatim and array order has been wrong before.
        by_name = {str(s.get('name') or '').strip().lower(): s for s in subs}
        for item in (result or {}).get('sub_shifts') or []:
            sub = by_name.get(str((item or {}).get('name') or '').strip().lower())
            brief = str((item or {}).get('brief') or '').strip()
            if not sub or not brief:
                continue
            sub_slug = str(sub.get('slug') or '')
            briefs[('sub_trend', sub_slug)] = brief
            rows.append({'scope': 'sub_trend', 'slug': sub_slug, 'brief': brief[:4000],
                         'input_sha256': digest, 'model': SYNTHESIS_MODEL})

    if rows:
        store.upsert_briefs(conn, rows)
        conn.commit()
    return briefs
