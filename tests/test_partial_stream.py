"""Progressive result streaming (wave 4, sub-plan D).

Commit 1: extract_tiled's on_partial callback (page-barrier granularity).
Commit 2: the job contract around it (Job.partial_facts/partial_pages,
server/app.py's partial response wiring) -- STORE seeded directly, no
threads. The mid-run real-thread integration test lives in test_server.py.
"""
import json

from fastapi.testclient import TestClient

from extractors.pdf_extractor import extract_tiled
from server.app import _run_extraction, app
from server.jobs import STORE


def _drawing_pdf(tmp_path, n_pages):
    import fitz

    pdf = tmp_path / f"{n_pages}p.pdf"
    doc = fitz.open()
    for i in range(n_pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"FLOOR PLAN SCALE 1:50 SHEET {i + 1}")
    doc.save(pdf)
    return str(pdf)


def _payload(name, fact, value, confidence=0.7):
    return json.dumps({"entities": [{
        "entity_type": "room", "id": "r", "name": name,
        "attributes": {fact: {"value": value, "confidence": confidence}}}]})


# --------------------------------------------------------------------------
# Commit 1: extract_tiled(on_partial=...)
# --------------------------------------------------------------------------


def test_on_partial_fires_once_per_completed_page(tmp_path):
    pdf = _drawing_pdf(tmp_path, 2)
    calls = []
    # Page 1's single tile sees "Kitchen", page 2's sees a distinct entity
    # "Bedroom" -- keyed off call order since the outer page loop is serial.
    seen_paths = []

    def paged_runner(prompt, image_path):
        seen_paths.append(image_path)
        if len(seen_paths) == 1:
            return _payload("Kitchen", "room_use", "kitchen")
        return _payload("Bedroom", "room_use", "bedroom")

    def on_partial(pfacts, pages_done, pages_total):
        calls.append((json.loads(json.dumps(pfacts)), pages_done, pages_total))

    final = extract_tiled(pdf, runner=paged_runner, grid=(1, 1), pages="all",
                          on_partial=on_partial)

    assert len(calls) == 2
    first_pfacts, first_done, first_total = calls[0]
    second_pfacts, second_done, second_total = calls[1]
    assert (first_done, first_total) == (1, 2)
    assert (second_done, second_total) == (2, 2)
    # First snapshot has ONLY page-1's entity.
    assert len(first_pfacts["entities"]) == 1
    assert first_pfacts["entities"][0]["name"] == "Kitchen"
    # Second (final page) snapshot has both.
    assert len(second_pfacts["entities"]) == 2
    names = {e["name"] for e in second_pfacts["entities"]}
    assert names == {"Kitchen", "Bedroom"}
    # pfacts shape mirrors the final return dict.
    assert set(first_pfacts.keys()) == {"project", "entities"}
    assert set(first_pfacts["project"].keys()) == set(final["project"].keys())
    # Final on_partial call's entities match the authoritative return value.
    assert second_pfacts["entities"] == final["entities"]


def test_on_partial_does_not_change_final_output(tmp_path):
    pdf = _drawing_pdf(tmp_path, 2)

    def runner(prompt, image_path):
        return _payload("Kitchen", "room_use", "kitchen")

    silent = extract_tiled(pdf, runner=runner, grid=(1, 1), pages="all")
    noisy = extract_tiled(pdf, runner=runner, grid=(1, 1), pages="all",
                          on_partial=lambda *a: None)
    assert silent == noisy


