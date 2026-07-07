# Progress Log

## 2026-07-07 — Session 1 (claude.ai, scaffold)
- Confirmed IfcOpenShell 0.8.5 installs and runs (pip, Ubuntu 24)
- Built rule schema (RASE-inspired JSON) with 10 NBC 2020 Part 9 rules — ALL UNVERIFIED (task V1)
- Built deterministic engine: 4-status output, confidence gating (0.9), exceptions, full audit trail
- Built IFC extractor (IfcStairFlight, IfcSpace, IfcWindow) with unit normalization to mm
- Smoke-tested end-to-end: generated IFC4 model -> extractor -> engine -> report. Caught and
  fixed unit bug (ifcopenshell assign_unit defaults to mm; extractor conversion was correct)
- Sample dwelling facts exercise all four statuses incl. low-confidence PDF-extracted fact -> REVIEW
- Deliberate design choice: window unobstructed open area NOT derived from overall dims
  (depends on operation type) — engine reports INFO_NOT_AVAILABLE instead of guessing

## Next session
- Start with V1 (verify rule values against published NBC 2020) — blocking
- Then T2 (real IFC models)
