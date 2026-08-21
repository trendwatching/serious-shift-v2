"""The art direction, ported verbatim from apps/frontend/scripts/generate-art.mjs.

Duplicated rather than shared, and deliberately so: the .mjs is a frontend build
script that cannot be imported from Python, and the values below are a design
decision — the four sphere ramps also appear in `generate-heroes.mjs` PALETTE and
in `--grad-sunset` in styles/tokens.css, and that file's exports are hashed by
check-frame.mjs. tests/test_art_style_contract.py parses the .mjs and asserts
these render byte-identically, so the duplication is checked rather than trusted.

Only the `collage` style is ported. The 17 Aug 2026 Miro review picked it, and
the other four presets exist to be compared against, which is a job the .mjs
still does with --samples.
"""
from __future__ import annotations

#: The four sunset ramps. `tone` names the near-black ground for the prompt.
RAMP: dict[str, dict[str, str]] = {
    'society':       {'hot': '#FF007A', 'dark': '#39001F', 'tone': 'deep plum, near-black'},
    'economy':       {'hot': '#0FA6FF', 'dark': '#022638', 'tone': 'deep navy, near-black'},
    'organizations': {'hot': '#C2C64F', 'dark': '#20260A', 'tone': 'deep moss green, near-black'},
    'consumers':     {'hot': '#FF6A1F', 'dark': '#3B1101', 'tone': 'deep rust, near-black'},
}

STYLE_NAME = 'collage'


def collage(ramp: dict[str, str]) -> str:
    """STYLES.collage in generate-art.mjs — kept string-identical."""
    return (
        f'Mixed-media cut-paper and photo collage, every element re-tinted into a '
        f'duotone of {ramp["hot"]} on {ramp["tone"]}. '
        'Torn paper edges, halftone dots, misregistered print artifacts, photographic '
        'fragments of real people of varied '
        'ages and body shapes (silhouetted or seen from behind, no readable faces) '
        'layered against bold flat graphic shapes. '
        'Brutalist poster energy in the spirit of mid-century protest graphics and '
        'conceptual surrealism. '
        'Handmade and imperfect, not glossy, not AI-slick.'
    )


#: Verbatim from the .mjs. Image models volunteer signage, headlines and UI the
#: moment a prompt mentions institutions or screens, and a baked-in word fights
#: the real headline the page sets over the art. Paraphrasing it is not safe:
#: this exact wording is what was tested against the model.
NO_TEXT = (
    ' Absolutely no text anywhere in the image: no words, no letters, no numbers, '
    'no signage, no logos, no watermarks, no captions.'
)

#: The second ban, added after the 19 Aug 2026 review of the first fleet: nearly
#: every image had come back with an arrow or a lightning bolt in it, or someone
#: at a screen. The brief prompt bans these too, but the brief and the image are
#: written by different models and this one reaches for them unprompted — so the
#: ban has to sit in the image prompt as well, not only upstream of it.
NO_SYMBOLS = (
    ' No explanatory symbols of any kind: no arrows, no lightning bolts, no '
    'circuitry, no glowing brains or orbs, no rising graphs, no networks of dots '
    'or connecting lines, no robots, no holograms, and nobody looking at a screen, '
    'laptop, phone or monitor. Nothing in the scene may be an object whose job is '
    'to carry writing: no books, no documents, no filled-in cards, no menus, no '
    'signs. Torn paper as a collage texture is fine; paper as the subject is not.'
)

#: The four output frames. `og` is not generated — it is cropped from the wide
#: master, so it costs nothing extra, exactly as the .mjs does it.
FRAMES: dict[str, dict] = {
    'hero': {
        'aspect': '4:5', 'width': 800, 'height': 1000, 'quality': 80,
        'clause': ('Vertical poster composition: one clear focal point in the upper '
                   'half, the rest of the frame giving it room, nothing essential '
                   'in the outer margins.'),
    },
    'wide': {
        'aspect': '21:9', 'width': 1600, 'height': 600, 'quality': 80,
        'clause': ('Panoramic frieze composition: low horizon, the focal subject '
                   'centered, nothing essential in the top or bottom sixth so the '
                   'image survives a letterbox crop.'),
    },
    'tile': {
        'aspect': '1:1', 'width': 640, 'height': 640, 'quality': 78,
        'clause': ('A single close-cropped detail of that world: one motif drawn far '
                   'too large for the frame, bleeding off at least two edges, bold '
                   'enough to read as a small thumbnail.'),
    },
}

#: Cropped from the `wide` master rather than generated.
OG: dict = {'width': 1200, 'height': 630, 'quality': 80, 'from': 'wide'}

#: Which crops ride along free on a generated master, per (scope, master frame).
#:
#: A sub-shift used to show its PARENT's poster on its own page — the tile was
#: the only thing that was its own. It now generates two masters like a key shift
#: does, and the two frames it does not generate fall out of them for nothing:
#: the 4:5 poster is a centre crop of the square tile master (1024px square down
#: to 800x1000 is a downscale, so it costs no sharpness), and the share card is a
#: crop of the wide master exactly as it is for a key shift.
#:
#: The tile stays the generated one rather than being cropped out of a 4:5
#: master, because its clause — one motif far too large for the frame, bleeding
#: off two edges — is what makes it read at 152px on the parent's list, and a
#: centre crop of a poster would not.
DERIVED: dict[tuple[str, str], tuple[str, ...]] = {
    ('key_trend', 'wide'): ('og',),
    ('sub_trend', 'tile'): ('hero',),
    ('sub_trend', 'wide'): ('og',),
}


#: What Gemini actually returns at `imageSize: 1K` for each generated aspect,
#: measured 2026-08-19. Not 1024x1024 for everything — it holds roughly a
#: megapixel and lets the aspect decide the sides. Recorded so the derived crops
#: above can be checked against reality rather than an assumption: every crop has
#: to be a DOWNSCALE of its master, or a "free" frame is a soft frame.
MASTER_PIXELS: dict[str, tuple[int, int]] = {
    'hero': (928, 1152),    # 4:5
    'wide': (1584, 672),    # 21:9
    'tile': (1024, 1024),   # 1:1
}


def spec_for(frame: str) -> dict:
    """The pixel spec for any frame, generated or derived."""
    return OG if frame == 'og' else FRAMES[frame]


def ramp_for(sphere: str) -> dict[str, str]:
    """The sphere's ramp, defaulting to Society rather than raising.

    A sphere the ramp does not know is a config change, not a reason to fail a
    publication — art is decoration and the map is content.
    """
    return RAMP.get(str(sphere or '').strip().lower(), RAMP['society'])

