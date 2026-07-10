# Multi-Page PDF Extraction Plan

> Produced by planning agent 2026-07-10, grounded in a read-only probe of the
> real Canadian permit corpus (samples/external/permits/). Execute with
> superpowers:executing-plans; tasks T1–T7 are commit-sized and TDD.

## Recommendation

Layered page selection: **deterministic PyMuPDF pre-classification** as the
default (`pages="auto"`), **fail-open toward inclusion**, every skip decision
reported in `project.pages` metadata, explicit override (`"all"` or
`"1,3-5"`). NO LLM triage (breaks determinism for a decision that governs
which facts exist). Tiled mode loops selected pages through the existing
per-page pipeline with page-stamped provenance, global page cap
(DEFAULT_MAX_TILED_PAGES=12, env-overridable), adaptive per-page grid (fix:
app.py hardcodes 3x3; pass grid=None -> choose_grid), cumulative progress
("page 2/4 (pdf p6): extracting tile r1c2") over one pages*tiles total —
existing ETA math unchanged. Cross-page dedupe by (entity_type, normalized
name) with a parenthetical-stripping fix so "Window A (schedule)" merges with
"Window A"; winning fact keeps its own page evidence.

## Corpus ground truth that shaped the design

- ottawa_addition.pdf: checklist pages CONTAIN drawing keywords ("floor plan
  drawing to include...") — negative keywords (checklist/application/...) with
  prose density + low vector count are the reliable skip discriminator.
- calgary_new_home (26p): all pages are true CAD drawings — selection must not
  prune; only the cap limits cost (12 pages x ~4 tiles ~ 14 min; capped pages
  reported so the reviewer can rerun with explicit pages).
- calgary_secondary_suite_new.pdf: PURE SCANS (0 words, 0 vectors) — classifier
  emits no_signal and INCLUDES (fail-open); scans are where LLM extraction is
  most needed.

## Key interfaces

- extractors/page_select.py (new, pure): PageStats, classify_page(stats) ->
  (label, reason), select_pages(stats, spec, max_pages) -> PageSelection
  {selected, skipped[{page,label,reason}], labels}, parse_pages_spec.
- extract_tiled(pdf_path, ..., grid=None, pages="auto"|"all"|[1-based],
  max_pages=None, page_index=None deprecated shim, progress_cb).
- project.pages metadata: {total, processed[], skipped[{page,label,reason}],
  selection}; tile labels/sources page-qualified ("p5:r1c1").
- Server: upload(..., pages=Form("auto")) validated -> 400; Job.pages_info;
  public() pages summary; done-message counts pages.
- UI: pages input (auto|all|1,3-5) + "processing 4 of 8 pages" summary line.
- _run_extraction: duration counter condition becomes "extracting tile" in
  stage (page prefix would break startswith); optional seed 25->18s.

## EO1/determinism

Classifier is a pure function of deterministic fitz stats. Selection shapes
what is READ, never pass/fail; asymmetric risk (skip = missed facts) handled
by strong-evidence-only skips, fail-open, mandatory reporting, "all" override.
Confidence caps and evidence page stamping unchanged.

## Tasks (each one commit, TDD)

T1 _entity_key parenthetical fix (+3 tests)
T2 page_select.py pure classifier/selection (+9 tests incl. Ottawa trap,
   Calgary notes-page non-skip, scan fail-open, cap reporting, determinism)
T3 extract_tiled multi-page loop (+5 tests incl. cross-page dedupe keeping
   winning fact's page provenance, page_index shim equivalence)
T4 cumulative progress + ETA (+3 tests incl. event ordering, output identity)
T5 server pages param + pages_info (+3 tests)
T6 UI pages input + summary line (build gate)
T7 CLI --pages flag, CLAUDE.md/progress.md docs, real-corpus smoke commands:
   ottawa_addition (expect skip 1-4 with reasons, process 5-8 at 2x2) and
   calgary_secondary_suite_new (all no_signal, included).

## Risks

False-negative skip (mitigated: multi-signal + fail-open + reporting + "all");
scans defeat classifier (cost-bounded by cap); generic-name cross-page
over-merge ("Bedroom" x2 floors — pre-existing, documented, evidence exposes);
long tiled jobs (~14 min at cap, per-tile timeout bounds); whole-mode 26-page
timeout (monitor; raise CLI timeout for whole mode if seen); stage-string
coupling (T4 changes both sides together + test).
