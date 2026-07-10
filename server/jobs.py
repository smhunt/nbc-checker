"""In-memory job store for uploaded-PDF analysis.

Extraction of a real drawing (especially tiled) takes seconds to minutes and
shells out to the `claude` CLI, so uploads run on a background thread and the
UI polls for status. Jobs are ephemeral (lost on server restart) — this is a
review aid, not a system of record.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

JobStatus = Literal["extracting", "checking", "done", "error"]

# Fixed allowance for the non-tile tail of a job (merge + engine + report).
_OVERHEAD_S = 3.0

# Seed for the ETA before the first tile of a job finishes.
_SEED_AVG_S = 25.0


def estimate_eta(durations: list[float], remaining: int, seed_avg: float,
                 in_stage_elapsed: float = 0.0) -> float | None:
    """Estimated seconds to completion, falling smoothly as the clock runs.

    `remaining` INCLUDES the in-progress unit; `in_stage_elapsed` is how long
    that unit has already been running, so the estimate decreases between
    callbacks instead of sitting frozen until the next tile completes (the UI
    re-anchors to this value on every poll — a frozen value produced a
    sawtooth countdown). Returns None when the last remaining unit has
    exhausted its budget: there is no basis for a number and the UI should
    say "finishing up…" instead.
    """
    per_tile = sum(durations) / len(durations) if durations else seed_avg
    if remaining <= 0:
        return _OVERHEAD_S
    current_left = per_tile - max(0.0, in_stage_elapsed)
    if current_left <= 0:
        if remaining <= 1:
            return None
        current_left = 0.0
    return round(current_left + per_tile * (remaining - 1) + _OVERHEAD_S, 1)


@dataclass
class Job:
    id: str
    filename: str
    ruleset_key: str
    mode: str
    status: JobStatus = "extracting"
    message: str = "Extracting facts from the drawing…"
    facts: dict | None = None
    overrides: dict = field(default_factory=dict)
    error: str | None = None
    # Verbose progress: current stage, tile counters, timing for the ETA.
    stage: str = "queued"
    progress_done: int = 0
    progress_total: int = 0
    started_at: float = field(default_factory=time.time)
    stage_changed_at: float = field(default_factory=time.time)
    tile_durations: list[float] = field(default_factory=list)

    def eta_s(self) -> float | None:
        if self.status in ("done", "error"):
            return None
        remaining = max(0, self.progress_total - self.progress_done)
        return estimate_eta(self.tile_durations, remaining, _SEED_AVG_S,
                            in_stage_elapsed=time.time() - self.stage_changed_at)

    def public(self) -> dict:
        return {
            "job_id": self.id,
            "filename": self.filename,
            "ruleset_key": self.ruleset_key,
            "mode": self.mode,
            "status": self.status,
            "message": self.message,
            "error": self.error,
            "stage": self.stage,
            "progress": {"done": self.progress_done, "total": self.progress_total},
            "elapsed_s": round(time.time() - self.started_at, 1),
            "eta_s": self.eta_s(),
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, filename: str, ruleset_key: str, mode: str) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], filename=filename, ruleset_key=ruleset_key, mode=mode)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for k, v in fields.items():
                setattr(job, k, v)


STORE = JobStore()
