# Progress Log

## 2026-07-07 — Session 1 (claude.ai, scaffold)
- Confirmed IfcOpenShell 0.8.5 installs and runs (pip, Ubuntu 24)
- Built rule schema (RASE-inspired JSON) with 10 NBC 2020 Part 9 rules — ALL UNVERIFIED (task V1)
- Built deterministic engine: 4-status output, confidence gating (0.9), exceptions, full audit trail
- Built IFC extractor (IfcStairFlight, IfcSpace, IfcWindow) with unit normalization to mm
- Smoke-tested end-to-end: generated IFC4 model -> extractor -> engine -> report. Caught and
  fixed unit bug (ifcopenshell assign_unit defaults to mm; extractor conversion was correct)
- Sample dwelling facts exercise all four statuses incl. low-confidence PDF-extracted fact -> REVIEW
- Deliberate design choice: window unobstructed open area NOT derived from overall dims
  (depends on operation type) — engine reports INFO_NOT_AVAILABLE instead of guessing

## 2026-07-07 — Session 2 (Claude Code, V1 rule verification)
- Repo on GitHub (public): https://github.com/smhunt/nbc-checker
- Added verification_notes schema (0.2.0): quote/sources/verified_date/reviewer per rule;
  verified flag only valid with quote+sources populated
- Obtained official NRC NBC 2020 PDF (publications.gc.ca NR24-28/2020E-PDF); kept PDF +
  searchable text extract in reference/ (gitignored — NRC copyright). All quotes checked
  directly against this text, not just research-agent reports.
- **V1 COMPLETE: all 12 rules verified against published NBC 2020 text.**
- Confirmed as encoded: riser 125-200, run 255-355, width 860, headroom 1950,
  handrail 865-1070, egress 0.35 m2/380 mm, guard openings 100 mm sphere
- Errors caught by verification (this is the pitch story — encoding from memory fails):
  1. CEILING HEIGHT was wrong: 2300 flat minimum is pre-2015/Ontario; NBC 2020 is
     2100 over lesser of space area or 10.0/5.2 m2, contiguous with entry. Fixed.
  2. GUARD HEIGHT structure was wrong: not a pure fall-height trigger; re-encoded as
     4 rules (S1 default 1070 / S2 interior in-unit 900 / S3 exterior single-dwelling
     900 iff <=1800 above grade) keyed on new guard_context fact
  3. Egress exceptions: sprinklered-suite qualifier is the only true exception;
     exterior door is an in-sentence alternative; values live in Sentence (2)
  4. Guard openings <= 100 -> < 100 (must PREVENT passage of 100 mm sphere) — judgment
     call, flag for code consultant
- Determinism demo: 3 consecutive runs -> identical SHA-256 report hash
- Future rules recorded in verification_notes: tread depth run..run+25 (needs fact-to-fact
  ops), 2050/1850 headroom tiers, 900 shared-stair width, 760 window-well clearance,
  full Table 9.5.3.1 room rows, secondary-suite 1950/1850 (alternate-threshold rules)
- Jurisdiction warnings: Ontario OBC differs materially (egress, guards, ceilings);
  BCBC 2024 reserves the secondary-suite ceiling sentences

## 2026-07-07 — Session 3 (Claude Code, T1–T7 full sprint, parallel agents)
Executed the whole T1–T7 plan (docs/superpowers/plans/2026-07-07-t1-t7-execution.md)
in one session, fanning out to 7 parallel research/build agents, merging + verifying
each deliverable inline.
- **T1 (ruleset):** 12 -> 38 rules, ALL verified verbatim against reference/nbc2020.txt.
  Batches: stairs/handrails/guards/window-well (A), ceiling table + doors (B), smoke
  alarms + 9.36 climate-zone envelope (C). Agent quotes spot-checked against the extract.
- **Engine:** added fact-to-fact comparison (value_fact + offset) for tread depth vs run.
  pytest suite (53 tests) caught a real dominance bug: a violation followed by a missing
  fact in the same rule reported info_not_available, masking FAIL — fixed with explicit
  status dominance.
