# NBC Checker T1–T7 Sprint Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete sprint tasks T1–T7: expand the verified ruleset to ~28 rules, extract from real IFC models, add the LLM PDF-drawing extraction path, build the human-review UI, export reports, assemble TRL 5–6 feasibility evidence, and draft the ISC proposal.

**Architecture:** Keep the two-stage neuro-symbolic pipeline unchanged (probabilistic extractors → facts JSON → deterministic engine). Add one engine capability (fact-to-fact comparison), a second extractor (`claude` CLI vision on PDFs, confidence-capped), a FastAPI reviewer backend that re-runs the engine on human-corrected facts, and a Vite/React UI on top.

**Tech Stack:** Python 3 (engine, extractors, FastAPI backend, reportlab/openpyxl exports), `claude` CLI headless for vision extraction (no API key on this machine), Vite + React + TypeScript for the UI, pytest for the new test suite.

## Global Constraints

- **EO1 invariant:** no generative model participates in pass/fail judgment. LLM-extracted facts are confidence-capped at **0.89** (< `CONFIDENCE_THRESHOLD` 0.9) so every LLM fact routes to human review in v1.
- **V1 discipline continues:** every NEW rule must be verified against `reference/nbc2020.txt` (official NRC extract, gitignored) at encoding time — quote + sources + date in `verification_notes`, else `verified_against_code_text: false`.
- **Determinism:** identical inputs → byte-identical reports. No timestamps inside report JSON (keep them in filenames/UI only).
- Don't guess derived facts; absent facts → `info_not_available`.
- **Ports (registered in ~/.claude/PORTS.md before first server start):** Frontend **3029** (Vite), Backend **3099** (FastAPI). HTTPS on both via `~/Code/.traefik/certs/{cert,key}.pem`; user-facing URL `https://dev.ecoworks.ca:3029`.
- House rules: CHANGELOG.md at root; docs/README.md; ChangelogModal (Changelog / How It Works / Roadmap tabs) in the UI; commit after every task; leave servers running when done.
- Python deps installed with `pip3 install <pkg> --break-system-packages`.

---

## Phase 1 (T1) — Engine: fact-to-fact comparisons + ruleset expansion to ~28 verified rules

### Task 1.1: pytest harness + engine regression tests

**Files:**
- Create: `tests/__init__.py` (empty), `tests/test_checker.py`
- Test: `tests/test_checker.py`

**Interfaces:**
- Consumes: `engine.checker.run_ruleset(ruleset: dict, facts: dict) -> dict`, `check_rule(rule, entities)`
- Produces: the pytest suite later tasks extend. Helper `mk_rule(**overrides) -> dict` and `mk_entity(**attrs) -> dict` used by all engine tests.

- [ ] **Step 1:** `pip3 install pytest --break-system-packages`
- [ ] **Step 2:** Write `tests/test_checker.py` with helpers and tests locking CURRENT behavior:

