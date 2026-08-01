"""
Template loader + renderer for the shared prompt files.

Prompt text lives in `packages/prompts/**/*.txt` — the single source of truth,
located via `paths.prompts_dir()` (see that module for how the tree is found in
both a checkout and the container).

Templates use `{{name}}` placeholders. Literal `{` / `}` (e.g. the JSON schema
examples inside the prompts) are left untouched — only double-brace tokens are
substituted.
"""
from __future__ import annotations

import re
from functools import lru_cache

from ..paths import prompts_dir

_TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@lru_cache(maxsize=None)
def load(name: str) -> str:
    """Return the raw template text for `name` (e.g. "voice.txt", "map/key_trends.txt").
    Trailing newlines are stripped so composed prompts match exactly."""
    return (prompts_dir() / name).read_text(encoding="utf-8").rstrip("\n")


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
