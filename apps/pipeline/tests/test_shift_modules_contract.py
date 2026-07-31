"""
The shift-module contract, guarded from both sides.

A shift page is an ordered list of {type, data} modules: the pipeline emits them
and the front end renders them. Nothing in either language enforces that the two
agree, so drift would show up as a silently missing section on a live page —
the front end skips types it doesn't recognise, which is the right runtime
behaviour but hides the mistake.

These tests make the canonical list (packages/contracts/shift_modules.json) the
arbiter: the pipeline may only emit types it declares, and the frontend registry
must have a component for each one. DB-free and network-free.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from serious_shift_pipeline.steps import generate_map_data as gm


def _repo_file(*parts: str) -> Path | None:
    """Locate a repo file by walking up — absent in an installed/sdist layout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent.joinpath(*parts)
        if candidate.is_file():
            return candidate
    return None


def _contract() -> dict:
    path = _repo_file("packages", "contracts", "shift_modules.json")
    if path is None:
        pytest.skip("canonical packages/contracts not present (installed/sdist build)")
    return json.loads(path.read_text())


# Representative editorial payloads: one with every field the prompts ask for, and
# one empty, so we see both the full module set and the degenerate case.
_FULL_KT = {
    "from": "a", "to": "b", "whats_changing": "c", "why_now": "d", "stat_text": "e",
    "human_needs": {"unlocked": "f", "threatened": "g"},
    "consumer_tension": "h",
    "timeline": {"now": "i", "next": "j", "beyond": "k"},
    "industries": [{"name": "Retail & Commerce", "text": "l"}],
    "opportunities": [{"name": "m", "text": "n"}],
    "read_time": "5 min read",
}
_FULL_ST = {
    "lede": "a", "from": "b", "to": "c", "quote": "d",
    "stat": {"value": "1%", "text": "e", "source": "f"},
    "whats_changing": "g", "why_now": "h",
    "human_needs": {"unlocked": "i", "threatened": "j"},
    "signals": ["k", "l"], "counter_signals": ["m"],
    "timeline": {"now": "n", "next": "o", "beyond": "p"},
    "territories": [{"name": "q", "text": "r"}],
}


def _emitted_types() -> set[str]:
    kt = gm.kt_modules({"subtitle": "dek", "hero_stat": {"value": "9%", "source": "s"}}, _FULL_KT)
    st = gm.st_modules({"description": "d"}, _FULL_ST)
    return {m["type"] for m in kt} | {m["type"] for m in st}


def test_pipeline_only_emits_declared_types():
    declared = set(_contract()["types"])
    undeclared = _emitted_types() - declared
    assert not undeclared, f"pipeline emits types missing from the contract: {sorted(undeclared)}"


def test_frontend_registers_every_declared_type():
    registry = _repo_file("apps", "frontend", "src", "shift", "modules.jsx")
    if registry is None:
        pytest.skip("frontend not present in this checkout")
    source = registry.read_text()
    # The registry is a flat object literal: `  some_type: Component,`
    registered = set(re.findall(r"^\s{2}(\w+):", source, re.MULTILINE))
    missing = set(_contract()["types"]) - registered
    assert not missing, f"frontend registry has no component for: {sorted(missing)}"


def test_module_order_matches_the_reference_template():
    """The COGNITIVE EROSION page order is the spec — lock it in so a reorder is
    a deliberate edit to this list and not an accident."""
    kt = gm.kt_modules({"subtitle": "dek", "hero_stat": {"value": "9%"}}, _FULL_KT)
    assert [m["type"] for m in kt] == [
        "dek", "from_to", "stat_band", "peel_tabs", "sub_shift_list",
        "human_needs", "tension_band", "timeline", "industries", "territories",
    ]
    st = gm.st_modules({"description": "d"}, _FULL_ST)
    assert [m["type"] for m in st] == [
        "lede", "from_to_solid", "tension_band", "stat_band", "peel_tabs",
        "human_needs", "signals", "counter_signals", "timeline", "territories",
    ]


def test_modules_are_omitted_when_the_model_returned_nothing():
    """A shift with no editorial body must still produce a renderable page rather
    than a list of empty bands."""
    kt = gm.kt_modules({"subtitle": "Just a dek", "hero_stat": None}, {})
    assert [m["type"] for m in kt] == ["dek", "sub_shift_list"]

    st = gm.st_modules({"description": "Only a description"}, {})
    assert [m["type"] for m in st] == ["lede"]


def test_stat_band_needs_a_value_not_just_prose():
    """stat_text alone can't render the band — the numeral comes from hero_stat."""
    kt = gm.kt_modules({"subtitle": "d", "hero_stat": None}, {"stat_text": "prose only"})
    assert "stat_band" not in {m["type"] for m in kt}
