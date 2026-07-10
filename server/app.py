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
from server.jobs import STORE, make_progress_cb  # noqa: E402
from server.overrides import apply_overrides, evidence_for, load_overrides, save_overrides  # noqa: E402
from server.pdfrender import (  # noqa: E402
    FORBIDDEN_NAME_TOKENS,
    render_page_png,
    resolve_document,
)

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
    record = {
        "value": _coerce_value(body.value),
        "confidence": 1.0,
        "source": f"human review: {note} ({today})",
    }
    # Keep the confirmed fact's link to the drawing region that justified it.
    evidence = evidence_for(_load_json(_facts_path()), body.entity_id, body.fact)
    if evidence is not None:
        record["evidence"] = evidence
    overrides.setdefault(body.entity_id, {})[body.fact] = record
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


def _run_extraction(job_id: str, pdf_path: str, mode: str, pages_spec="auto") -> None:
    """Background worker: extract facts from the PDF, then mark the job done."""
    try:
        from extractors.pdf_extractor import extract, extract_tiled, tile_concurrency

        STORE.update(job_id, status="extracting",
                     message="Reading the drawing… tiled mode can take a few minutes."
                     if mode == "tiled" else "Reading the drawing…")

        # Progress callback: verbose stage + tile counters + per-tile timing
        # for the ETA (server/jobs.py::make_progress_cb). Purely observational
        # — the facts are identical with or without it.
        _cb = make_progress_cb(STORE, job_id)

        if mode == "tiled":
            # grid=None -> per-page adaptive choose_grid (letter 2x2, big sheets 3x3)
            workers = tile_concurrency()
            STORE.update(job_id, workers=workers)
            facts = extract_tiled(pdf_path, grid=None, pages=pages_spec, progress_cb=_cb,
                                  workers=workers)
        else:
            facts = extract(pdf_path, progress_cb=_cb)
        STORE.update(job_id, stage="running deterministic checks")
        n = len(facts.get("entities", []))
        pages_meta = facts.get("project", {}).get("pages")
        message = f"Extracted {n} element(s). All LLM-read values route to human review."
        if pages_meta:
            total, processed = pages_meta["total"], len(pages_meta["processed"])
            n_skipped = len(pages_meta.get("skipped", []))
            message = (f"Extracted {n} element(s) from {processed} of {total} pages"
                       f"{f' ({n_skipped} skipped — see report metadata)' if n_skipped else ''}."
                       f" All LLM-read values route to human review.")
            STORE.update(job_id, pages_info={"total": total, "selected": processed,
                                             "skipped": n_skipped})
        STORE.update(job_id, facts=facts, status="done", stage="done", message=message)
    except Exception as exc:  # extraction is best-effort; surface the failure
        STORE.update(job_id, status="error", stage="error", error=f"{type(exc).__name__}: {exc}")


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    ruleset: str = Form("nbc"),
    mode: str = Form("whole"),
    pages: str = Form("auto"),
):
    """Accept a PDF plan, kick off background extraction, return a job id.

    ruleset: 'nbc' (NBC 2020) or 'obc' (Ontario OBC 2024).
    mode:    'whole' (fast, one pass) or 'tiled' (slower, ~6x more facts).
    pages:   'auto' (drawing pages only, skips reported), 'all', or '1,3-5'
             (tiled mode; whole mode always reads the full file).
    """
    if ruleset not in RULESETS:
        raise HTTPException(status_code=400, detail=f"unknown ruleset '{ruleset}' (use nbc or obc)")
    if mode not in ("whole", "tiled"):
        raise HTTPException(status_code=400, detail=f"unknown mode '{mode}' (use whole or tiled)")
    from extractors.page_select import parse_pages_spec
    try:
        pages_spec = parse_pages_spec(pages)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    fname = file.filename or "upload.pdf"
    if not fname.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF files are accepted")

    up_dir = ROOT / "reports" / "uploads"
    up_dir.mkdir(parents=True, exist_ok=True)
    job = STORE.create(filename=fname, ruleset_key=ruleset, mode=mode)
    dest = up_dir / f"{job.id}.pdf"
    dest.write_bytes(await file.read())

    threading.Thread(target=_run_extraction, args=(job.id, str(dest), mode, pages_spec),
                     daemon=True).start()
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
    record = {
        "value": _coerce_value(body.value),
        "confidence": 1.0,
        "source": f"human review: {note} ({today})",
    }
    evidence = evidence_for(job.facts, body.entity_id, body.fact)
    if evidence is not None:
        record["evidence"] = evidence
    job.overrides.setdefault(body.entity_id, {})[body.fact] = record
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


# --- PDF evidence drill-down: serve source PDFs + rendered page PNGs -------
# Registered BEFORE the StaticFiles mount below — a '/' mount would shadow
# any route added after it.

ALLOWED_DPI = {96, 150, 200}


def _page_cache_dir() -> Path:
    d = ROOT / "reports" / "page_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _check_name(name: str) -> None:
    """400 on empty names or anything smelling of path traversal."""
    if not name or any(tok in name for tok in FORBIDDEN_NAME_TOKENS):
        raise HTTPException(status_code=400, detail="invalid document name")


def _check_dpi(dpi: int) -> None:
    if dpi not in ALLOWED_DPI:
        raise HTTPException(
            status_code=400,
            detail=f"dpi must be one of {sorted(ALLOWED_DPI)}",
        )


def _page_png_response(pdf_path: Path, page: int, dpi: int) -> FileResponse:
    try:
        png = render_page_png(pdf_path, page, dpi, _page_cache_dir())
    except ValueError as exc:  # page out of range
        raise HTTPException(status_code=404, detail=str(exc))
    return FileResponse(png, media_type="image/png")


@app.get("/api/documents/{name}/pdf")
def document_pdf(name: str):
    """Serve a whitelisted source PDF (reports/uploads, samples/**) by basename."""
    _check_name(name)
    path = resolve_document(name)
    if path is None:
        raise HTTPException(status_code=404, detail="document not found")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@app.get("/api/documents/{name}/page/{page}.png")
def document_page_png(name: str, page: int, dpi: int = 150):
    """Render one page of a whitelisted PDF to PNG (cached, fixed dpi set)."""
    _check_name(name)
    _check_dpi(dpi)
    path = resolve_document(name)
    if path is None:
        raise HTTPException(status_code=404, detail="document not found")
    return _page_png_response(path, page, dpi)


def _job_pdf_path(job_id: str) -> Path:
    _check_name(job_id)
    path = ROOT / "reports" / "uploads" / f"{job_id}.pdf"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="job pdf not found")
    return path


@app.get("/api/jobs/{job_id}/pdf")
def job_pdf(job_id: str):
    """Serve the original uploaded PDF for a job."""
    path = _job_pdf_path(job_id)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@app.get("/api/jobs/{job_id}/page/{page}.png")
def job_page_png(job_id: str, page: int, dpi: int = 150):
    """Render one page of a job's uploaded PDF to PNG (cached, fixed dpi set)."""
    _check_dpi(dpi)
    return _page_png_response(_job_pdf_path(job_id), page, dpi)


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
