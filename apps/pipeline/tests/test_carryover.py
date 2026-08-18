"""What a republication is allowed to move.

These pin the one property the whole carry-forward exists for: a shift that
survives a run keeps its URL. Everything downstream — hero and OG artwork,
`shift_module_overrides`, `shift_refs`, innovation links, external inbound
links — is keyed on that slug and detaches silently when it moves, so a
regression here is invisible until someone notices a page has gone grey.
"""
from __future__ import annotations

import json

import pytest

from serious_shift_pipeline.mapgen import carryover


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _Conn:
    """Answers the two queries `load_published_taxonomy` can make."""

    def __init__(self, *, document=None, refs=()):
        self.document = document
        self.refs = list(refs)

    def execute(self, sql, params=None):
        if 'FROM documents' in sql:
            return _Cursor([{'body': self.document}] if self.document is not None else [])
        if 'FROM shift_refs' in sql:
            return _Cursor(self.refs)
        raise AssertionError(f'unexpected query: {sql}')


def _doc(*shifts):
    return {'key_trends': [
        {'slug': s, 'name': n, 'subtitle': '', 'domain_id': d}
        for s, n, d in shifts
    ]}


def _row(rid, name, domain='society'):
    return {'id': rid, 'domain_id': domain, 'name': name}


# ── loading ──────────────────────────────────────────────────────────────

def test_no_publication_yet_is_not_an_error():
    """A fresh database must behave exactly as it did before this module."""
    assert carryover.load_published_taxonomy(_Conn()) == {}


def test_the_document_is_read_as_json_whether_or_not_the_driver_parsed_it():
    parsed = carryover.load_published_taxonomy(
        _Conn(document=_doc(('proof-premium', 'Proof Premium', 'society'))))
    as_text = carryover.load_published_taxonomy(
        _Conn(document=json.dumps(_doc(('proof-premium', 'Proof Premium', 'society')))))
    assert parsed == as_text
    assert parsed['society'][0]['slug'] == 'proof-premium'


def test_shift_refs_answers_when_the_document_cannot():
    """`shift_refs` survives the v2 truncation, so it still answers after a
    half-finished run — which is exactly when we most need to know what is live."""
    got = carryover.load_published_taxonomy(_Conn(refs=[
        {'slug': 'proof-premium', 'title': 'Proof Premium', 'domain_id': 'society'}]))
    assert got['society'][0]['name'] == 'Proof Premium'


def test_a_shift_missing_its_slug_or_name_is_skipped_not_fatal():
    got = carryover.load_published_taxonomy(_Conn(document={'key_trends': [
        {'slug': '', 'name': 'Nameless', 'domain_id': 'society'},
        {'slug': 'real', 'name': 'Real Shift', 'domain_id': 'society'},
    ]}))
    assert [s['slug'] for s in got['society']] == ['real']


# ── pinning ──────────────────────────────────────────────────────────────

def test_an_unchanged_name_keeps_its_slug():
    previous = carryover.load_published_taxonomy(
        _Conn(document=_doc(('proof-premium', 'Proof Premium', 'society'))))
    slugs, report = carryover.pin_slugs([_row(1, 'Proof Premium')], previous)
    assert slugs == {1: 'proof-premium'}
    assert (report['carried'], report['renamed'], report['added']) == (1, 0, 0)


def test_casing_and_spacing_do_not_count_as_a_rename():
    """The URL does not distinguish these, so neither may we."""
    previous = carryover.load_published_taxonomy(
        _Conn(document=_doc(('proof-premium', 'Proof Premium', 'society'))))
    slugs, report = carryover.pin_slugs([_row(1, 'proof  premium')], previous)
    assert slugs == {1: 'proof-premium'}
    assert report['carried'] == 1


def test_word_order_is_meaning_in_a_coined_name():
    """"Trust Proxy" and "Proxy Trust" are two shifts, not one renamed."""
    previous = carryover.load_published_taxonomy(
        _Conn(document=_doc(('trust-proxy', 'Trust Proxy', 'society'))))
    slugs, _ = carryover.pin_slugs([_row(1, 'Proxy Trust')], previous)
    assert slugs[1] != 'trust-proxy'


def test_a_rename_keeps_the_slug_and_is_reported():
    """The point of the exercise: the label moves, the page does not."""
    previous = carryover.load_published_taxonomy(
        _Conn(document=_doc(('silent-commerce', 'Silent Commerce', 'consumers'))))
    slugs, report = carryover.pin_slugs(
        [_row(1, 'Silent Commerce Rising', domain='consumers')], previous)
    assert slugs == {1: 'silent-commerce'}
    assert report['renamed'] == 1
    assert report['renames'] == [('Silent Commerce', 'Silent Commerce Rising')]


