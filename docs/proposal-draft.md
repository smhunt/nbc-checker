# Proposal — Deterministic AI-Assisted Compliance Checking of Building Permit Applications

| | |
|---|---|
| **Challenge** | Deterministic AI-Assisted Compliance Checking of Building Permit Applications *(working title — official ISC challenge posting could not be located publicly as of 2026-07-07; confirm exact challenge name, challenge number, and Essential Outcomes wording against the official Challenge Notice before submission)* |
| **Program** | Innovative Solutions Canada — Challenge Stream, **Phase 2 (Prototype Development)** |
| **Sponsoring department** | National Research Council Canada (Construction Research Centre) — *assumed, VERIFY* |
| **Proponent** | EcoWorks (contact: sean@ecoworks.ca) |
| **Date** | 2026-07-07 |
| **Status** | **DRAFT** — all bracketed items and "VERIFY" flags must be resolved before the 2026-08-04 2:00 pm ET close |
| **Requested funding** | $475,000 CAD over 18 months (within the ISC Phase 2 ceiling of up to $1M / 2 years) |
| **Prototype repository** | https://github.com/smhunt/nbc-checker |

> **Program-structure notes (verified against official ISC pages, 2026-07-07):**
> - ISC Challenge Stream Phase 2 provides "up to two years and up to $1 million" for prototype development (ISC program eligibility page, ised-isde.canada.ca).
> - **Phase 2 entry normally requires successful completion of Phase 1.** EcoWorks does not hold a Phase 1 award. The ISC Grant Instructions (Call 004) define an **"Entry at Phase 2"** pathway: *"The Entry at Phase 2 option is for innovators who have already proven the feasibility of their solution using sources of funding outside of the ISC program and whose technology is now between TRL 5 to 9."* This proposal is written for that pathway. **CRITICAL: confirm the specific Challenge Notice is open for Entry at Phase 2 — if it is not, this proposal cannot proceed without a Phase 1 award.**
> - Small-business eligibility (verified): for-profit; incorporated in Canada; 499 or fewer FTEs; R&D activities in Canada; ≥50% of annual wages/salaries/fees paid to Canada-based employees and contractors; ≥50% of FTEs with Canada as ordinary place of work; ≥50% of senior executives resident in Canada. **EcoWorks must confirm it satisfies each criterion at time of submission (incorporation status — business decision pending).**
> - Evaluation (per ISC Grant Instructions, Call 004): mandatory criteria include Scope (solution must "clearly demonstrate how the solution meets all of the Essential Outcomes"), Proof of Feasibility and Current TRL, Innovation, and Advance on State of the Art; Additional Outcomes are point-rated (0–10 points); minimum passing score 65 of 130 points.

---

## 1. Problem statement

Municipal building departments across Canada face a permit-review bottleneck. Review of Part 9 (housing and small buildings) permit applications is manual, provision-by-provision work performed by a shrinking pool of qualified plans examiners, while application volumes rise with housing-supply pressure. The consequences are well known to every builder and homeowner: review queues measured in weeks or months, inconsistent interpretations between reviewers and between municipalities, and re-submission cycles triggered by omissions that could have been caught mechanically on day one.

Generic "AI plan review" is not an acceptable answer for a regulatory decision. A permit decision must be **explainable, reproducible, and appealable**: a reviewer, an applicant, and ultimately a court must be able to see exactly which code provision was applied, to which measured value, from which document. A large language model that emits "compliant / non-compliant" is a black box — it can produce different answers on identical inputs, it cannot cite a defensible chain of evidence, and no chief building official can sign their name to it. The regulatory context demands the opposite property: **identical inputs must produce identical results, every time, with a full audit trail.**

The opportunity is a division of labour that plays to the strengths of each technology: probabilistic AI is genuinely good at *reading* messy inputs (drawings, models, schedules); deterministic rule engines are the only defensible way to *judge* them; and human plans examiners must remain the authority wherever the machine is uncertain.

## 2. Proposed solution

