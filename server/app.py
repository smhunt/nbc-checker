"""FastAPI review service — reviewer confirms/corrects UNCERTAIN facts,
engine deterministically re-runs (challenge EO4).

The engine never changes: every response re-derives the report as a pure
function of (ruleset, facts + human overrides). `report_sha256` proves it —
identical inputs always hash identically.

Config via environment:
    NBC_RULES      path to ruleset JSON   (default rules/nbc2020_part9_core.json)
    NBC_FACTS      path to facts JSON     (default samples/sample_dwelling_facts.json)
    NBC_OVERRIDES  path to overrides JSON (default reports/overrides.json)

Run:  uvicorn server.app:app --port 3099
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

import hashlib as _hashlib
import threading

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.checker import run_ruleset  # noqa: E402
from engine.export import to_pdf, to_xlsx  # noqa: E402
from server.jobs import STORE  # noqa: E402
from server.overrides import apply_overrides, load_overrides, save_overrides  # noqa: E402

# Rulesets the user can check an uploaded plan against.
RULESETS = {
    "nbc": ROOT / "rules" / "nbc2020_part9_core.json",
    "obc": ROOT / "rules" / "obc2024_part9_core.json",
}

app = FastAPI(title="NBC Checker Review API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dev.ecoworks.ca:3029",   # Vite dev server
        "https://localhost:3029",
        "https://nbc.dev.ecoworks.ca",    # Traefik production route
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _rules_path() -> str:
    return os.environ.get("NBC_RULES", str(ROOT / "rules" / "nbc2020_part9_core.json"))


def _facts_path() -> str:
    return os.environ.get("NBC_FACTS", str(ROOT / "samples" / "sample_dwelling_facts.json"))


def _overrides_path() -> str:
    return os.environ.get("NBC_OVERRIDES", str(ROOT / "reports" / "overrides.json"))


def _load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _coerce_value(value):
    """Numeric strings become int/float; 'true'/'false' become booleans.

    Non-string JSON values (numbers, booleans) pass through unchanged.
    """
    if isinstance(value, str):
        s = value.strip()
        if s.lower() == "true":
            return True
        if s.lower() == "false":
            return False
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            pass
    return value


def _state() -> dict:
    ruleset = _load_json(_rules_path())
    facts = _load_json(_facts_path())
    overrides = load_overrides(_overrides_path())

    effective_facts = apply_overrides(facts, overrides)
    report = run_ruleset(ruleset, effective_facts)
    report_sha256 = hashlib.sha256(
        json.dumps(report, sort_keys=True).encode("utf-8")
    ).hexdigest()

    rules_meta = {
        rule["rule_id"]: {
            "provision": rule.get("provision"),
            "title": rule.get("title"),
            "verification_notes": rule.get("verification_notes"),
        }
        for rule in ruleset.get("rules", [])
    }

    return {
        "report": report,
        "facts": effective_facts,
        "overrides": overrides,
        "rules": rules_meta,
        "report_sha256": report_sha256,
    }


class OverrideRequest(BaseModel):
    entity_id: str
    fact: str
    value: object
    note: str = ""


@app.get("/api/state")
def get_state() -> dict:
    return _state()


@app.post("/api/override")
def post_override(body: OverrideRequest) -> dict:
    path = _overrides_path()
    overrides = load_overrides(path)
    note = body.note.strip() or "confirmed by reviewer"
    today = datetime.date.today().isoformat()
    overrides.setdefault(body.entity_id, {})[body.fact] = {
        "value": _coerce_value(body.value),
        "confidence": 1.0,
        "source": f"human review: {note} ({today})",
    }
    save_overrides(path, overrides)
    return _state()


@app.delete("/api/override/{entity_id}/{fact}")
def delete_override(entity_id: str, fact: str) -> dict:
    path = _overrides_path()
    overrides = load_overrides(path)
    if entity_id not in overrides or fact not in overrides[entity_id]:
        raise HTTPException(status_code=404, detail="override not found")
    del overrides[entity_id][fact]
    if not overrides[entity_id]:
        del overrides[entity_id]
    save_overrides(path, overrides)
    return _state()


@app.get("/api/export/{fmt}")
def export(fmt: str):
    """Export the current (overrides-applied) report as PDF or Excel.

    The exported artifact reflects the same human overrides the reviewer sees,
    so the downloaded audit trail matches the on-screen state exactly.
    """
    fmt = fmt.lower()
    if fmt not in ("pdf", "xlsx"):
        raise HTTPException(status_code=404, detail=f"unknown export format '{fmt}' (use pdf or xlsx)")

    report = _state()["report"]
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    if fmt == "pdf":
        path = out_dir / "nbc_report.pdf"
        to_pdf(report, str(path))
        return FileResponse(path, media_type="application/pdf", filename="nbc_report.pdf")
    path = out_dir / "nbc_report.xlsx"
    to_xlsx(report, str(path))
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="nbc_report.xlsx",
    )


# --- Upload your own PDF plan ---------------------------------------------

def _rules_meta(ruleset: dict) -> dict:
    return {
        rule["rule_id"]: {
            "provision": rule.get("provision"),
            "title": rule.get("title"),
            "verification_notes": rule.get("verification_notes"),
        }
        for rule in ruleset.get("rules", [])
    }


def _job_state(job) -> dict:
    """Build the same state shape as /api/state for a completed upload job."""
    ruleset = _load_json(str(RULESETS[job.ruleset_key]))
    effective_facts = apply_overrides(job.facts, job.overrides)
    report = run_ruleset(ruleset, effective_facts)
    sha = _hashlib.sha256(json.dumps(report, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "report": report,
        "facts": effective_facts,
        "overrides": job.overrides,
        "rules": _rules_meta(ruleset),
        "report_sha256": sha,
    }


def _run_extraction(job_id: str, pdf_path: str, mode: str) -> None:
    """Background worker: extract facts from the PDF, then mark the job done."""
    try:
        from extractors.pdf_extractor import extract, extract_tiled

        STORE.update(job_id, status="extracting",
                     message="Reading the drawing… tiled mode can take a few minutes."
                     if mode == "tiled" else "Reading the drawing…")
        if mode == "tiled":
            facts = extract_tiled(pdf_path, grid=(3, 3))
        else:
            facts = extract(pdf_path)
        n = len(facts.get("entities", []))
        STORE.update(job_id, facts=facts, status="done",
                     message=f"Extracted {n} element(s). All LLM-read values route to human review.")
    except Exception as exc:  # extraction is best-effort; surface the failure
        STORE.update(job_id, status="error", error=f"{type(exc).__name__}: {exc}")


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    ruleset: str = Form("nbc"),
    mode: str = Form("whole"),
):
    """Accept a PDF plan, kick off background extraction, return a job id.

    ruleset: 'nbc' (NBC 2020) or 'obc' (Ontario OBC 2024).
    mode:    'whole' (fast, one pass) or 'tiled' (slower, ~6x more facts).
    """
    if ruleset not in RULESETS:
        raise HTTPException(status_code=400, detail=f"unknown ruleset '{ruleset}' (use nbc or obc)")
    if mode not in ("whole", "tiled"):
        raise HTTPException(status_code=400, detail=f"unknown mode '{mode}' (use whole or tiled)")
    fname = file.filename or "upload.pdf"
    if not fname.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF files are accepted")

    up_dir = ROOT / "reports" / "uploads"
    up_dir.mkdir(parents=True, exist_ok=True)
    job = STORE.create(filename=fname, ruleset_key=ruleset, mode=mode)
    dest = up_dir / f"{job.id}.pdf"
    dest.write_bytes(await file.read())

    threading.Thread(target=_run_extraction, args=(job.id, str(dest), mode), daemon=True).start()
    return job.public()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    out = job.public()
    if job.status == "done" and job.facts is not None:
        out.update(_job_state(job))
    return out


@app.post("/api/jobs/{job_id}/override")
def job_override(job_id: str, body: OverrideRequest) -> dict:
    job = STORE.get(job_id)
    if job is None or job.facts is None:
        raise HTTPException(status_code=404, detail="job not found or not ready")
    note = body.note.strip() or "confirmed by reviewer"
    today = datetime.date.today().isoformat()
    job.overrides.setdefault(body.entity_id, {})[body.fact] = {
        "value": _coerce_value(body.value),
        "confidence": 1.0,
        "source": f"human review: {note} ({today})",
    }
    out = job.public()
    out.update(_job_state(job))
    return out


@app.delete("/api/jobs/{job_id}/override/{entity_id}/{fact}")
def job_delete_override(job_id: str, entity_id: str, fact: str) -> dict:
    job = STORE.get(job_id)
    if job is None or job.facts is None:
        raise HTTPException(status_code=404, detail="job not found or not ready")
    if entity_id not in job.overrides or fact not in job.overrides[entity_id]:
        raise HTTPException(status_code=404, detail="override not found")
    del job.overrides[entity_id][fact]
    if not job.overrides[entity_id]:
        del job.overrides[entity_id]
    out = job.public()
    out.update(_job_state(job))
    return out


@app.get("/api/jobs/{job_id}/export/{fmt}")
def job_export(job_id: str, fmt: str):
    job = STORE.get(job_id)
    if job is None or job.facts is None:
        raise HTTPException(status_code=404, detail="job not found or not ready")
    fmt = fmt.lower()
    if fmt not in ("pdf", "xlsx"):
        raise HTTPException(status_code=404, detail=f"unknown export format '{fmt}'")
    report = _job_state(job)["report"]
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    if fmt == "pdf":
        path = out_dir / f"upload_{job.id}.pdf"
        to_pdf(report, str(path))
        return FileResponse(path, media_type="application/pdf", filename="nbc_report.pdf")
    path = out_dir / f"upload_{job.id}.xlsx"
    to_xlsx(report, str(path))
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="nbc_report.xlsx",
    )


# Serve the production UI build from the same origin (no CORS, no dev server).
# Mounted last so all /api routes above take precedence. In development the
# Vite dev server on :3029 proxies /api here instead.
_UI_DIST = ROOT / "ui" / "dist"
if _UI_DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_UI_DIST), html=True), name="ui")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=3099)
