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

### PDF extraction: runners, caching, concurrency

Env vars that shape the PDF extraction path (`extractors/runners.py`, `extractors/pdf_extractor.py`, `extractors/extract_cache.py`):

| Variable                | Default                        | Meaning |
|--------------------------|--------------------------------|---------|
| `ANTHROPIC_API_KEY`      | unset                          | Presence alone flips the default runner from CLI to API (`select_runner`, `extractors/runners.py`) — no other config needed. |
| `NBC_RUNNER`             | auto (`api` iff key set, else `cli`) | Explicit override: `cli` forces the `claude` CLI even with a key present; `api` forces the direct Anthropic API and **fails loud** (`RuntimeError`) if no key is set — there is no silent downgrade. Invalid values raise `ValueError`. Decided ONCE per extraction job. |
| `NBC_EXTRACT_MODEL`      | `claude-sonnet-4-6`             | Model id the API runner calls (`get_extract_model()`). Only used when the API runner is selected — irrelevant to the CLI path. **Read `docs/ab-model-results.md` before changing this** — it's a template until `scripts/ab_extract_models.py` records a real A/B run; the default stays Sonnet until that doc shows Haiku (or another candidate) is accuracy-equivalent. |
| `NBC_TILE_CONCURRENCY`   | `4`                             | Thread-pool size for per-page tile extraction (`tile_concurrency()`). `1` reproduces the exact legacy serial path (progress strings included). Contention risk under the CLI runner (shared `~/.claude` subscription) — drop to `1` if that's observed; the API runner has no such shared-process constraint. |
| `NBC_EXTRACT_CACHE`      | `1` (on)                        | `0` disables the raw-response cache entirely (passthrough, no reads/writes). Cache key includes runner identity (`cli:claude` / `api:<model>`), so switching `NBC_RUNNER` or `NBC_EXTRACT_MODEL` naturally misses instead of replaying a different model's answer under the wrong label. |
| `NBC_EXTRACT_CACHE_DIR`  | `reports/extract_cache`         | Cache directory override. Flat files, no index, no eviction — always safe to delete. |
| `NBC_BLANK_TILE_SKIP`    | `1` (on)                        | `0` disables the pre-LLM blank-tile skip (`classify_tile_content`) — every tile is sent to the model even if it has zero words/vectors/images in its clip. Scans are never skipped regardless of this flag (a full-page image intersects every tile). |

**Cache-key coherence**: because the cache key is `sha256(schema-version + runner identity + prompt + input-file bytes)`, changing `NBC_RUNNER` (cli↔api) or `NBC_EXTRACT_MODEL` changes the runner identity string and therefore always produces a fresh cache key — an A/B run comparing two models never accidentally replays a cached response from the other model. The CLI runner's underlying model is unpinned by Anthropic (`cli:claude` doesn't encode which model answered), which is a documented weakness with no automatic lever; a runner's `.cache_id` is the manual bump path if that ever needs forcing.

#### Secrets delivery for a launchd/nohup-run server

The review server (`uvicorn server.app:app --port 3099`) is typically started outside an interactive shell (nohup, a launch script, or launchd), so `ANTHROPIC_API_KEY` can't rely on being in the invoking shell's exported environment. Two supported patterns — **never** put a real key in any file committed to this repo, in a CLI argument (visible in `ps`), or in a log line:

1. **Mode-600 env file, sourced before start** (this machine's pattern — the file already exists at `~/.config/nbc-checker/env`, outside the repo):
   ```bash
   set -a; . ~/.config/nbc-checker/env; set +a
   python3 -m uvicorn server.app:app --port 3099
   ```
   `set -a` exports every variable the sourced file defines (so uvicorn's subprocess/thread pool inherits `ANTHROPIC_API_KEY`) without needing `export` lines inside the file itself; `set +a` immediately turns that back off so it doesn't leak into unrelated variables set afterward in the same shell. Keep the file at `chmod 600`.

2. **launchd `EnvironmentVariables`** (for a `launchctl`-managed service): set the key directly in the job's `.plist` under `<key>EnvironmentVariables</key>` rather than sourcing a file from a `ProgramArguments` wrapper script. launchd never execs through a login shell, so anything relying on `.zshrc`/`.bash_profile` silently won't apply — `EnvironmentVariables` is the only reliable injection point for a launchd job.

Either way, the process only ever needs `ANTHROPIC_API_KEY` in its own environment at startup — `select_runner` reads `os.environ` once per job, so a key rotated on disk requires a process restart to take effect (no hot-reload).

## Non-negotiable invariants

- **No generative model ever participates in pass/fail judgment** (challenge EO1). LLMs only produce facts, and LLM-extracted facts must NEVER carry confidence 1.0 — the sub-0.9 confidence forces the engine to route them to human review.
- **Don't guess derived facts.** If a value depends on information the extractor doesn't have (e.g. window unobstructed open area depends on operation type), leave the fact absent so the engine reports `info_not_available` rather than deriving a plausible number.
- **`verified_against_code_text` stays `false`** until the rule's values are actually checked against the published NBC 2020 text (task V1 — currently ALL rules are unverified). Never flip it as a side effect of other edits.
- Determinism is the product's core claim: identical inputs must produce identical reports.