EcoWorks proposes a **two-stage neuro-symbolic pipeline** for automated pre-checking of Part 9 permit applications against the National Building Code of Canada 2020:

```
IFC/BIM model ──→ deterministic IFC extractor (confidence = 1.0) ─┐
                                                                  ├─→ facts.json ──→ deterministic rule engine ──→ audited report
PDF drawings ──→ LLM vision extractor (confidence capped ≤ 0.89) ─┘                       │
                                                                        human review gate ┘ (confirm/correct → deterministic re-run)
```

1. **Probabilistic extraction, never judgment.** Generative AI is used only where it is safe and uniquely useful: reading dimension annotations off drawing sheets and translating them into a typed facts schema. Every LLM-extracted fact carries a confidence score that is *hard-capped below the engine's trust threshold*, so no LLM output can ever be treated as ground truth.
2. **Deterministic judgment.** A pure-function rule engine evaluates machine-readable NBC rules (RASE-inspired schema: applicability / requirements / exceptions) against the facts. Four statuses per check — `pass`, `fail`, `info_not_available`, `uncertain` — with a complete audit trail: the provision cited, every fact used, its value, confidence, and source document, and every comparison performed.
3. **Human review gate.** Facts below the confidence threshold, and facts the extractors cannot derive, are routed to a plans examiner, who confirms or corrects them through a review interface. The engine then re-runs deterministically; the human's decision is recorded with provenance, and the original extracted facts are never overwritten.

**Why determinism is the differentiator.** Every result in our reports is reproducible byte-for-byte: the prototype demonstrates three consecutive runs of the full ruleset producing an identical SHA-256 hash of the report, and that hash is embedded in every exported PDF/Excel report so any party can verify the document matches the evaluation. Competing "AI plan review" products either keep the model in the judgment loop (unexplainable) or hand-digitize rules without a published evidence trail. Our rules carry the verbatim NBC sentence they encode, the page source, the verification date, and the reviewer — a chain of custody from published code text to check result. This is a system a chief building official can defend.

## 3. Essential Outcomes mapping

**IMPORTANT CAVEAT:** the official Challenge Notice (with the authoritative Essential Outcomes text) could not be located on public ISC/NRC pages as of 2026-07-07. The "outcome" wording below is **per EcoWorks' interpretation of the challenge as recorded in project planning notes — every row must be VERIFIED against the official posting.** EO5's subject matter is not recorded in our notes at all.

All "prototype evidence today" claims below are true of the repository at https://github.com/smhunt/nbc-checker as of 2026-07-07 (some components in working tree pending commit).

