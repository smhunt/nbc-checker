#!/usr/bin/env python3
"""Manual A/B harness: compare PDF-extraction models on cost, latency, accuracy.

This is a DIAGNOSTIC tool, never wired into pytest/CI (see the module-level
guard note below) and never imported for its side effects — every non-dry-run
invocation makes real, BILLED calls to the Anthropic API via
`extractors.runners.make_api_runner`. Nothing here runs automatically.

Why this exists: `extractors/runners.py::DEFAULT_EXTRACT_MODEL` is pinned to
`claude-sonnet-4-6` until a measured A/B run justifies changing it (see
CLAUDE.md's "PDF extraction: runners, caching, concurrency" section). This
script is that measurement: for each candidate model it re-runs the SAME
tiled extraction over the SAME PDF(s), diffs the resulting facts against a
hand-reviewed "expected" facts file, and records latency/cost/accuracy so the
model choice is evidence, not vibes.

Usage:
    # Cost estimate only, no network calls, no anthropic import beyond
    # module load (make_api_runner itself lazy-imports anthropic and is only
    # CALLED in the non-dry-run branch):
    python3 scripts/ab_extract_models.py --dry-run \\
        --models claude-sonnet-4-6,claude-haiku-4-5-20251001 \\
        --pdf samples/A-201_stair_section.pdf \\
        --expected samples/sample_dwelling_facts.json

    # Real run (needs a valid ANTHROPIC_API_KEY in the environment):
    python3 scripts/ab_extract_models.py \\
        --models claude-sonnet-4-6,claude-haiku-4-5-20251001 \\
        --pdf samples/A-201_stair_section.pdf \\
        --expected samples/sample_dwelling_facts.json \\
        --runs 2 --out docs/ab-model-results.md

Multiple --pdf/--expected pairs may be given; they are paired positionally
(1st --pdf with 1st --expected, and so on) — `argparse` enforces equal counts
before anything else runs.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time

if __package__ in (None, ""):  # executed as a script: repo root isn't on
    _here = os.path.dirname(os.path.abspath(__file__))  # sys.path by default
    sys.path.insert(0, os.path.dirname(_here))

import json  # noqa: E402

from extractors.pdf_extractor import _entity_key  # noqa: E402

# ---------------------------------------------------------------------------
# Pricing table (USD per million tokens, input / output). AS OF 2026-07-10 —
# these are published list prices, not billed usage; check
# https://www.anthropic.com/pricing before using this table for a real
# budget decision, and update the "as of" date whenever it changes.
# Unlisted model ids fall back to DEFAULT_PRICE (conservatively the most
# expensive listed tier) so a typo'd model id still prints a real number
# rather than silently estimating $0.
# ---------------------------------------------------------------------------
PRICING_USD_PER_MTOK = {
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
    "claude-haiku-4-5-20251001": {"in": 1.00, "out": 5.00},
    "claude-opus-4-6": {"in": 15.00, "out": 75.00},
}
DEFAULT_PRICE = {"in": 15.00, "out": 75.00}

# Rough per-tile token estimate used ONLY for the pre-run cost projection
# (never for billing math after real usage is recorded — that uses the
# actual resp.usage counts). A ~2000px tile PNG plus the extraction prompt
# is comfortably under 1600 input tokens on Anthropic's image tokenizer
# (roughly tokens = width_px * height_px / 750); the extraction prompt text
# itself is a few hundred tokens. Output is small (a handful of JSON facts).
EST_INPUT_TOKENS_PER_TILE = 1600
EST_OUTPUT_TOKENS_PER_TILE = 300

DEFAULT_GRID = (2, 2)
DEFAULT_DPI = 200


def price_for(model: str) -> dict:
    return PRICING_USD_PER_MTOK.get(model, DEFAULT_PRICE)


def estimate_cost_usd(model: str, n_tiles: int) -> float:
    """Cost projection from a tile count, using EST_*_TOKENS_PER_TILE and
    the pricing table. Pure arithmetic — no I/O."""
    price = price_for(model)
    in_tok = n_tiles * EST_INPUT_TOKENS_PER_TILE
    out_tok = n_tiles * EST_OUTPUT_TOKENS_PER_TILE
    return (in_tok / 1_000_000) * price["in"] + (out_tok / 1_000_000) * price["out"]


# ---------------------------------------------------------------------------
# Tile-count / pixel-dimension estimation (no LLM calls; PyMuPDF only)
# ---------------------------------------------------------------------------

def estimate_tile_count(pdf_path: str) -> int:
    """Best-effort tile count for a cost estimate, without ever touching an
    LLM. Prefers the real deterministic page selector + adaptive grid logic
    (`extractors.page_select` + `extractors.pdf_extractor.choose_grid`) so
    the estimate matches what `extract_tiled(pages="auto")` would actually
    render; falls back to a flat one-page/default-grid guess if PyMuPDF
    (`fitz`) isn't importable or the file can't be opened — a dry run should
    never hard-fail just because it can't get a precise number.
    """
    try:
        from extractors.page_select import collect_page_stats, select_pages
        from extractors.pdf_extractor import choose_grid

        stats = collect_page_stats(pdf_path)
        selection = select_pages(stats, "auto")
        stat_by_page = {s.page: s for s in stats}
        total = 0
        for p in selection.selected:
            st = stat_by_page[p]
            cols, rows = choose_grid(st.width, st.height)
            total += cols * rows
        return total or DEFAULT_GRID[0] * DEFAULT_GRID[1]
    except Exception:
        return DEFAULT_GRID[0] * DEFAULT_GRID[1]


def estimate_tile_pixel_dims(pdf_path: str, dpi: int = DEFAULT_DPI) -> list[tuple]:
    """Per selected page, the (width_px, height_px) of ONE tile under the
    adaptive grid — grid+dpi math (`page_points / cols * dpi/72`), not an
    actual render. This is the number the A/B risk note in
    docs/superpowers/plans/subplans/C-api-runner.md cares about: the
    Anthropic API downscales images with a long edge over 1568px, and a
    large-sheet 3x3 grid tile can be ~2600px — potentially LOSING legibility
    relative to the CLI path, which is exactly what this harness measures.
    Falls back to `[]` (nothing to report) under the same failure modes as
    `estimate_tile_count`.
    """
    try:
        from extractors.page_select import collect_page_stats, select_pages
        from extractors.pdf_extractor import choose_grid

        stats = collect_page_stats(pdf_path)
        selection = select_pages(stats, "auto")
        stat_by_page = {s.page: s for s in stats}
        zoom = dpi / 72.0
        out = []
        for p in selection.selected:
            st = stat_by_page[p]
            cols, rows = choose_grid(st.width, st.height)
            tile_w_px = round((st.width / cols) * zoom)
            tile_h_px = round((st.height / rows) * zoom)
            out.append((p, cols, rows, tile_w_px, tile_h_px))
        return out
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Ground truth adapter for the one pairing available without a live key.
#
# samples/sample_dwelling_facts.json is a whole-PROJECT facts file that mixes
# entities/attributes from the IFC model and the A-201 PDF drawing in the
# SAME entities (see CLAUDE.md's facts-schema note) — most of it (window and
# door dimensions, per-step riser/tread aggregates, energy-compliance
# values...) is stuff a PDF extraction of samples/A-201_stair_section.pdf
# could never produce, because it was never printed on that sheet. Diffing
# the whole file would report those as spurious "missing" facts and drown
# out the signal we actually want.
#
# samples/generate_sample_drawing.py's module docstring documents the
# drawing's real printed annotations verbatim:
#   RISER 190 mm / TREAD RUN 255 mm / CLEAR WIDTH 910 mm (plan note) /
#   HANDRAIL 920 mm ABOVE NOSING / HEADROOM 2050 mm
# A201_EXPECTED_FACTS mirrors that list exactly, keyed by the same
# (entity_type, normalized name) pair `_entity_key` would produce — this is
# the TRUE ground truth for this specific PDF, independent of how any one
# facts file happens to label its sources.
# ---------------------------------------------------------------------------
A201_EXPECTED_FACTS = {
    ("stair_flight", "main stair, ground to second floor"): {
        "riser_height_mm", "tread_run_mm", "clear_width_mm", "headroom_mm",
    },
    ("handrail", "main stair handrail"): {"height_above_nosing_mm"},
}


def filter_pdf_sourced_facts(expected: dict, allowlist: dict = A201_EXPECTED_FACTS) -> dict:
    """Reduce a whole-project facts file to the subset a PDF extraction of
    samples/A-201_stair_section.pdf could plausibly reproduce (see the
    module comment above `A201_EXPECTED_FACTS`). No-op (returns unchanged
    structure) for any entity/fact not named in `allowlist` — callers pairing
    a different PDF with a different hand-reviewed expected file should pass
    their own `allowlist` (or skip this adapter entirely and hand
    `diff_facts` an already-scoped expected file, e.g. a casestudy
    reviewed-facts document).
    """
    out_entities = []
    for ent in (expected or {}).get("entities", []):
        key = (str(ent.get("entity_type", "")).strip().lower(),
               str(ent.get("name") or "").strip().lower())
        wanted = allowlist.get(key)
        if not wanted:
            continue
        attrs = {k: v for k, v in (ent.get("attributes") or {}).items() if k in wanted}
        if attrs:
            out_entities.append({
                "entity_type": ent.get("entity_type"),
                "id": ent.get("id"),
                "name": ent.get("name"),
                "attributes": attrs,
            })
    return {"entities": out_entities}


# ---------------------------------------------------------------------------
# Pure diff: extracted facts vs. expected facts
# ---------------------------------------------------------------------------

def _raw_value(attr):
    """Facts-schema attribute -> its bare value. An attribute is either a
    plain value (confidence 1.0 implied) or `{"value", "confidence",
    "source"}` (+ optional evidence) — see CLAUDE.md's facts schema note."""
    if isinstance(attr, dict) and "value" in attr:
        return attr["value"]
    return attr


