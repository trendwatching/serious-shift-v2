"""Phase 3 asks each sphere to keep the shifts it already publishes.

The invariant these exist to hold is disjointness: a sphere is shown its OWN
live names under CONTINUITY and asked to return them, while every OTHER
sphere's live names go under TAKEN, which forbids reusing or even echoing them.
If the two blocks ever overlap the prompt tells the model to return and to avoid
the same words in the same breath, and the carry-forward quietly stops working
— with no error anywhere, because drift is deliberately never a gate.
"""
from __future__ import annotations

import serious_shift_pipeline.mapgen.phases.key_trends as kt_phase
from serious_shift_pipeline.mapgen.config import KT_CHANGE_BUDGET


class _FakeConn:
    """Hands back an incrementing id, which is all the INSERT needs."""

    def __init__(self):
        self._id = 0

    def execute(self, sql, params=None):
        self._id += 1
        current = self._id
        return type('_C', (), {'fetchone': lambda _self: {'id': current}})()

    def commit(self):
        pass


def _kt(name):
    return {'name': name, 'subtitle': f'{name} subtitle', 'claim_ids': [1]}

TWO_SPHERES = [
    {'id': 'society', 'name': 'Society', 'description': 'x'},
    {'id': 'economy', 'name': 'Economy', 'description': 'y'},
]

PUBLISHED = {
    'society': [{'slug': 'proof-premium', 'name': 'Proof Premium',
                 'subtitle': 'Verification becomes the product.'}],
    'economy': [{'slug': 'entry-freeze', 'name': 'Entry Freeze',
                 'subtitle': 'The junior rung disappears.'}],
}


def _capture(monkeypatch, *, previous, domains=TWO_SPHERES, returns=None):
    """Run phase 3 against fakes and return {domain_name: rendered prompt}."""
    monkeypatch.setattr(kt_phase, 'DOMAINS', domains)
    prompts: dict = {}

    def fake(items, prompt_of, default=None, describe=None):
        dom = items[0]
        prompts[dom['name']] = prompt_of(dom)
        names = (returns or {}).get(dom['id'])
        if names is None:
            # Distinct words per name: shared head/tail words now count as a
            # family and are deliberately walked past.
            names = [f'{dom["name"]}{i} Trend{i}' for i in range(kt_phase.MIN_KTS_PER_DOM)]
        return [{'key_trends': [_kt(n) for n in names]}]

    monkeypatch.setattr(kt_phase, 'generate_json', fake)
    out = kt_phase.phase3_key_trends(
        _FakeConn(), 'key', {d['id']: [] for d in domains}, previous=previous)
    return prompts, out


def test_a_sphere_is_shown_its_own_live_shifts(monkeypatch):
    prompts, _ = _capture(monkeypatch, previous=PUBLISHED)
    assert 'Proof Premium' in prompts['Society']
    assert 'Verification becomes the product.' in prompts['Society']


def test_a_spheres_own_names_are_never_in_its_taken_block(monkeypatch):
    """The disjointness invariant. TAKEN forbids echoes, so a live name landing
    there would forbid the very carry-forward CONTINUITY asks for."""
    prompts, _ = _capture(monkeypatch, previous=PUBLISHED)
    taken = prompts['Society'].split('TAKEN —', 1)[1]
    assert 'Proof Premium' not in taken


def test_another_spheres_live_names_are_reserved_before_it_is_asked(monkeypatch):
    """Society runs first and must not coin the name Economy is about to be
    asked to carry forward."""
    prompts, _ = _capture(monkeypatch, previous=PUBLISHED)
    taken = prompts['Society'].split('TAKEN —', 1)[1]
    assert 'Entry Freeze' in taken


def test_a_first_run_renders_the_none_line_and_does_not_crash(monkeypatch):
    prompts, out = _capture(monkeypatch, previous={})
    assert '- (none)' in prompts['Society']
    assert len(out['society']) == kt_phase.MIN_KTS_PER_DOM


def test_the_template_leaves_no_token_unrendered(monkeypatch):
    """A stray {{token}} reaches the model verbatim and is invisible in output."""
    prompts, _ = _capture(monkeypatch, previous=PUBLISHED)
    assert '{{' not in prompts['Society']


def test_the_change_budget_is_named_in_the_prompt(monkeypatch):
    prompts, _ = _capture(monkeypatch, previous=PUBLISHED)
    assert f'at most {KT_CHANGE_BUDGET} names' in prompts['Society']


def test_a_failed_sphere_carries_forward_rather_than_retiring_live_shifts(monkeypatch):
    """generate_json swallows a failed call into `default`. Against a published
    map that would retire every live URL in the sphere — and everything keyed to
    them — because one batch errored. A stale week is the cheaper failure."""
    published = {'society': [
        {'slug': f'live-{i}', 'name': f'Live Shift {i}', 'subtitle': f's{i}'}
        for i in range(kt_phase.MIN_KTS_PER_DOM)]}
    _, out = _capture(
        monkeypatch,
        previous=published,
        domains=[{'id': 'society', 'name': 'Society', 'description': 'x'}],
        returns={'society': []},
    )
    assert [kt['name'] for kt in out['society']] == \
        [entry['name'] for entry in published['society']]


def test_a_failed_sphere_with_nothing_published_still_publishes_short(monkeypatch):
    """Without a prior map there is nothing to carry, so the count gate decides
    — the behaviour this had before carryover existed."""
    _, out = _capture(
        monkeypatch,
        previous={},
        domains=[{'id': 'society', 'name': 'Society', 'description': 'x'}],
        returns={'society': []},
    )
    assert out['society'] == []