```python
import json
from engine.checker import run_ruleset, check_rule, Status

def mk_rule(**over):
    r = {
        "rule_id": "T-1", "provision": "TEST", "title": "t",
        "applies_to": {"entity_type": "thing", "where": {}},
        "requires": {"all": [{"fact": "x_mm", "op": ">=", "value": 100}]},
        "exceptions": [], "unit_system": "mm",
    }
    r.update(over)
    return r

def mk_entity(**attrs):
    return {"entity_type": "thing", "id": "e1", "name": "E1", "attributes": attrs}

def one(rule, entity):
    rs = check_rule(rule, [entity])
    assert len(rs) == 1
    return rs[0]

def test_pass():           assert one(mk_rule(), mk_entity(x_mm=150)).status == Status.PASS
def test_fail():           assert one(mk_rule(), mk_entity(x_mm=50)).status == Status.FAIL
def test_absent_fact():    assert one(mk_rule(), mk_entity()).status == Status.INFO_NOT_AVAILABLE
def test_low_confidence():
    e = mk_entity(x_mm={"value": 150, "confidence": 0.8, "source": "pdf"})
    assert one(mk_rule(), e).status == Status.UNCERTAIN
def test_fail_dominates():
    r = mk_rule(requires={"all": [
        {"fact": "x_mm", "op": ">=", "value": 100},
        {"fact": "y_mm", "op": ">=", "value": 100}]})
    assert one(r, mk_entity(x_mm=50)).status == Status.FAIL
def test_where_skips():
    r = mk_rule(applies_to={"entity_type": "thing", "where": {"kind": "a"}})
    assert check_rule(r, [mk_entity(x_mm=150, kind="b")]) == []
def test_exception_waives():
    r = mk_rule(exceptions=[{"description": "d", "fact": "waived", "op": "==", "value": True}])
    res = one(r, mk_entity(x_mm=50, waived=True))
    assert res.status == Status.PASS
def test_determinism():
    rs = {"ruleset_id": "t", "code_edition": "t", "rules": [mk_rule()]}
    f = {"project": {}, "entities": [mk_entity(x_mm=150)]}
    assert json.dumps(run_ruleset(rs, f)) == json.dumps(run_ruleset(rs, f))
```

- [ ] **Step 3:** Run `python3 -m pytest tests/ -q` → all pass (these lock existing behavior; if any fails, STOP — bug found, fix engine first).
- [ ] **Step 4:** Commit `test: add pytest regression suite for engine`.

### Task 1.2: fact-to-fact comparison (`value_fact` + `offset`)

**Files:**
- Modify: `engine/checker.py` (requirement loop, ~line 160)
- Test: `tests/test_checker.py`

**Interfaces:**
- Produces: requirement schema extension — `{"fact": F, "op": OP, "value_fact": G, "offset": N}` compares F against (value of G + N). `value` and `value_fact` are mutually exclusive. If G absent → INFO_NOT_AVAILABLE; G low-confidence → UNCERTAIN (same gating as F).

- [ ] **Step 1:** Add failing tests:

```python
def vf_rule():
    return mk_rule(requires={"all": [
        {"fact": "depth_mm", "op": ">=", "value_fact": "run_mm", "offset": 0},
        {"fact": "depth_mm", "op": "<=", "value_fact": "run_mm", "offset": 25}]})

def test_value_fact_pass():   assert one(vf_rule(), mk_entity(depth_mm=260, run_mm=255)).status == Status.PASS
def test_value_fact_fail():   assert one(vf_rule(), mk_entity(depth_mm=290, run_mm=255)).status == Status.FAIL
def test_value_fact_ref_absent(): assert one(vf_rule(), mk_entity(depth_mm=260)).status == Status.INFO_NOT_AVAILABLE
def test_value_fact_ref_uncertain():
    e = mk_entity(depth_mm=260, run_mm={"value": 255, "confidence": 0.5, "source": "pdf"})
    assert one(vf_rule(), e).status == Status.UNCERTAIN
```

- [ ] **Step 2:** Run → 4 fail (KeyError 'value').
- [ ] **Step 3:** Implement in the `for req in rule["requires"]["all"]` loop: resolve the comparison target before `OPS[...]`:

```python
# inside the requirement loop, replacing the direct use of req["value"]:
if "value_fact" in req:
    ref = _lookup(entity, req["value_fact"])
    facts_used.append({"fact": ref.name, "value": ref.value,
                       "confidence": ref.confidence, "source": ref.source,
                       "present": ref.present})
    if not ref.present:
        status = Status.INFO_NOT_AVAILABLE
        detail_parts.append(f"'{req['value_fact']}' (comparison reference) not found in extracted model")
        continue
    if ref.confidence is not None and ref.confidence < CONFIDENCE_THRESHOLD:
        if status == Status.PASS:
            status = Status.UNCERTAIN
        detail_parts.append(
            f"'{req['value_fact']}'={ref.value} (comparison reference) extracted at confidence "
            f"{ref.confidence:.2f} < {CONFIDENCE_THRESHOLD} — requires human review")
        continue
    target = ref.value + req.get("offset", 0)
    target_desc = f"{req['value_fact']}+{req.get('offset', 0)} ({target})"
else:
    target = req["value"]
    target_desc = str(target)
```
then use `target` in the comparison and `target_desc` in the comparison/violation strings.

