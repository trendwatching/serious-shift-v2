"""
Shared text helpers.

Two slug functions, deliberately kept separate — they have different consumers
and different output, and merging them would change either live URLs or on-disk
paths:

  url_slug  hyphen-separated, stored in domain_key_trends.slug / domain_sub_trends.slug
            and used in the URL the frontend routes on. Must stay byte-identical
            to the frontend's slugify (apps/frontend/src/shift/theme.js) or deep
            links 404 — packages/contracts/slug_fixtures.json pins both sides.

  fs_slug   underscore-separated and length-capped, used for the raw_content/
            directory a thinker's scraped files land in. Changing it orphans
            everything already on disk.
"""
from __future__ import annotations

import re

_NON_WORD = re.compile(r"[^\w\s-]", re.UNICODE)
_SPACE_RUN = re.compile(r"[\s_]+")
_DASH_RUN = re.compile(r"-+")


def url_slug(text: str) -> str:
    """URL-safe slug: 'AI's Rôle, Revisited' -> 'ais-rôle-revisited'.

    Punctuation is dropped rather than turned into a separator, so an apostrophe
    closes up ("can't" -> "cant") instead of splitting the word ("can-t").
    """
    s = _NON_WORD.sub("", str(text or "").lower())
    s = _SPACE_RUN.sub("-", s)
    return _DASH_RUN.sub("-", s).strip("-")


def fs_slug(text: str, max_len: int = 60) -> str:
    """Filesystem-safe slug for raw_content directories/filenames."""
    s = _NON_WORD.sub("", str(text or "").lower())
    return _SPACE_RUN.sub("_", s).strip("_")[:max_len]
