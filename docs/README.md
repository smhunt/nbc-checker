# NBC Checker — Architecture & API

Prototype for deterministic AI-assisted compliance checking of building permit
applications against NBC 2020 Part 9 (NRC ISC Phase 2 challenge).

## System Overview

Two-stage neuro-symbolic pipeline; the stages communicate only through a facts
JSON document:

```
IFC model ──→ extractors/ifc_extractor.py (deterministic, confidence=1.0) ─┐
                                                                           ├─→ facts ─→ engine/checker.py ─→ report
PDF drawings ─→ LLM extractor (planned, confidence < 1.0) ─────────────────┘
```

The review layer (phase 4) closes the human-in-the-loop cycle:

```
report (uncertain / info_not_available checks)
   │
   ▼
ui/ (React review app) ──→ server/ (FastAPI) ──→ reports/overrides.json
   ▲                                                    │
   └──── deterministic re-run: engine(ruleset, facts + overrides) ◄──┘
```

**Non-negotiable invariant:** no generative model ever participates in
pass/fail judgment (challenge EO1). LLMs only produce facts, always at
confidence < 1.0, which routes them to human review. Reviewer confirmations
become overrides at confidence 1.0 with a `human review: …` source — then the
engine re-runs as a pure function.

## Tech Stack

| Layer      | Technology                          | Notes                                     |
|------------|-------------------------------------|-------------------------------------------|
| Engine     | Python 3 (stdlib only)              | Pure function of (ruleset, facts)          |
| Extraction | IfcOpenShell                        | `pip install ifcopenshell --break-system-packages` |
| Ruleset    | JSON (RASE-inspired schema)         | Every rule cites its NBC provision         |
| Backend    | FastAPI + Uvicorn                   | Review API, override persistence           |
| Frontend   | Vite + React + TypeScript           | Plain CSS, no UI library                   |
| Tests      | pytest + fastapi TestClient         | `python3 -m pytest tests/ -q`              |

## File Structure

```
nbc-checker/
├── engine/
│   └── checker.py            # deterministic rule engine (4-status output)
├── extractors/
│   └── ifc_extractor.py      # IfcOpenShell fact extraction (confidence 1.0)
├── rules/
│   ├── nbc2020_part9_core.json  # NBC 2020 rules (38, all verified) + verification_notes
│   └── obc2024_part9_core.json  # Ontario OBC 2024 variant (23 rules; ON-vs-NBC noted)
├── samples/
│   ├── sample_dwelling_facts.json
│   ├── generate_sample_ifc.py
│   └── smoke_test.ifc
├── server/                   # review API (phase 4)
│   ├── app.py                # FastAPI endpoints
│   └── overrides.py          # load/save/apply reviewer overrides
├── ui/                       # review web app (Vite + React + TS)
│   └── src/
│       ├── api.ts            # typed API client
│       ├── App.tsx
│       └── components/       # SummaryBar, ResultsTable, DetailDrawer, ChangelogModal
├── tests/
│   ├── test_checker.py       # engine regression suite
│   └── test_server.py        # review API round-trip tests
├── reports/                  # run outputs + overrides.json (reviewer state)
├── run_check.py              # CLI entry point
└── CHANGELOG.md
```

## Review API

Configuration via environment variables (defaults relative to repo root):

| Variable        | Default                              |
|-----------------|--------------------------------------|
| `NBC_RULES`     | `rules/nbc2020_part9_core.json`      |
| `NBC_FACTS`     | `samples/sample_dwelling_facts.json` |
| `NBC_OVERRIDES` | `reports/overrides.json`             |

### Endpoints

| Method | Path                                  | Description |
|--------|---------------------------------------|-------------|
| GET    | `/api/state`                          | Full state: `report` (fresh engine run on facts + overrides), `facts` (merged), `overrides`, `rules` (per-rule provision/title/verification_notes), `report_sha256` (canonical report hash — the determinism proof) |
| POST   | `/api/override`                       | Body `{entity_id, fact, value, note}`. Persists a reviewer override (confidence 1.0, source `human review: <note> (<date>)`), re-runs the engine, returns the same shape as `/api/state`. Numeric strings are coerced to numbers, `true`/`false` to booleans. |
| DELETE | `/api/override/{entity_id}/{fact}`    | Removes an override (404 if absent), re-runs, returns state |
| GET    | `/api/export/{fmt}`                   | `501` — export wired in phase 5 |

### Run

```bash
# Backend (plain HTTP; the Vite dev server proxies /api to it)
python3 -m uvicorn server.app:app --port 3099

# Frontend
cd ui && npm install && npm run dev
```

## Ports

| Service  | Port | URL                              |
|----------|------|----------------------------------|
| Frontend | 3029 | https://dev.ecoworks.ca:3029     |
| Backend  | 3099 | https://dev.ecoworks.ca:3099     |

The Vite dev server terminates TLS with the shared mkcert certificate
(`~/Code/.traefik/certs/`) and proxies `/api` to the backend on
`http://localhost:3099`.
