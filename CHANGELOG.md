# Changelog

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