def _is_numeric(value) -> bool:
    # bool is a subtype of int in Python; treat it as non-numeric so
    # True/False compare by equality, not by tolerance-window arithmetic.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _flatten(facts: dict) -> dict:
    """`{"entities": [...]}` -> `{(entity_type, normalized_name, fact): raw_value}`.

    Uses `extractors.pdf_extractor._entity_key` (imported, not reimplemented)
    for the entity part of the key, so an entity seen as 'Window A
    (schedule)' in one extraction and 'Window A' in the ground truth still
    line up — exactly the same normalization the tiled merge itself uses.
    """
    out = {}
    for ent in (facts or {}).get("entities", []):
        etype, name = _entity_key(ent)
        for fact, attr in (ent.get("attributes") or {}).items():
            out[(etype, name, fact)] = _raw_value(attr)
    return out


def diff_facts(extracted: dict, expected: dict, tolerance_mm: float = 1.0) -> dict:
    """Compare one extraction run's facts against a hand-reviewed expected
    set. Pure function: no I/O, no env reads, no network — safe to unit test
    and safe to call from anywhere.

    Matching key: `(entity_type, normalized name, fact key)`, normalized via
    `extractors.pdf_extractor._entity_key` (parenthetical-qualifier-stripped,
    case/space-insensitive — the same rule the tiled merge uses). Numeric
    values are compared within `tolerance_mm` (absolute difference);
    everything else (strings, booleans) needs an exact match.

    Returns counts:
      found        — expected facts that appear (correct or not) in extracted
      matched      — found AND within tolerance / exactly equal
      wrong_value  — found but outside tolerance / not equal
      hallucinated — facts in extracted with no corresponding expected key
      missing      — expected facts absent from extracted entirely
    (`found == matched + wrong_value` by construction.)
    """
    exp = _flatten(expected)
    got = _flatten(extracted)

    matched = 0
    wrong_value = 0
    for key, exp_val in exp.items():
        if key not in got:
            continue
        got_val = got[key]
        if _is_numeric(exp_val) and _is_numeric(got_val):
            ok = abs(float(exp_val) - float(got_val)) <= tolerance_mm
        else:
            ok = exp_val == got_val
        if ok:
            matched += 1
        else:
            wrong_value += 1

    found = matched + wrong_value
    missing = len(exp) - found
    hallucinated = sum(1 for k in got if k not in exp)

    return {
        "found": found,
        "matched": matched,
        "wrong_value": wrong_value,
        "hallucinated": hallucinated,
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# Real run (network calls — never exercised by --dry-run or by any test)
# ---------------------------------------------------------------------------

def _usage_recorder():
    """Returns (usage_cb, totals) — `usage_cb` is passed to
    `make_api_runner(..., usage_cb=...)` and accumulates input/output token
    counts across every call the runner makes; `totals` is the live dict the
    caller reads after the run. `resp.usage` fields are read defensively
    (`getattr`) since the exact attribute names can vary across SDK/model
    versions and this is a diagnostic, not the product's confidence path."""
    totals = {"input_tokens": 0, "output_tokens": 0, "calls": 0}

    def usage_cb(usage):
        totals["calls"] += 1
        if usage is None:
            return
        totals["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
        totals["output_tokens"] += getattr(usage, "output_tokens", 0) or 0

    return usage_cb, totals


def run_one(model: str, pdf_path: str, expected: dict,
           tolerance_mm: float = 1.0) -> dict:
    """One (model, pdf) extraction run: real API calls happen here and only
    here. Returns a result dict with wall-clock, token usage, projected cost
    from ACTUAL usage (not the pre-run estimate), tile pixel dims, and the
    `diff_facts` scoring. `workers=1` (serial) is deliberate — this is a
    diagnostic that wants clean per-call timing, not the product's
    parallel-throughput path. The `--max-tiles` safety cap is enforced by the
    caller BEFORE this is invoked (a whole pdf/model pair is skipped rather
    than partially run), so no cap is threaded through to `extract_tiled`
    here — `pages="auto"` (the default) picks whatever the deterministic
    page classifier would pick in production.
    """
    from extractors.pdf_extractor import extract_tiled
    from extractors.runners import make_api_runner

    usage_cb, totals = _usage_recorder()
    runner = make_api_runner("image", model=model, usage_cb=usage_cb)

    tile_dims = estimate_tile_pixel_dims(pdf_path)
    started = time.monotonic()
    facts = extract_tiled(pdf_path, runner=runner, workers=1)
    wall_s = time.monotonic() - started

    price = price_for(model)
    actual_cost = ((totals["input_tokens"] / 1_000_000) * price["in"]
                   + (totals["output_tokens"] / 1_000_000) * price["out"])

    return {
        "model": model,
        "pdf": os.path.basename(pdf_path),
        "wall_s": wall_s,
        "tile_dims": tile_dims,
        "usage": dict(totals),
        "cost_usd": actual_cost,
        "diff": diff_facts(facts, expected, tolerance_mm=tolerance_mm),
        "facts": facts,
    }


# ---------------------------------------------------------------------------
# Results table (docs/ab-model-results.md)
# ---------------------------------------------------------------------------

RESULTS_TABLE_HEADER = (
    "| Model | PDF | Run | Wall (s) | In tok | Out tok | Cost ($) | "
    "Found | Matched | Wrong | Hallucinated | Missing |\n"
    "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
)


def format_result_row(result: dict, run_idx: int) -> str:
    d = result["diff"]
    u = result["usage"]
    return (
        f"| {result['model']} | {result['pdf']} | {run_idx} | "
        f"{result['wall_s']:.1f} | {u['input_tokens']} | {u['output_tokens']} | "
        f"{result['cost_usd']:.4f} | {d['found']} | {d['matched']} | "
        f"{d['wrong_value']} | {d['hallucinated']} | {d['missing']} |"
    )


def append_results(out_path: str, results: list) -> None:
    """Append a results table for this invocation to `out_path`. Creates the
    file with the standard header if it doesn't already exist. Never
    overwrites prior runs — A/B history accumulates."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"\n## Run recorded {stamp}\n", RESULTS_TABLE_HEADER]
    for r in results:
        lines.append(format_result_row(r, run_idx=r.get("run_idx", 1)))
    lines.append("")
    block = "\n".join(lines)

    if not os.path.exists(out_path):
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("# A/B model results\n" + block)
    else:
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(block)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="A/B PDF-extraction models on cost, latency, and accuracy "
                    "against a hand-reviewed expected facts file.",
    )
    p.add_argument("--models", required=True,
                   help="Comma-separated Anthropic model ids, e.g. "
                        "claude-sonnet-4-6,claude-haiku-4-5-20251001")
    p.add_argument("--pdf", action="append", required=True,
                   help="Path to a drawing PDF. Repeatable; paired positionally "
                        "with --expected.")
    p.add_argument("--expected", action="append", required=True,
                   help="Path to a facts-schema JSON with known-correct values "
                        "for the paired --pdf. Repeatable.")
    p.add_argument("--runs", type=int, default=1,
                   help="Repetitions per (model, pdf) pair (default 1).")
    p.add_argument("--out", default="docs/ab-model-results.md",
                   help="Results markdown file to append to (default "
                        "docs/ab-model-results.md).")
    p.add_argument("--max-tiles", type=int, default=None,
                   help="Safety cap: max pages passed through to extract_tiled's "
                        "max_pages (bounds both the tile count and the spend). "
                        "Also caps the pre-run cost estimate.")
    p.add_argument("--tolerance-mm", type=float, default=1.0,
                   help="Numeric comparison tolerance for diff_facts (default 1.0).")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the projected tile count and cost, then exit "
                        "without calling anything (no network, no anthropic "
                        "SDK use).")
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)

    if len(args.pdf) != len(args.expected):
        print(f"error: {len(args.pdf)} --pdf but {len(args.expected)} --expected "
              "(must be paired 1:1)", file=sys.stderr)
        return 2

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        print("error: --models produced no model ids", file=sys.stderr)
        return 2

    # ---- cost projection (no network calls) ------------------------------
    print("Projected tile counts and cost (pre-run estimate; --dry-run stops here):")
    plan = []  # (model, pdf, expected_path, n_tiles)
    total_projected = 0.0
    skipped_over_cap = []
    for pdf_path, expected_path in zip(args.pdf, args.expected):
        n_tiles = estimate_tile_count(pdf_path)
        over_cap = args.max_tiles is not None and n_tiles > args.max_tiles
        for model in models:
            cost = estimate_cost_usd(model, n_tiles) * args.runs
            tag = "  [SKIPPED: exceeds --max-tiles]" if over_cap else ""
            print(f"  {model:32s} {os.path.basename(pdf_path):30s} "
                  f"~{n_tiles} tiles x {args.runs} run(s)  ~${cost:.4f}{tag}")
            if over_cap:
                skipped_over_cap.append((model, pdf_path))
                continue
            total_projected += cost
            plan.append((model, pdf_path, expected_path, n_tiles))
    print(f"Total projected cost: ~${total_projected:.4f} "
          f"({len(plan)} of {len(models) * len(args.pdf)} model/pdf pair(s), "
          f"{args.runs} run(s) each)")
    if skipped_over_cap:
        print(f"{len(skipped_over_cap)} pair(s) skipped: projected tile count "
              f"exceeds --max-tiles={args.max_tiles}", file=sys.stderr)

    if args.dry_run:
        return 0

    if not plan:
        print("error: nothing left to run after --max-tiles filtering", file=sys.stderr)
        return 1

    # ---- real run (network calls from here down) --------------------------
    all_results = []
    for model, pdf_path, expected_path, n_tiles in plan:
        raw_expected = _load_json(expected_path)
        expected = filter_pdf_sourced_facts(raw_expected)
        for run_idx in range(1, args.runs + 1):
            print(f"[{model}] {os.path.basename(pdf_path)} run {run_idx}/{args.runs} ...",
                  file=sys.stderr)
            result = run_one(model, pdf_path, expected,
                             tolerance_mm=args.tolerance_mm)
            result["run_idx"] = run_idx
            all_results.append(result)
            print(f"    wall={result['wall_s']:.1f}s cost=${result['cost_usd']:.4f} "
                  f"diff={result['diff']}", file=sys.stderr)

    append_results(args.out, all_results)
    print(f"Results appended to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
