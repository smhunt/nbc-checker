# Sub-plan A: Parallel tile extraction (wave 3)

Recommendation: ThreadPoolExecutor, futures keyed by tile index, per-page pool
barrier, env NBC_TILE_CONCURRENCY default 4 (1 == exact legacy serial).
Threads not asyncio: runner contract is sync `(prompt, path) -> str` (all test
fakes are sync lambdas); subprocess.run releases the GIL.

## Design
1. Refactor loop body of `_extract_tiles` into
   `_process_one_tile(pdf_name, tile, runner) -> tuple`:
   ("ok", {"tile": label, "entities": [...]}) | ("unparsed", label) |
   ("failed", label). Contains _tile_prompt, runner call, _parse_entities,
   provenance/evidence stamping. Catches ValueError (as today) PLUS
   RuntimeError and subprocess.TimeoutExpired (failure isolation). Never
   raises per-tile; never touches shared state. label = p{page}:{label} when
   tile has "page" else label.
2. `tile_concurrency()`: NBC_TILE_CONCURRENCY env, default
   DEFAULT_TILE_CONCURRENCY=4, clamped >=1.
   `_extract_tiles(..., workers=1)`; `extract_tiled(..., workers=None)` ->
   tile_concurrency().
   workers<=1 or len(tiles)<=1: existing serial loop byte-identical, legacy
   progress strings exact. Else: submit all to pool
   (max_workers=min(workers, len(tiles))), futures={submit: index}; collect
   via as_completed into results[index]; THEN iterate range(len(tiles)) in
   index order appending to tile_facts/skipped -> merge order identical to
   serial (determinism by construction). Pages remain a serial outer loop
   (pool per page — required by streaming's page barrier).
3. Progress (workers>1): one event at batch submit
   "{prefix}extracting tiles (0/{grand_total} done, {n} in flight)" with
   done=done_offset; one per completion
   "{prefix}extracting tiles ({done_offset+completed}/{grand_total} done,
   {in_flight} in flight)" with done=done_offset+completed. progress_cb
   invoked ONLY from the coordinating thread (as_completed loop) — document
   invariant. "extracting tile" stays a substring of the new format so the
   server duration guard still fires. The two serial-string tests
   (test_tiled_progress_callback_ordering, test_multipage_progress_event_ordering)
   get workers=1 added — they test serial semantics.
4. ETA: durations measured between completion events become inter-completion
   gaps ~= mean_tile/W in steady state -> estimate_eta math UNCHANGED. Only
   fix the seed: Job gains workers:int=1; eta_s() passes
   seed_avg=_SEED_AVG_S/max(1,workers). _run_extraction sets
   workers=tile_concurrency() for tiled mode. Known bias: tail underestimate
   ~one batch; "finishing up…" path absorbs it.
5. Failure isolation in BOTH serial+parallel paths (determinism proof needs
   it): per-tile RuntimeError/TimeoutExpired -> tiles_unparsed entry. Guard:
   if EVERY tile failed with runtime errors (zero parsed, zero prose-skips)
   raise RuntimeError("all N tiles failed — is the claude CLI
   available/authenticated?"). Runtime bounded by CLI_TIMEOUT_S per call.
6. Rate limits: NO adaptive backoff (timing-dependent state machine vs
   determinism story). Knob + failure isolation + all-failed guard. Document
   shared-subscription risk + possible ~/.claude contention in docs.

## Commits
1. Pure refactor _process_one_tile (ValueError only) +
   test_process_one_tile_ok_unparsed_shapes; suite green.
2. Failure isolation: test_tile_cli_error_recorded_not_fatal,
   test_tile_timeout_recorded_not_fatal, test_all_tiles_failed_raises_runtime_error,
   test_prose_only_tiles_do_not_trigger_all_failed_guard.
3. Parallel execution: tile_concurrency, workers params, pool branch,
   aggregate progress; update 2 serial tests to workers=1. Tests:
   test_parallel_output_identical_to_serial (deterministic sleeps REVERSING
   completion order; assert == serial incl. ids + tiles_unparsed order; use
   generous delay spreads 50ms vs 0 to avoid flake),
   test_parallel_progress_done_monotonic_and_completion_counted,
   test_parallel_failure_does_not_sink_other_tiles,
   test_workers_1_emits_exact_legacy_event_strings,
   test_env_var_sets_default_concurrency,
   test_parallel_progress_cb_does_not_change_output.
4. Server+ETA wiring: Job.workers, seed division, _run_extraction sets it.
   Tests: test_job_eta_seed_scaled_by_workers (W=4, no durations, remaining=8
   -> ~8*25/4+3=53), test_eta_uses_intercompletion_durations_as_throughput,
   worker-duration-counter substring still matches parallel stage format.
5. Docs: CLAUDE.md/README/CHANGELOG/progress.md — NBC_TILE_CONCURRENCY,
   subscription caveat, failure-isolation behavior change (CLI errors now
   degrade to tiles_unparsed), run_check --pdf stderr format change.

## Risks
Concurrent claude CLI contention on ~/.claude (knob to 1); transient errors
no longer fail jobs (visible in tiles_unparsed); thread-safe fakes required;
ETA tail bias documented.
