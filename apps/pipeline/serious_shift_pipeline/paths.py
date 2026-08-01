"""
Locate the shared `packages/` tree — the single source of truth for database
migrations, prompt templates and the module contract.

The pipeline image is built from the repo root and copies `packages/` in beside
the package (`/app/packages`, `/app/serious_shift_pipeline`), so the same
walk-up lookup works in the container and in a source checkout. Nothing is
vendored into the package any more.

Set SS_PACKAGES_DIR to override (useful when the tree is mounted elsewhere).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def packages_dir() -> Path:
    """Absolute path to `packages/`. Raises if it cannot be found — a missing
    tree means migrations and prompts are unavailable, which must fail loudly
    rather than silently degrade."""
    override = os.environ.get("SS_PACKAGES_DIR")
    if override:
        p = Path(override).expanduser().resolve()
        if not p.is_dir():
            raise RuntimeError(f"SS_PACKAGES_DIR={override!r} is not a directory")
        return p

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "packages"
        if (candidate / "db" / "migrations").is_dir():
            return candidate

    raise RuntimeError(
        "Could not locate the shared 'packages/' tree. Expected it alongside "
        f"the package (searched upward from {Path(__file__).resolve().parent}). "
        "Set SS_PACKAGES_DIR to point at it explicitly."
    )


def migrations_dir() -> Path:
    """`packages/db/migrations` — dbmate-format schema migrations."""
    return packages_dir() / "db" / "migrations"


def prompts_dir() -> Path:
    """`packages/prompts` — Claude prompt templates."""
    return packages_dir() / "prompts"


def contracts_dir() -> Path:
    """`packages/contracts` — shared JSON contracts (shift module schema)."""
    return packages_dir() / "contracts"