- [ ] **Step 4:** Run full suite → all pass. Re-run both sample suites → summaries unchanged (9/4/3/1, 1/1/3/0).
- [ ] **Step 5:** Commit `feat: engine supports fact-to-fact comparisons (value_fact + offset)`.

### Task 1.3: encode + verify new rules, batch A — stairs/handrails/guards completions

Every rule in Tasks 1.3–1.5 follows the same procedure: (a) grep `reference/nbc2020.txt` for the article, (b) read the sentence(s), (c) encode with sentence-level provision cite, (d) fill `verification_notes` (quote, sources incl. "NBC 2020 official PDF … verbatim in reference/nbc2020.txt", verified_date, reviewer), (e) `verified_against_code_text: true` only if quote matches the extract.

**Files:**
- Modify: `rules/nbc2020_part9_core.json`, `samples/sample_dwelling_facts.json` (facts to exercise each new rule)

Rules to add (candidate values — MUST be corrected to whatever the reference text says):
1. `NBC-9.8.4.2-tread-depth` — depth ≥ run, ≤ run+25 (Sentence 9.8.4.2.(2), uses value_fact; facts `tread_depth_mm`,`tread_run_mm`)
2. `NBC-9.8.2.1-width-shared` — shared/exit stairs ≥900 (Sentence 9.8.2.1.(1); `where {"service": "shared"}`)
3. `NBC-9.8.2.2-headroom-shared` — ≥2050 (Sentence 9.8.2.2.(2); `where {"service": "shared"}`)
4. `NBC-9.8.4.4-uniformity` — riser/run uniformity tolerances (grep "9.8.4.4"; encode max deviation facts `riser_range_mm`, `run_range_mm`)
5. `NBC-9.8.6.3-landing-length` — landing dimensions (grep "9.8.6"; entity `landing`)
6. `NBC-9.8.7.1-handrail-required` — where handrails required (presence: entity stair_flight fact `has_handrail == true`; applicability per sentence — likely width/riser-count triggers)
7. `NBC-9.8.7.5-handrail-clearance` — clearance behind handrail ≥50 mm (already seen in extract at 9.8.7.5)
8. `NBC-9.9.10.1-window-well` — clearance ≥760 mm (Sentence (3); entity window, fact `window_well_clearance_mm`, `where {"opens_into_window_well": true}`)

- [ ] Encode all 8 with verification (procedure above); add sample entities: a shared stair flight, a landing, tread_depth on stair-01, a window-well window.
- [ ] `python3 -m pytest tests/ -q` pass; run both suites; eyeball every new rule fires at least once in the facts suite.
- [ ] Commit `feat: T1 batch A — 8 verified stair/handrail/guard rules`.

### Task 1.4: batch B — ceiling table rows + secondary suite + doors

Rules 9–16 (same procedure):
9. `NBC-9.5.3.1-ceiling-kitchen` (2100, table row), 10. `-ceiling-bedroom-master` (2100), 11. `-ceiling-bedroom-other` (2100), 12. `-ceiling-bath` (2100), 13. `-ceiling-hall` (2100 whole space), 14. `-basement-clear` (2000 clear; fact `clear_height_mm`)
15. `NBC-9.5.3.1-ceiling-secondary-suite` — 1950 (Sentence (2); `where {"in_secondary_suite": true}`; the primary living/dining rule gets `where {"in_secondary_suite": {"op": "!=", "value": true}}`? NO — engine `where` equality on missing fact yields INFO_NOT_AVAILABLE noise. Instead: room rules stay as-is; secondary-suite rooms carry `room_use: "secondary_suite_room"`. Decide at encoding; document choice in verification_notes.)
16. `NBC-9.5.5.1-doorway-height` + width rows for entrance/interior doors (grep "9.5.5"; entity `door`, facts `clear_width_mm`, `height_mm`, `door_location`)

