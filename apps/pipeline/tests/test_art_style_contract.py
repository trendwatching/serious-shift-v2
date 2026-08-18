"""The Python port and generate-art.mjs must describe the same picture.

`mapgen/art/style.py` copies the collage style, the four sphere ramps, the frame
specs and the no-text guard out of `apps/frontend/scripts/generate-art.mjs`,
because a frontend build script cannot be imported from Python. Duplication is
the right call there — but only if it is checked, otherwise the two drift and
the site ends up with two house styles depending on which tool drew the image.

Skipped when the .mjs is absent, the same escape hatch the other repo-file tests
use: the pipeline is installed without the frontend tree.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from serious_shift_pipeline.mapgen.art.style import FRAMES, NO_TEXT, OG, RAMP, collage

_MJS = (Path(__file__).resolve().parents[3]
        / 'apps' / 'frontend' / 'scripts' / 'generate-art.mjs')

pytestmark = pytest.mark.skipif(
    not _MJS.exists(), reason='generate-art.mjs not present (installed layout)')


@pytest.fixture(scope='module')
def source() -> str:
    return _MJS.read_text(encoding='utf-8')


@pytest.mark.parametrize('sphere', sorted(RAMP))
def test_every_sphere_ramp_matches_the_javascript(source, sphere):
    """The ramps are also PALETTE in generate-heroes.mjs and --grad-sunset in
    tokens.css, so a drift here is a drift in the site's colour identity."""
    pattern = (rf"{sphere}:\s*\{{\s*hot:\s*'([^']+)',\s*dark:\s*'([^']+)',"
               rf"\s*tone:\s*'([^']+)'")
    found = re.search(pattern, source)
    assert found, f'{sphere} ramp not found in generate-art.mjs'
    hot, dark, tone = found.groups()
    assert RAMP[sphere] == {'hot': hot, 'dark': dark, 'tone': tone}


def test_the_collage_style_renders_the_same_words(source):
    """The style string is the house style. Reassembled from the .mjs template
    literal and compared to what the Python renders for the same ramp."""
    block = re.search(r"collage:\s*\(ramp\)\s*=>\s*(.*?),\n\}", source, re.S)
    assert block, 'collage style not found in generate-art.mjs'
    literal = block.group(1)
    # Concatenated string parts, with ${ramp.hot} / ${ramp.tone} interpolated.
    parts = re.findall(r"[`']((?:[^`'\\]|\\.)*)[`']", literal)
    rendered = ''.join(parts)
    for sphere, ramp in RAMP.items():
        expected = (rendered
                    .replace('${ramp.hot}', ramp['hot'])
                    .replace('${ramp.tone}', ramp['tone']))
        assert collage(ramp) == expected, f'collage style drifted for {sphere}'


@pytest.mark.parametrize('frame', ['hero', 'wide'])
def test_the_generated_frames_match(source, frame):
    found = re.search(
        rf"{frame}:\s*\{{[^}}]*?aspect:\s*'([^']+)'[^}}]*?w:\s*(\d+),\s*h:\s*(\d+),"
        rf"\s*quality:\s*(\d+)", source, re.S)
    assert found, f'{frame} frame not found in generate-art.mjs'
    aspect, width, height, quality = found.groups()
    spec = FRAMES[frame]
    assert (spec['aspect'], spec['width'], spec['height'], spec['quality']) == (
        aspect, int(width), int(height), int(quality))


def test_the_tile_frame_matches_the_javascripts_sub_frame(source):
    """Named `sub` in the .mjs and `tile` here — the DB frame is what the URL
    says, and the URL says tile."""
    found = re.search(
        r"sub:\s*\{[^}]*?aspect:\s*'([^']+)'[^}]*?w:\s*(\d+),\s*h:\s*(\d+),"
        r"\s*quality:\s*(\d+)", source, re.S)
    assert found, 'sub frame not found in generate-art.mjs'
    aspect, width, height, quality = found.groups()
    spec = FRAMES['tile']
    assert (spec['aspect'], spec['width'], spec['height'], spec['quality']) == (
        aspect, int(width), int(height), int(quality))


def test_the_og_crop_matches(source):
    found = re.search(r"OG\s*=\s*\{[^}]*?w:\s*(\d+),\s*h:\s*(\d+),\s*quality:\s*(\d+)",
                      source, re.S)
    assert found, 'OG frame not found in generate-art.mjs'
    width, height, quality = found.groups()
    assert (OG['width'], OG['height'], OG['quality']) == (
        int(width), int(height), int(quality))


def test_the_no_text_guard_is_word_for_word(source):
    """Weaken this and the model starts writing garbled signage into posters."""
    block = re.search(r"const NO_TEXT\s*=\s*((?:\s*\+?\s*'[^']*')+)", source)
    assert block, 'NO_TEXT not found in generate-art.mjs'
    parts = re.findall(r"[`']((?:[^`'\\]|\\.)*)[`']", block.group(1))
    assert NO_TEXT == ''.join(parts)