- **T2 (IFC):** fetch_models.sh (FZK-Haus etc.), extractor now does attribute->pset->Qto,
  derives risers from Qto height/count, geometry bbox fallback for space height. Finding:
  IfcStairFlight is rare in real exports (vendor psets / IfcStair only) — shapes Phase 2.
- **T3 (PDF):** pdf_extractor.py drives claude CLI headless; every LLM fact capped at 0.89
  (< 0.9 threshold) so all route to human review (EO1). Live run: all 5 drawing
  annotations extracted, nothing invented, all capped.
- **T4 (UI):** FastAPI backend (:3099) + Vite/React reviewer (:3029), both HTTPS. Live-
  verified EO4 loop: uncertain handrail -> confirm -> PASS -> delete -> reverts, SHA moves
  predictably. Ports registered in PORTS.md.
- **T5 (export):** engine/export.py PDF + Excel, byte-deterministic; wired to /api/export
  and run_check --export-pdf/--export-xlsx.
- **T6:** docs/feasibility-evidence.md + docs/determinism_demo.sh (5 runs -> identical
  SHA-256). The V1 verification story (3 encoding errors caught) is the headline evidence.
- **T7:** docs/proposal-draft.md. RESEARCH RED FLAGS surfaced (business decisions, not
  code): (1) the specific ISC challenge posting could not be found publicly — all EO1–EO7
  wording is INTERPOLATED and must be verified against the real Challenge Notice; EO5
  unknown. (2) Phase 2 normally requires a completed Phase 1; there is an "Entry at
  Phase 2" pathway for TRL 5–9 solutions proven with outside funding (our evidence fits) —
  but only if the specific Challenge Notice opens that option. (3) ISC needs a Canadian
  for-profit incorporation (EcoWorks status pending). Phase 2 ceiling is ~$1M/2yr, so the
  $475K/18mo plan fits comfortably.

## 2026-07-07 — Session 4 (Claude Code, Phase 2: Ontario + real-plan hardening)
Triggered by processing a REAL uploaded Ontario permit (change of use, fish market ->
dwelling). The upload exposed three gaps, all now closed (parallel agents + inline):
- **Ontario OBC 2024 ruleset** (rules/obc2024_part9_core.json, 23 rules, 19 verified):
  right jurisdiction for ON projects; documents OBC-vs-NBC per rule. Key: Ontario-only
  920 mm exit-stair + 1500 mm high guards, egress 1000 mm max sill, and 2024 harmonized
  stair run (210->255) and ceilings (2300/75% -> 2100 area-based). 4 rules honestly
  unverified (e-Laws/CanLII not machine-readable).
- **Tiled high-DPI PDF extraction** (extract_tiled): 3x3 @ 200 DPI, per-tile 0.89 cap,
  merge/dedupe highest-confidence. Real sheet: 3 facts -> 17 facts (~6x).
- **Renovation scoping**: rule scope=new_work_only skips work_status=existing entities;
  jurisdiction now surfaced in report. 65 tests total.
- **Case study** (docs/casestudy-real-permit.md): real plan end-to-end vs OBC. Every LLM
  value routed to human review (EO1 held on real input); flagged a 254 mm run, 1 mm under
  the OBC 255 min. Original PDF + address/designer NOT committed (public repo privacy);
  committed facts anonymized.
- Bug fixed: pdf_extractor needed --allowedTools Read for the nested CLI to read uploads.
- Docs: feasibility addendum, CHANGELOG 0.5.0, UI changelog 0.5.0, README.

## 2026-07-07 — Session 4b (official Challenge Notice reconciliation)
- User supplied the official posting URL (challenge OPENED today, closes Aug 4 14:00 ET).
- Direct Phase 2 entry confirmed (TRL 5-9, no Phase 1 prerequisite) — red flag resolved.
  Max $500K/18mo/~2 grants; our $475K/18mo plan fits.
- Proposal rewritten against the 10 OFFICIAL EOs + 4 Additional Outcomes. EO6's four
  categories (Pass/Fail/Info Not Available/Uncertain) match our engine verbatim.
- Honest gaps became Phase A/C commitments: Part 3 (EO2), French CNB + Quebec CC (EO10),
  Canadian data residency (EO8), BCF export (EO9), NRC digitalized-code format (EO5).
