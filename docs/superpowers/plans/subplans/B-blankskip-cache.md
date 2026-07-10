# Sub-plan B: Blank-tile skip + tile-hash extraction cache (wave 2)

## Blank skip
- Signal: content-object counting via PyMuPDF clip intersection, computed in
  render_page_to_tiles while the page is open. Per tile:
  words = len(page.get_text("words", clip=clip));
  vector_items = count of page.get_drawings() item rects intersecting clip
  (fetch drawings/images ONCE per page before tile loop);
  images = count of page.get_image_info() bboxes intersecting clip.
  Tile descriptor gains "content": {"words", "vector_items", "images"}.
- classify_tile_content(content: dict | None) -> (blank: bool, reason: str),
  pure, env-free. Blank ONLY if all three counts == 0 (threshold zero, no
  tuning). None/missing stats -> (False, "no content stats — fail-open").
  Full-page scan image intersects every clip -> scans structurally never
  skipped. Overlap: clips already include the 12% overlap strips, so a tile
  whose only content is in the seam is non-blank by construction.
- Gate in _extract_tiles (not the classifier): NBC_BLANK_TILE_SKIP=0 disables
  (default on). On blank: progress_cb "{prefix}skipping blank tile {label}"
  (fails the "extracting tile" duration guard on purpose), append
  {"tile": label, "reason": "blank: 0 words, 0 vector items, 0 images in
  clip (incl. 12% overlap)"} to tiles_skipped, continue — runner never called.
- Metadata: project.tiles_skipped ALWAYS present ([] when none) in both
  rendered and bypass return paths; project.tiles = labels actually sent to
  the LLM (check ui/ for consumers of project.tiles before landing).

## Cache
- New extractors/extract_cache.py: DEFAULT_CACHE_DIR reports/extract_cache
  (env NBC_EXTRACT_CACHE_DIR), CACHE_SCHEMA="1".
  cache_key(runner_id, prompt, input_bytes) =
  sha256("nbc-extract-cache/1\0" + runner_id + "\0" + prompt + "\0" +
  sha256(input_bytes)). runner_id = getattr(runner, "identity", None) or
  getattr(runner, "cache_id", None) or __qualname__ (wave 1 stamps .identity;
  CLI model unpinned — documented; bump CACHE_SCHEMA to invalidate manually).
- cached(runner, cache_dir=None) -> same-signature wrapper with
  .stats={"hits","misses","bypassed"} and .inner. Stores
  {version, runner_id, prompt_sha256, input_sha256, created_at, response}
  as {key}.json; atomic write (.tmp + os.replace). RAW RESPONSE TEXT ONLY —
  never parsed facts (parser/cap/bbox changes must re-apply to cached
  responses; EO1 hazard otherwise). created_at never enters output.
- Fail-open: NBC_EXTRACT_CACHE=0 -> passthrough; unreadable input file ->
  passthrough (covers fake /tmp tile paths); corrupt entry -> miss+rewrite;
  runner exception -> propagates, never cached. No eviction; dir documented
  deletable (page_cache precedent).
- Wiring (after wave 1's runner=None refactor): resolution becomes
  runner or cached(select_runner(kind)). Explicit runners (all test fakes)
  NEVER wrapped. Cache hit/miss stats NEVER in facts output (breaks
  run-to-run identity).
- CLI runners append their abs-path suffix INSIDE run_claude/_image, so the
  wrapper keys on the pre-suffix prompt by construction — no cross-machine
  key poisoning.

## ETA / progress
- _MIN_COUNTED_TILE_S = 1.0 in server/jobs.py: durations below it excluded
  from tile_durations (cache hits ~ms; real tiles 10-60s). Blank-skip stage
  text already fails the "extracting tile" guard. Refactor: move the _cb
  closure from server/app.py into server/jobs.py::make_progress_cb(store,
  job_id) so it's directly testable; replace the inspect.getsource test.

## Commits + tests
1. classify_tile_content + content stats in render_page_to_tiles.
   Tests: test_classify_tile_content_blank_when_all_zero,
   test_classify_tile_content_fail_open_without_stats,
   test_classify_tile_content_any_image_means_not_blank,
   test_rendered_tiles_carry_content_stats (tmp fitz PDF, text one quadrant),
   test_scan_page_full_page_image_marks_every_tile_nonblank (2x2).
2. Skip wiring + metadata + env gate.
   Tests: test_blank_tile_skipped_reported_and_runner_not_called,
   test_blank_skip_deterministic_two_runs_identical,
   test_blank_skip_disabled_by_env, test_overlap_strip_content_prevents_skip,
   test_scan_fail_open_end_to_end, test_progress_ticks_fire_for_skipped_tiles.
3. extract_cache.py + tests/test_extract_cache.py (tmp dirs):
   test_miss_calls_runner_and_writes_entry,
   test_hit_returns_identical_text_without_calling_runner,
   test_prompt_change_invalidates, test_input_bytes_change_invalidates,
   test_runner_cache_id_change_invalidates, test_env_disable_bypasses,
   test_unreadable_input_file_bypasses_fail_open,
   test_corrupt_entry_is_a_miss_and_rewritten,
   test_runner_exception_not_cached.
4. Cache as default runner: test_cached_tiled_replay_byte_identical_to_fresh
   (counting fake wrapped explicitly in cached(cache_dir=tmp); 2nd run zero
   runner calls; sorted-json equal), test_confidence_cap_applied_on_cache_replay
   (cached 1.0 claim still caps 0.89), test_cache_stats_never_in_facts_output,
   test_explicit_runner_is_never_wrapped.
5. make_progress_cb + _MIN_COUNTED_TILE_S:
   test_progress_cb_counts_normal_tile_durations,
   test_progress_cb_excludes_subsecond_ticks_from_eta_stats,
   test_progress_cb_skip_stage_never_counts_duration.
6. Docs: CLAUDE.md (tiles_skipped, env vars, cache dir deletable),
   CHANGELOG, progress.md.

Risks: page-border single-rect defeats savings (never correctness); CLI model
drift not in key (cache_id bump lever); get_text clip boundary semantics —
verify in commit-1 tests; project.tiles semantic shift (check UI).