def test_partial_entity_ids_prefix_stable(tmp_path):
    """merge_tile_facts assigns ids in first-seen order over an append-only
    tile_facts list -- confirm this holds empirically across partials: the
    id assigned to page-1's entity in the page-1 partial must be identical
    to its id in the page-2 partial and the final result, and a brand-new
    entity first seen on page 2 must get a fresh id that never collides with
    or reorders page 1's."""
    pdf = _drawing_pdf(tmp_path, 2)
    seen_paths = []

    def runner(prompt, image_path):
        seen_paths.append(image_path)
        if len(seen_paths) == 1:
            return _payload("Kitchen", "room_use", "kitchen")
        return _payload("Bedroom", "room_use", "bedroom")

    snapshots = []
    extract_tiled(pdf, runner=runner, grid=(1, 1), pages="all",
                 on_partial=lambda pfacts, d, t: snapshots.append(json.loads(json.dumps(pfacts))))

    page1_entities = {e["name"]: e["id"] for e in snapshots[0]["entities"]}
    page2_entities = {e["name"]: e["id"] for e in snapshots[1]["entities"]}
    assert page1_entities["Kitchen"] == "pdf-entity-1"
    # Page-1's entity keeps its id once page 2's new entity is folded in.
    assert page2_entities["Kitchen"] == page1_entities["Kitchen"]
    # The new page-2 entity gets a fresh id, never colliding with page 1's.
    assert page2_entities["Bedroom"] == "pdf-entity-2"
    assert page2_entities["Bedroom"] != page2_entities["Kitchen"]


def test_on_partial_snapshot_not_mutated_by_later_pages(tmp_path):
    """A snapshot handed to on_partial must never change after the fact --
    lock this by NOT deep-copying in the test (that would hide an aliasing
    bug) and instead asserting the retained reference is unaffected once a
    later page has run."""
    pdf = _drawing_pdf(tmp_path, 2)
    seen_paths = []

    def runner(prompt, image_path):
        seen_paths.append(image_path)
        if len(seen_paths) == 1:
            return _payload("Kitchen", "room_use", "kitchen")
        return _payload("Bedroom", "room_use", "bedroom")

    retained = {}

    def on_partial(pfacts, pages_done, pages_total):
        if pages_done == 1:
            retained["pfacts"] = pfacts
            retained["tiles_len"] = len(pfacts["project"]["tiles"])
            retained["entities_len"] = len(pfacts["entities"])

    extract_tiled(pdf, runner=runner, grid=(1, 1), pages="all", on_partial=on_partial)

    # The page-1 snapshot must still show exactly page 1's state, even though
    # page 2 has since appended to the extractor's internal accumulators.
    assert len(retained["pfacts"]["project"]["tiles"]) == retained["tiles_len"] == 1
    assert len(retained["pfacts"]["entities"]) == retained["entities_len"] == 1
    assert retained["pfacts"]["entities"][0]["name"] == "Kitchen"


def test_on_partial_not_fired_on_tiles_bypass_path():
    """The `tiles=` bypass branch has no page loop -- on_partial must never
    fire there (documented in extract_tiled's docstring)."""
    calls = []
    tiles = [{"path": "/tmp/r1c1.png", "label": "r1c1", "row": 1, "col": 1}]
    extract_tiled("A-201.pdf", runner=lambda p, i: _payload("K", "room_use", "kitchen"),
                 tiles=tiles, on_partial=lambda *a: calls.append(a))
    assert calls == []


# --------------------------------------------------------------------------
# Commit 2: job contract -- STORE seeded directly, no threads.
# --------------------------------------------------------------------------


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("NBC_OVERRIDES", str(tmp_path / "overrides.json"))
    return TestClient(app)


def _stair_facts(name="stale-partial"):
    return {
        "project": {"name": name},
        "entities": [{
            "entity_type": "stair_flight", "id": "s1", "name": "Stair",
            "attributes": {"riser_height_mm": {"value": 190, "confidence": 0.8, "source": "x"}},
        }],
    }


