"""POST the published shift list to an external endpoint.

Fired from `_publish_candidate` immediately after the document promotion commits,
so a receiver sees exactly the taxonomy the site is serving — there is no other
moment at which the taxonomy changes.

The payload keys on **slugs and names**, not database ids, because
`domain_key_trends.id` is recycled by `reset_v2_tables` on every run. The durable
identity is `(scope, slug)` in `shift_refs`, which is also what
`POST /api/innovations/ingest` accepts in its `shifts` field — so a receiver can
hand any value here straight back to the ingest endpoint.

Delivery follows the `run.notify()` contract: stdlib urllib, an explicit timeout,
and failure logged rather than raised. The map is already committed by the time
this runs, and a dead receiver must not be able to turn a good publication into a
failed run.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..core.redaction import redact_secrets

WEBHOOK_ENV = 'SS_SHIFTS_WEBHOOK_URL'
TIMEOUT_SECONDS = 15


def _href(domain_id: str, slug: str) -> str:
    """Site-relative path. Correct for both scopes: a sub-shift's published slug
    is already the two-segment `parent/child` path (see export.py), which is the
    same fact seo.py's route builder relies on."""
    return f'/{domain_id}/{slug}'


def build_shift_map_payload(out: dict, *, run_id: str | None = None,
                            published_at: str | None = None) -> dict:
    """Shape the published document into spheres → key shifts → sub-shifts.

    Order is editorial, not alphabetical: spheres come in document order (which is
    `sort_order`: Society, Economy, Consumers, Organizations), and the shifts under
    them follow `key_trend_ids` / `sub_trend_ids` rather than being re-sorted here.

    An id that does not resolve is skipped rather than raising. The publication gate
    has already proven every reference resolves, so this cannot happen in practice —
    and if it somehow does, the notification is the wrong place to discover it.
    """
    shifts_by_id = {str(s.get('id')): s for s in out.get('key_trends') or []}
    subs_by_id = {str(s.get('id')): s for s in out.get('sub_trends') or []}

    spheres = []
    n_shifts = n_subs = 0
    for domain in out.get('domains') or []:
        domain_id = str(domain.get('id') or '')
        key_shifts = []
        for shift_id in domain.get('key_trend_ids') or []:
            shift = shifts_by_id.get(str(shift_id))
            if not shift:
                continue
            sub_shifts = []
            for sub_id in shift.get('sub_trend_ids') or []:
                sub = subs_by_id.get(str(sub_id))
                if not sub:
                    continue
                sub_slug = str(sub.get('slug') or '')
                sub_shifts.append({
                    'slug': sub_slug,
                    'name': sub.get('name') or '',
                    'description': sub.get('description') or '',
                    'href': _href(domain_id, sub_slug),
                })
            slug = str(shift.get('slug') or '')
            key_shifts.append({
                'slug': slug,
                'name': shift.get('name') or '',
                'subtitle': shift.get('subtitle') or '',
                'velocity': shift.get('velocity') or '',
                'href': _href(domain_id, slug),
                'sub_shifts': sub_shifts,
            })
            n_subs += len(sub_shifts)
        n_shifts += len(key_shifts)
        spheres.append({
            'id': domain_id,
            'name': domain.get('name') or '',
            'label': domain.get('label') or '',
            'key_shifts': key_shifts,
        })

    if published_at is None:
        published_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    return {
        'event': 'shift_map.published',
        # `updated` is a date, so two publications on one day share it. Order and
        # dedupe on `published_at` or `run_id`.
        'published_at': published_at,
        'updated': out.get('updated'),
        'run_id': run_id,
        'totals': {
            'spheres': len(spheres),
            'key_shifts': n_shifts,
            'sub_shifts': n_subs,
        },
        'spheres': spheres,
    }


def post_shift_map(out: dict) -> bool:
    """Deliver the published shift list. Returns True only on a delivered POST.

    Unset SS_SHIFTS_WEBHOOK_URL disables the hook silently — dev machines, tests and
    CI publish exactly as they did before.
    """
    url = os.environ.get(WEBHOOK_ENV, '').strip()
    if not url:
        return False

    payload = build_shift_map_payload(out, run_id=os.environ.get('SS_RUN_ID') or None)
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS):
            pass
    except Exception as e:  # noqa: BLE001 — delivery must never break the run
        print(f'[shift-map] delivery failed: {redact_secrets(e)}', flush=True)
        return False

    host = urllib.parse.urlsplit(url).hostname or url
    totals = payload['totals']
    print(f'✓  shift map → {host} · {totals["key_shifts"]} key shifts · '
          f'{totals["sub_shifts"]} sub shifts', flush=True)
    return True
