"""In-memory job store for uploaded-PDF analysis.

Extraction of a real drawing (especially tiled) takes seconds to minutes and
shells out to the `claude` CLI, so uploads run on a background thread and the
UI polls for status. Jobs are ephemeral (lost on server restart) — this is a
review aid, not a system of record.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

JobStatus = Literal["extracting", "checking", "done", "error"]


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

    def public(self) -> dict:
        return {
            "job_id": self.id,
            "filename": self.filename,
            "ruleset_key": self.ruleset_key,
            "mode": self.mode,
            "status": self.status,
            "message": self.message,
            "error": self.error,
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