def test_two_shifts_merely_sharing_a_noun_are_not_a_rename():
    """The prompt asks for these to be differentiated, so they are distinct
    shifts — pinning one onto the other would hand a live URL to a new page."""
    previous = carryover.load_published_taxonomy(
        _Conn(document=_doc(('trust-proxy', 'Trust Proxy', 'society'))))
    slugs, report = carryover.pin_slugs([_row(1, 'Trust Collapse')], previous)
    assert slugs == {1: 'trust-collapse'}
    assert report['renamed'] == 0
    assert report['added'] == 1


def test_a_shift_is_not_the_same_shift_in_another_sphere():
    previous = carryover.load_published_taxonomy(
        _Conn(document=_doc(('proof-premium', 'Proof Premium', 'society'))))
    slugs, report = carryover.pin_slugs(
        [_row(1, 'Proof Premium', domain='economy')], previous)
    assert slugs[1] != 'proof-premium'
    assert report['retired'] == 1


@pytest.mark.parametrize('order', [(0, 1), (1, 0)])
def test_a_newcomer_never_takes_a_surviving_shifts_slug(order):
    """The regression that would quietly break the most.

    Two spheres coin the same name; one has been live for weeks. The survivor
    must keep the bare slug whichever order the rows arrive in — if the newcomer
    takes it, every inbound link, the hero image and the editor's overrides all
    silently transfer to a different sphere's page.
    """
    previous = carryover.load_published_taxonomy(
        _Conn(document=_doc(('proof-premium', 'Proof Premium', 'society'))))
    newcomer = _row(1, 'Proof Premium', domain='economy')
    survivor = _row(2, 'Proof Premium', domain='society')
    rows = [newcomer, survivor]
    slugs, report = carryover.pin_slugs([rows[order[0]], rows[order[1]]], previous)
    assert slugs[2] == 'proof-premium'
    assert slugs[1] == 'proof-premium-2'
    assert (report['carried'], report['added']) == (1, 1)


def test_a_retired_slug_is_not_handed_to_an_unrelated_shift():
    """Artwork and overrides are keyed on the slug and outlive the shift, so
    reusing a just-retired slug would dress a new page in a departed one's hero
    image and silently apply its editor overrides."""
    previous = carryover.load_published_taxonomy(
        _Conn(document=_doc(('proof-premium', 'Proof Premium', 'society'))))
    slugs, report = carryover.pin_slugs(
        [_row(1, 'Proof Premium', domain='economy')], previous)
    assert slugs[1] == 'proof-premium-2'
    assert report['retired'] == 1


def test_every_row_gets_a_slug_and_no_two_share_one():
    previous = carryover.load_published_taxonomy(
        _Conn(document=_doc(('a-shift', 'A Shift', 'society'))))
    rows = [_row(i, n) for i, n in enumerate(
        ['A Shift', 'A Shift', 'Other Thing', 'Other Thing'], start=1)]
    slugs, _ = carryover.pin_slugs(rows, previous)
    assert len(slugs) == len(rows)
    assert len(set(slugs.values())) == len(rows)


def test_retired_shifts_are_counted_so_a_human_can_see_what_left():
    previous = carryover.load_published_taxonomy(_Conn(document=_doc(
        ('kept', 'Kept Shift', 'society'), ('gone', 'Gone Shift', 'society'))))
    _, report = carryover.pin_slugs([_row(1, 'Kept Shift')], previous)
    assert (report['carried'], report['retired']) == (1, 1)


def test_pinning_is_order_independent():
    """Pass 2 resolves best-score-first, so shuffling the input cannot change
    which shift inherits which slug."""
    previous = carryover.load_published_taxonomy(_Conn(document=_doc(
        ('silent-commerce', 'Silent Commerce', 'consumers'),
        ('proof-premium', 'Proof Premium', 'consumers'))))
    rows = [_row(1, 'Silent Commerce Rising', 'consumers'),
            _row(2, 'Proof Premium Effect', 'consumers')]
    forward, _ = carryover.pin_slugs(rows, previous)
    backward, _ = carryover.pin_slugs(list(reversed(rows)), previous)
    assert forward == backward


@pytest.mark.parametrize('previous', [{}, {'society': []}])
def test_with_nothing_to_carry_slugs_come_from_the_name(previous):
    slugs, report = carryover.pin_slugs([_row(1, 'Brand New')], previous)
    assert slugs == {1: 'brand-new'}
    assert report['had_previous'] is bool(previous)
