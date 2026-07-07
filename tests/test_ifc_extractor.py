"""Regression tests for extractors/ifc_extractor.py (T2).

Generates the smoke-test IFC in a tmp path via subprocess (the generator
writes to a cwd-relative path), then asserts each extraction path:
direct attribute, Qto fallback, derived riser, pset ceiling height and
window dimensions. Downloaded external models are deliberately NOT tested
here (network-dependent); they are exercised manually.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extractors.ifc_extractor import extract  # noqa: E402


@pytest.fixture(scope="module")
def facts(tmp_path_factory) -> dict:
    """Generate the sample IFC in an isolated tmp dir and extract facts."""
    tmp = tmp_path_factory.mktemp("ifc")
    # The generator writes to "samples/smoke_test.ifc" relative to cwd.
    (tmp / "samples").mkdir()
    shutil.copy(REPO_ROOT / "samples" / "generate_sample_ifc.py", tmp / "generate_sample_ifc.py")
    subprocess.run([sys.executable, "generate_sample_ifc.py"], cwd=tmp, check=True)
    ifc_path = tmp / "samples" / "smoke_test.ifc"
    assert ifc_path.exists()
    return extract(str(ifc_path))


def _by_name(facts: dict, name: str) -> dict:
    matches = [e for e in facts["entities"] if e["name"] == name]
    assert len(matches) == 1, f"expected exactly one entity named {name!r}, got {len(matches)}"
    return matches[0]


def test_entity_inventory(facts):
    kinds = sorted(e["entity_type"] for e in facts["entities"])
    assert kinds == ["room", "stair_flight", "stair_flight", "window"]


def test_riser_from_direct_attribute(facts):
    attrs = _by_name(facts, "Main Stair Flight")["attributes"]
    riser = attrs["riser_height_mm"]
    assert riser["value"] == 185.0
    assert riser["confidence"] == 1.0
    assert "derived" not in riser["source"]
    assert attrs["number_of_risers"] == 14


def test_riser_derived_from_qto_height_over_riser_count(facts):
    attrs = _by_name(facts, "Basement Stair Flight")["attributes"]
    riser = attrs["riser_height_mm"]
    assert riser["value"] == pytest.approx(175.0)  # 2800 mm / 16 risers
    assert riser["confidence"] == 1.0
    assert "derived" in riser["source"]
    assert "Qto Height / NumberOfRisers" in riser["source"]
    assert attrs["number_of_risers"] == 16


def test_tread_from_qto_fallback(facts):
    attrs = _by_name(facts, "Basement Stair Flight")["attributes"]
    assert attrs["tread_run_mm"]["value"] == 260.0
    assert attrs["tread_run_mm"]["confidence"] == 1.0


def test_space_ceiling_height_from_pset(facts):
    attrs = _by_name(facts, "Living Room")["attributes"]
    assert attrs["room_use"] == "living_room"
    height = attrs["ceiling_height_mm"]
    assert height["value"] == 2450.0
    assert height["confidence"] == 1.0
    assert "derived" not in height["source"]  # pset value, not geometry


def test_window_dimensions_present(facts):
    attrs = _by_name(facts, "Bedroom Window W-01")["attributes"]
    assert attrs["overall_height_mm"]["value"] == 1200.0
    assert attrs["overall_width_mm"]["value"] == 900.0
    # Open area must NOT be derived (depends on operation type) — EO1.
    assert "unobstructed_open_area_m2" not in attrs


def test_all_lengths_plausible_mm(facts):
    """Every *_mm fact should be in a plausible millimetre range."""
    for entity in facts["entities"]:
        for key, val in entity["attributes"].items():
            if not key.endswith("_mm"):
                continue
            value = val["value"] if isinstance(val, dict) else val
            assert 50.0 <= value <= 20000.0, f"{entity['name']}.{key} = {value} not plausible mm"


def test_sources_cite_ifc_global_id(facts):
    for entity in facts["entities"]:
        for val in entity["attributes"].values():
            if isinstance(val, dict):
                assert f"#{entity['id']}" in val["source"]