- Evaluation notes: inclusivity is 20/130 pts — needs a substantive plan; question window
  closes ~Jul 25 (consider requesting NRC sample code data via EO5).

## Next session
- Verify the 4 unverified OBC rules against machine-readable e-Laws (JS-rendered; needs
  browser fetch or the OBC compendium PDF)
- Tag OBC rules with new_work_only scope so change-of-use projects check only new work
- Partial-area/sloped-ceiling evaluation (needs area/topology facts)
- Real-IFC hardening: vendor-pset mapping, i18n room-use classification

## 2026-07-09/10 — Session 5 (Part 3 entry + PDF evidence drill-down)
- **NBC 2020 Part 3 ruleset shipped** (`rules/nbc2020_part3_core.json`, 35 rules, 100%
  verified verbatim against the official extract): fire separations (Table 3.1.3.1 pairings,
  closure ratings, corridor separations, self-closing devices), occupancy classification +
  occupant load (Table 3.1.17.1 rows, dwelling sleeping-room basis, posting), exits 3.4
  (widths, rise/landings, handrails/guards, treads/risers, headroom, exit count),
  accessibility 3.8 (entrances, path/ramp/door widths, slope, WC stalls, grab bars).
  Closes the proposal's biggest EO2 gap ("Part 3 not yet covered" -> delivered evidence).
- Four parallel encoding agents + main-session spot-verification of every quote. Agents
  caught 8 brief-vs-code discrepancies (no 3.1.17.2; headroom is 3.4.3.4; ramp slope is
  3.4.6.7; no 920 mm in Part 3 guards; 3.8 rewritten in 2020: 1000 mm path not 920,
  850 mm doors not 800, ALL entrances barrier-free not 50%; stalls are 3.8.3.12) —
  more proof encoding-from-memory fails and verification-against-text is the product.
