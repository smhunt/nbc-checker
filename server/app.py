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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.checker import run_ruleset  # noqa: E402
from engine.export import to_pdf, to_xlsx  # noqa: E402
from server.overrides import apply_overrides, load_overrides, save_overrides  # noqa: E402

app = FastAPI(title="NBC Checker Review API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://dev.ecoworks.ca:3029", "https://localhost:3029"],
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=3099)
