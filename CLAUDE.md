# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Prototype for deterministic AI-assisted compliance checking of building permit applications against NBC 2020 Part 9 (NRC ISC Phase 2 challenge, proposal closes Aug 4 2026). Python, no package manager config — dependencies: `ifcopenshell`, `anthropic` (`pip install ifcopenshell anthropic --break-system-packages`). The PDF extraction path prefers the direct Anthropic API (`extractors/runners.py`) when `ANTHROPIC_API_KEY` is set, else falls back to the `claude` CLI in headless mode — either way, extraction never needs a package manager beyond `pip`.

`prompt_plan.md` holds the sprint plan and task list (V1–T7); `progress.md` is the per-session log — append a session entry when work is done.

## Commands

Run from the repo root (`run_check.py` relies on `sys.path.insert(0, ".")` and writes to `reports/`):

```bash
# Check facts JSON against the ruleset (human-readable report + reports/last_report.json)
python3 run_check.py rules/nbc2020_part9_core.json samples/sample_dwelling_facts.json

# Extract facts from an IFC model and check them
python3 run_check.py rules/nbc2020_part9_core.json --ifc samples/smoke_test.ifc

# Check an Ontario project against the OBC 2024 ruleset (correct jurisdiction for ON)
python3 run_check.py rules/obc2024_part9_core.json samples/casestudy/ontario_permit_facts.json

# Extract facts from a PDF drawing (LLM path; --export-pdf/--export-xlsx also available)
python3 run_check.py rules/nbc2020_part9_core.json --pdf samples/A-201_stair_section.pdf

# Regenerate the smoke-test IFC model
python3 samples/generate_sample_ifc.py

# Engine directly (raw JSON report to stdout)
python3 engine/checker.py rules/nbc2020_part9_core.json samples/sample_dwelling_facts.json
```

There is no test suite, linter, or build. The two commands above against both sample inputs ARE the regression suite — any engine change requires re-running both and eyeballing the four statuses.

## Architecture

Two-stage neuro-symbolic pipeline; the stages communicate only through a facts JSON document:

```
IFC model ──→ extractors/ifc_extractor.py (deterministic, confidence=1.0) ─┐
                                                                           ├─→ facts ─→ engine/checker.py ─→ report
PDF drawings ─→ LLM extractor (planned, confidence < 1.0) ─────────────────┘
```

- **`rules/nbc2020_part9_core.json`** — machine-readable NBC rules, RASE-inspired schema: `applies_to` (entity_type + `where` conditions), `requires.all` (fact/op/value comparisons), `exceptions`. Every rule cites its NBC provision and carries `verified_against_code_text`.
- **`engine/checker.py`** — pure function of (ruleset, facts). Four statuses per check: `pass`, `fail`, `info_not_available` (required fact absent), `uncertain` (fact confidence < `CONFIDENCE_THRESHOLD` = 0.9, or applicability undeterminable). FAIL dominates other statuses within a check. Full audit trail (facts used, comparisons, sources) in every result.
- **`extractors/ifc_extractor.py`** — IfcOpenShell-based; handles IfcStairFlight, IfcSpace, IfcWindow with property-set fallbacks. Normalizes all lengths to mm via `calculate_unit_scale`.

### Facts schema

`{"project": {...}, "entities": [{"entity_type", "id", "name", "attributes": {...}}]}`. An attribute is either a plain value (treated as confidence 1.0) or `{"value", "confidence", "source"}` plus an optional `"evidence"` object `{"doc", "page", "bbox"?}` — `doc` is a basename only, `page` is 1-based, `bbox` is `[x0,y0,x1,y1]` normalized 0–1 with **top-left origin, y down** (fitz/raster space, not PDF user space). Evidence is machine-usable provenance for the UI drill-down; the engine passes it through to `facts_used` untouched and it never influences pass/fail. All lengths in mm. Source strings remain the human-readable provenance (`model.ifc#<GlobalId>` or PDF sheet + region). Tiled multi-page extraction adds `project.pages` (`{total, processed, skipped[{page,label,reason}], selection}`): page selection is a deterministic classifier (`extractors/page_select.py`, `pages=auto|all|1,3-5`), skips require strong checklist evidence, scans fail open, and every skip is reported — never silently drop a page. `project.tiles` is the tile labels actually sent to the LLM; `project.tiles_skipped` (`[{tile, reason}]`, always present, `[]` when none) lists tiles skipped as blank crops before ever reaching the model — a tile is blank only when words, vector items, and images are ALL zero within its overlap-inclusive clip (`extractors/pdf_extractor.py::classify_tile_content`; `NBC_BLANK_TILE_SKIP=0` disables). `project.tiles_unparsed` remains the separate list of tiles the model answered but that failed to parse.

Extraction responses are cached by (schema version, runner identity, prompt, input-file bytes) in `reports/extract_cache/` (`NBC_EXTRACT_CACHE_DIR` override; `NBC_EXTRACT_CACHE=0` disables) — raw response text only, never parsed facts, so parser/cap/bbox-mapping fixes still re-apply on a cache replay. The directory has no index or eviction policy and is always safe to delete. See `extractors/extract_cache.py`.

Tiled extraction runs each page's tiles through a `ThreadPoolExecutor` (`extractors/pdf_extractor.py::_extract_tiles`, `NBC_TILE_CONCURRENCY` env, default 4, clamped >= 1) — `NBC_TILE_CONCURRENCY=1` reproduces the exact pre-parallel serial behavior byte-for-byte, including progress strings. Futures are keyed by tile index and merged back in index order regardless of completion order, so parallel output is identical to serial output (determinism by construction — locked by `tests/test_pdf_extractor.py::test_parallel_output_identical_to_serial`, which deliberately reverses completion order). Per-tile CLI/API failures (`RuntimeError`, `subprocess.TimeoutExpired`) no longer kill the job — they degrade to a `project.tiles_unparsed` entry, same bucket as a prose-only response; only if EVERY tile in one call hard-fails (zero parsed, zero prose-only skips, at least one hard failure) does `_extract_tiles` raise `RuntimeError` ("all N tile(s) failed — is the claude CLI available/authenticated?"). Progress callbacks are fired ONLY from the coordinating thread/loop — never from a worker — and for `workers>1` use an aggregate format (`"extracting tiles (N/total done, M in flight)"`) rather than one message per tile; `Job.workers` (`server/jobs.py`) records the concurrency actually used so `eta_s()` can divide its pre-first-measurement seed by it (once real inter-completion durations are measured, `estimate_eta`'s math is unchanged — durations already reflect W-way throughput). Running several `claude` CLI subprocesses concurrently can contend on `~/.claude` under a shared subscription; set `NBC_TILE_CONCURRENCY=1` if that's observed.

## Non-negotiable invariants

- **No generative model ever participates in pass/fail judgment** (challenge EO1). LLMs only produce facts, and LLM-extracted facts must NEVER carry confidence 1.0 — the sub-0.9 confidence forces the engine to route them to human review.
- **Don't guess derived facts.** If a value depends on information the extractor doesn't have (e.g. window unobstructed open area depends on operation type), leave the fact absent so the engine reports `info_not_available` rather than deriving a plausible number.
- **`verified_against_code_text` stays `false`** until the rule's values are actually checked against the published NBC 2020 text (task V1 — currently ALL rules are unverified). Never flip it as a side effect of other edits.
- Determinism is the product's core claim: identical inputs must produce identical reports.