| EO | Outcome (per interpretation — **VERIFY**) | Prototype evidence today | Phase 2 plan to full delivery |
|----|----|----|----|
| **EO1** | No generative model participates in pass/fail judgment; all compliance determinations are deterministic and reproducible | `engine/checker.py` is a pure function of (ruleset, facts) — no model call anywhere in the judgment path. The LLM extraction path (`extractors/pdf_extractor.py`) hard-caps every fact at `MAX_LLM_CONFIDENCE = 0.89`, below the engine's 0.9 trust threshold, so LLM facts can only ever yield `uncertain` (human review), never pass/fail. Determinism demonstrated: 3 consecutive runs → identical SHA-256 report hash. 53-test pytest suite enforces the invariants (incl. FAIL-dominance and confidence gating). | Formalize the invariant as a documented architectural contract with CI-enforced tests; third-party security/design review; determinism verification made a first-class report feature (hash embedded in every export — already prototyped). |
| **EO2** | Extraction of building characteristics from BIM/IFC models | `extractors/ifc_extractor.py` (IfcOpenShell): IfcStairFlight, IfcSpace, IfcWindow via attributes, property sets, Qto_ quantity sets, and geometry fallback (bounding-box z-extent for space heights); all lengths normalized to mm; deterministic facts at confidence 1.0 with per-fact provenance (`model.ifc#<GlobalId>`). 8 extractor tests. | Extend entity coverage (doors, railings/guards, walls, envelope assemblies), geometry-derived facts (riser from flight geometry), validation against real permit-quality IFC from pilot municipalities; IDS/bSDD alignment (ACCORD). |
| **EO3** | Extraction of building characteristics from 2D drawings (PDF) | `extractors/pdf_extractor.py`: LLM vision reads *only explicitly annotated dimensions* from drawing sheets into the same facts schema; per-fact confidence and source ("sheet + region"); confidence capped at 0.89; prompt forbids inference ("NEVER infer a value that is not printed on the drawing"). Sample drawing (`samples/A-201_stair_section.pdf`) and 9 tests. Sample facts include a real low-confidence PDF fact (0.82) that the engine routes to human review. | Harden across real drawing sets from pilot municipalities: multi-sheet packages, schedules, title-block metadata; measure extraction precision/recall against reviewer ground truth; calibrate confidence scoring empirically. |
| **EO4** | Human-in-the-loop review of uncertain/missing information | FastAPI review service (`server/app.py`) + React review UI (`ui/`): results table filterable by status, click-through to facts and provision text; reviewer confirms/corrects `uncertain` facts or supplies `info_not_available` values; overrides are persisted separately with provenance (`"human review: <note> (<date>)"`) and **never mutate the original extracted facts**; engine re-runs deterministically and the report hash proves it. 13 server tests. | Reviewer workflow features (assignment, sign-off, batch review), role-based access, override history views, pilot-driven UX iteration with practicing plans examiners. |
| **EO5** | *(subject matter not recorded in project notes — obtain from official posting)* | Candidate evidence if EO5 concerns traceability/citation: every check result records the NBC provision cited, all facts used with value/confidence/source, and every comparison performed; every rule embeds the verbatim NBC 2020 sentence it encodes plus source/date/reviewer in `verification_notes`. | **VERIFY official text, then map.** |
| **EO6** | Export of compliance reports (PDF/Excel or similar) | `engine/export.py`: PDF (reportlab) and XLSX (openpyxl) exporters, pure functions of the report — deterministic output (timestamps pinned) with the report SHA-256 embedded so a reviewer can verify the document matches the evaluation; per-check provision citation and fact provenance included. 4 export tests. | Municipal formatting requirements from pilots; BCF export for model-based issue round-tripping; e-permitting portal integration formats. |
| **EO7** | Open API for integration with municipal e-permitting systems | FastAPI service already exposes the pipeline over HTTP (report retrieval, fact override endpoints, export) — the seed of the open API. | Publish a versioned, documented OpenAPI specification; authentication/tenancy; integration adapters piloted against at least one municipal e-permitting workflow; reference client. |

**Additional prototype evidence (proof of feasibility, TRL 5–6):**

- **38 machine-readable NBC 2020 Part 9 rules, 100% verified against the published code text** (`rules/nbc2020_part9_core.json`, schema 0.2.0). Every rule carries `verification_notes` with the verbatim NBC quote, source citation, verification date, and reviewer. Coverage: stair geometry (9.8.4.1/9.8.4.2 incl. tread-depth fact-to-fact bounds and 9.8.4.4 uniformity), stair width/headroom (9.8.2), landings (9.8.6.3), handrails (9.8.7.1/9.8.7.4/9.8.7.5), guards (9.8.8.3 encoded as its true multi-context structure, 9.8.8.5 openings), egress windows and window wells (9.9.10.1), room-by-room ceiling heights per Table 9.5.3.1 incl. secondary suites, doorway sizes (9.5.5.1), smoke alarm locations (9.10.19.3), and climate-zone-parameterized energy envelope RSI values (9.36.2.6, conditioned on HRV presence).
- **Verification catches real errors — the core argument for this methodology.** Encoding from memory or secondary sources fails: verification against the published text caught a wrong ceiling-height rule (2300 mm flat — actually the pre-2015/Ontario value; NBC 2020 is 2100 mm over a defined partial area), a structurally wrong guard-height encoding, and a mis-structured egress-window exception. A checker whose rules are not evidence-verified is a liability; ours ships the evidence.
- **Engine capabilities:** four-status output; FAIL dominance (a violation is never masked by a missing fact elsewhere in the same check); exception clauses; fact-to-fact comparisons with offsets (e.g. tread depth ≥ run and ≤ run + 25 mm); confidence gating at a configurable threshold (0.9).
- **Current end-to-end run:** 54 checks against a 25-entity sample dwelling — 26 pass / 11 fail / 16 info-not-available / 1 routed to human review; full audit trail in `reports/last_report.json`.
- **53 passing pytest tests** across engine, extractors (IFC + PDF), exporters, and review server.

