"""The publication webhook: payload shape, and the promise that it cannot fail a run.

The hook fires post-commit, after the map is already promoted and the site is already
serving it. So the property that matters most here is negative — no configuration, no
network condition and no receiver error may propagate out of `post_shift_map` — and it
is tested directly, because the alternative failure mode is a good publication being
recorded as a failed run.

The shape tests exist because the payload is a contract with a system outside this
repo (docs/SHIFT-MAP-WEBHOOK.md): slugs and ordering are the parts a receiver builds
against, and both are derived rather than stored, so nothing else would catch a drift.
"""
from __future__ import annotations

import json

from serious_shift_pipeline.mapgen import publish_hook
from serious_shift_pipeline.mapgen.publish_hook import (
    build_shift_map_payload, post_shift_map,
)


def _document() -> dict:
    """A miniature publication: two spheres, two key shifts, three sub-shifts.

    Deliberately declared with the ids out of array order, so a payload that walked
    `key_trends` directly instead of following `key_trend_ids` would fail the order
    assertions below rather than passing by coincidence.
    """
    return {
        'updated': '2026-08-17',
        'domains': [
            {'id': 'society', 'name': 'Society', 'label': 'AI × Society',
             'horizon': '2028', 'key_trend_ids': ['kt-2', 'kt-1']},
            {'id': 'economy', 'name': 'Economy', 'label': 'AI × Economy',
             'horizon': '2027', 'key_trend_ids': []},
        ],
        'key_trends': [
            {'id': 'kt-1', 'domain_id': 'society', 'slug': 'consent-collapse',
             'name': 'Consent Collapse', 'subtitle': 'Permission stops scaling.',
             'velocity': 'accelerating', 'sub_trend_ids': ['st-3']},
            {'id': 'kt-2', 'domain_id': 'society', 'slug': 'psyche-capture',
             'name': 'Psyche Capture', 'subtitle': 'Interior state as product.',
             'velocity': 'rising', 'sub_trend_ids': ['st-2', 'st-1']},
        ],
        'sub_trends': [
            {'id': 'st-1', 'key_trend_id': 'kt-2', 'domain_id': 'society',
             'slug': 'psyche-capture/mood-markets', 'name': 'Mood Markets',
             'description': 'Emotional read-outs priced like any other signal.'},
            {'id': 'st-2', 'key_trend_id': 'kt-2', 'domain_id': 'society',
             'slug': 'psyche-capture/affect-audits', 'name': 'Affect Audits',
             'description': 'Feeling measured on a schedule.'},
            {'id': 'st-3', 'key_trend_id': 'kt-1', 'domain_id': 'society',
             'slug': 'consent-collapse/opt-out-theatre', 'name': 'Opt-Out Theatre',
             'description': 'Refusal offered, refusal engineered away.'},
        ],
    }


# ── Shape ────────────────────────────────────────────────────────────────────

def test_order_is_editorial_not_array_order():
    payload = build_shift_map_payload(_document(), run_id='r1')

    assert [s['id'] for s in payload['spheres']] == ['society', 'economy']
    society = payload['spheres'][0]
    # `key_trend_ids` says kt-2 then kt-1; the arrays say the reverse.
    assert [s['slug'] for s in society['key_shifts']] == [
        'psyche-capture', 'consent-collapse']
    assert [s['name'] for s in society['key_shifts'][0]['sub_shifts']] == [
        'Affect Audits', 'Mood Markets']


def test_sub_shift_slug_keeps_both_segments():
    """The two-segment form IS `shift_refs.slug` for scope='sub_trend' — it is what
    POST /api/innovations/ingest accepts, so truncating it would break the round trip."""
    payload = build_shift_map_payload(_document())
    sub = payload['spheres'][0]['key_shifts'][0]['sub_shifts'][0]

    assert sub['slug'] == 'psyche-capture/affect-audits'
    assert sub['href'] == '/society/psyche-capture/affect-audits'


def test_key_shift_fields_and_href():
    payload = build_shift_map_payload(_document())
    shift = payload['spheres'][0]['key_shifts'][0]

    assert shift['slug'] == 'psyche-capture'
    assert shift['name'] == 'Psyche Capture'
    assert shift['subtitle'] == 'Interior state as product.'
    assert shift['velocity'] == 'rising'
    assert shift['href'] == '/society/psyche-capture'