- Engine: `in`/`not_in` ops (set membership, e.g. valid occupancy groups); ruleset
  schema + verification-contract test suite runs against every rules/*.json.
- **PDF evidence drill-down shipped** (plan in docs/superpowers/plans/): facts carry
  optional `evidence {doc, page, bbox}` (normalized top-left coords); engine passes it
  through the audit trail untouched (EO1); tiled extractor converts LLM tile-fraction
  bboxes to page coords via the deterministic clip-rect geometry (validation + page-level
  fallback); page-PNG endpoints (traversal-hardened, dpi-whitelisted, cached); UI
  EvidenceViewer zooms/animates to the fact's region with highlights; human overrides
  copy evidence so confirmation keeps the drawing link. Sample handrail fact carries a
  PyMuPDF-text-search-derived bbox for the demo.
- Visual verification on nbc.dev.ecoworks.ca: UNCERTAIN handrail -> view on drawing ->
  zoom to "HANDRAIL 920 mm ABOVE NOSING" annotation -> confirm with note -> deterministic
  re-run -> PASS (27/11/16/0), evidence + note preserved in the override audit trail.
- 338 tests passing. All work committed granularly and pushed.

## Next session
- Part 3 follow-ups recorded in verification_notes: 1100 mm stair tier (needs OR in
  where-conditions or boolean fact), B2 vertical-rise 2400, closure-table remaining rows,
  bf_control entity for 3.8.3.8, exterior walks 1600 mm
- Multi-page PDF extraction loop (schema already carries 1-based page)
- Real tiled-extraction run to eyeball LLM bbox quality on the casestudy sheet

## 2026-07-10 — Session 5b (UI sprint: progress/ETA, resizable drawer, larger locator)
- Part 3 follow-ups: 45 rules total (multi-storey stair tier via boolean fact, B2 rise,
  all six closure rows, exterior walks 1600, bf_control 400-1200, headroom companions)
- Proposal EO2 updated: Part 3 gap -> delivered evidence (35->45 rules)
- Backend: extract/extract_tiled accept observational progress_cb (facts proven identical
  with/without); jobs expose stage/progress/elapsed/eta_s; ETA from measured tile times
- UI: verbose processing panel (stage, tile n of m, elapsed, local ETA countdown,
  "finishing up…"), drag-resizable drawer (380px-70vw, localStorage, dbl-click reset),
  evidence viewer 4:3 + Expand overlay (85vw/85vh, 200 dpi, Esc dismiss)
- LIVE verification: real 9-tile job through the browser — progress read "extracting tile
  r2c1 / tile 3 of 9 / 0:37 elapsed ~70s remaining"; real elapsed 158.9s (~17s/tile, seed
  25 was conservative). ALL 7 real-run facts carried bboxes within ~2% of PyMuPDF
  ground-truth annotation positions; expanded viewer highlighted the annotation from the
  uploaded job's own evidence. Drawer resize persisted (420->681, localStorage).
- 377 tests passing. Sprint plan: docs/superpowers/plans/2026-07-10-ui-progress-sprint.md

## 2026-07-10 — Session 5c (sample permit corpus)
- Two research agents surveyed public sample/example permit drawing sets; 17 PDFs
  (~122 MB) fetched via committed samples/fetch_permits.sh into gitignored
  samples/external/permits/. Canadian: Calgary full 23-sheet new-home DP/BP set,
  secondary suites x2, basement, garage, patio; Ottawa (OBC!) addition/sundeck/
  accessory/basement; Edmonton + Alberta (open licence) + Winnipeg garage guides.
  US (extraction density + Part 3): Cotati REAL approved sets (ADU 28MB, mixed-use
  63MB), Lynnwood commercial TI, TRDI 37-sheet commercial CDs.
- Not redistributed (Calgary prohibits reproduction; others unlicensed public
  records) — fetch script preserves reproducibility. San Diego ADU plans fail via
  curl (server aborts); Vancouver 403s non-browser clients; NIBS matched IFC+PDF
  pairs (the ideal dual-extractor test) are OFFLINE — retry portal.nibs.org later.
- Sample-facts cleanup: fictional 'drawings A-000' sources -> designer-declared
  spec values (conf 1.0 now consistent with EO1 story).
- Ottawa addition (real OBC sheet, p.6 floor plan) through tiled extraction: 7 entities,
  11 facts, 11/11 with evidence bboxes, ALL conf <= 0.89 (EO1 held). Model read the
  window schedule + normalized printed imperial (9'x7' -> 2743x2134 mm). Engine (OBC +
  NBC): zero false verdicts — everything routed to info_not_available / uncertain
  (kitchen room_use at 0.89 -> applicability review). Follow-ups: multi-page extraction
  loop (checklist pages precede drawings), dedupe 'Window A (schedule)' vs 'Window A'.
- DIRECTION (user): Canadian content and codes only — US permit sets removed from the
  corpus and fetch script (13 Canadian sets remain: Calgary x6 incl. 23-sheet new home,
  Ottawa x4 OBC, Edmonton, Alberta OGL, Winnipeg).

## 2026-07-10 — Session 5d (multi-page extraction, plan T1-T7 executed)
- Plan docs/superpowers/plans/2026-07-10-multipage-extraction.md executed in full, TDD,
  one commit per task. 407 -> tests passing incl. 12 classifier + 5 multi-page + 3
  progress + 3 server tests.
- Deterministic page selection (extractors/page_select.py): skip needs strong checklist
  evidence; scans fail open (no_signal); every skip carries a reason; page cap (12,
  NBC_MAX_TILED_PAGES) reported. Corpus-validated: Ottawa skips p1-4, Calgary 26 CAD
  sheets keep all (cap only), scanned suite all included.
- extract_tiled: pages=auto|all|1,3-5, per-page adaptive choose_grid (server no longer
  hardcodes 3x3), page-qualified provenance ("p6 tile r1c2"), cross-page merge (with T1
  parenthetical dedupe fix), project.pages audit metadata; page_index deprecated shim.
- ACCEPTANCE (real Ottawa addition, --pages auto): 8p -> processed [5,6,7,8], 4 checklist
  skips with reasons, 16 tiles (4x 2x2), 5 entities / 8 facts ALL bboxed, evidence spans
  pages 6 AND 8 (section-view facts the single-page pipeline could never see), max conf
  0.89. CLI --pages flag; UI pages input + processed-pages summary.
- Smoke command (corpus gitignored, not CI):
  python3 extractors/pdf_extractor.py --tiled --pages auto samples/external/permits/ottawa_addition.pdf
