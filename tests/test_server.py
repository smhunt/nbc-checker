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


# --- Upload / job flow (extraction stubbed so no CLI is called) ---

def _fake_facts():
    return {
        "project": {"name": "uploaded.pdf", "jurisdiction": "Ontario"},
        "entities": [{
            "entity_type": "stair_flight", "id": "s1", "name": "Stair",
            "attributes": {
                "service": "private",
                "riser_height_mm": {"value": 210, "confidence": 0.8, "source": "pdf tile r1c1"},
            },
        }],
    }


@pytest.fixture
def upload_client(client, monkeypatch):
    # Run the background "thread" synchronously and stub the extractor.
    import extractors.pdf_extractor as pe
    import server.app as appmod
    monkeypatch.setattr(pe, "extract", lambda p: _fake_facts())
    monkeypatch.setattr(pe, "extract_tiled", lambda p, **k: _fake_facts())

    class _SyncThread:
        def __init__(self, target, args=(), daemon=None):
            self._t, self._a = target, args
        def start(self):
            self._t(*self._a)

    monkeypatch.setattr(appmod.threading, "Thread", _SyncThread)
    return client


def _upload(c):
    return c.post(
        "/api/upload",
        files={"file": ("plan.pdf", b"%PDF-1.4 fake", "application/pdf")},
        data={"ruleset": "obc", "mode": "whole"},
    )


def test_upload_rejects_non_pdf(upload_client):
    r = upload_client.post(
        "/api/upload",
        files={"file": ("plan.txt", b"hi", "text/plain")},
        data={"ruleset": "nbc", "mode": "whole"},
    )
    assert r.status_code == 400


def test_upload_bad_ruleset(upload_client):
    r = upload_client.post(
        "/api/upload",
        files={"file": ("p.pdf", b"%PDF", "application/pdf")},
        data={"ruleset": "zzz", "mode": "whole"},
    )
    assert r.status_code == 400


def test_upload_then_job_report(upload_client):
    up = _upload(upload_client)
    assert up.status_code == 200
    job_id = up.json()["job_id"]

    job = upload_client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done"
    assert job["report"]["code_edition"].startswith("OBC")
    # LLM fact at 0.8 confidence -> the rise check must be uncertain, never fail.
    rise = [r for r in job["report"]["results"] if r["rule_id"].endswith("rise-private")]
    assert rise and all(r["status"] == "uncertain" for r in rise)