def test_job_partial_report_while_extracting(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    job = STORE.create(filename="p.pdf", ruleset_key="nbc", mode="tiled")
    STORE.update(job.id, status="extracting", partial_facts=_stair_facts(),
                partial_pages={"done": 1, "total": 3})

    r = client.get(f"/api/jobs/{job.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["partial"] is True
    assert body["partial_pages"] == {"done": 1, "total": 3}
    assert "report" in body and "facts" in body and "rules" in body
    # NO report_sha256 on a partial response -- the determinism badge is final-only.
    assert "report_sha256" not in body
    assert any(res["entity_id"] == "s1" for res in body["report"]["results"])


def test_partial_override_and_export_rejected(tmp_path, monkeypatch):
    """EMPIRICALLY verify (not just assume from reading the gate condition)
    that override/export 404 while only partial_facts is set: job.facts
    stays None throughout the streaming window, and every one of these
    endpoints gates on `job.facts is not None`."""
    client = _client(tmp_path, monkeypatch)
    job = STORE.create(filename="p.pdf", ruleset_key="nbc", mode="tiled")
    STORE.update(job.id, status="extracting", partial_facts=_stair_facts(),
                partial_pages={"done": 1, "total": 2})
    assert STORE.get(job.id).facts is None  # sanity: the lock's precondition

    r = client.post(f"/api/jobs/{job.id}/override",
                    json={"entity_id": "s1", "fact": "riser_height_mm", "value": 190, "note": "n"})
    assert r.status_code == 404

    r = client.delete(f"/api/jobs/{job.id}/override/s1/riser_height_mm")
    assert r.status_code == 404

    r = client.get(f"/api/jobs/{job.id}/export/pdf")
    assert r.status_code == 404

    r = client.get(f"/api/jobs/{job.id}/export/xlsx")
    assert r.status_code == 404


def test_final_job_response_has_no_partial_flag(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    job = STORE.create(filename="p.pdf", ruleset_key="nbc", mode="tiled")
    # A residual partial_facts from mid-run must not leak into the done
    # response -- the done branch takes priority and the response shape must
    # stay byte-identical to a job that never streamed at all.
    STORE.update(job.id, status="done",
                facts={"project": {"name": "final"}, "entities": []},
                partial_facts=_stair_facts(), partial_pages={"done": 1, "total": 2})

    r = client.get(f"/api/jobs/{job.id}")
    body = r.json()
    assert "partial" not in body
    assert "partial_pages" not in body
    assert "report_sha256" in body  # the done response IS signed


def test_run_extraction_wires_on_partial(monkeypatch):
    """Spy extract_tiled: assert _run_extraction passes an on_partial
    callback, invoking it lands a deep-copied snapshot in Job.partial_facts/
    partial_pages, and later mutation of the caller's dict can't leak back
    (proves the server-side json.loads(json.dumps(...)) severed aliasing)."""
    import extractors.pdf_extractor as pe

    job = STORE.create(filename="p.pdf", ruleset_key="nbc", mode="tiled")
    mutable_pfacts = _stair_facts(name="page-1-partial")

    def fake_extract_tiled(pdf_path, **kwargs):
        on_partial = kwargs.get("on_partial")
        assert on_partial is not None, "on_partial must be passed for tiled mode"
        on_partial(mutable_pfacts, 1, 2)
        # Mutate AFTER firing -- must not affect the already-stored snapshot.
        mutable_pfacts["project"]["name"] = "MUTATED"
        mutable_pfacts["entities"][0]["name"] = "MUTATED"
        return {"project": {"name": "final"}, "entities": []}

    monkeypatch.setattr(pe, "extract_tiled", fake_extract_tiled)
    _run_extraction(job.id, "fake.pdf", "tiled")

    stored = STORE.get(job.id)
    assert stored.partial_pages == {"done": 1, "total": 2}
    assert stored.partial_facts["project"]["name"] == "page-1-partial"
    assert stored.partial_facts["entities"][0]["name"] == "Stair"
    assert stored.status == "done"


def test_run_extraction_whole_mode_never_wires_on_partial(monkeypatch):
    """Whole-PDF mode has no page loop -- extract() must never receive
    on_partial (it doesn't accept the kwarg)."""
    import extractors.pdf_extractor as pe

    job = STORE.create(filename="p.pdf", ruleset_key="nbc", mode="whole")

    def fake_extract(pdf_path, **kwargs):
        assert "on_partial" not in kwargs
        return {"project": {"name": "final"}, "entities": []}

    monkeypatch.setattr(pe, "extract", fake_extract)
    _run_extraction(job.id, "fake.pdf", "whole")
    assert STORE.get(job.id).partial_facts is None
