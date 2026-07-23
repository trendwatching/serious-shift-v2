"""
Template loader + renderer for the shared prompt files.

The canonical prompt text lives in `packages/prompts/**/*.txt` (the single source
of truth, edited by hand). A copy is vendored into this package under
`prompts/templates/` and shipped as package-data, so the deployed container — which
builds from `apps/pipeline` and never sees `packages/` — still has the prompts.

This mirrors how core/migrate.py handles SQL migrations: prefer the canonical
`packages/prompts` on a source checkout, fall back to the vendored copy otherwise.
Keep the two in sync with `scripts/sync_prompts.py` (a test enforces it).

Templates use `{{name}}` placeholders. Literal `{` / `}` (e.g. the JSON schema
examples inside the prompts) are left untouched — only double-brace tokens are
substituted.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

# Vendored copy that ships inside the wheel/image.
_VENDORED = Path(__file__).resolve().parent / "templates"

_TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _canonical_dir() -> Path | None:
    """Canonical packages/prompts, when running from a source checkout. Walk up
    from this file rather than assuming a fixed depth (works from tests, the repo,
    or an editable install)."""
    for parent in Path(__file__).resolve().parents:
        cand = parent / "packages" / "prompts"
        if cand.is_dir():
            return cand
    return None


@lru_cache(maxsize=None)
def load(name: str) -> str:
    """Return the raw template text for `name` (e.g. "voice.txt", "map/key_trends.txt").
    Prefers the canonical packages/prompts copy, falls back to the vendored copy.
    Trailing newlines are stripped so composed prompts match exactly."""
    canonical = _canonical_dir()
    if canonical and (canonical / name).is_file():
        return (canonical / name).read_text(encoding="utf-8").rstrip("\n")
    return (_VENDORED / name).read_text(encoding="utf-8").rstrip("\n")


def render(template: str, /, **values: object) -> str:
    """Substitute every `{{name}}` token in `template` with values[name].
    Raises KeyError on an unknown token so typos fail loudly."""
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            raise KeyError(f"no value for prompt placeholder {{{{{key}}}}}")
        return str(values[key])
    return _TOKEN.sub(sub, template)


def load_and_render(name: str, /, **values: object) -> str:
    """Convenience: load(name) then render(..., **values)."""
    return render(load(name), **values)
