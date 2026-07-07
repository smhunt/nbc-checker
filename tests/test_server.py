"""Review-server tests — override round-trip drives the EO4 loop:
reviewer confirms an UNCERTAIN fact -> deterministic re-run flips the check."""

import json

import pytest
from fastapi.testclient import TestClient

from engine.checker import run_ruleset
from server.app import _facts_path, _rules_path, app
from server.overrides import apply_overrides, load_overrides, save_overrides


def _expected_baseline_summary():
    """Engine-derived truth for the configured sample suite (no overrides).

    Computed rather than hardcoded so the test tracks the evolving ruleset/
    sample files, which this test suite does not own.
    """
    with open(_rules_path()) as f:
        ruleset = json.load(f)
    with open(_facts_path()) as f:
        facts = json.load(f)
    return run_ruleset(ruleset, facts)["summary"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with overrides isolated to a per-test temp file."""
    monkeypatch.setenv("NBC_OVERRIDES", str(tmp_path / "overrides.json"))
    monkeypatch.delenv("NBC_RULES", raising=False)
    monkeypatch.delenv("NBC_FACTS", raising=False)
    return TestClient(app)


def _result(state, rule_id, entity_id):
    matches = [
        r for r in state["report"]["results"]
        if r["rule_id"] == rule_id and r["entity_id"] == entity_id
    ]
    assert len(matches) == 1
    return matches[0]


# ---------------------------------------------------------------- overrides.py


def test_load_overrides_missing_file(tmp_path):
    assert load_overrides(str(tmp_path / "nope.json")) == {}


def test_save_load_round_trip(tmp_path):
    path = str(tmp_path / "o.json")
    o = {"e1": {"x_mm": {"value": 5, "confidence": 1.0, "source": "human review: ok (2026-07-07)"}}}
    save_overrides(path, o)
    assert load_overrides(path) == o


def test_apply_overrides_returns_new_dict():
    facts = {"entities": [{"entity_type": "t", "id": "e1", "attributes": {"a": 1}}]}
    o = {"e1": {"a": {"value": 2, "confidence": 1.0, "source": "s"}}}
    merged = apply_overrides(facts, o)
    assert merged is not facts
    assert facts["entities"][0]["attributes"]["a"] == 1  # input untouched
    assert merged["entities"][0]["attributes"]["a"]["value"] == 2


def test_apply_overrides_adds_absent_fact():
    """info_not_available -> resolved: the entity may lack the fact entirely."""
    facts = {"entities": [{"entity_type": "t", "id": "e1", "attributes": {}}]}
    o = {"e1": {"new_fact": {"value": 42, "confidence": 1.0, "source": "s"}}}
    merged = apply_overrides(facts, o)
    assert merged["entities"][0]["attributes"]["new_fact"]["value"] == 42


# -------------------------------------------------------------------- /api/state


def test_state_shape_and_summary(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    state = r.json()
    for key in ("report", "facts", "overrides", "rules", "report_sha256"):
        assert key in state
    # Baseline of the sample suite with no overrides matches the engine run
    assert state["report"]["summary"] == _expected_baseline_summary()
    assert sum(state["report"]["summary"].values()) == len(state["report"]["results"])
    assert state["overrides"] == {}
    # rules map carries provision/title/verification_notes per rule_id
    meta = state["rules"]["NBC-9.8.7.4-handrail-height"]
    assert meta["provision"].startswith("NBC 2020")
    assert "quote" in meta["verification_notes"]


def test_report_sha256_stable_across_identical_gets(client):
    a = client.get("/api/state").json()
    b = client.get("/api/state").json()
    assert a["report_sha256"] == b["report_sha256"]
    assert len(a["report_sha256"]) == 64


# ------------------------------------------------------ override round-trip (EO4)


def test_override_flips_uncertain_to_pass_and_back(client):
    rule, entity = "NBC-9.8.7.4-handrail-height", "handrail-01"
    baseline = client.get("/api/state").json()
    assert _result(baseline, rule, entity)["status"] == "uncertain"

    # Reviewer confirms the LLM-extracted handrail height on site
    r = client.post("/api/override", json={
        "entity_id": entity,
        "fact": "height_above_nosing_mm",
        "value": 920,
        "note": "confirmed on site",
    })
    assert r.status_code == 200
    state = r.json()
    assert _result(state, rule, entity)["status"] == "pass"
    override = state["overrides"][entity]["height_above_nosing_mm"]
    assert override["value"] == 920
    assert override["confidence"] == 1.0
    assert override["source"].startswith("human review: confirmed on site (")
    baseline_summary = baseline["report"]["summary"]
    assert state["report"]["summary"]["uncertain"] == baseline_summary["uncertain"] - 1
    assert state["report"]["summary"]["pass"] == baseline_summary["pass"] + 1

    # DELETE flips the check back to uncertain
    r = client.delete(f"/api/override/{entity}/height_above_nosing_mm")
    assert r.status_code == 200
    state = r.json()
    assert _result(state, rule, entity)["status"] == "uncertain"
    assert state["overrides"] == {}
    assert state["report_sha256"] == baseline["report_sha256"]


def test_override_coerces_numeric_strings(client):
    state = client.post("/api/override", json={
        "entity_id": "handrail-01",
        "fact": "height_above_nosing_mm",
        "value": "920",
        "note": "typed into UI",
    }).json()
    assert state["overrides"]["handrail-01"]["height_above_nosing_mm"]["value"] == 920


def test_override_resolves_info_not_available(client):
    """Reviewer supplies a fact the extractor could not derive."""
    rule, entity = "NBC-9.5.3.1-ceiling-living", "room-dining"
    assert _result(client.get("/api/state").json(), rule, entity)["status"] == "info_not_available"
    state = client.post("/api/override", json={
        "entity_id": entity,
        "fact": "ceiling_height_mm",
        "value": 2400,
        "note": "read from A-101 section",
    }).json()
    assert _result(state, rule, entity)["status"] == "pass"


def test_delete_absent_override_404(client):
    r = client.delete("/api/override/handrail-01/height_above_nosing_mm")
    assert r.status_code == 404


def test_export_unknown_format_404(client):
    r = client.get("/api/export/bcf")
    assert r.status_code == 404


def test_export_pdf(client):
    r = client.get("/api/export/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_export_xlsx(client):
    r = client.get("/api/export/xlsx")
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # xlsx is a zip
