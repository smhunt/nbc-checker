"""Job progress + ETA: callback ordering, ETA math, public() shape."""
import json
import time

from extractors.pdf_extractor import extract, extract_tiled
from server.jobs import Job, estimate_eta


def _payload():
    return json.dumps({"entities": [{
        "entity_type": "t", "id": "a", "name": "A",
        "attributes": {"x_mm": {"value": 1, "confidence": 0.8}}}]})


def _tiles(*labels):
    return [{"path": f"/tmp/{l}.png", "label": l, "row": 1, "col": i + 1}
            for i, l in enumerate(labels)]


def test_tiled_progress_callback_ordering():
    events = []
    extract_tiled(
        "A-201.pdf",
        runner=lambda p, i: _payload(),
        tiles=_tiles("r1c1", "r1c2"),
        progress_cb=lambda stage, done, total: events.append((stage, done, total)),
    )
    assert events[0] == ("extracting tile r1c1", 0, 2)
    assert events[1] == ("extracting tile r1c2", 1, 2)
    assert events[-1] == ("merging extracted facts", 2, 2)


def test_whole_pdf_progress_stages():
    events = []
    extract("A-201.pdf", runner=lambda p, f: _payload(),
            progress_cb=lambda s, d, t: events.append(s))
    assert events[0].startswith("reading")
    assert len(events) >= 2


def test_progress_cb_does_not_change_output():
    kwargs = dict(runner=lambda p, i: _payload(), tiles=_tiles("r1c1"))
    silent = extract_tiled("A-201.pdf", **kwargs)
    noisy = extract_tiled("A-201.pdf", progress_cb=lambda *a: None, **kwargs)
    assert silent == noisy


def test_estimate_eta_uses_measured_durations():
    # 2 tiles done at 10s each, 3 remaining -> 30s + overhead 3s
    assert estimate_eta([10.0, 10.0], remaining=3, seed_avg=25.0) == 33.0


def test_estimate_eta_seed_before_first_measurement():
    assert estimate_eta([], remaining=4, seed_avg=25.0) == 103.0


def test_estimate_eta_none_when_nothing_remains():
    assert estimate_eta([5.0], remaining=0, seed_avg=25.0) == 3.0


def test_estimate_eta_decreases_with_time_spent_in_current_stage():
    # The server-side ETA must fall between tile completions, not sit frozen
    # until the next callback (the UI re-anchors to it every poll).
    e0 = estimate_eta([10.0], remaining=3, seed_avg=25.0, in_stage_elapsed=0.0)
    e4 = estimate_eta([10.0], remaining=3, seed_avg=25.0, in_stage_elapsed=4.0)
    assert e0 == 33.0 and e4 == 29.0


def test_estimate_eta_overrun_tile_does_not_go_negative():
    # Current tile has taken longer than the average: its remaining share
    # clamps to 0, later tiles still counted.
    e = estimate_eta([10.0], remaining=3, seed_avg=25.0, in_stage_elapsed=50.0)
    assert e == 23.0  # 0 + 2*10 + 3


def test_estimate_eta_none_when_last_unit_budget_exhausted():
    # Single remaining unit (whole-PDF pass or final tile) running past its
    # estimate: no basis for a number — UI shows "finishing up…".
    assert estimate_eta([], remaining=1, seed_avg=25.0, in_stage_elapsed=30.0) is None


def test_job_eta_falls_as_clock_advances():
    job = Job(id="j2", filename="f.pdf", ruleset_key="nbc", mode="whole")
    job.stage = "reading the drawing (single pass)"
    job.progress_done, job.progress_total = 0, 1
    job.stage_changed_at = time.time() - 5
    eta = job.public()["eta_s"]
    assert eta is not None and abs(eta - (25.0 - 5 + 3.0)) < 0.5


def test_job_public_carries_progress_fields():
    job = Job(id="j1", filename="f.pdf", ruleset_key="nbc", mode="tiled")
    job.started_at = time.time() - 10
    job.stage = "extracting tile r1c1"
    job.progress_done, job.progress_total = 1, 9
    job.tile_durations = [12.0]
    job.stage_changed_at = time.time()
    pub = job.public()
    assert pub["stage"] == "extracting tile r1c1"
    assert pub["progress"] == {"done": 1, "total": 9}
    assert pub["elapsed_s"] >= 10
    expected = estimate_eta([12.0], remaining=8, seed_avg=25.0, in_stage_elapsed=0.0)
    assert abs(pub["eta_s"] - expected) < 0.5
