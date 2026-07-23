"""
Guards the vendored prompt copies against drift.

Canonical prompt text lives in packages/prompts/**. A copy is vendored into the
pipeline package (prompts/templates/) and the backend (apps/backend/src/prompts/)
so the per-app Docker builds ship them. This test fails if any copy is stale —
run `python scripts/sync_prompts.py` to fix.

Skipped when packages/ is absent (e.g. running from an installed wheel), since
there is nothing to compare against.
"""
import importlib.util
from pathlib import Path

import pytest


def _repo_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "packages" / "prompts").is_dir() and (parent / "scripts" / "sync_prompts.py").is_file():
            return parent
    return None


def test_prompts_vendored_in_sync():
    root = _repo_root()
    if root is None:
        pytest.skip("canonical packages/prompts not present (installed build)")
    spec = importlib.util.spec_from_file_location("sync_prompts", root / "scripts" / "sync_prompts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.check() == 0, "vendored prompt copies are stale — run scripts/sync_prompts.py"
