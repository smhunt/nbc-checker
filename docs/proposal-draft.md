# Proposal — Deterministic AI-Assisted Compliance Checking of Building Permit Applications

| | |
|---|---|
| **Challenge** | **Deterministic artificial intelligence-assisted compliance checking for building permit applications** (official title) |
| **Challenge ID** | e97db6c2-b413-415c-a8f9-63e6a0283748 |
| **Posting** | https://ised-isde.canada.ca/site/innovative-solutions-canada/en/deterministic-artificial-intelligence-assisted-compliance-checking-building-permit-applications |
| **Program** | Innovative Solutions Canada — Challenge Stream, **Phase 2 (Prototype Development), direct entry** |
| **Sponsoring department** | National Research Council Canada (NRC) |
| **Proponent** | EcoWorks (contact: sean@ecoworks.ca) |
| **Date** | 2026-07-07 (challenge opened this day) |
| **Deadline** | **August 4, 2026, 14:00 Eastern** (questions close 10 calendar days before) |
| **Status** | DRAFT — remaining VERIFY flags are business items (§9), not challenge-text items |
| **Requested funding** | $475,000 CAD over 18 months (Notice maximum: $500,000 / up to 18 months; ~2 grants anticipated) |
| **Prototype repository** | https://github.com/smhunt/nbc-checker |

