"""Generated artwork: geometry, idempotency, and the rule that it never blocks.

The load-bearing test here is the isolation one. Art generation is now the most
expensive and most failure-prone step in a run that otherwise fails closed, and
a Gemini outage must cost this week's images rather than the taxonomy.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from serious_shift_pipeline.mapgen import art
from serious_shift_pipeline.mapgen.art import gemini, raster
from serious_shift_pipeline.mapgen.art.prompts import (concept_from_modules,
                                                       image_prompt, prompt_sha256)
from serious_shift_pipeline.mapgen.art.style import FRAMES, OG, RAMP, ramp_for


def _png(width=1024, height=1024, colour=(120, 30, 90)) -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (width, height), colour).save(buffer, 'PNG')
    return buffer.getvalue()


def _document():
    return {
        'key_trends': [{'slug': 'silent-commerce', 'name': 'Silent Commerce',
                        'domain_id': 'consumers', 'subtitle': 's', 'modules': []}],
        'sub_trends': [{'slug': 'silent-commerce/charm-arithmetic',
                        'name': 'Charm Arithmetic', 'domain_id': 'consumers',
                        'subtitle': 's', 'modules': []}],
    }


# ── geometry: Pillow must do exactly what object-fit: cover did ──────────

@pytest.mark.parametrize('frame', ['hero', 'wide', 'tile'])
def test_each_frame_lands_on_its_exact_pixel_size(frame):
    spec = FRAMES[frame]
    encoded, digest = raster.cover_crop(_png(), spec['width'], spec['height'],
                                        spec['quality'])
    with Image.open(io.BytesIO(encoded)) as image:
        assert (image.width, image.height) == (spec['width'], spec['height'])
        assert image.format == 'JPEG'
    assert len(digest) == 64


def test_og_is_a_crop_of_the_wide_master_not_a_second_generation():
    """One generation, two outputs — which is why the OG card costs nothing."""
    assert OG['from'] == 'wide'
    master = _png()
    encoded, _ = raster.cover_crop(master, OG['width'], OG['height'], OG['quality'])
    with Image.open(io.BytesIO(encoded)) as image:
        assert (image.width, image.height) == (1200, 630)


def test_a_portrait_master_still_covers_a_panoramic_frame():
    encoded, _ = raster.cover_crop(_png(800, 1400), 1600, 600, 80)
    with Image.open(io.BytesIO(encoded)) as image:
        assert (image.width, image.height) == (1600, 600)


def test_the_digest_is_over_the_encoded_bytes():
    """It is the ETag and the ?v= cache-buster, so identical input must give an
    identical URL and a regeneration must give a different one."""
    first, digest_a = raster.cover_crop(_png(colour=(10, 20, 30)), 640, 640, 78)
    _, digest_b = raster.cover_crop(_png(colour=(10, 20, 30)), 640, 640, 78)
    _, digest_c = raster.cover_crop(_png(colour=(200, 10, 10)), 640, 640, 78)
    assert digest_a == digest_b != digest_c
    assert first[:2] == b'\xff\xd8'  # JPEG SOI


# ── prompt assembly and idempotency ──────────────────────────────────────

def test_the_style_and_the_no_text_guard_are_not_the_brief_to_argue_with():
    prompt = image_prompt('consumers', 'hero', 'A queue of people at a doorway.')
    assert RAMP['consumers']['hot'] in prompt
    assert 'A queue of people at a doorway.' in prompt
    assert FRAMES['hero']['clause'] in prompt
    assert 'No text, no letters' in prompt


def test_an_unknown_sphere_falls_back_rather_than_raising():
    assert ramp_for('not-a-sphere') == RAMP['society']
    assert ramp_for('') == RAMP['society']


def test_the_hash_covers_the_model_and_the_aspect_not_just_the_words():
    """The same words at a different aspect ratio are a different image."""
    base = prompt_sha256('m', '4:5', 'p')
    assert base != prompt_sha256('m', '21:9', 'p')
    assert base != prompt_sha256('other', '4:5', 'p')
    assert base != prompt_sha256('m', '4:5', 'p2')
    assert base == prompt_sha256('m', '4:5', 'p')


def test_the_fallback_concept_keeps_a_sentence_case_initial_intact():
    """"AI treated as…" must not become "aI treated as…"."""
    concept = concept_from_modules('X', arc_from='AI treated as a tool',
                                   arc_to='AI treated as a colleague')
    assert 'AI treated as a tool' in concept
    concept = concept_from_modules('X', arc_from='Trust in brands',
                                   arc_to='Trust in agents')
    assert 'trust in brands' in concept


# ── the rule: art never blocks a publish ─────────────────────────────────

class _Conn:
    def __init__(self):
        self.committed = 0

    def execute(self, sql, params=None):
        return type('_C', (), {'fetchall': lambda _s: [], 'fetchone': lambda _s: None})()

    def commit(self):
        self.committed += 1


def test_a_dead_gemini_never_raises_and_the_document_survives(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'present')
    monkeypatch.setattr(gemini, 'generate_image',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    document = _document()
    stats = art.generate_and_attach(
        _Conn(), document, {('key_trend', 'silent-commerce'): 'a brief'})
    assert stats['failed'] >= 1
    # No key means no key: the frontend falls through to its gradient, which is
    # a finished design. A null or a 404 URL would paint a broken image instead.
    assert 'hero_image' not in document['key_trends'][0]


def test_no_api_key_is_not_fatal(monkeypatch):
    """Unlike the ANTHROPIC_API_KEY check in cli.main, which exits 1."""
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    document = _document()
    stats = art.generate_and_attach(_Conn(), document, {})
    assert stats['generated'] == 0
    assert 'hero_image' not in document['key_trends'][0]


def test_a_shift_with_no_brief_is_skipped_not_guessed(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'present')
    calls = []
    monkeypatch.setattr(gemini, 'generate_image',
                        lambda *a, **k: calls.append(a) or _png())
    art.generate_and_attach(_Conn(), _document(), {})
    assert calls == []


# ── attaching URLs to the candidate ──────────────────────────────────────

def test_urls_carry_the_content_digest_so_a_swap_is_instant():
    document = _document()
    rows = {
        ('key_trend', 'silent-commerce', 'hero'): {'sha256': 'a' * 64},
        ('key_trend', 'silent-commerce', 'wide'): {'sha256': 'b' * 64},
        ('key_trend', 'silent-commerce', 'og'): {'sha256': 'c' * 64},
        ('sub_trend', 'silent-commerce/charm-arithmetic', 'tile'): {'sha256': 'd' * 64},
    }
    attached = art._attach(document, rows)
    shift, sub = document['key_trends'][0], document['sub_trends'][0]
    assert shift['hero_image'] == '/art/hero/silent-commerce.jpg?v=aaaaaaaaaaaa'
    assert shift['hero_image_wide'].startswith('/art/wide/silent-commerce.jpg?v=')
    assert shift['og_image'].startswith('/art/og/')
    assert sub['tile_image'].endswith('?v=dddddddddddd')
    # A sub-shift PAGE inherits the parent's poster; only its tile is its own.
    assert sub['hero_image'] == shift['hero_image']
    assert attached == 4


def test_a_missing_frame_leaves_the_key_off_entirely():
    document = _document()
    art._attach(document, {('key_trend', 'silent-commerce', 'hero'): {'sha256': 'a' * 64}})
    shift = document['key_trends'][0]
    assert 'hero_image' in shift
    assert 'hero_image_wide' not in shift
    assert 'og_image' not in shift


def test_the_route_is_not_nested_under_shift():
    """/shift is already a ServeDir nest_service in the backend; an overlapping
    route panics at router construction."""
    document = _document()
    art._attach(document, {('key_trend', 'silent-commerce', 'hero'): {'sha256': 'a' * 64}})
    assert document['key_trends'][0]['hero_image'].startswith('/art/')
