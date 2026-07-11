# Changelog

## [Unreleased]
### Added
- Documented the PDF extraction runner/model/cache env vars (`NBC_RUNNER`, `NBC_EXTRACT_MODEL`, `NBC_TILE_CONCURRENCY`, `NBC_EXTRACT_CACHE`, `NBC_EXTRACT_CACHE_DIR`, `NBC_BLANK_TILE_SKIP`) and the secrets-delivery pattern for a launchd/nohup-run server in CLAUDE.md — no behavior change: `DEFAULT_EXTRACT_MODEL` only matters once a valid `ANTHROPIC_API_KEY` selects the API runner, which this machine doesn't currently have (the provisioned key 401s)
- `scripts/ab_extract_models.py` — manual A/B harness comparing extraction models on cost/latency/accuracy against a hand-reviewed facts file (`diff_facts`, unit-tested in `tests/test_ab_diff.py`); never wired into pytest/CI, makes no network calls except when actually invoked without `--dry-run`. `docs/ab-model-results.md` ships as a template — no run has happened yet
- **Progressive result streaming**: tiled extraction now publishes a report preview after every completed page (`extract_tiled(on_partial=...)`, page-barrier granularity — the outer page loop stays serial even under wave-3's within-page tile parallelism), so a review of a large multi-page plan can start before the whole job finishes. `GET /api/jobs/{id}` serves it mid-run as `{"partial": true, "partial_pages": {"done", "total"}, report, facts, rules}` — deliberately with NO `report_sha256` (a partial value can still change once a later page reads the same fact at higher confidence) and empty `overrides` (overrides/export stay 404-gated on `job.facts`, which is unset until the job is fully done, so the review-changing surface locks automatically for the whole streaming window). The UI shows a "partial results" banner, hides the determinism-sha badge while streaming, and the detail drawer swaps the override form for an explanatory note on a partial report. The final response is unchanged (no `partial` key) — byte-identical to a job that never streamed
- **Parallel tile extraction**: tiled mode now runs each page's tiles through a thread pool (`NBC_TILE_CONCURRENCY`, default 4; `=1` reproduces the exact previous serial behaviour byte-for-byte, including progress strings) instead of one LLM call at a time — a 3x3-grid page that used to take ~9 sequential calls now completes in roughly a quarter of the wall time at the default concurrency. Futures are keyed by tile index and merged back in index order regardless of completion order, so output is identical to the old serial path; `Job.workers` scales the upload progress ETA's pre-first-measurement seed accordingly
- **Blank-tile skip**: before an extraction tile ever reaches the LLM, a deterministic zero-threshold content check (words/vector items/images intersecting the tile's overlap-inclusive clip, computed once per page) skips tiles with no content at all — never a scan (a full-page image intersects every clip, so scanned sheets are structurally never skipped) and never a tile whose only content is in the 12% overlap seam. Every skip is reported in `project.tiles_skipped`; `NBC_BLANK_TILE_SKIP=0` disables. `project.tiles` now means the labels actually sent to the LLM (blank-skipped tiles excluded); `project.tiles_unparsed` is unchanged (tiles the model answered but that failed to parse)
- **Extraction response cache**: identical (runner identity, prompt, input-file bytes) calls replay the model's raw response from `reports/extract_cache/` instead of re-running the LLM — repeat runs over the same drawing are near-instant. Caches raw text only, never parsed facts, so parser/EO1-cap/bbox-mapping fixes still apply on replay; fails open on a disabled flag (`NBC_EXTRACT_CACHE=0`), an unreadable input, or a corrupt entry; a runner exception is never cached; no eviction, directory always safe to delete (`NBC_EXTRACT_CACHE_DIR` override)
- **Multi-page PDF extraction**: tiled mode processes all drawing pages (deterministic page classifier skips checklist/cover pages with per-page reasons in `project.pages`; scans fail open; `pages=auto|all|1,3-5` on upload and CLI), adaptive per-page tile grid (letter 2x2 / large sheets 3x3), cross-page entity merge keeping each fact's own page evidence, cumulative "page 2/4" progress with continuous ETA
- Verbose processing progress: stage-by-stage messages, tile counters, elapsed time and a live ETA (measured per-tile timing) during PDF analysis
- Resizable review drawer (drag the left edge; width persists; double-click to reset)
- Larger evidence locator: 4:3 viewer plus an Expand overlay (85% of the screen, 200 dpi)
- NBC 2020 **Part 3 ruleset** (`rules/nbc2020_part3_core.json`) — first Part 3 categories per Challenge Notice EO2: fire separations, closures, corridor separations, self-closing devices, occupant load, occupancy classification; all verified verbatim against the official NRC text
- Engine `in`/`not_in` operators (set-membership requirements, e.g. valid major-occupancy groups)
- Ruleset schema + verification-contract test suite across all rulesets
- **PDF evidence drill-down:** facts may carry an optional `evidence` `{doc, page, bbox}` region (normalized top-left coords); the engine passes it through the audit trail untouched; tiled extraction converts LLM tile-fraction bboxes to page coordinates deterministically; page-image endpoints (traversal-hardened, cached); the detail drawer's "view" buttons zoom the source sheet to the exact annotation with highlights; human overrides preserve the evidence link
### Changed
- `facts_used` entries now include an `evidence` key (null when absent). Reports produced from identical inputs remain byte-identical, but `report_sha256` differs from pre-0.7 builds for the same facts file because the report schema gained a field.
- Upload progress ETA excludes sub-1-second tile intervals (cache hits, blank-tile skips) from the measured per-tile average so it doesn't skew optimistic; the progress callback moved from `server/app.py` into `server/jobs.py::make_progress_cb` (directly unit-testable)
- **Behavior change:** a per-tile CLI/API error (transient failure, timeout) no longer fails the whole extraction job — it now degrades to a `project.tiles_unparsed` entry, same as a tile the model answered in pure prose. Only a page where *every* tile hard-fails (and none parsed or came back prose-only) raises. `python3 extractors/pdf_extractor.py --tiled` stderr progress output changes shape at `NBC_TILE_CONCURRENCY>1` (default): per-tile `"extracting tile <label>"` lines become aggregate `"extracting tiles (N/total done, M in flight)"` lines; `NBC_TILE_CONCURRENCY=1` keeps the old per-tile lines
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