> **Program-structure notes (verified against the official Challenge Notice, 2026-07-07):**
> - **This challenge accepts proposals at Phase 2 only — direct entry, no Phase 1 prerequisite.** Required Technology Readiness Level: **5–9 inclusive**, with proof of feasibility. Our prototype and feasibility evidence (docs/feasibility-evidence.md) target exactly this gate. *(The earlier draft's "Entry at Phase 2" eligibility risk is resolved.)*
> - Funding: maximum **$500,000 CAD per grant**, duration **up to 18 months**, estimated **2 grants**.
> - Small-business eligibility (per Notice): for-profit; incorporated in Canada; ≤499 FTEs; R&D in Canada; ≥50% of annual wages to Canada-based employees/contractors; ≥50% of FTEs primarily working in Canada; ≥50% of senior executives resident in Canada. **EcoWorks must confirm each criterion at submission (incorporation status — business decision pending).**
> - Evaluation: Part 1 mandatory pass/fail — Phase 2 Scope (**all Essential Outcomes must be addressed**), Proof of Feasibility & TRL 5–9 with evidence, Innovation, Advance on State of the Art (0–20 pts). Part 2 point-rated, minimum 65/130: Additional Outcomes (0–10), S&T risks (0–10), project risks (0–10), project plan (0–20), implementation team (0–20), **inclusivity (0–20)**, financial controls (0–10), commercialization strategy (0–10).

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

The ten Essential Outcomes below are **quoted from the official Challenge Notice** (accessed 2026-07-07). All "prototype evidence today" claims are true of the repository at https://github.com/smhunt/nbc-checker as of 2026-07-07.

| EO | Official outcome (abridged quote) | Prototype evidence today | Phase 2 plan to full delivery |
|----|----|----|----|
| **EO1** | "Process 2D drawing files (PDF and/or CAD) and BIM/IFC models … along with additional structured or unstructured data included in a typical Canadian building permit application submission" | Both ingestion paths working: IFC/BIM (`extractors/ifc_extractor.py`, IfcOpenShell — attributes → psets → Qto → geometry fallback) and PDF drawings (`extractors/pdf_extractor.py` — high-DPI tiled LLM vision; validated on a **real Ontario permit sheet**, 17 facts from one dense A1 sheet). Both emit one typed facts schema with per-fact provenance. | CAD (DWG/DXF) ingestion; structured permit-form data (application metadata, schedules); multi-sheet package handling from pilot corpora. |
| **EO2** | "Check code compliance across a range of building typologies as defined in **Part 3 and Part 9** of the NBC" | Part 9 housing: 38 verified NBC 2020 rules + 23-rule Ontario OBC 2024 variant. **Part 3: 35 verified rules delivered** (`rules/nbc2020_part3_core.json`) across the four entry categories — fire separations (Table 3.1.3.1 pairings, closure ratings, corridor separations), occupancy classification and occupant load (Table 3.1.17.1), exits (3.4 widths/rise/landings/guards/treads/headroom/exit count), and accessibility (3.8 entrances, path/ramp/door widths, WC stalls) — same verification discipline, every rule quoted verbatim from the official text. | Phase A deepens Part 3 coverage (travel distance and other topology-dependent rules, remaining table tiers recorded per-rule in verification_notes) and publishes the Part 3/Part 9 typology coverage matrix. |
| **EO3** | "Include a deterministic component(s) that utilizes machine-readable construction codes, machine-executable compliance rules and/or an ontology of construction codes, for consistency, accuracy and repeatability" | The core of the prototype: pure-function rule engine over machine-readable, provision-cited rules; **repeatability demonstrated** — 5 consecutive runs → identical SHA-256 report hash; every rule carries the verbatim code sentence it encodes (`verification_notes`), giving a chain of custody from published text to verdict. 65-test suite enforces the invariants. | Scale the ruleset with the authoring toolchain (schema validation, evidence linter); align the rule model with an ontology/digitalized-code format per EO5. |
| **EO4** | "Involve human-in-the-loop workflows, and provide traceability and auditability of AI-generated compliance checks with reference to applicable code provisions" | Review UI + FastAPI service: reviewer confirms/corrects `uncertain`/missing facts; overrides persist separately with provenance and never mutate extracted facts; deterministic re-run with hash proof. Every check cites its provision and lists every fact used (value/confidence/source document). Validated on the real permit: every LLM-extracted value routed to review; zero AI-decided verdicts. | Reviewer workflow (assignment, sign-off, batch), role-based access, full audit-log export. |
| **EO5** | "Be compatible with one or more digitalized code formats (sample data can be optionally provided by NRC for the project)" | Rules are already a documented machine-readable JSON format (RASE-inspired: applicability/requirements/exceptions) with schema versioning — a working digitalized-code format. | **Request NRC sample data on award**; build a bidirectional mapping between our schema and the NRC/AHJ digitalized-code format; ACCORD/IDS alignment study (also Additional Outcome 1/4). |
| **EO6** | "Generate itemized compliance verification results with at least four categories: Meets (Pass); Does not Meet (Fail); Information Not Available…; Uncertain…" | **Exact match, by design:** the engine's four statuses are precisely `pass` / `fail` / `info_not_available` / `uncertain`, itemized per check with full audit trail. The Notice's parenthetical definitions (missing info in drawing/permit data or ruleset; uncertain) match our semantics (absent facts; sub-threshold confidence or undeterminable applicability). | Category semantics documentation for building officials; per-category workflow guidance in UI. |
| **EO7** | "Include an intuitive user interface (UI) for AEC practitioners or building officials, and/or include open Application Programming Interface(s) (APIs)" | **Both delivered:** React reviewer UI (status-filterable results, provision text with verbatim code quote, override forms, determinism badge) and a FastAPI HTTP API (`/api/state`, `/api/override`, `/api/export/{fmt}`). | OpenAPI spec publication, authentication/tenancy, UX iteration with practicing plans examiners in pilots. |
| **EO8** | "Support Canadian data residency, such as a cloud-based solution in a data centre located in Canada" | Architecture is residency-friendly today: fully self-hostable (pure Python + static UI), runs on-premises with no foreign data egress; the only external call is LLM extraction, which is swappable. | Production deployment on Canadian-region cloud (e.g. AWS/Azure/GCP Canadian regions or OVH Canada) including Canadian-hosted or on-prem model inference for extraction; residency statement in security review. |
| **EO9** | "Export compliance verification results in multiple formats (e.g. PDF, Excel, BIM Collaboration Format)" | PDF and Excel exporters delivered (`engine/export.py`), byte-deterministic with embedded report hash, provision citation and fact provenance per check. | **BCF export** (issues anchored to IFC GlobalIds — our facts already carry them as provenance), promoted from stretch goal to committed Phase C deliverable. |
| **EO10** | "Support compliance verification against both French and English building codes, such as the French version of the National Building Code or the Quebec Construction Code" | Architecture-ready: rulesets are data, not code — the engine is language-agnostic, jurisdiction is a first-class report field, and the Ontario OBC variant already proves the multi-code pattern (23 rules, per-rule difference notes). | **Gap acknowledged — no French ruleset yet.** Phase A adds a French NBC 2020 ruleset (CNB 2020 — the official French edition, same provision numbering, so `verification_notes` quotes swap to French text) and scopes a Quebec Construction Code (Chapter I) variant with a Québec code consultant. Bilingual UI strings. |

### 3a. Additional Outcomes mapping (point-rated, 0–10)

| AO | Official outcome (abridged) | Position |
|----|----|----|
| **AO1** | Compatibility with buildingSMART/ISO standards: ISO 19650, ISO 16739/IFC, BCF, IDS, openBIM | IFC (ISO 16739) ingestion working today via IfcOpenShell with GlobalId-level provenance. Phase A ACCORD/IDS alignment study; Phase C BCF export (EO9). ISO 19650 information-management alignment documented for pilots. |
| **AO2** | ≥90% verification accuracy on simple digitalized rules, ≥80% on complex rules | Phase B pilot measures accuracy against reviewer ground truth on real permit sets — the design gives this a strong starting position: *deterministic* rules cannot vary run-to-run, so accuracy failures reduce to extraction quality and rule-encoding fidelity, both of which our confidence gate and verification evidence trail are built to expose. Targets adopted as Phase B exit criteria. |
| **AO3** | Version tracking of drawings/models/data incl. identity, trust, digital seals/signatures | Foundations exist: every report is content-hashed (SHA-256), facts carry per-document provenance, human overrides are separately persisted with reviewer identity and date. Phase C adds revision tracking across resubmissions and a digital-seal integration study. |
| **AO4** | Configurable data pipeline with an NRC or AHJ digitalized-codes database | Directly aligned with EO5 plan: schema mapping to the NRC format, plus a ruleset-sync mechanism (rules are versioned data files — a codes-database pipeline is an importer, not a re-architecture). |

**Additional prototype evidence (proof of feasibility, TRL 5–6):**

- **38 machine-readable NBC 2020 Part 9 rules, 100% verified against the published code text** (`rules/nbc2020_part9_core.json`, schema 0.2.0). Every rule carries `verification_notes` with the verbatim NBC quote, source citation, verification date, and reviewer. Coverage: stair geometry (9.8.4.1/9.8.4.2 incl. tread-depth fact-to-fact bounds and 9.8.4.4 uniformity), stair width/headroom (9.8.2), landings (9.8.6.3), handrails (9.8.7.1/9.8.7.4/9.8.7.5), guards (9.8.8.3 encoded as its true multi-context structure, 9.8.8.5 openings), egress windows and window wells (9.9.10.1), room-by-room ceiling heights per Table 9.5.3.1 incl. secondary suites, doorway sizes (9.5.5.1), smoke alarm locations (9.10.19.3), and climate-zone-parameterized energy envelope RSI values (9.36.2.6, conditioned on HRV presence).
- **Verification catches real errors — the core argument for this methodology.** Encoding from memory or secondary sources fails: verification against the published text caught a wrong ceiling-height rule (2300 mm flat — actually the pre-2015/Ontario value; NBC 2020 is 2100 mm over a defined partial area), a structurally wrong guard-height encoding, and a mis-structured egress-window exception. A checker whose rules are not evidence-verified is a liability; ours ships the evidence.
- **Engine capabilities:** four-status output; FAIL dominance (a violation is never masked by a missing fact elsewhere in the same check); exception clauses; fact-to-fact comparisons with offsets (e.g. tread depth ≥ run and ≤ run + 25 mm); confidence gating at a configurable threshold (0.9).
- **Current end-to-end run:** 54 checks against a 25-entity sample dwelling — 26 pass / 11 fail / 16 info-not-available / 1 routed to human review; full audit trail in `reports/last_report.json`.
- **Ontario OBC 2024 variant ruleset delivered** (23 rules, 19 verified; per-rule NBC-difference notes) — the multi-jurisdiction pattern EO10 requires, already proven.
- **Validated on a real Ontario permit drawing** (change of use): tiled high-DPI extraction recovered 17 facts (~6× whole-sheet); every LLM value routed to human review — zero AI-decided verdicts on real input; flagged a tread run 1 mm under the OBC minimum (`docs/casestudy-real-permit.md`).
- **65 passing pytest tests** across engine, extractors (IFC + PDF, incl. tiling), exporters, and review server.

## 4. Work plan — 18 months, 3 phases

### Phase A (M1–M6): Ruleset industrialization — Part 9 depth, Part 3 entry, French codes

Goal: from 61 rules (38 NBC + 23 OBC) to production-scale coverage across the Notice's required scope, with the rule-authoring pipeline itself as a product.

- **A1.** Rule-authoring toolchain: schema validation, verification-evidence linter (no rule marked verified without quote + source), coverage dashboard against the Part 9 and Part 3 tables of contents.
- **A2.** Expand NBC 2020 Part 9 coverage to 150+ verified rules (target divisions: 9.5–9.12, 9.25–9.27, 9.32, 9.36), prioritized by pilot-municipality review-failure statistics.
- **A3.** **Part 3 expansion (EO2):** the four entry categories are already delivered in the prototype (35 verified rules: occupancy 3.1.2/3.1.17, fire separations 3.1.3/3.1.8/3.3, exits 3.4, accessibility 3.8). Phase A adds travel distance and other topology-dependent rules, the stricter tiers recorded per-rule in verification_notes (e.g. 1 100 mm multi-storey exit stairs, Group B2 vertical rise, remaining closure-table rows), and publishes the Part 3/Part 9 typology coverage matrix.
- **A4.** **Jurisdiction/language variants (EO10):** the delivered Ontario OBC 2024 variant (23 rules, per-rule NBC-difference notes) proves the multi-code pattern. Add the **French NBC (CNB 2020)** ruleset — same provision numbering, French verbatim quotes — and scope a Quebec Construction Code (Chapter I) variant with a Québec code consultant. Bilingual UI strings.
- **A5.** P.Eng/code-consultant review of all rule encodings; adjudicate flagged judgment calls (e.g. guard-opening "prevent passage of a 100 mm sphere" encoded as < 100 vs ≤ 100).
- **A6.** Digitalized-code format compatibility (EO5/AO4): request NRC sample data; map our schema bidirectionally to the NRC/AHJ format; ACCORD/buildingSMART (IDS, bSDD) alignment memo (AO1).

**Milestone M6:** ≥150 verified NBC Part 9 rules + first Part 3 categories + OBC variant + CNB (French) ruleset started; independent code-consultant sign-off; toolchain demo.
**Deliverables:** ruleset releases (NBC-EN, NBC-FR, OBC), Part 3 coverage matrix, verification evidence corpus, NRC-format mapping memo, standards-alignment memo.

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
- **C2.** Security, privacy (drawings are applicants' IP), and reliability hardening; third-party security review; **Canadian data-residency deployment (EO8)** — Canadian-region cloud with Canadian-hosted or on-prem model inference for the extraction path; on-premises packaging for municipalities.
- **C3.** **BCF export (EO9/AO1)** — compliance issues anchored to IFC GlobalIds (already carried as fact provenance); revision tracking across resubmissions and digital-seal integration study (AO3).
- **C4.** Certification/acceptance path: engage NRC Codes Canada and provincial regulators on what evidence a determinism-verified checker needs for formal acceptance as a pre-check aid; publish the determinism verification protocol.
- **C5.** Final prototype delivery to NRC per Phase 2 requirements; dissemination (conference presentations, open documentation).

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
| **Part 3 depth (EO2)** — the prototype's 35 Part 3 rules cover the dimensional/tabular categories; travel distances and fire-compartment topology need spatial facts the extractors do not yet supply | The delivered rules prove the schema is typology-generic in practice (mixed-use sample runs both Part 3 and Part 9 rulesets). Phase A expands to topology-dependent rules alongside Phase B extraction hardening; coverage matrix reported honestly per milestone, with conservative-encoding notes (never-lenient) recorded per rule. |
| **Bilingual codes (EO10)** — no French ruleset yet; Quebec Construction Code has provincial amendments | CNB 2020 is the same code with the same numbering — rulesets are data, so the French variant is a translation-and-reverify task, not new engineering (the OBC variant already proved the multi-code pattern). Québec code consultant budgeted for the QCC variant scope. |
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
8. **Part 3 coverage is entry-level, not deep** — 35 verified rules across the four Phase A categories (fire separations, occupancy, exits, accessibility); travel-distance and topology-dependent provisions remain Phase A work, and stricter tiers not yet encoded are documented per-rule as conservative gaps. **No French ruleset exists yet** (EO10; Phase A deliverable). Zoning bylaws remain out of scope — the Notice concerns building-code compliance.

## 9. Pre-submission checklist (remove before submission)

- [x] ~~Locate the official Challenge Notice~~ — found 2026-07-07 (opened same day); title, ID, sponsor, deadline confirmed above.
- [x] ~~Replace interpolated EO rows with official text~~ — all ten official EOs + four Additional Outcomes mapped (§3, §3a).
- [x] ~~Confirm Phase 2 entry~~ — the Notice accepts **direct Phase 2 proposals** (TRL 5–9); no Phase 1 prerequisite. Max $500,000 / 18 months confirmed; budget fits.
- [ ] Confirm EcoWorks incorporation and all ISC small-business eligibility criteria (**hard gate — for-profit Canadian corporation required**).
- [ ] Secure P.Eng/code-consultant commitment (Fanshawe network) and municipal letters of support (Middlesex Centre, London) — feeds the 20-pt Implementation Team criterion.
- [ ] Address the point-rated criteria explicitly in the submission form: project plan (20 pts), team (20 pts), **inclusivity (20 pts — prepare a substantive plan)**, financial controls (10), commercialization (10), S&T + project risks (10+10).
- [ ] Add a Québec code consultant contact for the EO10/QCC scope (budget line exists).
- [ ] Consider requesting NRC sample digitalized-code data (offered in EO5) via the question process — **questions close 10 days before the 2026-08-04 deadline (~July 25)**.
- [ ] Attach feasibility evidence document (docs/feasibility-evidence.md) incl. the real-permit case study, determinism SHA demonstration, and test-suite results.

---

*Sources (accessed 2026-07-07):*
- ***Official Challenge Notice** — https://ised-isde.canada.ca/site/innovative-solutions-canada/en/deterministic-artificial-intelligence-assisted-compliance-checking-building-permit-applications (all Essential/Additional Outcomes quoted; $500K/18 months/2 grants; direct Phase 2 entry TRL 5–9; opened 2026-07-07, closes 2026-08-04 14:00 ET; evaluation criteria).*
- *ISC program eligibility and process — https://ised-isde.canada.ca/site/innovative-solutions-canada/en/program-eligibility-and-process (small-business eligibility criteria).*
- *ISC Grant Instructions and Procedures, Call 004 — https://ised-isde.canada.ca/site/innovative-solutions-canada/en/grant-instructions-and-procedures-call-004 (evaluation criteria structure; 65/130 minimum score).*
