"""Assembling one image prompt, and the hash that decides whether to pay for it."""
from __future__ import annotations

import hashlib

from .style import FRAMES, NO_SYMBOLS, NO_TEXT, collage, ramp_for


def _lower_initial(text: str) -> str:
    """Narrative copy arrives sentence-cased and gets spliced mid-sentence.

    Only a sentence-case initial is lowered — "AI treated as…" must not become
    "aI treated as…". Ported from `lower()` in generate-art.mjs.
    """
    value = str(text or '').strip()
    if len(value) > 1 and value[0].isupper() and not value[1].isupper():
        return value[0].lower() + value[1:]
    return value


def concept_from_modules(name: str, dek: str = '', arc_from: str = '',
                         arc_to: str = '') -> str:
    """The fallback concept sentence, when no authored brief exists.

    This is what generate-art.mjs splices today: the shift's name, its from/to
    arc and its dek. Keeping it means a brief that failed to generate degrades to
    the current quality rather than to no art at all.
    """
    arc = ''
    if arc_from and arc_to:
        arc = (f' The world is moving from {_lower_initial(arc_from)} '
               f'to {_lower_initial(arc_to)}.')
    scene = f' {dek.strip()}' if dek else ''
    return f'The scene expresses the shift "{name}".{arc}{scene}'


def image_prompt(sphere: str, frame: str, concept: str) -> str:
    """style + concept + frame clause + the two guards, in that order.

    The brief occupies the concept slot and nothing else. Style, ramp, framing and
    the bans stay in code so an authored brief cannot argue with the art direction
    — which is the failure mode of letting a model describe its own composition.

    The visual register is the one piece of art direction that is NOT here. It
    varies per shift, and a register chosen in code can contradict the scene the
    brief describes outright — "stage it as a crowd seen whole" landing under a
    brief about two people in a doorway. So it is handed to the brief writer
    instead (`phases/art_briefs.REGISTERS`) and reaches the image in the brief's
    own words, which are more specific than a generic clause could be.
    """
    spec = FRAMES[frame]
    return (f'{collage(ramp_for(sphere))} '
            f'{concept.strip()} '
            f'{spec["clause"]}{NO_TEXT}{NO_SYMBOLS}')


def prompt_sha256(model: str, aspect: str, prompt: str) -> str:
    """The idempotency key, identical in shape to the .mjs ledger's promptHash.

    Covers the model and the aspect as well as the text, because the same words
    at a different aspect ratio are a different image. Sixteen hex characters is
    what the JS used and is plenty for equality on a table this size.
    """
    digest = hashlib.sha256(f'{model}|{aspect}|{prompt}'.encode()).hexdigest()
    return digest[:16]
