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


def test_stat_band_rejects_prose_as_a_numeral():
    """hero_stat.value is prose lifted from a claim, but the band renders it at
    ~99px. A leading figure is salvaged; unsalvageable prose drops the module."""
    prose = "200 years of encyclical history, first time dedicated entirely to technology (2026)"
    kt = gm.kt_modules({"subtitle": "d", "hero_stat": {"value": prose}}, {})
    band = next((m for m in kt if m["type"] == "stat_band"), None)
    assert band and band["data"]["value"] == "200", band
    # the full prose is kept as the explanatory text, not thrown away
    assert prose in band["data"]["text"]

    # no leading figure at all → no band
    kt2 = gm.kt_modules({"subtitle": "d", "hero_stat": {"value": "Boom Supersonic achieved flight"}}, {})
    assert "stat_band" not in {m["type"] for m in kt2}

    # an explicit stat_value from the model always wins
    kt3 = gm.kt_modules({"subtitle": "d", "hero_stat": {"value": prose}}, {"stat_value": "2:1"})
    assert next(m for m in kt3 if m["type"] == "stat_band")["data"]["value"] == "2:1"


def test_short_figure_extraction():
    for raw, want in [
        ("25%", "25%"), ("18-34", "18-34"), ("3×", "3×"),
        ("200 years of encyclical history, first time dedicated to tech", "200"),
        ("16 million Claude chats harvested via 24,000 fake accounts", "16 million"),
        ("195 references verified in 30 minutes with zero errors", "195"),
        ("Boom Supersonic achieved supersonic flight in 2025", None),
        ("", None), (None, None),
    ]:
        assert gm._short_figure(raw) == want, f"{raw!r} -> {gm._short_figure(raw)!r}, want {want!r}"


def test_stat_band_needs_a_value_not_just_prose():
    """stat_text alone can't render the band — the numeral comes from hero_stat."""
    kt = gm.kt_modules({"subtitle": "d", "hero_stat": None}, {"stat_text": "prose only"})
    assert "stat_band" not in {m["type"] for m in kt}
