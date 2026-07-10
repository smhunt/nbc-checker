# Changelog

## [Unreleased]
### Added
- Verbose processing progress: stage-by-stage messages, tile counters, elapsed time and a live ETA (measured per-tile timing) during PDF analysis
- Resizable review drawer (drag the left edge; width persists; double-click to reset)
- Larger evidence locator: 4:3 viewer plus an Expand overlay (85% of the screen, 200 dpi)
- NBC 2020 **Part 3 ruleset** (`rules/nbc2020_part3_core.json`) — first Part 3 categories per Challenge Notice EO2: fire separations, closures, corridor separations, self-closing devices, occupant load, occupancy classification; all verified verbatim against the official NRC text
- Engine `in`/`not_in` operators (set-membership requirements, e.g. valid major-occupancy groups)
- Ruleset schema + verification-contract test suite across all rulesets
- **PDF evidence drill-down:** facts may carry an optional `evidence` `{doc, page, bbox}` region (normalized top-left coords); the engine passes it through the audit trail untouched; tiled extraction converts LLM tile-fraction bboxes to page coordinates deterministically; page-image endpoints (traversal-hardened, cached); the detail drawer's "view" buttons zoom the source sheet to the exact annotation with highlights; human overrides preserve the evidence link
### Changed
- `facts_used` entries now include an `evidence` key (null when absent). Reports produced from identical inputs remain byte-identical, but `report_sha256` differs from pre-0.7 builds for the same facts file because the report schema gained a field.
### Fixed
- Engine status dominance: a violated requirement can no longer be masked to `info_not_available` by a later missing fact in the same rule (FAIL > INFO_NOT_AVAILABLE > UNCERTAIN > PASS)

## [0.6.0] - 2026-07-07
### Added
- **Upload your own PDF plan in the review UI** — pick a file, choose the code (NBC 2020 or Ontario OBC 2024) and extraction mode (Fast one-pass / Thorough tiled), and see the compliance report in the browser
- Backend upload pipeline: `POST /api/upload` runs extraction on a background thread; `GET /api/jobs/{id}` polls for the report; per-job override + PDF/Excel export endpoints
- Uploaded results support the same confirm/correct human-review loop and deterministic re-run as the sample project

## [0.5.0] - 2026-07-07
### Added
- Ontario OBC 2024 ruleset variant (`rules/obc2024_part9_core.json`, 23 rules) — correct jurisdiction for Ontario projects; documents every OBC-vs-NBC difference per rule
- High-DPI tiled PDF extraction (`extract_tiled`) — ~6× more facts from real multi-view permit sheets, EO1 confidence cap preserved per tile
- Renovation scoping: rules may declare `scope: new_work_only`; the engine skips existing-to-remain elements (`work_status: existing`)
- Report now surfaces `jurisdiction` from the project
- Case study on a real Ontario permit drawing (`docs/casestudy-real-permit.md`)
### Fixed
- PDF extractor grants the headless CLI read access (`--allowedTools Read`) so the `--pdf` path works on real uploads

## [0.4.0] - 2026-07-07
### Added
- Human-review web UI (Vite + React + TS): results table, summary filter chips, detail drawer with NBC code quotes, override workflow
- FastAPI review service (`server/`): `/api/state`, `/api/override`, override persistence in `reports/overrides.json`
- Deterministic re-run on every override — report SHA-256 badge proves identical inputs give identical reports (EO4)
- Server test suite (`tests/test_server.py`): override round-trip flips UNCERTAIN → PASS and back

## [0.3.0] - 2026-07-07
### Added
- T1-T3 pipeline: expanded NBC 2020 Part 9 ruleset, IFC extractor hardening
- Engine support for fact-to-fact comparisons (`value_fact` + `offset`)
- Pytest regression suite locking the four-status engine contract
### Fixed
- FAIL now truly dominates other statuses within a check

## [0.2.0] - 2026-07-07
### Added
- V1 verification: every rule checked against the published NBC 2020 text
- `verification_notes` with verbatim code quotes, sources, and reviewer trail on every rule

## [0.1.0] - 2026-07-07
### Added
- Deterministic rule engine (`engine/checker.py`) with four-status output: pass / fail / info_not_available / uncertain
- Machine-readable NBC 2020 Part 9 core ruleset (RASE-inspired schema)
- IfcOpenShell-based extractor and sample dwelling facts document