## 4. Work plan — 18 months, 3 phases

### Phase A (M1–M6): Ruleset industrialization + Ontario OBC variant

Goal: from 38 rules to production-scale Part 9 coverage, with the rule-authoring pipeline itself as a product.

- **A1.** Rule-authoring toolchain: schema validation, verification-evidence linter (no rule marked verified without quote + source), coverage dashboard against the Part 9 table of contents.
- **A2.** Expand NBC 2020 Part 9 coverage to 150+ verified rules (target divisions: 9.5–9.12, 9.25–9.27, 9.32, 9.36), prioritized by pilot-municipality review-failure statistics.
- **A3.** **Ontario OBC variant ruleset.** The prototype's verification notes already document material NBC-vs-OBC differences per rule (egress windows: per-floor requirement and 1000 mm max sill; guards: 920 mm exit stairs / 1500 mm above 10 m; ceiling heights: OBC retains the 2.3 m/75% structure; handrail heights: 1070 mm only since 2022). Phase A formalizes jurisdiction as a first-class ruleset dimension.
- **A4.** P.Eng/code-consultant review of all rule encodings; adjudicate flagged judgment calls (e.g. guard-opening "prevent passage of a 100 mm sphere" encoded as < 100 vs ≤ 100).
- **A5.** ACCORD/buildingSMART alignment study: map the rule schema to emerging open formats (IDS, bSDD); decision memo on adoption.

**Milestone M6:** ≥150 verified NBC rules + OBC variant layer; independent code-consultant sign-off; toolchain demo.
**Deliverables:** ruleset releases, verification evidence corpus, jurisdiction-variant design report, standards-alignment memo.

### Phase B (M7–M12): Municipal pilot with real permit sets

Goal: prove the pipeline on real applications, with practicing plans examiners in the loop.

- **B1.** Onboard 2 pilot municipalities (targets: Middlesex Centre, City of London, ON — letters of support pending, see §6); data-sharing agreements; anonymized corpus of 30–50 real Part 9 permit sets (drawings; IFC where available).
- **B2.** Extraction hardening against the pilot corpus: IFC coverage extension, multi-sheet PDF packages, measured extraction precision/recall vs. reviewer ground truth, empirical confidence calibration.
- **B3.** Reviewer study: plans examiners use the review UI on live-shadow applications; measure time-to-first-finding, override rates, false-positive/negative rates vs. unaided review.
- **B4.** Report/export iteration to municipal formatting and record-keeping requirements.

**Milestone M12:** pilot interim report — quantitative accuracy and time-savings evidence on real permit sets; reviewer acceptance findings.
**Deliverables:** pilot evaluation report, hardened extractors, calibrated confidence model, updated UI.

### Phase C (M13–M18): Hardening, open API, certification path

Goal: a deployable system and a route to regulatory acceptance.

