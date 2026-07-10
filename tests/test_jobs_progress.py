"""Job progress + ETA: callback ordering, ETA math, public() shape."""
import json
import time

from extractors.pdf_extractor import extract, extract_tiled
from server.jobs import Job, JobStore, estimate_eta, make_progress_cb


def _payload():
    return json.dumps({"entities": [{
        "entity_type": "t", "id": "a", "name": "A",
        "attributes": {"x_mm": {"value": 1, "confidence": 0.8}}}]})


def _tiles(*labels):
    return [{"path": f"/tmp/{l}.png", "label": l, "row": 1, "col": i + 1}
            for i, l in enumerate(labels)]


def test_tiled_progress_callback_ordering():
    # workers=1 pins exact legacy serial semantics -- this test asserts the
    # literal per-tile progress strings, which only the serial branch emits.
    events = []
    extract_tiled(
        "A-201.pdf",
        runner=lambda p, i: _payload(),
        tiles=_tiles("r1c1", "r1c2"),
        progress_cb=lambda stage, done, total: events.append((stage, done, total)),
        workers=1,
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


def _drawing_pdf(tmp_path, n_pages):
    import fitz
    pdf = tmp_path / f"{n_pages}p.pdf"
    doc = fitz.open()
    for i in range(n_pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"FLOOR PLAN SCALE 1:50 SHEET {i + 1}")
    doc.save(pdf)
    return str(pdf)


def test_multipage_progress_event_ordering(tmp_path):
    # workers=1 pins exact legacy serial semantics for this per-tile string test.
    pdf = _drawing_pdf(tmp_path, 2)
    events = []
    extract_tiled(pdf, runner=lambda p, i: _payload(), pages="all", grid=(1, 1),
                  progress_cb=lambda s, d, t: events.append((s, d, t)), workers=1)
    assert events[0] == ("page 1/2 (pdf p1): rendering tiles", 0, 2)
    assert events[1] == ("page 1/2 (pdf p1): extracting tile r1c1", 0, 2)
    assert events[2] == ("page 2/2 (pdf p2): rendering tiles", 1, 2)
    assert events[3] == ("page 2/2 (pdf p2): extracting tile r1c1", 1, 2)
    assert events[-1] == ("merging extracted facts", 2, 2)
    dones = [d for _, d, _ in events]
    assert dones == sorted(dones)  # monotonic over ONE grand total


def test_multipage_progress_cb_does_not_change_output(tmp_path):
    pdf = _drawing_pdf(tmp_path, 2)
    kwargs = dict(runner=lambda p, i: _payload(), pages="all", grid=(1, 1))
    silent = extract_tiled(pdf, **kwargs)
    noisy = extract_tiled(pdf, progress_cb=lambda *a: None, **kwargs)
    assert silent == noisy


def _job_cb(mode="tiled"):
    """A store + job wired up like `_run_extraction`'s real usage, plus the
    `progress_cb` `make_progress_cb` builds for it."""
    store = JobStore()
    job = store.create(filename="f.pdf", ruleset_key="nbc", mode=mode)
    cb = make_progress_cb(store, job.id)
    return store, job, cb


def test_progress_cb_counts_normal_tile_durations(monkeypatch):
    """The page-prefixed stage text ("page 1/2 (pdf p1): extracting tile
    r1c1") must still match the "extracting tile" substring the duration
    counter keys on."""
    store, job, cb = _job_cb()
    t = [1000.0]
    monkeypatch.setattr(time, "time", lambda: t[0])

    cb("page 1/2 (pdf p1): extracting tile r1c1", 0, 4)
    t[0] += 12.0
    cb("page 1/2 (pdf p1): extracting tile r1c2", 1, 4)  # closes the r1c1 interval
    t[0] += 8.0
    cb("page 1/2 (pdf p1): extracting tile r2c1", 2, 4)  # closes the r1c2 interval

    assert store.get(job.id).tile_durations == [12.0, 8.0]


def test_progress_cb_excludes_subsecond_ticks_from_eta_stats(monkeypatch):
    """A cache hit or a blank-tile skip completes in well under a second;
    such intervals must not enter tile_durations (they would drag the
    measured per-tile average toward zero and make the ETA for the
    remaining REAL tiles wildly optimistic)."""
    store, job, cb = _job_cb()
    t = [1000.0]
    monkeypatch.setattr(time, "time", lambda: t[0])

    cb("extracting tile r1c1", 0, 3)
    t[0] += 0.3  # cache hit: well under the 1.0s floor
    cb("extracting tile r1c2", 1, 3)
    t[0] += 15.0  # a real, slow tile
    cb("extracting tile r1c3", 2, 3)

    assert store.get(job.id).tile_durations == [15.0]


def test_progress_cb_skip_stage_never_counts_duration(monkeypatch):
    """The blank-skip stage text never contains "extracting tile", so the
    interval STARTING at a skip tick is never counted as a tile duration —
    independent of how long it is (fails the guard "on purpose", per the
    sub-plan). The interval ENDING at a skip tick (measuring the real tile
    extraction that preceded it) is still counted normally."""
    store, job, cb = _job_cb()
    t = [1000.0]
    monkeypatch.setattr(time, "time", lambda: t[0])

    cb("extracting tile r1c1", 0, 3)
    t[0] += 15.0  # r1c1's own real extraction time
    cb("skipping blank tile r1c2", 1, 3)  # closes r1c1's interval -> counted
    t[0] += 20.0  # elapsed since the skip tick -- must NOT be counted
    cb("extracting tile r1c3", 2, 3)

    assert store.get(job.id).tile_durations == [15.0]


# --------------------------------------------------------------------------
# Parallel tiles: Job.workers + ETA seed scaling (wave 3, sub-plan A, task A4)
# --------------------------------------------------------------------------

def test_progress_cb_counts_durations_for_aggregate_parallel_format(monkeypatch):
    """The wave-3 aggregate progress string used for workers>1
    ('extracting tiles (N/total done, M in flight)') must still contain the
    'extracting tile' substring the duration counter keys on, so parallel-mode
    inter-completion gaps still feed the ETA exactly like serial-mode ones."""
    store, job, cb = _job_cb()
    t = [1000.0]
    monkeypatch.setattr(time, "time", lambda: t[0])

    cb("extracting tiles (0/4 done, 4 in flight)", 0, 4)
    t[0] += 9.0
    cb("extracting tiles (1/4 done, 3 in flight)", 1, 4)
    t[0] += 7.0
    cb("extracting tiles (2/4 done, 2 in flight)", 2, 4)

    assert store.get(job.id).tile_durations == [9.0, 7.0]


def test_job_eta_seed_scaled_by_workers():
    # No durations measured yet -> falls back to the seed, which must be
    # divided by workers: 8 remaining * (25/4) + 3 overhead == 53.0.
    job = Job(id="j3", filename="f.pdf", ruleset_key="nbc", mode="tiled", workers=4)
    job.progress_done, job.progress_total = 0, 8
    job.stage_changed_at = time.time()
    eta = job.eta_s()
    assert eta is not None
    assert abs(eta - 53.0) < 0.5


def test_job_eta_seed_unscaled_at_default_workers():
    # workers defaults to 1 (whole-PDF mode, or a tiled job that predates
    # wave 3 wiring) -> seed is unchanged from pre-wave-3 behaviour.
    job = Job(id="j3b", filename="f.pdf", ruleset_key="nbc", mode="whole")
    job.progress_done, job.progress_total = 0, 1
    job.stage_changed_at = time.time()
    assert job.workers == 1
    eta = job.eta_s()
    assert eta is not None
    assert abs(eta - 28.0) < 0.5  # 25.0 seed + 3.0 overhead, unscaled


def test_eta_uses_intercompletion_durations_as_throughput():
    """Once real inter-completion gaps are measured, `estimate_eta`'s math is
    UNCHANGED -- the workers seed-scaling only matters before the first
    measurement. Two jobs with identical measured durations but different
    `workers` must produce the identical ETA."""
    job = Job(id="j4", filename="f.pdf", ruleset_key="nbc", mode="tiled", workers=4)
    job.tile_durations = [5.0, 6.0, 4.0]
    job.progress_done, job.progress_total = 3, 10
    job.stage_changed_at = time.time()
    eta = job.eta_s()
    expected = estimate_eta(job.tile_durations, remaining=7, seed_avg=25.0 / 4,
                            in_stage_elapsed=0.0)
    assert eta is not None
    assert abs(eta - expected) < 0.5

    job2 = Job(id="j5", filename="f.pdf", ruleset_key="nbc", mode="tiled", workers=1)
    job2.tile_durations = list(job.tile_durations)
    job2.progress_done, job2.progress_total = 3, 10
    job2.stage_changed_at = time.time()
    assert abs(job2.eta_s() - eta) < 0.5
