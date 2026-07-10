# Sub-plan D: Progressive result streaming (wave 4)

Decisions:
- Page-granularity partials via on_partial(pfacts, pages_done, pages_total)
  callback on extract_tiled, fired at the PAGE BARRIER in the multi-page loop
  (after _extract_tiles returns for page k), re-running pure merge_tile_facts
  over accumulated tile_facts. Full facts-dict shape identical to final
  return. No callback in extract() (single pass). Bypass tiles= path: no
  partials (documented). Fire after EVERY page incl. last (final merge stays
  authoritative). Callback observational only — final output must be
  identical with/without it. Docstring states the parallel-tiles contract:
  tile results appended in deterministic (page, tile) order; partials publish
  only the contiguous completed-page prefix, in page order (parallelism pools
  WITHIN a page, so placement needs no change).
- Job contract: Job.partial_facts: dict|None and Job.partial_pages:
  dict|None ({"done","total"}). GET /api/jobs/{id} while status=="extracting"
  and partial_facts set: adds "partial": true + report/facts/rules (NO
  report_sha256 — determinism badge is final-only) + partial_pages. Done
  response byte-identical to today (no partial key). Override/export
  endpoints UNCHANGED: they gate on job.facts is not None, which stays None
  until done -> locked during streaming for free.
- Server: refactor _job_state into pure
  _report_state(ruleset_key, facts, overrides) (report/facts/rules, no sha);
  _job_state = _report_state + sha + overrides; new _job_partial_state(job) =
  _report_state(job.ruleset_key, job.partial_facts, {}) + {"partial": True}.
  _run_extraction passes _on_partial which deep-copies via
  json.loads(json.dumps(pfacts)) (sever aliasing) then
  STORE.update(partial_facts=snapshot, partial_pages={...}) — atomic ref
  swap under store lock.
- Entity-id stability VERIFIED: merge_tile_facts assigns pdf-entity-{i+1} in
  first-seen order over append-only tile_facts -> ids are prefix-stable
  across partials and final. Still LOCK overrides until final (a fact's
  winning value can change when a later page has higher confidence).
- UI: api.ts Job gains partial?: boolean, partial_pages?. UploadPanel: new
  optional prop onPartial(job); in poll loop if (job.partial && job.report)
  onPartial(job). App: showPartial(job) like showJob but report_sha256:'',
  preserves selectedKey; final showJob clears partial state and preserves
  selection when same job. Banner above SummaryBar: "Partial results —
  extraction in progress (page {done} of {total}). Overrides and export
  unlock when extraction completes." Hide determinism badge when sha empty.
  DetailDrawer readOnly prop: hides OverrideForm with explanatory note
  (server already 404s; UX only).

Commits + tests:
1. Extractor callback (tests in tests/test_partial_stream.py or
   test_jobs_progress.py, using _drawing_pdf + grid=(1,1) + pages="all"):
   test_on_partial_fires_once_per_completed_page (2p PDF, 2 calls, first
   snapshot page-1 entities only, counters right),
   test_on_partial_does_not_change_final_output (determinism),
   test_partial_entity_ids_prefix_stable,
   test_on_partial_snapshot_not_mutated_by_later_pages.
2. Job contract (seed STORE directly, no threads):
   test_job_partial_report_while_extracting (partial:true, report present,
   NO report_sha256 key), test_partial_override_and_export_rejected (404s),
   test_final_job_response_has_no_partial_flag,
   test_run_extraction_wires_on_partial (spy extract_tiled; invoke callback;
   partial_facts lands).
3. Mid-run integration: real thread + stub extract_tiled publishing a page-1
   partial then blocking on threading.Event then returning final:
   test_partial_visible_mid_run_then_final_matches_nonstreaming (bounded
   poll; final report/sha equal to plain non-streaming stub run).
4. UI wiring (api.ts, UploadPanel, App, DetailDrawer, index.css); gate:
   npm run build zero TS errors.
5. Docs: CHANGELOG; jobs.py module docstring note (partials are ephemeral
   previews; only final carries report_sha256).

Risks: value churn between partials (banner + locked overrides); snapshot
aliasing (json deep-copy + non-mutation test); poll-time report recompute
(same cost profile as done-path today); whole mode gets no benefit (fine).
