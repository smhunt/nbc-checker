# Phase 2 Execution — Ontario OBC + real-plan hardening

**Goal:** Make the checker usable on the real Ontario permit plan (47 Fisherman's Wharf Rd) it was just tested against: correct jurisdiction (OBC), richer PDF extraction, and renovation (existing-vs-new) modelling. Then re-run that plan end-to-end and document it as a case study.

**Driver:** The uploaded plan is an Ontario change-of-use/renovation. Our NBC 2020 ruleset is the wrong jurisdiction; whole-sheet extraction was sparse; and "existing to remain" work must be excluded from checks.

## Phase 1 (parallel, disjoint file ownership)

- **P1a — Ontario OBC Part 9 ruleset** (`rules/obc2024_part9_core.json`, new). Mirror the NBC ruleset's schema and categories (stairs, handrails, guards, egress, ceilings, doorways, smoke alarms). Values verified against the current Ontario Building Code (O. Reg. 163/24, in force 2025-01-01) — verbatim + sources in `verification_notes`, `verified_against_code_text` only where confirmed. Record every place OBC differs from NBC 2020.
- **P1b — High-DPI tiled PDF extraction** (`extractors/pdf_extractor.py`, `tests/test_pdf_extractor.py`). Render PDF pages to high-DPI images (PyMuPDF), tile into overlapping regions, extract per tile, merge+dedupe facts. Preserve the 0.89 confidence cap and the whole-file path. Backward-compatible.
- **P1c — Renovation scope + jurisdiction** (`engine/checker.py`, `tests/test_checker.py`, `samples/sample_reno_facts.json`). Rules may declare `"scope": "new_work_only"`; the engine skips such a rule for an entity whose `work_status == "existing"`. Entities without `work_status` are in-scope (greenfield default → no regression). Carry `project.jurisdiction`/`code_edition` through to the report.

## Phase 2 (integration, orchestrator)

Re-extract the Fisherman's Wharf PDF with the tiled extractor, run against the OBC ruleset, export PDF+Excel, save under `samples/casestudy/`. Honest write-up of what extracted and what the verdicts mean.

## Phase 3 (docs/finalize, orchestrator)

Feasibility-evidence addendum (real-plan case study), CHANGELOG 0.5.0, UI ChangelogModal entry, README ruleset table, progress.md + prompt_plan.md. Commit + push each phase.

## Invariants (unchanged)

EO1 confidence cap 0.89 on LLM facts; verification discipline for every new rule; determinism; no guessed facts; commit frequently.