- [ ] Encode + verify + sample entities (kitchen, master bedroom, unfinished basement, entrance door) + pytest + both suites.
- [ ] Commit `feat: T1 batch B — ceiling table, secondary suite, doorway rules`.

### Task 1.5: batch C — smoke alarms + 9.36 parameterized envelope demo

17. `NBC-9.10.19.3-smoke-alarm-storey` — presence per storey (entity `storey`, fact `has_smoke_alarm == true`; verify trigger text in 9.10.19)
18. `NBC-9.10.19.3-smoke-alarm-sleeping` — alarm outside each sleeping area (entity `sleeping_area`, fact `smoke_alarm_within_5m == true` — encode per actual sentence)
19–20. `NBC-9.36.2.6-wall-rsi-zone{5,6}` — effective RSI for above-grade walls by climate zone (grep "9.36.2.6" + Table; entity `wall_assembly`, `where {"climate_zone": "5"}`, fact `effective_rsi`; without HRV vs with HRV columns — encode the without-HRV column, note the other). This is the parameterized-rule demo from the plan.

- [ ] Encode + verify + sample entities (2 storeys, sleeping area, wall assembly zone 5) + pytest + both suites. Target total ≥26 rules, ALL with `verified_against_code_text: true`.
- [ ] Update README rule count; commit `feat: T1 batch C — smoke alarm + climate-zone envelope rules (ruleset ~28)`.

## Phase 2 (T2) — Real IFC models + extractor extensions

### Task 2.1: fetch real models + extraction smoke report

**Files:**
- Create: `samples/fetch_models.sh` (curl with -f, models land in `samples/external/`, gitignored)
- Modify: `.gitignore` (+ `samples/external/`)

Model sources (try in order, keep what downloads):
- `https://www.ifcwiki.org/images/e/e3/AC20-FZK-Haus.ifc` (KIT FZK-Haus, IFC4 detached house)
- `https://github.com/buildingSMART/Sample-Test-Files/raw/master/IFC%204.0/BuildingSMARTSpec/wall-with-opening-and-window.ifc` (fallback minimal)
- `https://www.ifcwiki.org/images/b/b1/AC20-Institute-Var-2.ifc` (larger, optional)

- [ ] Write + run fetch script; `python3 extractors/ifc_extractor.py samples/external/AC20-FZK-Haus.ifc | head -50` to see what v1 extracts (expect gaps — that drives 2.2).
- [ ] Commit `feat: fetch script for real IFC test models`.

### Task 2.2: extractor extensions (Qto sets, geometry-derived heights, riser derivation)

