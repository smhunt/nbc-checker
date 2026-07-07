# NBC Compliance Checker — July Sprint Plan

**Goal:** Working prototype demonstrating TRL 5–6 feasibility evidence for ISC challenge
(Deterministic AI-Assisted Compliance Checking of Building Permit Applications).
**Deadline driver:** Proposal closes **August 4, 2026, 2:00 pm ET**. Prototype evidence
must exist before proposal writing finishes (target: prototype frozen July 25).

## Architecture (v1, as built)

```
IFC model ─→ ifc_extractor.py (deterministic, conf=1.0) ─┐
                                                          ├─→ facts.json ─→ engine/checker.py ─→ report
PDF drawings ─→ [T3: LLM extractor] (conf<1.0) ──────────┘        (pure function, 4-status output)
```

- **Rules:** `rules/nbc2020_part9_core.json` — RASE-inspired schema (applicability /
  requirement / exception), every rule cites its NBC provision.
- **Engine:** `engine/checker.py` — deterministic, four statuses (pass / fail /
  info_not_available / uncertain), confidence threshold 0.9, full audit trail per check.
- **Key invariant (EO1):** no generative model ever participates in pass/fail judgment.
  LLMs only produce facts, always tagged with confidence < 1.0, which the engine routes
  to human review unless verified.

## Tasks

### V1 — Verify all rule values against NBC 2020 published text  ✅ DONE 2026-07-07
All 12 rules verified against the official NRC PDF (kept in reference/, gitignored);
evidence recorded per rule in verification_notes. All three flagged risks were real:
ceiling height was wrong (2300 flat -> 2100 partial-area), guard heights re-encoded to
the actual S1/S2/S3 structure, egress exception structure corrected. See progress.md
Session 2 for the full list.

### T1 — Expand ruleset  ✅ DONE 2026-07-07 (38 rules, all verified)
Delivered 9.8.4.4 uniformity, 9.8.6.3 landings, 9.8.7.1 handrails-required, 9.5.5 doorway
sizes, 9.10.19.3 smoke alarms, 9.36.2.6 climate-zone envelope (parameterized demo), plus
ceiling Table 9.5.3.1 rows and tread-depth (fact-to-fact). Every value verified verbatim.

### T2 — Real IFC test models  ✅ DONE 2026-07-07
fetch_models.sh (FZK-Haus + buildingSMART). Extractor: attribute->pset->Qto chain, riser
derived from Qto height/count, geometry bbox fallback for space height. Finding recorded:
IfcStairFlight rare in real exports — needs vendor-pset mapping + i18n room-use.

### T3 — PDF drawing extraction path  ✅ DONE 2026-07-07
extractors/pdf_extractor.py drives the claude CLI headless (no API key needed); confidence
hard-capped at 0.89 in code so all LLM facts route to human review. Live-verified.

### T4 — Review UI  ✅ DONE 2026-07-07
FastAPI (:3099) + Vite/React (:3029), both HTTPS. Confirm/correct UNCERTAIN -> deterministic
re-run, live-verified. Ports registered in PORTS.md.

### T5 — Report export  ✅ DONE 2026-07-07
engine/export.py PDF + Excel, byte-deterministic, provision + provenance per check. Wired to
/api/export and run_check flags. BCF still a stretch goal.

### T6 — Feasibility evidence document  ✅ DONE 2026-07-07
docs/feasibility-evidence.md + docs/determinism_demo.sh (5 runs -> identical SHA-256).

### T7 — Proposal draft  ✅ DRAFT 2026-07-07 (needs business verification)
docs/proposal-draft.md written. ⚠️ The official ISC challenge posting could NOT be found —
ALL EO1–EO7 wording in the draft is interpolated and MUST be verified against the real
Challenge Notice. Eligibility flags: Phase 1 prerequisite (Entry-at-Phase-2 pathway exists
for TRL 5–9 proven with outside funding — our evidence fits), Canadian for-profit incorp
required. Phase 2 ceiling ~$1M/2yr; $475K/18mo plan fits.

## Open decisions
1. Rule format future: stay JSON or adopt/align with ACCORD open formats (BSDD, IDS)?
   Research task — alignment strengthens the proposal's standards story.
2. Engine language long-term: Python core is right for IfcOpenShell; wrap with FastAPI
   for EO7 open API, or port engine to TypeScript later? (Recommend: keep Python.)
3. Which municipality to approach for a letter of support / sample permit sets?
   (Middlesex Centre relationship? London?)
4. Confidence threshold 0.9 — arbitrary v1 value; make configurable per deployment.
5. Partner strategy: solo EcoWorks vs. teaming with a code consulting firm.

## Guardrails
- Do not let any LLM output flow into pass/fail without a confidence tag.
- Do not mark rules verified without checking the published code text.
- Small reviewable commits; engine changes require re-running both sample suites.
