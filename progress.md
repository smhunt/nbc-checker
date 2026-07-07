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

## Next session
- T2 (real IFC models) — extend extractor for geometry-derived facts
- T1 (expand ruleset) — candidates already listed per-rule in verification_notes
