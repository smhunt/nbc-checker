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
import math
import os
import re
import subprocess
import tempfile

# EO1 invariant: no LLM-extracted fact may ever reach the engine's
# CONFIDENCE_THRESHOLD (0.9 in engine/checker.py). Capping at 0.89 guarantees
# every LLM fact lands below the threshold and is routed to human review
# (`uncertain` status), regardless of how confident the model claims to be.
MAX_LLM_CONFIDENCE = 0.89

EXTRACTION_PROMPT = '''You are a drawing-takeoff assistant. Extract ONLY dimensions explicitly annotated on this architectural drawing. Return JSON: {"entities": [{"entity_type": "...", "id": "...", "name": "...", "attributes": {"<fact>": {"value": <number>, "confidence": <0..1 your certainty>, "source": "<sheet> <where on sheet>"}}}]}
Known entity_types and facts: stair_flight (riser_height_mm, tread_run_mm, clear_width_mm, headroom_mm, service), handrail (height_above_nosing_mm), guard (guard_height_mm, fall_height_mm, guard_context, max_opening_mm), room (room_use, ceiling_height_mm), window (overall_height_mm, overall_width_mm), door (clear_width_mm, height_mm).
NEVER infer a value that is not printed on the drawing. If unsure, omit the fact. Each attribute may also include "page": <1-based page number the annotation appears on>. Output ONLY the JSON object.'''

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
    out = {
        "value": value.get("value"),
        "confidence": _coerce_confidence(value.get("confidence")),
        "source": value.get("source") or default_source,
    }
    # Raw locator hints from the model. These are NOT the final evidence
    # object — the extraction path that knows the page geometry converts
    # them (tiled: bbox -> page coordinates; whole-PDF: page number only)
    # and removes the raw keys.
    if "bbox" in value:
        out["bbox"] = value["bbox"]
    if "page" in value:
        out["page"] = value["page"]
    return out


def tile_bbox_to_page(frac_bbox, clip, page_w, page_h) -> list | None:
    """Map an LLM-reported bbox (fractions 0-1 of a tile image, top-left
    origin) to normalized page coordinates via the tile's clip rect (page
    points, fitz top-left space). Pure and deterministic.

    Returns None (caller degrades to page-level evidence) when the input is
    malformed, out of range, degenerate, or absurdly large. Because inputs
    are fractions of the tile the model actually saw, a hallucinated bbox is
    geometrically confined to that tile — worst case is a wrong region within
    the right neighbourhood, immediately visible to the reviewer.
    """
    if not isinstance(frac_bbox, (list, tuple)) or len(frac_bbox) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in frac_bbox)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
        return None
    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0
    if x0 < 0 or y0 < 0 or x1 > 1 or y1 > 1:
        return None
    try:
        cx0, cy0, cx1, cy1 = (float(v) for v in clip)
        page_w, page_h = float(page_w), float(page_h)
    except (TypeError, ValueError):
        return None
    cw, ch = cx1 - cx0, cy1 - cy0
    if cw <= 0 or ch <= 0 or page_w <= 0 or page_h <= 0:
        return None
    px0 = (cx0 + x0 * cw) / page_w
    py0 = (cy0 + y0 * ch) / page_h
    px1 = (cx0 + x1 * cw) / page_w
    py1 = (cy0 + y1 * ch) / page_h
    area = (px1 - px0) * (py1 - py0)
    if area < 1e-6 or area > 0.6:  # degenerate speck or most-of-the-page box
        return None
    return [round(v, 4) for v in (px0, py0, px1, py1)]


def _locate_json_object(text: str) -> str:
    """Return the JSON-object substring of a response.

    A tile crop with few/no dimensions often gets a prose preamble ("the only
    annotated fact is...") before the JSON object. We strip fences, then slice
    from the first `{` to the last `}` so that leading/trailing prose doesn't
    defeat `json.loads`. Pure prose with no braces is returned unchanged and
    will (correctly) fail to parse.
    """
    stripped = _strip_fences(text)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def _parse_entities(raw_text: str, default_source: str) -> list:
    """Parse one LLM response into a list of normalized entity dicts.

    Shared by the whole-sheet (`extract`) and tiled (`extract_tiled`) paths so
    both apply identical fence-stripping, shape validation, and — critically —
    the EO1 confidence cap (via `_normalize_attribute`) to every fact. Raises
    ValueError on unparseable or wrong-shaped JSON.
    """
    try:
        payload = json.loads(_locate_json_object(raw_text))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(
            f"PDF extraction returned unparseable JSON: {exc}: {str(raw_text)[:300]}"
        )
    if not isinstance(payload, dict) or not isinstance(payload.get("entities"), list):
        raise ValueError(
            "PDF extraction returned unparseable JSON: "
            f"expected object with 'entities' list, got: {str(payload)[:300]}"
        )

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
    return entities


