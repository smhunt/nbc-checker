# Extraction Speedups — Master Plan (4 sub-plans, reconciled)

> Four planning agents designed these independently (2026-07-10), each grounded
> in the code and told the others' seams. This document reconciles them into
> one execution order. Sub-plans: (A) parallel tiles, (B) blank-skip + cache,
> (C) API runner + model A/B, (D) progressive streaming.

Combined effect on a 12-page tiled job: ~14 min today → ~3.5 min (parallel x4)
minus blank tiles (~10-30% fewer calls) minus cache hits (repeat runs ~instant),
with results reviewable from the first completed page (streaming) and a
possible further 2-3x from Haiku if the A/B supports it.

## Execution order (waves) and why

1. **Wave 1 — Runner infrastructure (from plan C, tasks 1-3).**
   `extractors/runners.py`: CLI runners move here; `select_runner(kind)`
   factory (API iff ANTHROPIC_API_KEY, NBC_RUNNER=cli|api override, decided
   once per job, fail-loud, never silent fallback); runners carry
   `.identity` ("cli:claude" / "api:<model>"); `extract`/`extract_tiled`
   change to `runner=None` + call-time resolution; `project.extractor`
   provenance. FIRST because both B (cache wrapping) and C depend on the
   runner=None refactor and identity attribute — do it once.
2. **Wave 2 — Blank-tile skip + extraction cache (plan B, all 6 tasks).**
   Resolution becomes `runner or cached(select_runner(kind))`.
3. **Wave 3 — Parallel tiles (plan A, all 5 tasks).**
   Benefits from `make_progress_cb` having moved to jobs.py in wave 2.
4. **Wave 4 — Progressive streaming (plan D, all 5 tasks).**
   Lands on the stabilized page loop; the page barrier survives wave 3
   because parallelism pools WITHIN a page (pages stay serial).
5. **Wave 5 — A/B harness + model decision (plan C, tasks 4-6).**
   BLOCKED ON USER: needs ANTHROPIC_API_KEY on this machine. Ships
   scripts/ab_extract_models.py; DEFAULT_EXTRACT_MODEL flips to
   claude-haiku-4-5-20251001 only if docs/ab-model-results.md supports it.

## Cross-plan seam contracts (binding on implementers)

- **Cache key** = sha256(schema-version + runner identity/cache_id + prompt +
  input-file bytes). The CLI runners append their absolute-path suffix INSIDE
  run_claude/run_claude_image, so the wrapper keys on the pre-suffix prompt by
  construction (verified) — no cross-machine key poisoning. API runner
  identity embeds the model id, so model changes invalidate; the CLI's
  underlying model is unpinned (documented weakness; cache_id version bump is
  the manual lever).
- **Cache stores raw response text, never parsed facts** — parser fixes, cap
  changes and bbox-mapping changes re-apply to cached responses (EO1 hazard
  otherwise). Cache hit/miss stats NEVER enter facts output (would break
  run-to-run identity). reports/extract_cache/, atomic writes, no eviction,
  documented deletable. NBC_EXTRACT_CACHE=0 disables.
- **Blank skip**: a tile is blank only if words==0 AND vector_items==0 AND
  images==0 within its overlap-inclusive clip (threshold zero, no tuning).
  Full-page scan images intersect every tile -> scans never skipped (fail-open
  by construction). Missing content stats -> fail open. Reported in
  project.tiles_skipped [{tile, reason}] — never silent (page_select
  precedent). NBC_BLANK_TILE_SKIP=0 disables.
- **Determinism under parallelism**: futures keyed by tile index, results
  merged in tile-index order regardless of completion order -> parallel output
  == serial output (locked by a reversed-completion-order test).
  NBC_TILE_CONCURRENCY (default 4, 1 == legacy serial incl. exact legacy
  progress strings). progress_cb fired ONLY from the coordinator thread.
- **ETA**: inter-completion gaps ARE throughput -> estimate_eta math unchanged;
  seed divided by Job.workers; durations below _MIN_COUNTED_TILE_S=1.0
  excluded (cache hits, blank skips; note: under W>=4 real completions can
  occasionally cluster <1s — losing samples is acceptable, observational
  only). _cb moves to server/jobs.py::make_progress_cb (kills the
  inspect.getsource test hack).
- **Failure isolation** (wave 3, applies to both serial+parallel): per-tile
  RuntimeError/Timeout degrade to tiles_unparsed entries; all-tiles-failed
  raises ("is the claude CLI available/authenticated?"). Behavior change:
  transient CLI errors no longer kill jobs — CHANGELOG + reviewer-visible.
- **Streaming**: on_partial(pfacts, pages_done, pages_total) fires at the page
  barrier only, publishing the contiguous completed-page prefix in page order;
  partial facts live in Job.partial_facts (separate field -> override/export
  gates on job.facts need zero changes and stay locked until final); partial
  responses carry "partial": true and NO report_sha256; final response
  byte-identical to a non-streaming run (server-level test). Entity ids are
  prefix-stable across partials (verified: first-seen ordering + append-only
  accumulation). UI: banner + readOnly drawer + hidden sha badge; selection
  preserved across partial refreshes.
- **API runner** (wave 1/5): anthropic SDK lazy-imported (CLI-only machines
  unaffected); base64 image blocks (tiles) / document blocks (whole PDF);
  no temperature/thinking params; typed-exception mapping, key never in
  messages/logs. RISK to measure in the A/B: API downscales images to 1568px
  long edge — large-sheet tiles are ~2600px, so API extraction could read
  small dimensions WORSE than the CLI path; harness records tile pixel dims,
  accuracy vs ground truth, latency, cost; optional claude-sonnet-5 arm
  (2576px). Cost scale: full 23-sheet Calgary set ~ $0.40 (Haiku) / $1.20
  (Sonnet 4.6) — latency, not money, is the constraint.
- **Secrets** (wave 5 docs): ANTHROPIC_API_KEY via launchd EnvironmentVariables
  or mode-600 env file sourced by the start script; never CLI args, never
  committed, never logged.

## Task inventory

Wave 1: C1 runners.py+factory+identity | C2 API runner (mocked SDK tests) |
        C3 runner=None resolution + provenance (+EO1 cap regression test)
Wave 2: B1 classify_tile_content + per-tile content stats | B2 skip wiring +
        tiles_skipped metadata | B3 extract_cache.py | B4 cache-as-default +
        replay-identity tests | B5 make_progress_cb + ETA floor | B6 docs
Wave 3: A1 _process_one_tile refactor | A2 failure isolation | A3 pool +
        aggregate progress | A4 Job.workers + seed scaling | A5 docs
Wave 4: D1 on_partial extractor hook | D2 job contract (partial_facts,
        _report_state refactor, get_job branch) | D3 mid-run integration +
        determinism proof | D4 UI (banner, readOnly, sha hidden) | D5 docs
Wave 5: C4 secrets/deployment docs | C5 ab_extract_models.py | C6 measured
        model decision commit (cites docs/ab-model-results.md)

Full task details (signatures, test names, risks) are in the four sub-plan
agent reports, summarized in progress.md session 5e; this file is the
authoritative ORDER and SEAMS document.

## Env var reference (added across waves)

NBC_TILE_CONCURRENCY (4) | NBC_BLANK_TILE_SKIP (1) | NBC_EXTRACT_CACHE (1)
NBC_EXTRACT_CACHE_DIR (reports/extract_cache) | NBC_RUNNER (auto: api iff key)
NBC_EXTRACT_MODEL (claude-sonnet-4-6 until A/B) | ANTHROPIC_API_KEY (unset)
