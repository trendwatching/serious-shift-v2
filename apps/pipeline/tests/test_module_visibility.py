"""The per-sphere module visibility matrix, guarded from the pipeline side.

A shift page is published complete and filtered on read. That split is what makes
a visibility change a one-row edit instead of a regeneration, and it rests on one
invariant that is easy to break by accident:

    hiding a module must never affect whether the document validates.

If someone ever "optimises" by dropping hidden modules at export, the next person
to un-hide one gets an empty section and no error. These tests pin the contract
block's shape and that invariant. The Rust side has the mirror-image test
(`module_policy::tests::default_visibility_matches_the_contract`).

DB-free and network-free.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from serious_shift_pipeline.mapgen import validation as gv
from serious_shift_pipeline.mapgen.config import DOMAINS


def _repo_file(*parts: str) -> Path | None:
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


def test_the_visibility_block_is_well_formed():
    contract = _contract()
    hidden = contract["visibility"]["hidden"]
    declared, order = set(contract["types"]), contract["order"]
    sphere_ids = {d["id"] for d in DOMAINS}

    assert set(hidden) == set(order), "visibility must cover exactly the two scopes"
    for scope, spheres in hidden.items():
        assert set(spheres) == sphere_ids, f"{scope} must name every sphere exactly once"
        for sphere, types in spheres.items():
            assert len(types) == len(set(types)), f"{scope}/{sphere} repeats a type"
            for type_ in types:
                assert type_ in declared, f"{scope}/{sphere} hides undeclared {type_!r}"
                # Hiding a type that cannot appear in this scope is dead config
                # that reads as a decision. It is not.
                assert type_ in order[scope], f"{scope}/{sphere} hides {type_!r}, absent from that order"


def test_the_matrix_matches_the_delivered_design():
    """The design gates industries and territories to Consumers on a key shift,
    and human_needs and territories to Consumers on a sub-shift. That asymmetry
    is deliberate and is the single easiest thing to invert by accident."""
    hidden = _contract()["visibility"]["hidden"]

    for sphere in ("society", "economy", "organizations"):
        assert "industries" in hidden["key_trend"][sphere]
        assert "territories" in hidden["key_trend"][sphere]
        assert "human_needs" in hidden["sub_trend"][sphere]
        assert "territories" in hidden["sub_trend"][sphere]
        # human_needs IS a key-shift section on every sphere.
        assert "human_needs" not in hidden["key_trend"][sphere]

    assert "industries" not in hidden["key_trend"]["consumers"]
    assert "territories" not in hidden["key_trend"]["consumers"]
    assert "human_needs" not in hidden["sub_trend"]["consumers"]
    assert "territories" not in hidden["sub_trend"]["consumers"]


def test_innovations_is_never_hidden_by_default():
    """Ingestion is a product feature, not a design flourish. It can still be
    switched off per sphere with a row, but not silently by the default."""
    hidden = _contract()["visibility"]["hidden"]
    for scope, spheres in hidden.items():
        for sphere, types in spheres.items():
            assert "innovations" not in types, f"{scope}/{sphere} hides innovations"


def test_hiding_never_relaxes_the_publication_gate():
    """The load-bearing invariant. Every module the validator requires is still
    required even where the matrix hides it, because the publication carries the
    complete list and only the read path filters."""
    contract = _contract()
    hidden = contract["visibility"]["hidden"]
    for scope, required in gv.REQUIRED_MODULES.items():
        overlap = {t for sphere in hidden[scope].values() for t in sphere} & required
        # The overlap is expected to be non-empty — tension_band and human_needs
        # are both required AND hidden somewhere. That is exactly the case the
        # invariant has to survive.
        assert overlap, f"{scope}: expected the matrix to hide a required module"
        for type_ in overlap:
            assert type_ in gv.REQUIRED_MODULES[scope]
