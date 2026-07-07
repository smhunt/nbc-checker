# Feasibility Evidence — Deterministic AI-Assisted NBC Compliance Checking

**Proponent:** EcoWorks (sean@ecoworks.ca)
**Date:** 2026-07-07
**Purpose:** TRL 5–6 feasibility evidence for the NRC ISC Phase 2 challenge, *Deterministic AI-Assisted Compliance Checking of Building Permit Applications*.
**Status:** Working prototype. All figures below are reproducible from this repository.

---

## 1. The problem

Municipal building-permit review is slow, inconsistent between reviewers, and does not scale with housing demand. Off-the-shelf AI is unacceptable for the decision itself: a generative model that "reads a plan and says pass/fail" cannot be audited, cannot cite the code provision it applied, and can silently hallucinate a verdict. Regulatory decisions require **reproducibility and a provenance trail**, which a probabilistic model cannot provide.

## 2. The approach: neuro-symbolic, deterministic core

The prototype separates *reading the building* (probabilistic, AI-assisted) from *judging the building* (deterministic, symbolic). The two stages communicate only through a facts JSON document, so no generative output ever reaches the pass/fail decision.

```
   INPUTS                 EXTRACTION (probabilistic)      FACTS         JUDGMENT (deterministic)
 IFC/BIM model ──▶ ifc_extractor  (confidence 1.0) ──┐
                                                      ├─▶ facts.json ─▶ engine/checker.py ─▶ report
 PDF drawings ──▶ pdf_extractor  (confidence ≤0.89) ──┘                 (pure function; no LLM)
```

- **Extraction** reads dimensions from an IFC model (directly, confidence 1.0) or from PDF drawings (via an LLM, confidence hard-capped below the review threshold).
- **Judgment** compares each fact against a machine-readable NBC 2020 rule and emits one of four statuses. It is a pure function of (ruleset, facts): identical inputs always produce an identical report.
- **Human gate**: anything extracted by an LLM, or otherwise below the 0.9 confidence threshold, is routed to `UNCERTAIN` and cannot become PASS/FAIL until a human confirms it.

This directly answers the challenge's central constraint (EO1): **no generative model participates in the compliance judgment.**

## 3. What is implemented today

| Capability | Evidence in repo |
|---|---|
| Machine-readable NBC 2020 ruleset | `rules/nbc2020_part9_core.json` — **38 rules, all verified** against the official published code text |
| Every rule cites its provision + carries a verbatim code quote | `verification_notes` object on every rule (quote, sources, date, reviewer) |
| Deterministic 4-status engine with full audit trail | `engine/checker.py` (~240 LoC, pure function) |
| Fact-to-fact comparison (e.g. tread depth vs run) | `value_fact` + `offset` operator |
| Automated regression suite | `tests/` — **53 tests**, all passing |
| IFC/BIM extraction (attributes, Qto sets, geometry, derived risers) | `extractors/ifc_extractor.py`; tested against real open house models |
| LLM PDF-drawing extraction, confidence-capped | `extractors/pdf_extractor.py` (cap 0.89, enforced in code + tested) |
| Human-in-the-loop review UI | `ui/` (React) + `server/` (FastAPI); confirm/correct → deterministic re-run |
| Auditable report export | `engine/export.py` — PDF + Excel, byte-deterministic |
| Determinism demonstration | `docs/determinism_demo.sh` |

### Coverage of the ruleset (NBC 2020 Part 9)

Stairs (rise 9.8.4.1, run 9.8.4.2, tread depth 9.8.4.2.(2), width 9.8.2.1, headroom 9.8.2.2, uniformity 9.8.4.4, landings 9.8.6.3), handrails (required 9.8.7.1, height 9.8.7.4, clearance 9.8.7.5), guards (height 9.8.8.3 across its four sentence cases, openings 9.8.8.5), egress windows (9.9.10.1 incl. well clearance), ceiling heights (Table 9.5.3.1, all room types + secondary suites), doorway sizes (Table 9.5.5.1), smoke alarms (9.10.19.3), and a climate-zone-parameterized energy-envelope demo (9.36.2.6 wall/ceiling RSI, zones 5–6).

## 4. Determinism demonstration (the core claim)

`docs/determinism_demo.sh` runs the engine on identical inputs five times and hashes each report:

```
run 1: 61fcda2595da28740aca35a583cbaaae85ff1d6c9957ddd3b5c0224021a19e3d
run 2: 61fcda2595da28740aca35a583cbaaae85ff1d6c9957ddd3b5c0224021a19e3d
run 3: 61fcda2595da28740aca35a583cbaaae85ff1d6c9957ddd3b5c0224021a19e3d
run 4: 61fcda2595da28740aca35a583cbaaae85ff1d6c9957ddd3b5c0224021a19e3d
run 5: 61fcda2595da28740aca35a583cbaaae85ff1d6c9957ddd3b5c0224021a19e3d
PASS: all 5 runs produced one identical SHA-256 — deterministic.
```

A generative model cannot guarantee this. Our engine can, and every check in the report cites the exact NBC sentence it applied.

## 5. Verification methodology — evidence the approach is necessary

Every rule value was checked against the official NRC-published NBC 2020 PDF (kept locally, not redistributed for copyright reasons). This exercise itself is evidence: **encoding rules "from memory" produced three material errors that verification caught**, each of which a naive AI checker would have shipped silently:

1. **Ceiling height** was encoded as a flat 2300 mm minimum. The real NBC 2020 rule is 2100 mm over a *partial area* (the lesser of the room area or a per-room-type figure). The 2300 mm value is pre-2015 national code, retained only in Ontario's OBC. A checker shipping it would have failed compliant homes.
2. **Guard heights** had the wrong logical structure — a fall-height trigger instead of the code's location-based sentences (interior in-unit vs exterior single-dwelling vs default). Re-encoded as four rules keyed on guard context.
3. **Egress-window exceptions** were misattributed; the only true exception is a sprinklered suite.

The lesson for the proposal: determinism plus a **verifiable evidence trail per rule** is not optional polish — it is what makes the tool trustworthy for regulatory use.

## 6. The review interface (human-in-the-loop, EO4)

The reviewer UI (`https://dev.ecoworks.ca:3029` when running) presents every check as a filterable table by status. Selecting a check opens a detail panel showing:

- the verbatim NBC 2020 provision text and its source citation,
- every fact used, with its value, **confidence, and provenance** (e.g. `A-201 Stair Sections.pdf p.2 (LLM extraction)` at confidence 0.82, highlighted amber as below-threshold),
- for `UNCERTAIN`/`INFO NOT AVAILABLE` facts, an inline **confirm/correct** form.

When a reviewer confirms a value, it is stored as a confidence-1.0 human fact (source `human review: <note> <date>`) and the engine re-runs deterministically. Live-verified end to end: an LLM-extracted handrail height (0.82, `UNCERTAIN`) becomes `PASS` on confirmation, and reverts on undo — with the report SHA changing predictably each time. A determinism badge in the header displays the current report hash.

*(Screenshots of the results table and the detail/override panel are captured from the live UI; the running instance is the canonical demo.)*

## 7. Real-world findings (honest limitations)

Testing the IFC extractor against real open house models (KIT FZK-Haus, buildingSMART samples) surfaced constraints that shape the Phase 2 plan:

- **`IfcStairFlight` is rare in real exports.** Real models often carry only `IfcStair` with stair data in vendor-specific property sets (e.g. German ArchiCAD psets). Production extraction needs vendor-pset mapping and geometry-based step analysis.
- **Space heights and window dimensions are reliably present** via base-quantity sets — the trusted path covers these well.
- **Room-use detection needs internationalization** (FZK's rooms are named in German), and requires classification references for robust use-type assignment.
- **Geometry-derived ceiling height is slab-to-slab**, generally exceeding finished ceiling height — flagged in the fact's source string, never silently preferred over authored values.
- **Jurisdiction:** all values are national NBC 2020. Ontario's OBC differs materially on several encoded rules (egress, guards, ceilings) — a per-jurisdiction ruleset variant is required for an Ontario pilot. The prototype already documents these differences per rule.
- **Partial-area and sloped-ceiling provisions** are acknowledged in rule notes but not yet machine-evaluated (they need area/topology facts).
- **LLM extraction accuracy** is mitigated structurally, not by trust: every LLM fact is human-gated by the confidence cap.

## 8. Reproduce this evidence

```bash
pip install ifcopenshell pytest fastapi uvicorn reportlab openpyxl --break-system-packages
python3 -m pytest tests/ -q                                              # 53 tests
python3 run_check.py rules/nbc2020_part9_core.json samples/sample_dwelling_facts.json
python3 run_check.py rules/nbc2020_part9_core.json --ifc samples/smoke_test.ifc
./docs/determinism_demo.sh                                               # identical SHA-256 x5
# Review app: uvicorn server.app:app --port 3099 ... ; cd ui && npm run dev
```
