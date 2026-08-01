"""Golden test for the map exporter.

`build_map_json_v2` assembles the single document the whole frontend reads. It is
the largest and most-branching function in the pipeline, so any refactor of it
needs a regression net that catches a changed field — not just a changed count.

The net is a digest of the canonicalised document. Committing the document itself
would mean a 1.7 MB fixture; a digest plus the structural summary catches the same
regressions in ~1 KB, and the summary is what makes a failure diagnosable.

Requires a populated database (DATABASE_URL), so it skips by default and runs in
CI's integration job. Regenerate after an intentional export change:

    DATABASE_URL=… python -m pytest tests/test_map_export_golden.py --update-golden
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib

import pytest

GOLDEN = pathlib.Path(__file__).parent / "fixtures" / "map_export_golden.json"

# Fields that legitimately change between runs and say nothing about correctness.
VOLATILE_TOP_LEVEL = {"updated"}

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="needs a populated DATABASE_URL (integration)",
)


def _canonical(doc: dict) -> str:
    """Stable serialisation: volatile fields dropped, keys sorted."""
    stable = {k: v for k, v in doc.items() if k not in VOLATILE_TOP_LEVEL}
    return json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _summarise(doc: dict) -> dict:
    """Structural shape — what a digest mismatch is diagnosed against."""
    kts = doc.get("key_trends") or []
    sts = doc.get("sub_trends") or []
    return {
        "domains": len(doc.get("domains") or []),
        "key_trends": len(kts),
        "sub_trends": len(sts),
        "synthesis_insights": len(doc.get("synthesis_insights") or []),
        "links": len(doc.get("links") or []),
        "kt_modules": sum(len(k.get("modules") or []) for k in kts),
        "st_modules": sum(len(s.get("modules") or []) for s in sts),
        "kt_fields": sorted(kts[0]) if kts else [],
        "st_fields": sorted(sts[0]) if sts else [],
        "top_level_keys": sorted(doc),
    }


def _load_exported() -> dict:
    from serious_shift_pipeline.core import db

    with db.connect() as conn:
        row = db.query_one(conn, "SELECT body::text AS body FROM documents WHERE key='map'")
    if not row:
        pytest.skip("no map document in this database — run generate_map_data --export-only")
    return json.loads(row["body"])


def test_map_export_is_unchanged(request):
    doc = _load_exported()
    actual = {"digest": hashlib.sha256(_canonical(doc).encode()).hexdigest(),
              "summary": _summarise(doc)}

    if request.config.getoption("--update-golden"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
        pytest.skip(f"golden updated: {GOLDEN}")

    if not GOLDEN.is_file():
        pytest.skip(f"no golden recorded yet — run with --update-golden ({GOLDEN})")

    expected = json.loads(GOLDEN.read_text())
    # Compare the summary first: a digest mismatch alone is undiagnosable, and
    # nine times out of ten the summary already shows what moved.
    assert actual["summary"] == expected["summary"], "export structure changed"
    assert actual["digest"] == expected["digest"], (
        "export content changed while its structure stayed the same — a field "
        "value differs. If intentional, re-record with --update-golden."
    )