def test_totals_count_what_was_emitted():
    payload = build_shift_map_payload(_document())

    assert payload['totals'] == {'spheres': 2, 'key_shifts': 2, 'sub_shifts': 3}
    emitted_subs = sum(len(k['sub_shifts'])
                       for s in payload['spheres'] for k in s['key_shifts'])
    assert payload['totals']['sub_shifts'] == emitted_subs


def test_envelope_carries_run_identity():
    payload = build_shift_map_payload(
        _document(), run_id='20260817T024003-synthesize-a1b2c3',
        published_at='2026-08-17T02:41:09Z')

    assert payload['event'] == 'shift_map.published'
    assert payload['updated'] == '2026-08-17'
    assert payload['run_id'] == '20260817T024003-synthesize-a1b2c3'
    # A date is not unique per delivery; this is what a receiver dedupes on.
    assert payload['published_at'] == '2026-08-17T02:41:09Z'


def test_a_dangling_reference_is_skipped_not_raised():
    """The gate proves every reference resolves, so this cannot happen — and if it
    somehow did, a notification is the wrong place to discover it."""
    doc = _document()
    doc['domains'][0]['key_trend_ids'].append('kt-missing')
    doc['key_trends'][1]['sub_trend_ids'].append('st-missing')

    payload = build_shift_map_payload(doc)

    assert payload['totals'] == {'spheres': 2, 'key_shifts': 2, 'sub_shifts': 3}


# ── Delivery ─────────────────────────────────────────────────────────────────

def test_unset_url_sends_nothing(monkeypatch):
    monkeypatch.delenv(publish_hook.WEBHOOK_ENV, raising=False)
    monkeypatch.setattr(publish_hook.urllib.request, 'urlopen', _explode)

    assert post_shift_map(_document()) is False


def test_a_dead_receiver_does_not_raise(monkeypatch, capsys):
    monkeypatch.setenv(publish_hook.WEBHOOK_ENV, 'https://receiver.example/shifts')
    monkeypatch.setattr(publish_hook.urllib.request, 'urlopen', _explode)

    # No pytest.raises: the whole point is that nothing escapes. A publication has
    # already committed by the time this runs.
    assert post_shift_map(_document()) is False
    assert 'delivery failed' in capsys.readouterr().out


def test_credentials_in_the_url_stay_out_of_the_log(monkeypatch, capsys):
    monkeypatch.setenv(publish_hook.WEBHOOK_ENV, 'https://tok:sec@receiver.example/x')
    monkeypatch.setattr(
        publish_hook.urllib.request, 'urlopen',
        lambda *a, **k: (_ for _ in ()).throw(
            OSError('refused by https://tok:sec@receiver.example/x')))

    post_shift_map(_document())

    assert 'sec@' not in capsys.readouterr().out


def test_a_delivered_post_carries_the_payload(monkeypatch, capsys):
    sent = {}

    class _Response:
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    def _capture(req, timeout=None):
        sent['url'] = req.full_url
        sent['headers'] = dict(req.headers)
        sent['body'] = json.loads(req.data)
        sent['timeout'] = timeout
        return _Response()

    monkeypatch.setenv(publish_hook.WEBHOOK_ENV, 'https://receiver.example/shifts')
    monkeypatch.setenv('SS_RUN_ID', '20260817T024003-export-a1b2c3')
    monkeypatch.setattr(publish_hook.urllib.request, 'urlopen', _capture)

    assert post_shift_map(_document()) is True
    assert sent['url'] == 'https://receiver.example/shifts'
    # urllib title-cases header names on the Request object.
    assert sent['headers']['Content-type'] == 'application/json'
    assert sent['timeout'] == publish_hook.TIMEOUT_SECONDS
    assert sent['body']['run_id'] == '20260817T024003-export-a1b2c3'
    assert sent['body']['totals']['sub_shifts'] == 3
    # The host reaches the log; nothing else about the delivery does.
    assert 'receiver.example' in capsys.readouterr().out


def _explode(*args, **kwargs):
    raise OSError('connection refused')
