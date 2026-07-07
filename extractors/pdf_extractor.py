"""
PDF drawing -> building facts extractor (LLM-assisted path, EO1).

This is the untrusted ingestion path: a generative model reads dimension
annotations off an architectural drawing and reports them as facts. The
model NEVER participates in pass/fail judgment — it only produces facts,
and every fact it produces is capped below the engine's CONFIDENCE_THRESHOLD
(0.9) so the checker routes it to `uncertain` / human review rather than
treating it as ground truth.

Uses the `claude` CLI in headless mode (`claude -p ... --output-format json`)
so no API key is needed on this machine.

Usage:
    from extractors.pdf_extractor import extract
    facts = extract("samples/A-201_stair_section.pdf")
"""

from __future__ import annotations

import json
import os
import subprocess

# EO1 invariant: no LLM-extracted fact may ever reach the engine's
# CONFIDENCE_THRESHOLD (0.9 in engine/checker.py). Capping at 0.89 guarantees
# every LLM fact lands below the threshold and is routed to human review
# (`uncertain` status), regardless of how confident the model claims to be.
MAX_LLM_CONFIDENCE = 0.89

EXTRACTION_PROMPT = '''You are a drawing-takeoff assistant. Extract ONLY dimensions explicitly annotated on this architectural drawing. Return JSON: {"entities": [{"entity_type": "...", "id": "...", "name": "...", "attributes": {"<fact>": {"value": <number>, "confidence": <0..1 your certainty>, "source": "<sheet> <where on sheet>"}}}]}
Known entity_types and facts: stair_flight (riser_height_mm, tread_run_mm, clear_width_mm, headroom_mm, service), handrail (height_above_nosing_mm), guard (guard_height_mm, fall_height_mm, guard_context, max_opening_mm), room (room_use, ceiling_height_mm), window (overall_height_mm, overall_width_mm), door (clear_width_mm, height_mm).
NEVER infer a value that is not printed on the drawing. If unsure, omit the fact. Output ONLY the JSON object.'''

CLI_TIMEOUT_S = 300


def run_claude(prompt: str, pdf_path: str) -> str:
    """Run the `claude` CLI headless against a PDF; return the assistant text.

    The CLI's --output-format json wraps the response in an envelope whose
    "result" field holds the assistant's text.
    """
    abs_path = os.path.abspath(pdf_path)
    full_prompt = f"{prompt}\n\nThe drawing file to read is at: {abs_path}"
    proc = subprocess.run(
        # --allowedTools "Read" grants the headless instance read-only access so
        # it can open the drawing; without it the nested CLI is denied file access
        # and returns prose instead of JSON.
        ["claude", "-p", full_prompt, "--allowedTools", "Read", "--output-format", "json"],
        capture_output=True,
        text=True,
        timeout=CLI_TIMEOUT_S,
    )
    if proc.returncode != 0:
        stderr_excerpt = (proc.stderr or "").strip()[:500]
        raise RuntimeError(
            f"claude CLI exited with code {proc.returncode}: {stderr_excerpt}"
        )
    envelope = json.loads(proc.stdout)
    return envelope["result"]


def _strip_fences(text: str) -> str:
    """Remove markdown code fences (``` / ```json) around a JSON payload."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def _coerce_confidence(raw) -> float:
    """Model-claimed confidence -> capped float. Missing/invalid -> 0.5."""
    try:
        conf = float(raw)
    except (TypeError, ValueError):
        return 0.5
    if not (0.0 <= conf <= 1.0):
        return 0.5
    return min(conf, MAX_LLM_CONFIDENCE)


def _normalize_attribute(value, default_source: str) -> dict:
    """Wrap/cap a model-reported attribute into the facts schema."""
    if not isinstance(value, dict):
        return {"value": value, "confidence": 0.5, "source": default_source}
    return {
        "value": value.get("value"),
        "confidence": _coerce_confidence(value.get("confidence")),
        "source": value.get("source") or default_source,
    }


def extract(pdf_path: str, runner=run_claude) -> dict:
    """Extract annotated dimensions from a drawing PDF into a facts dict.

    Every returned fact carries confidence <= MAX_LLM_CONFIDENCE (EO1):
    the engine will report `uncertain` for all of them, forcing human review.
    """
    raw_text = runner(EXTRACTION_PROMPT, pdf_path)
    try:
        payload = json.loads(_strip_fences(raw_text))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(
            f"PDF extraction returned unparseable JSON: {exc}: {str(raw_text)[:300]}"
        )
    if not isinstance(payload, dict) or not isinstance(payload.get("entities"), list):
        raise ValueError(
            "PDF extraction returned unparseable JSON: "
            f"expected object with 'entities' list, got: {str(payload)[:300]}"
        )

    pdf_name = os.path.basename(pdf_path)
    default_source = f"{pdf_name} (LLM extraction)"

    entities = []
    for i, ent in enumerate(payload["entities"]):
        if not isinstance(ent, dict):
            continue
        raw_attrs = ent.get("attributes")
        attributes = {}
        if isinstance(raw_attrs, dict):
            for fact, value in raw_attrs.items():
                attributes[fact] = _normalize_attribute(value, default_source)
        entities.append(
            {
                "entity_type": str(ent.get("entity_type", "unknown")),
                "id": str(ent.get("id") or f"pdf-entity-{i + 1}"),
                "name": str(ent.get("name") or f"PDF entity {i + 1}"),
                "attributes": attributes,
            }
        )

    return {
        "project": {
            "name": f"{pdf_name} (drawing extraction)",
            "sources": [pdf_path],
        },
        "entities": entities,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python3 extractors/pdf_extractor.py <drawing.pdf>", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(extract(sys.argv[1]), indent=2))