**Files:**
- Modify: `extractors/ifc_extractor.py`
- Create: `tests/test_ifc_extractor.py`
- Modify: `samples/generate_sample_ifc.py` (add Qto_StairFlightBaseQuantities, a window with dims, a space with height pset — so tests don't depend on downloads)

**Interfaces:**
- Produces: same facts schema; new derivations, each with `source` explaining derivation, confidence 1.0 ONLY for values read/computed deterministically from model data:
  - `_find_qto(entity, qto_name, prop)` — read `Qto_StairFlightBaseQuantities.RiserHeight/TreadLength`, `Qto_SpaceBaseQuantities.Height`
  - stair riser fallback: if `NumberOfRisers` present AND flight height derivable from Qto `Height` → `riser_height_mm = height/number_of_risers`, source notes `derived: Qto height / NumberOfRisers`
  - space ceiling height fallback: geometry bbox z-extent via `ifcopenshell.geom` (settings USE_WORLD_COORDS), only when no pset/Qto height; source notes `derived: geometry bbox`. NOTE: bbox height = slab-to-slab of the space shape, generally ≥ finished ceiling height — document as measurement caveat in source string; do NOT silently prefer it over psets.
- [ ] TDD: extend generator, write tests (riser from attribute, riser from Qto fallback, riser derived from height/count, space height from pset, window dims), implement, `python3 -m pytest tests/ -q`.
- [ ] Run `run_check.py --ifc samples/external/AC20-FZK-Haus.ifc` and `--ifc samples/smoke_test.ifc`; eyeball; record findings in progress.md.
- [ ] Commit `feat: T2 — Qto/geometry-derived facts in IFC extractor`.

## Phase 3 (T3) — PDF drawing extraction via claude CLI (the AI-assisted half)

### Task 3.1: sample drawing generator

**Files:**
- Create: `samples/generate_sample_drawing.py` (matplotlib: stair section with dimension annotations "R 190", "T 255", "handrail 920 above nosing", title block "A-201"), output `samples/A-201_stair_section.pdf` (committed — it's our own artifact)

- [ ] `pip3 install matplotlib --break-system-packages` (if missing); write generator; run; visually check PDF.
- [ ] Commit `feat: sample stair-section drawing for PDF extraction demo`.

### Task 3.2: pdf_extractor with confidence cap

**Files:**
- Create: `extractors/pdf_extractor.py`
- Create: `tests/test_pdf_extractor.py`
- Modify: `run_check.py` (add `--pdf <path>` input mode)

**Interfaces:**
- Produces: `extract(pdf_path: str, runner=run_claude) -> dict` (facts schema). `runner(prompt: str, pdf_path: str) -> str` shells out to `claude -p <prompt> --output-format json` with the PDF attached (`claude -p` supports file references in the prompt: `Read the drawing at <abs path>`); test injects a fake runner.
- **Invariant enforcement in code:** `MAX_LLM_CONFIDENCE = 0.89`; every fact confidence = `min(model_reported, MAX_LLM_CONFIDENCE)`; if model omits confidence → 0.5. Source = `"<pdf name> p.<n> (LLM extraction: <region/note>)"`. A unit test asserts no fact can exceed 0.89 even if the fake runner returns 1.0.

Extraction prompt (verbatim in module):
```
You are a drawing-takeoff assistant. Extract ONLY dimensions explicitly annotated
on this architectural drawing. Return JSON: {"entities": [{"entity_type": ...,
"id": ..., "name": ..., "attributes": {"<fact>": {"value": <number>,
"confidence": <0..1 your certainty the annotation says this>,
"source": "<sheet> <where on sheet>"}}}]}
Known entity_types/facts: stair_flight (riser_height_mm, tread_run_mm,
clear_width_mm, headroom_mm, service), handrail (height_above_nosing_mm),
guard (guard_height_mm, fall_height_mm, guard_context, max_opening_mm),
room (room_use, ceiling_height_mm), window (...), door (...).
NEVER infer a value that is not printed on the drawing. If unsure, omit the fact.
Output ONLY the JSON object.
```

- [ ] TDD with fake runner (cap test, schema test, junk-JSON → clear error). Implement. Integration: run real `claude -p` extraction on A-201 PDF once; check facts land as UNCERTAIN in the engine report (`run_check.py rules/... --pdf samples/A-201_stair_section.pdf`).
- [ ] Commit `feat: T3 — LLM PDF extractor, confidence hard-capped at 0.89 (EO1)`.

## Phase 4 (T4) — Review UI (human-in-the-loop, EO4)

### Task 4.1: ports + FastAPI reviewer backend

**Files:**
- Create: `server/app.py`, `server/overrides.py`, `tests/test_server.py`
- Modify: `~/.claude/PORTS.md` (register nbc-checker: Frontend 3029, Backend 3099; remove 3029 from Available? frontend range says 3029+ → update to 3030+; remove 3099 from available backends)

**Interfaces (backend, port 3099, HTTPS via traefik certs, uvicorn):**
- `GET /api/state` → `{project, summary, results, facts, overrides}` — engine run output on (base facts + overrides applied)
- `POST /api/override` body `{"entity_id": str, "fact": str, "value": num|str|bool, "note": str}` → stores in `reports/overrides.json` as full-confidence human fact `{"value": v, "confidence": 1.0, "source": "human review: <note> <ISO date>"}`, re-runs engine, returns new state. Overrides file is the audit trail of human decisions.
- `DELETE /api/override/{entity_id}/{fact}` → remove override, re-run.
- `GET /api/export/{fmt}` (fmt: pdf|xlsx) → FileResponse (wired in Phase 5; returns 501 until then).
- CORS: allow `https://dev.ecoworks.ca:3029`.
- Facts source selectable by env `NBC_FACTS` (default `samples/sample_dwelling_facts.json`), ruleset `NBC_RULES` (default `rules/nbc2020_part9_core.json`).

- [ ] `pip3 install fastapi uvicorn --break-system-packages`; TDD overrides.py (apply/remove/persist round-trip) with pytest + fastapi TestClient for endpoints; implement; register ports in PORTS.md; start: `python3 -m uvicorn server.app:app --port 3099 --ssl-keyfile ~/Code/.traefik/certs/key.pem --ssl-certfile ~/Code/.traefik/certs/cert.pem` (background); `curl -sk https://dev.ecoworks.ca:3099/api/state | head`.
- [ ] Commit `feat: T4 — FastAPI reviewer backend with human-override audit trail`.

### Task 4.2: Vite React UI

**Files:**
- Create: `ui/` (Vite React-TS scaffold: `npm create vite@latest ui -- --template react-ts`), key files:
  - `ui/vite.config.ts` — port 3029 strict, host true, HTTPS certs recipe from house CLAUDE.md, proxy `/api` → `https://localhost:3099` (secure: false)
  - `ui/src/App.tsx` — layout: header (project name, ruleset, determinism badge showing SHA-256 of report JSON), SummaryBar, ResultsTable, DetailDrawer, ChangelogModal
  - `ui/src/components/summary-bar.tsx` — 4 status chips with counts, click = filter toggle
  - `ui/src/components/results-table.tsx` — rows: status pill, rule_id, title, provision, entity; filterable; row click opens drawer
  - `ui/src/components/detail-drawer.tsx` — provision + verbatim `verification_notes.quote` from the rule (ship ruleset to UI via `/api/state`), facts_used table (value/confidence/source), comparisons list; for UNCERTAIN/INFO facts: override form (value input + note) → POST `/api/override`; existing overrides shown with delete
  - `ui/src/components/changelog-modal.tsx` — house pattern: `APP_VERSION`, `CHANGELOG`, `ROADMAP`, `HOW_IT_WORKS` exports, three tabs
  - `ui/src/api.ts` — `getState()`, `postOverride()`, `deleteOverride()`, types mirroring report schema
- Create: `CHANGELOG.md` (root, 0.1.0 → today), `docs/README.md` (architecture, stack table, file structure, API table)

Design notes (frontend-design skill to be loaded at execution): dense reviewer tool, not marketing page; status colors: pass=green, fail=red, info=grey, uncertain=amber; mono for values/provisions.

- [ ] Scaffold, implement, `npm run dev` (background), verify `https://dev.ecoworks.ca:3029` renders state, override round-trip works (mark handrail 920 confirmed → status flips REVIEW→PASS deterministically), delete override → flips back.
- [ ] Commit `feat: T4 — reviewer UI (filter, drill-down, confirm/correct → deterministic re-run)`.

## Phase 5 (T5) — Report export

### Task 5.1: PDF + Excel exporters

**Files:**
- Create: `engine/export.py`, `tests/test_export.py`
- Modify: `server/app.py` (wire `/api/export/{fmt}`), `run_check.py` (`--export-pdf/--export-xlsx` flags)

**Interfaces:**
- `to_xlsx(report: dict, path: str)` — openpyxl; Sheet1 "Summary" (project, ruleset, counts, engine note, report SHA-256); Sheet2 "Checks": columns rule_id | provision | title | entity | status | detail | facts used (fact=value @conf [source]; joined "; ") | comparisons
- `to_pdf(report: dict, path: str)` — reportlab platypus; title page (project, summary table, determinism statement + SHA), then one block per check: heading `[STATUS] rule_id — title`, provision line, detail, facts table with provenance
- Both pure functions of the report dict (no timestamps inside → deterministic bytes given same report; SHA computed over report JSON).

- [ ] `pip3 install reportlab openpyxl --break-system-packages`; TDD (xlsx: reopen with openpyxl and assert cells; pdf: file exists + >1KB + contains rule_id via pypdf text if trivial, else size/smoke); implement; wire endpoints + CLI; export both from the sample report; open/eyeball.
- [ ] Commit `feat: T5 — PDF and Excel audit report export`.

## Phase 6 (T6) — Feasibility evidence document

### Task 6.1: evidence doc with screenshots + determinism demo

**Files:**
- Create: `docs/feasibility-evidence.md`, `docs/img/*.png` (UI screenshots via Chrome MCP), `docs/determinism_demo.sh`

Content (2–3 pages): challenge restated; architecture diagram (mermaid, the two-stage pipeline); what's implemented (rule count, all verified, extractors, review loop, exports); determinism demonstration (script runs engine 3×, prints identical SHA-256 — include captured output); screenshots (results table, drawer with provision quote + override, exported PDF); verification methodology (V1 story: 3 encoding errors caught against official text — this is evidence the deterministic+verified approach is necessary); honest limitations (geometry derivation caveats, single-jurisdiction NBC values, Ontario differs, partial-area ceiling rules not machine-encoded, LLM extraction always routes to human).

- [ ] Write doc; screenshot UI via claude-in-chrome MCP; run determinism script; commit `docs: T6 — TRL 5-6 feasibility evidence`.

## Phase 7 (T7) — Proposal draft

### Task 7.1: EO research + draft

**Files:**
- Create: `docs/proposal-draft.md`

- [ ] Research agent: find the official NRC ISC Phase 2 challenge text ("Deterministic AI-assisted compliance checking of building permit applications") — exact Essential Outcomes EO1–EO7 wording, evaluation criteria, budget/duration constraints. If the posting is not public/findable, mark the EO table "per prompt_plan.md interpretation — VERIFY against official challenge text" (business input needed).
- [ ] Draft: problem statement; approach (neuro-symbolic, deterministic core); EO1–EO7 mapping table (each EO → prototype evidence with file/screenshot references); work plan (18 months, phases: ruleset industrialization → municipal pilot → certification/API); budget table ≤ $500K (personnel, P.Eng/code-consultant subcontract, municipal pilot, infra); team section (EcoWorks + Fanshawe-network P.Eng collaborator — NAMED PLACEHOLDER, business decision); risks (jurisdiction variants, IFC quality in permit submissions, LLM extraction accuracy → always-human-gated).
- [ ] Update progress.md session log + prompt_plan.md task statuses; final commit + push.

---

## Self-review notes

- Spec coverage: T1 (tasks 1.1–1.5), T2 (2.1–2.2), T3 (3.1–3.2), T4 (4.1–4.2), T5 (5.1), T6 (6.1), T7 (7.1). House rules (CHANGELOG, docs/README, ChangelogModal, ports, HTTPS, keep-running) folded into 4.x. Open decision #2 (FastAPI wrap = EO7 open API) partially addressed by server/app.py — noted in evidence doc.
- Rule VALUES in tasks 1.3–1.5 are deliberately labeled candidates — the task IS to verify them against the official text; encoding unverified values verbatim from this plan would violate V1 discipline.
- Type consistency: facts schema unchanged everywhere; `/api/state` is the single state shape consumed by UI; exporters consume the report dict as produced by `run_ruleset`.
