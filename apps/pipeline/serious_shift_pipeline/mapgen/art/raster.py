"""Pillow doing what Playwright did in the .mjs: `object-fit: cover`, then JPEG.

The frontend script screenshots a Chromium page with `object-fit: cover` and a
clip rect. That is a browser because the script already had one for other
reasons, not because the crop needs one — it is a scale-to-cover and a centre
crop, which is four lines of arithmetic. Doing it with Pillow is what keeps the
pipeline image `python:3.13-slim` instead of shipping a browser in a cron
container.
"""
from __future__ import annotations

import hashlib
import io
from math import ceil



def cover_crop(master: bytes, width: int, height: int, quality: int) -> tuple[bytes, str]:
    """Scale to cover `width`x`height`, centre-crop, encode JPEG.

    Pillow is imported HERE, not at module scope. `mapgen.cli` imports the art
    package eagerly, so a module-level `from PIL import Image` made Pillow a hard
    requirement of the entire CLI: an environment without it could not run
    mapgen at all, could not `--export-only`, could not even collect the test
    suite. That is precisely the fragility the art package is supposed not to
    have — art is decoration, and a missing decoration library must cost the
    decoration.

    Returns `(jpeg_bytes, sha256_hex)`. The digest is over the ENCODED bytes, so
    it is the ETag the backend serves and the cache-buster the document carries —
    identical input therefore produces an identical URL, and a regenerated image
    always produces a different one.
    """
    from PIL import Image
    from PIL.Image import Resampling

    with Image.open(io.BytesIO(master)) as image:
        image.load()
        scale = max(width / image.width, height / image.height)
        resized = image.resize(
            (max(width, ceil(image.width * scale)), max(height, ceil(image.height * scale))),
            Resampling.LANCZOS)
        left = (resized.width - width) // 2
        top = (resized.height - height) // 2
        cropped = resized.crop((left, top, left + width, top + height))
        # RGB because a source with alpha cannot be written as JPEG, and the
        # design has no transparent artwork.
        if cropped.mode != 'RGB':
            cropped = cropped.convert('RGB')
        buffer = io.BytesIO()
        cropped.save(buffer, 'JPEG', quality=quality, optimize=True, progressive=True)

    encoded = buffer.getvalue()
    return encoded, hashlib.sha256(encoded).hexdigest()