def test_job_override_flips_and_exports(upload_client):
    job_id = _upload(upload_client).json()["job_id"]
    # Confirm the 210 mm riser as reviewed -> now a confident value -> FAIL (>200).
    body = {"entity_id": "s1", "fact": "riser_height_mm", "value": 210, "note": "confirmed"}
    after = upload_client.post(f"/api/jobs/{job_id}/override", json=body).json()
    rise = [r for r in after["report"]["results"] if r["rule_id"].endswith("rise-private")]
    assert rise and any(r["status"] == "fail" for r in rise)

    pdf = upload_client.get(f"/api/jobs/{job_id}/export/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_job_not_found(upload_client):
    assert upload_client.get("/api/jobs/deadbeef").status_code == 404


# --- PDF evidence drill-down: document/page serving -------------------------

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def evidence_pdf():
    """A tiny real 1-page PDF placed in reports/uploads as a fake job upload.

    Also reachable through /api/documents since reports/uploads is first in
    the resolution whitelist. Teardown removes the PDF and any cached PNGs.
    """
    import fitz

    from server.app import ROOT

    up_dir = ROOT / "reports" / "uploads"
    up_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = up_dir / "testjob123.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((50, 100), "stair riser 210 mm")
    doc.save(str(pdf_path))
    doc.close()
    yield pdf_path
    pdf_path.unlink(missing_ok=True)
    cache = ROOT / "reports" / "page_cache"
    if cache.is_dir():
        for f in cache.glob("testjob123_p*_*.png"):
            f.unlink()


def test_page_png_renders_and_caches(client, evidence_pdf):
    from server.app import ROOT

    r = client.get("/api/jobs/testjob123/page/1.png?dpi=96")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == PNG_MAGIC

    cache_file = ROOT / "reports" / "page_cache" / "testjob123_p1_96.png"
    assert cache_file.is_file()
    mtime = cache_file.stat().st_mtime_ns

    # Second request serves the cached PNG without re-rendering.
    r2 = client.get("/api/jobs/testjob123/page/1.png?dpi=96")
    assert r2.status_code == 200
    assert r2.content == r.content
    assert cache_file.stat().st_mtime_ns == mtime

    # The documents route resolves the same file from reports/uploads.
    r3 = client.get("/api/documents/testjob123.pdf/page/1.png?dpi=96")
    assert r3.status_code == 200
    assert r3.content[:8] == PNG_MAGIC


def test_document_name_traversal_rejected(client, evidence_pdf):
    from server.pdfrender import resolve_document

    # The resolver itself refuses separators, '..', and empty names outright.
    for bad in ("../x.pdf", "a/b.pdf", "..\\x.pdf", "..", ""):
        assert resolve_document(bad) is None

    # URL-encoded traversal decodes to a forbidden name -> 400/404, never 200.
    for encoded in ("..%2Fx.pdf", "a%2Fb.pdf", "..%5Cx.pdf", "%2E%2E%2Fx.pdf"):
        r = client.get(f"/api/documents/{encoded}/pdf")
        assert r.status_code in (400, 404), encoded
        r = client.get(f"/api/documents/{encoded}/page/1.png")
        assert r.status_code in (400, 404), encoded

    # Raw traversal segments never reach a file outside the whitelist.
    r = client.get("/api/documents/../../server/app.py/pdf")
    assert r.status_code in (400, 404)

    # Job routes reject traversal in job_id the same way.
    r = client.get("/api/jobs/..%2Ftestjob123/pdf")
    assert r.status_code in (400, 404)


def test_page_out_of_range_404(client, evidence_pdf):
    r = client.get("/api/jobs/testjob123/page/99.png?dpi=96")
    assert r.status_code == 404
    r = client.get("/api/documents/testjob123.pdf/page/0.png?dpi=96")
    assert r.status_code == 404
    # Unknown document is also 404, before any rendering happens.
    r = client.get("/api/documents/no-such-doc-xyz.pdf/page/1.png?dpi=96")
    assert r.status_code == 404


def test_dpi_whitelist_400(client, evidence_pdf):
    for bad_dpi in (72, 300, 1):
        r = client.get(f"/api/jobs/testjob123/page/1.png?dpi={bad_dpi}")
        assert r.status_code == 400, bad_dpi
        r = client.get(f"/api/documents/testjob123.pdf/page/1.png?dpi={bad_dpi}")
        assert r.status_code == 400, bad_dpi
    # Default dpi (150) is whitelisted and renders fine.
    r = client.get("/api/jobs/testjob123/page/1.png")
    assert r.status_code == 200


def test_job_pdf_download(client, evidence_pdf):
    r = client.get("/api/jobs/testjob123/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    # The documents route serves the same PDF by basename.
    r = client.get("/api/documents/testjob123.pdf/pdf")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    # Missing upload -> 404.
    assert client.get("/api/jobs/nojob999/pdf").status_code == 404


def test_override_preserves_evidence(tmp_path, monkeypatch):
    """Confirming a fact must keep its drawing-region link (audit story)."""
    ev = {"doc": "A-201_stair_section.pdf", "page": 1, "bbox": [0.41, 0.31, 0.47, 0.34]}
    facts = {
        "project": {"name": "ev-test"},
        "entities": [{
            "entity_type": "handrail", "id": "hr-1", "name": "HR",
            "attributes": {"height_above_nosing_mm": {
                "value": 920, "confidence": 0.82, "source": "pdf", "evidence": ev}},
        }],
    }
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(facts))
    monkeypatch.setenv("NBC_FACTS", str(facts_path))
    monkeypatch.setenv("NBC_OVERRIDES", str(tmp_path / "ov.json"))
    from fastapi.testclient import TestClient

    from server.app import app
    c = TestClient(app)

    r = c.post("/api/override", json={
        "entity_id": "hr-1", "fact": "height_above_nosing_mm",
        "value": 920, "note": "confirmed on drawing"})
    assert r.status_code == 200
    state = r.json()
    attr = next(e for e in state["facts"]["entities"] if e["id"] == "hr-1")[
        "attributes"]["height_above_nosing_mm"]
    assert attr["confidence"] == 1.0 and attr["evidence"] == ev
    # ... and the engine's audit trail carries it too.
    used = [f for res in state["report"]["results"] for f in res["facts_used"]
            if f["fact"] == "height_above_nosing_mm"]
    assert used and all(f["evidence"] == ev for f in used)
    # Deleting the override restores the original (evidence intact).
    r = c.delete("/api/override/hr-1/height_above_nosing_mm")
    attr = next(e for e in r.json()["facts"]["entities"] if e["id"] == "hr-1")[
        "attributes"]["height_above_nosing_mm"]
    assert attr["confidence"] == 0.82 and attr["evidence"] == ev