- **C1.** Versioned, documented open API (OpenAPI spec, authentication, tenancy); integration adapter against at least one municipal e-permitting workflow (EO7).
- **C2.** Security, privacy (drawings are applicants' IP), and reliability hardening; third-party security review; deployment packaging (cloud + on-premises option for municipalities).
- **C3.** Certification/acceptance path: engage NRC Codes Canada and provincial regulators on what evidence a determinism-verified checker needs for formal acceptance as a pre-check aid; publish the determinism verification protocol.
- **C4.** Final prototype delivery to NRC per Phase 2 requirements; dissemination (conference presentations, open documentation).

**Milestone M18:** delivered prototype (TRL 7–8): full pipeline, open API, pilot-validated, certification-path report.
**Deliverables:** prototype delivery package, API documentation, security review report, final project report.

## 5. Budget — total $475,000 CAD (≤ $500,000, within ISC Phase 2 ceiling)

| Line item | Detail | Amount (CAD) |
|---|---|---:|
| Lead developer / architect | Founder, ~60% FTE × 18 months | $144,000 |
| Second developer (contract) | Extraction + UI focus, avg 50% × 12 months | $96,000 |
| Code consultant / P.Eng subcontract | **[NAME TBD — Fanshawe network]**; rule verification sign-off, judgment-call adjudication, OBC variant review | $66,000 |
| Municipal pilot costs | 2 municipalities: data preparation/anonymization, plans-examiner participation, workshops, travel | $48,000 |
| Cloud infrastructure & LLM API usage | Hosting, CI, extraction API costs across pilot corpus | $24,000 |
| Code documents, licences, standards engagement | NBC/OBC document licences; ACCORD/buildingSMART participation | $12,000 |
| Third-party security & privacy review | Phase C hardening gate | $18,000 |
| Dissemination | Conferences, publications, demo events | $15,000 |
| Project administration | Accounting, reporting, agreements | $27,000 |
| Contingency (~5%) | | $25,000 |
| **Total** | | **$475,000** |

*Figures are draft planning numbers; confirm against the Challenge Notice's maximum grant amount and the ISC Grant Instructions cost rules before submission.*

## 6. Team

- **EcoWorks — Sean Hunt (lead).** Solo founder combining AI/software engineering with building-domain knowledge; author of the prototype (rule engine, extractors, verification methodology). *(Corporate status vs. ISC small-business eligibility criteria — business decision pending; confirm incorporation before submission.)*
- **P.Eng / code consultant — [NAME TBD].** To be engaged from the Fanshawe College network; responsible for independent verification sign-off of rule encodings and adjudication of flagged interpretation questions. **Business decision pending.**
- **Letters of support — targets:** Municipality of Middlesex Centre; City of London, ON (building division). Both would anchor the Phase B pilot and supply anonymized permit sets. **Business decisions pending — no commitments in hand as of this draft.**

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **Jurisdictional code variants** (NBC vs. Ontario OBC vs. BCBC) — a national tool checked against the wrong edition is worse than useless | Already engineered for: the prototype's per-rule `verification_notes` document specific Ontario OBC differences (egress-window per-floor rule and sill height; guard heights for exit stairs and >10 m; ceiling-height structure; handrail-height history) and BCBC 2024 reservations. Phase A makes jurisdiction a first-class ruleset dimension with the OBC variant as the proving case. |
| **IFC quality in real permit submissions** — real-world models may lack the attributes/quantity sets the extractor expects, or applicants may submit no BIM at all | Extractor already implements a fallback chain (attributes → property sets → Qto quantity sets → geometry) and reports `info_not_available` rather than guessing. The PDF path is a co-equal input, not an afterthought, because drawings remain the dominant Part 9 submission format. Phase B measures against real permit sets before any claims are made. |
| **LLM extraction accuracy** — vision models will misread drawings | Structurally mitigated, not just monitored: LLM facts are hard-capped at 0.89 confidence, below the engine's 0.9 threshold, so **every** LLM-extracted fact is routed to human review; the prompt forbids inferring un-annotated values; extraction errors can therefore cause reviewer workload, never a wrong automated verdict. Phase B calibrates measured precision/recall. |
| **Rule maintenance burden** — codes change (NBC 2025 published); hand-encoded rules rot | The `verification_notes` evidence trail (verbatim quote + source + date + reviewer per rule) makes every rule re-verifiable and diff-able against a new code edition; Phase A builds the authoring toolchain that enforces it. Our own V1 experience — 3 substantive errors caught in 12 initially-encoded rules — is the existence proof that unverified rules fail and that the evidence discipline works. |
| **Entry at Phase 2 eligibility** — no ISC Phase 1 award held | Proposal targets the official Entry at Phase 2 pathway (outside-funded feasibility, TRL 5–9). Prototype evidence package (feasibility document, determinism demo, test suite, verified ruleset) is the required proof of feasibility. **If the Challenge Notice is not open to Entry at Phase 2, stop and reassess.** |
| **Municipal partnership risk** — pilots depend on letters of support not yet secured | Two candidate municipalities identified; outreach is a pre-submission action item. Pilot design tolerates a single municipality at reduced corpus size. |

## 8. Limitations (honest statement)

Mirroring the project's feasibility evidence, we state plainly what the prototype does **not** yet do:

1. **Coverage is a fraction of Part 9.** 38 verified rules across stairs, guards, handrails, egress windows, ceiling heights, doorways, smoke alarms, and selected 9.36 envelope values — out of hundreds of Part 9 provisions. Phase A exists because coverage, not architecture, is the remaining scale problem.
2. **Derived facts are deliberately not guessed.** Where a value depends on information the extractor lacks (e.g. window unobstructed open area depends on operation type), the fact is left absent and the engine reports `info_not_available`. This is a design principle, but it means real-world runs surface many "info not available" results until extraction deepens.
3. **The IFC extractor has been exercised on generated and open sample models, not on production permit submissions.** Real submission quality is an open empirical question — hence the Phase B pilot.
4. **The PDF extractor reads explicitly annotated dimensions only** and has been exercised on a synthetic sample sheet; multi-sheet real drawing sets are untested. All its output is human-gated by construction.
5. **The 0.9 confidence threshold is an engineering default, not an empirically calibrated value**; Phase B calibrates it and makes it a per-deployment setting.
6. **Some encodings embed interpretation judgment calls** (e.g. guard openings encoded as < 100 mm to "prevent passage" of a 100 mm sphere). These are flagged in `verification_notes` for professional adjudication rather than silently decided.
7. **The tool is a pre-check aid, not a permit decision system.** It is designed to make plans examiners faster and more consistent; the human remains the authority, and nothing in the architecture proposes otherwise.
8. **Zoning bylaws and Parts other than Part 9 are out of scope** for this project.

## 9. Pre-submission checklist (remove before submission)

- [ ] Locate the official Challenge Notice; replace working title, confirm challenge number, sponsoring department, and closing details.
- [ ] Replace every "per interpretation — VERIFY" EO row with the official Essential Outcomes text; obtain EO5's subject; map Additional Outcomes (point-rated, 0–10 pts).
- [ ] **Confirm the challenge is open for Entry at Phase 2** (no Phase 1 award held) and confirm the Notice's maximum grant amount and duration.
- [ ] Confirm EcoWorks incorporation and all ISC small-business eligibility criteria.
- [ ] Secure P.Eng/code-consultant commitment (Fanshawe network) and municipal letters of support (Middlesex Centre, London).
- [ ] Attach feasibility evidence document (T6) with architecture diagram, screenshots, sample reports, determinism SHA demonstration.

---

*Sources for program-structure claims (accessed 2026-07-07):*
- *ISC Challenge Stream overview — https://ised-isde.canada.ca/site/innovative-solutions-canada/en/challenges (Phase 1: up to 6 months / $150,000; Phase 2: up to 2 years / $1,000,000, occasionally up to $2M).*
- *ISC program eligibility and process — https://ised-isde.canada.ca/site/innovative-solutions-canada/en/program-eligibility-and-process (small-business eligibility criteria; phase funding).*
- *ISC Grant Instructions and Procedures, Call 004 — https://ised-isde.canada.ca/site/innovative-solutions-canada/en/grant-instructions-and-procedures-call-004 (Entry at Phase 2 quotation; TRL 5–9; evaluation criteria structure; Essential vs Additional Outcomes assessment; 65/130 minimum score).*
- *NRC Construction Sector Digitalization and Productivity Challenge program — https://nrc.canada.ca/en/research-development/research-collaboration/programs/construction-digitalization-productivity-challenge-program ("Performing R&D to support the development of digital portals for submitting electronic building plans and permits and to support virtual inspections").*
