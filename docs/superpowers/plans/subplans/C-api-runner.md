# Sub-plan C: Direct API runner + model selection (waves 1 and 5)

## Wave 1 scope (tasks C1-C3)
- New extractors/runners.py. Move run_claude/run_claude_image + CLI_TIMEOUT_S
  here essentially verbatim (same --allowedTools Read, same ["result"]
  envelope); pdf_extractor re-exports them for back-compat (__main__ etc.).
- select_runner(kind: "pdf" | "image"): API runner iff ANTHROPIC_API_KEY set;
  NBC_RUNNER=cli|api override; NBC_RUNNER=api without key -> RuntimeError
  ("NBC_RUNNER=api but ANTHROPIC_API_KEY is not set") — fail loud, never
  silent downgrade; invalid value -> ValueError. Selection happens ONCE per
  extract/extract_tiled call (job start); no mid-job fallback path exists.
- Runners carry .identity: "cli:claude" / f"api:{model}" (closures with
  attribute set post-def, or tiny callable class; NOT functools.partial).
- make_cli_runner(kind), make_api_runner(kind, model=None).
  DEFAULT_EXTRACT_MODEL="claude-sonnet-4-6" (flip to
  claude-haiku-4-5-20251001 ONLY after measured A/B); get_extract_model()
  reads NBC_EXTRACT_MODEL. API_TIMEOUT_S=120, API_MAX_RETRIES=2,
  MAX_TOKENS_TILE=4096, MAX_TOKENS_PDF=8192.
- API runner: lazy `import anthropic` (CLI-only machines unaffected; missing
  package -> clear ImportError with install hint at job start). Client built
  once per runner: anthropic.Anthropic(api_key=os.environ[...],
  timeout=API_TIMEOUT_S, max_retries=API_MAX_RETRIES) — explicit key so
  selection and auth can't disagree. messages.create non-streaming; content:
  media block FIRST then {"type":"text","text":prompt}. Tile: image block
  base64 PNG. Whole-PDF: document block base64 PDF (check size, clear error
  >30MB). NO temperature/thinking params (forward-compat: newer models
  reject non-default temperature). stop_reason "refusal" or "max_tokens" ->
  RuntimeError. Return "".join(text blocks).
  IMPORTANT: API runner does NOT append the CLI's "file to read is at:"
  suffix — the payload travels in the request.
- Error mapping most-specific-first: AuthenticationError -> RuntimeError
  ("Anthropic API auth failed — check ANTHROPIC_API_KEY"); RateLimitError ->
  RuntimeError("rate limited after retries"); APIStatusError/
  APIConnectionError -> RuntimeError with status/type. Key NEVER in messages
  or logs.
- extract/extract_tiled: runner=None default; resolve at call time via
  factory (wave 2 wraps with cached()). project gains
  "extractor": getattr(runner, "identity", "unknown").
- Dependency: pip3 install "anthropic~=<current-minor>" --break-system-packages;
  document in CLAUDE.md/README (no requirements file in repo).

Wave-1 tests (new tests/test_runners.py; mock SDK via _client_factory seam on
make_api_runner or patching anthropic.Anthropic):
selection matrix (default cli w/o key; api when key; NBC_RUNNER=cli overrides
key; =api w/o key raises; invalid raises; NBC_EXTRACT_MODEL override);
test_api_runner_image_sends_base64_png_block_then_prompt_text;
test_api_runner_pdf_sends_document_block;
test_api_runner_concatenates_text_blocks;
test_api_runner_refusal_or_max_tokens_raises_runtime_error;
test_api_error_message_never_contains_key;
test_api_runner_identity_includes_model_id;
test_cli_runner_identity_is_cli_claude;
test_run_claude_reexported_from_pdf_extractor;
test_runners_module_imports_without_anthropic_installed (sys.modules poison).
tests/test_pdf_extractor.py: factory-resolution tests for extract and
extract_tiled (monkeypatch select_runner), runner identity in project meta,
test_confidence_cap_applies_with_api_identity_runner (EO1 regression).

## Wave 5 scope (tasks C4-C6)
- C4 docs: secrets delivery (launchd EnvironmentVariables OR mode-600
  ~/.config/nbc-checker/env sourced via `set -a; . file; set +a` — file
  already provisioned on this machine), env var reference, integration smoke
  procedure, cache-key coherence note.
- C5 scripts/ab_extract_models.py: per (model, pdf, run) call
  extract_tiled(pdf, runner=make_api_runner("image", model)) with a usage-
  recording wrapper (resp.usage in/out tokens), wall clock, tile pixel dims
  (RISK: API downscales >1568px long edge; large-sheet 3x3 tiles ~2600px —
  API could read small text WORSE than CLI; optionally add claude-sonnet-5
  arm, 2576px). Fact-level diff vs expected JSON:
  (entity_type, normalized name, fact key) matched within ±1mm; report
  found/matched/wrong/hallucinated, latency/tile, $ (hardcoded price table
  with as-of date), run variance. Prints cost estimate BEFORE running;
  --max-tiles guard. Ground truth: samples/A-201_stair_section.pdf +
  samples/sample_dwelling_facts.json; real corpus sheet vs a hand-reviewed
  expected file (casestudy reviewed-facts pattern). Output
  docs/ab-model-results.md. Pure diff helper unit-tested
  (test_ab_diff_matches_within_tolerance); no CI API calls.
- C6: run A/B (needs VALID key), write results doc, flip
  DEFAULT_EXTRACT_MODEL only if supported, cite doc in commit.

Risks: API downscale legibility regression (measure first); cost bounded
(23-sheet Calgary ~ $0.40 Haiku / $1.20 Sonnet); silent runner drift
(provenance surfaces it); pin dated Haiku snapshot; record response.model.