def extract(pdf_path: str, runner=run_claude, progress_cb=None) -> dict:
    """Extract annotated dimensions from a drawing PDF into a facts dict.

    Every returned fact carries confidence <= MAX_LLM_CONFIDENCE (EO1):
    the engine will report `uncertain` for all of them, forcing human review.
    """
    pdf_name = os.path.basename(pdf_path)
    if progress_cb:
        progress_cb("reading the drawing (single pass)", 0, 1)
    raw_text = runner(EXTRACTION_PROMPT, pdf_path)
    if progress_cb:
        progress_cb("normalizing extracted facts", 1, 1)
    entities = _parse_entities(raw_text, f"{pdf_name} (LLM extraction)")

    # Whole-PDF mode has no controlled raster geometry, so bboxes would be
    # unanchored — discard them and keep page-level evidence only (the viewer
    # degrades to opening that page fit-to-view).
    for ent in entities:
        for attr in ent["attributes"].values():
            attr.pop("bbox", None)
            raw_page = attr.pop("page", None)
            if (isinstance(raw_page, (int, float)) and not isinstance(raw_page, bool)
                    and float(raw_page).is_integer() and raw_page >= 1):
                attr["evidence"] = {"doc": pdf_name, "page": int(raw_page)}

    return {
        "project": {
            "name": f"{pdf_name} (drawing extraction)",
            "sources": [pdf_path],
        },
        "entities": entities,
    }


# --------------------------------------------------------------------------
# High-DPI tiled extraction
#
# A whole 1/8"-scale multi-view sheet is too low-resolution for the model to
# read the small dimension annotations. We render the page at ~200 DPI, split
# it into an overlapping NxM grid of crops, run the SAME extraction prompt on
# each crop, and merge the results. The EO1 confidence cap is applied per tile
# (via `_parse_entities`), so no tiling path can ever emit a fact at >= 0.9.
# --------------------------------------------------------------------------

TILE_OVERLAP = 0.12  # 12% overlap so annotations on a tile seam aren't cut


