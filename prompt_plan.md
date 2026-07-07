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

### T1 — Expand ruleset to 25–30 Part 9 rules
Candidates: 9.8.4.4 (uniformity of risers/runs), 9.8.6 (landings), 9.8.7.1 (where
handrails required), 9.7 (windows/glazing), 9.5.5 (doorway sizes), 9.10.19 (smoke alarm
locations — presence check), 9.36 prescriptive envelope values (climate-zone-dependent —
good demo of parameterized rules).

### T2 — Real IFC test models
Download 2–3 open sample house IFC models (buildingSMART sample files, IFC.js samples,
or model one in SketchUp/Blender+BlenderBIM). Extend extractor: derive riser height from
geometry when RiserHeight attribute absent; pull Qto_ quantity sets; space heights from
bounding geometry.

### T3 — PDF drawing extraction path (the "AI-assisted" half)
Claude API vision on drawing sheets → same facts schema, confidence per fact, source =
sheet + region. NEVER emit confidence 1.0 from LLM extraction. This is the core
neuro-symbolic story: probabilistic extraction, deterministic judgment, human gate.

### T4 — Review UI
React artifact or small Vite app: results table filterable by status, click-through to
facts + provision text, reviewer can confirm/correct UNCERTAIN facts → re-run →
deterministic re-evaluation. This demonstrates EO4 (human-in-the-loop) for screenshots.

### T5 — Report export
PDF + Excel export of the audit report (EO6). Include per-check provision citation and
fact provenance. BCF export stretch goal.

### T6 — Feasibility evidence document
2–3 pages: architecture diagram, screenshots, sample reports, determinism demonstration
(same input run 3×, identical SHA-256 of report), limitations honestly stated. This is
the TRL 5–6 evidence attached to the proposal.

### T7 — Proposal draft (parallel track from ~July 20)
Map prototype to Essential Outcomes EO1–EO7 point by point. Team section: line up code
consultant / P.Eng collaborator (Fanshawe network). Budget: 18 months, ≤$500K.

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
