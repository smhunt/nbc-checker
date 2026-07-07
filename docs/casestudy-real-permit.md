# Case Study — a real Ontario permit plan through the full pipeline

**Date:** 2026-07-07
**Input:** a real Ontario building-permit drawing (single sheet A1: two floor plans + two elevations) for a change of use — an existing fish market converted to a two-storey dwelling, with a new deck. *The original drawing and its address/designer details are not committed to this public repo; the extracted facts here are anonymized.*

This exercises the whole neuro-symbolic pipeline on a genuine permit document, in its correct jurisdiction, and shows the EO1 safety property holding on real (not synthetic) input.

## What ran

```
permit PDF ─▶ pdf_extractor.extract_tiled (3×3, 200 DPI, LLM per tile, ≤0.89) ─▶ facts ─▶ engine ─▶ report
                                                                                   │
                                          ruleset: rules/obc2024_part9_core.json (Ontario OBC 2024)
```

## Result 1 — tiling dramatically improves extraction

| Extraction mode | Entities | Facts |
|---|---|---|
| Whole sheet (one LLM pass) | 1 | 3 |
| **3×3 tiled, 200 DPI** | **11** | **17** |

At 1/8" scale with four views on one sheet, whole-sheet extraction can't resolve the small annotations. Tiling into overlapping high-DPI crops recovered stairs, doors, windows, and room labels — a ~6× increase — while never inventing a value (one pure-prose tile was skipped, not fabricated).

## Result 2 — every extracted value routed to human review (EO1)

Representative extracted facts (all from the LLM path, confidence ≤ 0.89 by construction):

| Element | Fact | Value | Confidence |
|---|---|---|---|
| Stair | riser height | 200 mm | 0.89 |
| Stair | tread run | **254 mm** | 0.85 |
| Door | height | 2032 mm | 0.75 |
| Window | 1981 × 1067 mm | — | 0.50 |
| Room | use = kitchen / living | — | 0.89 |

Against the Ontario OBC ruleset, the raw extraction produced **0 pass / 0 fail / 28 info-not-available / 2 review**. No pass or fail was issued from an AI-read number — exactly the required behaviour. The stair rules reported *info-not-available* because the drawing never states whether the stairs are private (in-dwelling) or shared, so applicability can't be determined and the engine refuses to guess.

## Result 3 — one human judgement unlocks the checks, still safely

When a reviewer supplies the single applicability fact the drawing doesn't state (`service = private`, a dwelling-unit stair) — the way they would in the review UI — the stair and ceiling checks evaluate, and the run becomes **0 pass / 0 fail / 22 info-not-available / 6 review**. The six now-evaluated checks (stair rise, stair run, ceiling height) all land in **REVIEW**, because the underlying values came from the LLM below the 0.9 threshold. A human still confirms each number before it can decide compliance.

Notably, the extracted **tread run of 254 mm sits 1 mm under the OBC 2024 minimum of 255 mm** — precisely the borderline a reviewer needs surfaced. (The drawing's own title block cites the older 2012 OBC, under which the minimum run was 210 mm and this stair passed — a real illustration of why the jurisdiction *and code edition* must be explicit.)

## What this demonstrates

- The pipeline handles a **real permit drawing**, not just synthetic fixtures.
- **Jurisdiction matters and is now handled:** the plan is Ontario, checked against the Ontario OBC ruleset, not the NBC.
- **EO1 holds on real input:** no AI-extracted number ever produced a pass/fail; everything was human-gated.
- The **honest failure modes are visible:** applicability facts (private/shared, existing/new) are as important as measurements, and today they come from the reviewer, not the drawing.

## Limits surfaced (feeding the roadmap)

- Applicability facts (`service`, `work_status`) are rarely annotated; a production system needs defaults per drawing type plus reviewer confirmation.
- Confidence is self-reported by the LLM and capped; it is a triage signal, not a calibrated probability.
- Change-of-use scoping (existing vs new) is modelled in the engine (`scope: new_work_only`) but the OBC ruleset does not yet tag which rules are new-work-only.

## Reproduce (with your own drawing)

```bash
python3 -c "from extractors.pdf_extractor import extract_tiled; import json; \
  json.dump(extract_tiled('your_sheet.pdf', grid=(3,3)), open('facts.json','w'), indent=2)"
python3 run_check.py rules/obc2024_part9_core.json facts.json --export-pdf --export-xlsx
```