def run_claude_image(prompt: str, image_path: str) -> str:
    """Run the `claude` CLI headless against a PNG tile; return assistant text.

    Mirrors `run_claude` but points the nested CLI at an image crop. The
    `--allowedTools Read` grant is required — without it the headless instance
    is denied file access and returns prose instead of JSON.
    """
    abs_path = os.path.abspath(image_path)
    full_prompt = f"{prompt}\n\nThe image to read is at: {abs_path}"
    proc = subprocess.run(
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


def choose_grid(page_width_pt: float, page_height_pt: float) -> tuple:
    """Pick a tile grid from page size. Large sheets (multi-view plans) get a
    denser 3x3 grid; small detail sheets stay at 2x2."""
    long_edge = max(page_width_pt, page_height_pt)
    # 792 pt = 11 in (Letter long edge). Anything meaningfully larger than a
    # tabloid sheet is a big multi-view plan and benefits from more tiles.
    return (3, 3) if long_edge > 1224 else (2, 2)


def render_page_to_tiles(
    pdf_path: str,
    grid: tuple = (2, 2),
    dpi: int = 200,
    out_dir: str | None = None,
    page_index: int = 0,
    overlap: float = TILE_OVERLAP,
) -> list:
    """Render one PDF page at `dpi` and slice it into an overlapping grid of
    PNG tiles. Returns a list of tile descriptors:
    `{"path", "label", "row", "col", "clip", "page_w", "page_h", "page"}`
    (rows/cols and page are 1-based; clip is [x0,y0,x1,y1] in page points,
    fitz top-left space — the geometry needed to map LLM tile-fraction
    bboxes back to page coordinates).

    Requires PyMuPDF (`import fitz`). Each tile is rendered directly from a clip
    rectangle so it keeps full `dpi` resolution rather than being downscaled.
    """
    import fitz  # PyMuPDF; imported lazily so unit tests need not render.

    cols, rows = grid
    if out_dir is None:
        base_tmp = os.path.join(os.getcwd(), "tmp")
        parent = base_tmp if os.path.isdir(base_tmp) else None
        out_dir = tempfile.mkdtemp(prefix="nbc_tiles_", dir=parent)
    os.makedirs(out_dir, exist_ok=True)

    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        pw, ph = page.rect.width, page.rect.height
        tile_w, tile_h = pw / cols, ph / rows
        ox, oy = tile_w * overlap, tile_h * overlap

        tiles = []
        for r in range(rows):
            for c in range(cols):
                x0 = max(0.0, c * tile_w - ox)
                y0 = max(0.0, r * tile_h - oy)
                x1 = min(pw, (c + 1) * tile_w + ox)
                y1 = min(ph, (r + 1) * tile_h + oy)
                clip = fitz.Rect(x0, y0, x1, y1)
                pix = page.get_pixmap(matrix=mat, clip=clip)
                label = f"r{r + 1}c{c + 1}"
                path = os.path.join(out_dir, f"{stem}_{label}.png")
                pix.save(path)
                tiles.append({
                    "path": path, "label": label, "row": r + 1, "col": c + 1,
                    "clip": [x0, y0, x1, y1], "page_w": pw, "page_h": ph,
                    "page": page_index + 1,
                })
    finally:
        doc.close()
    return tiles


def _tile_prompt(pdf_name: str, tile: dict) -> str:
    """The whole-sheet extraction prompt, plus which crop the model is seeing."""
    return (
        f"{EXTRACTION_PROMPT}\n\n"
        f"This is region row {tile['row']} col {tile['col']} (tile {tile['label']}) "
        f"of sheet {pdf_name}. Extract ONLY dimensions visible in THIS crop; "
        f"ignore anything cut off at the edges of the image.\n"
        f"Each attribute may also include \"bbox\": [x0, y0, x1, y1] — fractions "
        f"0-1 of THIS image, origin at the TOP-LEFT corner, drawn tightly around "
        f"the printed dimension annotation you read the value from. If you cannot "
        f"locate it precisely, omit bbox."
    )


_WS_RE = re.compile(r"\s+")


def _entity_key(entity: dict) -> tuple:
    """Dedupe key: (entity_type, normalized name-or-id). Case/space-insensitive
    so 'Main Stair' and 'main  stair' collapse to one entity across tiles."""
    etype = str(entity.get("entity_type", "unknown")).strip().lower()
    label = str(entity.get("name") or entity.get("id") or "").strip().lower()
    label = _WS_RE.sub(" ", label)
    return (etype, label)


def merge_tile_facts(tile_facts: list) -> dict:
    """Merge per-tile facts dicts into one deduped `{"entities": [...]}`.

    Pure function (no rendering / no CLI) so the merge/dedupe policy is unit
    testable on its own. Policy:
      - dedupe entities by (entity_type, normalized name/id);
      - union attributes across every tile that saw the entity;
      - when the same fact appears in multiple tiles, keep the HIGHEST-
        confidence instance (whole {value,confidence,source} triple);
      - assign stable, deterministic ids in first-seen order.

    Input elements are facts dicts with an "entities" list whose attributes are
    already normalized+capped (produced by `_parse_entities`). This function
    never raises confidence, so any cap applied upstream is preserved.
    """
    merged: dict = {}
    order: list = []
    for tf in tile_facts:
        for ent in (tf or {}).get("entities", []):
            key = _entity_key(ent)
            if key not in merged:
                merged[key] = {
                    "entity_type": str(ent.get("entity_type", "unknown")),
                    "name": ent.get("name"),
                    "id": ent.get("id"),
                    "attributes": {},
                }
                order.append(key)
            attrs = merged[key]["attributes"]
            for fact, value in (ent.get("attributes") or {}).items():
                if not isinstance(value, dict):
                    continue
                incoming = value.get("confidence", 0.0) or 0.0
                current = attrs.get(fact)
                if current is None or incoming > (current.get("confidence", 0.0) or 0.0):
                    attrs[fact] = value

    entities = []
    for i, key in enumerate(order):
        e = merged[key]
        # Assign fresh, deterministic ids in first-seen order. Tile-provided ids
        # can collide or differ for the same entity across crops, so we don't
        # trust them for identity — the (type, name) key already deduped.
        entities.append(
            {
                "entity_type": e["entity_type"],
                "id": f"pdf-entity-{i + 1}",
                "name": str(e["name"] or f"PDF entity {i + 1}"),
                "attributes": e["attributes"],
            }
        )
    return {"entities": entities}


def extract_tiled(
    pdf_path: str,
    runner=run_claude_image,
    grid: tuple = (2, 2),
    dpi: int = 200,
    tiles: list | None = None,
    out_dir: str | None = None,
    page_index: int = 0,
    progress_cb=None,
) -> dict:
    """Tiled extraction: render+slice a page, extract each tile, merge results.

    `tiles` may be supplied directly (list of `{"path","label","row","col"}`)
    to bypass rendering — used by unit tests so no PDF/PyMuPDF is needed there.
    Every fact is capped at MAX_LLM_CONFIDENCE per tile (EO1) before merging,
    and each fact's source records which tile it came from.
    """
    pdf_name = os.path.basename(pdf_path)
    if tiles is None:
        if progress_cb:
            progress_cb("rendering page into tiles", 0, 0)
        tiles = render_page_to_tiles(
            pdf_path, grid=grid, dpi=dpi, out_dir=out_dir, page_index=page_index
        )

    tile_facts = []
    skipped = []
    for i, tile in enumerate(tiles):
        if progress_cb:
            # Progress reporting only — never feeds back into the facts (EO1
            # and determinism: identical inputs yield identical outputs with
            # or without a callback attached).
            progress_cb(f"extracting tile {tile['label']}", i, len(tiles))
        tile_source = f"{pdf_name} tile {tile['label']} (LLM extraction)"
        raw_text = runner(_tile_prompt(pdf_name, tile), tile["path"])
        try:
            entities = _parse_entities(raw_text, tile_source)
        except ValueError:
            # Tiles are independent: a crop the model answers in pure prose
            # (e.g. "no dimensions in this region") must not sink the other
            # tiles. Record it and move on.
            skipped.append(tile["label"])
            continue
        # Stamp tile provenance onto every fact so the winning instance after
        # the merge always says which crop it was read from — and convert the
        # model's tile-fraction bbox (if any) into a page-coordinate evidence
        # object using the tile's deterministic clip geometry.
        clip = tile.get("clip")
        page_no = tile.get("page", 1)
        for ent in entities:
            for attr in ent["attributes"].values():
                attr["source"] = tile_source
                raw_bbox = attr.pop("bbox", None)
                attr.pop("page", None)  # the tile knows its page; ignore model's
                evidence = {"doc": pdf_name, "page": page_no}
                if clip is not None and raw_bbox is not None:
                    page_bbox = tile_bbox_to_page(
                        raw_bbox, clip, tile.get("page_w"), tile.get("page_h"))
                    if page_bbox is not None:
                        evidence["bbox"] = page_bbox
                attr["evidence"] = evidence
        tile_facts.append({"tile": tile["label"], "entities": entities})

    if progress_cb:
        progress_cb("merging extracted facts", len(tiles), len(tiles))
    merged = merge_tile_facts(tile_facts)
    return {
        "project": {
            "name": f"{pdf_name} (tiled drawing extraction)",
            "sources": [pdf_path],
            "tiles": [t["label"] for t in tiles],
            "tiles_unparsed": skipped,
        },
        "entities": merged["entities"],
    }


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if not args:
        print(
            "usage: python3 extractors/pdf_extractor.py [--tiled [CxR]] <drawing.pdf>",
            file=sys.stderr,
        )
        sys.exit(2)
    if args[0] == "--tiled":
        grid = (2, 2)
        rest = args[1:]
        if rest and "x" in rest[0]:
            c, r = rest[0].lower().split("x")
            grid = (int(c), int(r))
            rest = rest[1:]
        print(json.dumps(extract_tiled(rest[0], grid=grid), indent=2))
    else:
        print(json.dumps(extract(args[0]), indent=2))
