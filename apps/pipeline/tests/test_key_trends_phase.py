"""Phase 3 must deliver a bounded COUNT RANGE of Key Trends per domain,
sequentially, with a cross-domain name ledger.

Derived from MIN/MAX_KTS_PER_DOM throughout: the overshoot case used to return a
literal 14, which silently stopped testing truncation the moment the ceiling
rose above it.
"""

import serious_shift_pipeline.mapgen.phases.key_trends as kt_phase


class _FakeCursor:
    def __init__(self, next_id):
        self._next_id = next_id

    def fetchone(self):
        return {'id': self._next_id()}


class _FakeConn:
    def __init__(self):
        self._id = 0

    def execute(self, sql, params=None):
        self._id += 1
        return _FakeCursor(lambda: self._id)

    def commit(self):
        pass


def _kt(name):
    return {'name': name, 'subtitle': f'{name} subtitle', 'claim_ids': [1]}


def test_overshoot_is_truncated_at_max(monkeypatch):
    monkeypatch.setattr(kt_phase, 'DOMAINS', [{'id': 'd1', 'name': 'D1', 'description': 'x'}])
    monkeypatch.setattr(
        kt_phase, 'generate_json',
        lambda items, prompt_of, default=None, describe=None:
            [{'key_trends': [_kt(f'Alpha{i} Omega{i}')
                            for i in range(kt_phase.MAX_KTS_PER_DOM + 5)]}])
    out = kt_phase.phase3_key_trends(_FakeConn(), 'key', {'d1': []})
    assert len(out['d1']) == kt_phase.MAX_KTS_PER_DOM


def test_short_response_is_retried_once(monkeypatch):
    monkeypatch.setattr(kt_phase, 'DOMAINS', [{'id': 'd1', 'name': 'D1', 'description': 'x'}])
    calls = []

    def fake(items, prompt_of, default=None, describe=None):
        calls.append(prompt_of(items[0]))
        n = 2 if len(calls) == 1 else kt_phase.MIN_KTS_PER_DOM
        return [{'key_trends': [_kt(f'Alpha{len(calls)}x{i} Omega{len(calls)}x{i}')
                                for i in range(n)]}]

    monkeypatch.setattr(kt_phase, 'generate_json', fake)
    out = kt_phase.phase3_key_trends(_FakeConn(), 'key', {'d1': []})
    assert len(calls) == kt_phase.MAX_KT_ATTEMPTS
    assert len(out['d1']) == kt_phase.MIN_KTS_PER_DOM


def test_domains_share_a_name_ledger(monkeypatch):
    monkeypatch.setattr(kt_phase, 'DOMAINS',
                        [{'id': 'd1', 'name': 'D1', 'description': 'x'}, {'id': 'd2', 'name': 'D2', 'description': 'x'}])
    prompts = []

    def fake(items, prompt_of, default=None, describe=None):
        prompts.append(prompt_of(items[0]))
        return [{'key_trends': [_kt(f'{items[0]["id"].upper()} Trend {i}')
                                for i in range(kt_phase.MIN_KTS_PER_DOM)]}]

    monkeypatch.setattr(kt_phase, 'generate_json', fake)
    kt_phase.phase3_key_trends(_FakeConn(), 'key', {'d1': [], 'd2': []})
    # The second domain's prompt must list the first domain's names as taken.
    assert 'D1 Trend 0' in prompts[1]
    assert 'D1 Trend 0' not in prompts[0]


# ── Name families across spheres ─────────────────────────────────────────────
# "Cognition Stake" (Society) and "Cognition Bleed" (Consumers) were both legal
# by exact equality; the 2026-08-19 review named three such key-shift pairs.


def test_a_new_name_echoing_a_family_across_spheres_is_walked_past(monkeypatch):
    monkeypatch.setattr(kt_phase, 'DOMAINS',
                        [{'id': 'd1', 'name': 'D1', 'description': 'x'},
                         {'id': 'd2', 'name': 'D2', 'description': 'x'}])

    def fake(items, prompt_of, default=None, describe=None):
        if items[0]['id'] == 'd1':
            names = ['Cognition Stake', 'Cognition Bleed', 'Power Fusion']
        else:
            names = ['Cognition Drift', 'Silent Commerce']
        return [{'key_trends': [_kt(n) for n in names]}]

    monkeypatch.setattr(kt_phase, 'generate_json', fake)
    out = kt_phase.phase3_key_trends(_FakeConn(), 'key', {'d1': [], 'd2': []})
    d1 = [kt['name'] for kt in out['d1']]
    d2 = [kt['name'] for kt in out['d2']]
    # two Cognitions fill the cap; the third, in another sphere, is walked past
    assert d1 == ['Cognition Stake', 'Cognition Bleed', 'Power Fusion']
    assert d2 == ['Silent Commerce']


def test_a_carried_name_is_exempt_from_the_family_cap(monkeypatch):
    """Continuity beats the lint: retiring a live label is a deliberate act,
    not a side-effect. Both live Cognitions return; a NEW third is refused."""
    monkeypatch.setattr(kt_phase, 'DOMAINS',
                        [{'id': 'd1', 'name': 'D1', 'description': 'x'}])
    previous = {'d1': [{'slug': 'cognition-stake', 'name': 'Cognition Stake',
                        'subtitle': 's'},
                       {'slug': 'cognition-bleed', 'name': 'Cognition Bleed',
                        'subtitle': 's'}]}

    def fake(items, prompt_of, default=None, describe=None):
        padding = [_kt(f'Alpha{i} Omega{i}')
                   for i in range(kt_phase.MIN_KTS_PER_DOM)]
        return [{'key_trends': [_kt('Cognition Stake'), _kt('Cognition Bleed'),
                                _kt('Cognition Trap'), _kt('Power Fusion')]
                 + padding}]

    monkeypatch.setattr(kt_phase, 'generate_json', fake)
    out = kt_phase.phase3_key_trends(_FakeConn(), 'key', {'d1': []}, previous=previous)
    names = [kt['name'] for kt in out['d1']]
    assert 'Cognition Stake' in names and 'Cognition Bleed' in names
    assert 'Cognition Trap' not in names
    assert 'Power Fusion' in names


def test_a_new_name_cannot_steal_a_reserved_live_name(monkeypatch):
    """Belt to the prompt's braces: another sphere's live name is refused in
    code, not just forbidden in the TAKEN block."""
    monkeypatch.setattr(kt_phase, 'DOMAINS',
                        [{'id': 'd1', 'name': 'D1', 'description': 'x'},
                         {'id': 'd2', 'name': 'D2', 'description': 'x'}])
    previous = {'d2': [{'slug': 'entry-freeze', 'name': 'Entry Freeze',
                        'subtitle': 's'}]}

    def fake(items, prompt_of, default=None, describe=None):
        if items[0]['id'] == 'd1':
            return [{'key_trends': [_kt('Entry Freeze'), _kt('Silent Commerce')]}]
        return [{'key_trends': [_kt('Entry Freeze')]}]

    monkeypatch.setattr(kt_phase, 'generate_json', fake)
    out = kt_phase.phase3_key_trends(_FakeConn(), 'key', {'d1': [], 'd2': []},
                                     previous=previous)
    assert [kt['name'] for kt in out['d1']] == ['Silent Commerce']
    assert [kt['name'] for kt in out['d2']] == ['Entry Freeze']
