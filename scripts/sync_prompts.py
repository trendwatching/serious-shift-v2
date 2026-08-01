#!/usr/bin/env python3
"""
Vendor the canonical prompt templates into each deployable app.

Single source of truth: packages/prompts/**/*.txt (edit these by hand).

Both Docker images build from their own app directory and never see packages/,
so — exactly like the DB migrations — a copy is vendored into each app:

  packages/prompts/**            →  apps/pipeline/serious_shift_pipeline/prompts/templates/**   (all files, package-data)
  packages/prompts/voice.txt     →  apps/backend/src/prompts/voice.txt                          (Rust include_str!)
  packages/prompts/personalize/  →  apps/backend/src/prompts/personalize/                       (Rust include_str!)

Run this after editing any prompt. `test_prompts_in_sync` fails if the copies drift.

Usage:  python scripts/sync_prompts.py [--check]
  --check : exit non-zero if any vendored copy is stale (used in CI); writes nothing.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "packages" / "prompts"

PIPELINE_DEST = ROOT / "apps" / "pipeline" / "serious_shift_pipeline" / "prompts" / "templates"
# The shift-module contract ships in the image too — the pipeline reads the
# reading order from it at export time and packages/ is not in the container.
CONTRACTS_SRC = ROOT / "packages" / "contracts"
CONTRACTS_DEST = ROOT / "apps" / "pipeline" / "serious_shift_pipeline" / "contracts"
BACKEND_DEST = ROOT / "apps" / "backend" / "src" / "prompts"

# Files the Rust backend embeds via include_str! (relative to packages/prompts).
BACKEND_FILES = ["voice.txt", "personalize/rewrite_section.txt"]


def _all_templates() -> list[Path]:
    return sorted(CANONICAL.rglob("*.txt"))


def _plan() -> list[tuple[Path, Path]]:
    """Return (src, dest) pairs for every file to vendor."""
    pairs: list[tuple[Path, Path]] = []
    for src in sorted(CONTRACTS_SRC.glob("*.json")) if CONTRACTS_SRC.is_dir() else []:
        pairs.append((src, CONTRACTS_DEST / src.name))
    for src in _all_templates():
        pairs.append((src, PIPELINE_DEST / src.relative_to(CANONICAL)))
    for rel in BACKEND_FILES:
        pairs.append((CANONICAL / rel, BACKEND_DEST / rel))
    return pairs


def check() -> int:
    stale = []
    for src, dest in _plan():
        if not dest.is_file() or dest.read_text(encoding="utf-8") != src.read_text(encoding="utf-8"):
            stale.append(dest)
    if stale:
        print("Vendored prompt copies are stale:")
        for d in stale:
            print(f"  {d.relative_to(ROOT)}")
        print("\nRun: python scripts/sync_prompts.py")
        return 1
    print(f"All {len(_plan())} vendored prompt copies are in sync.")
    return 0


def sync() -> int:
    n = 0
    for src, dest in _plan():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        n += 1
    print(f"Vendored {n} prompt files → pipeline + backend.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="Verify sync without writing (CI).")
    args = ap.parse_args()
    if not CANONICAL.is_dir():
        sys.exit(f"canonical prompts dir not found: {CANONICAL}")
    return check() if args.check else sync()


if __name__ == "__main__":
    raise SystemExit(main())
