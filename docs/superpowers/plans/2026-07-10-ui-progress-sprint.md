# UI Sprint: verbose processing + ETA, resizable drawer, larger PDF locator

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> Constraint from user: use at most 10 agents (plan uses 1 + main session).

**Goal:** (1) The upload/analyze flow reports verbose stage-by-stage progress
with an estimated finish time; (2) the detail drawer width is drag-adjustable
and persisted; (3) the PDF evidence locator is larger, with an expand mode.

## Task A — backend job progress + ETA (main session, TDD)

**Files:** `server/jobs.py`, `server/app.py`, `extractors/pdf_extractor.py`,
`tests/test_jobs_progress.py`

- `extract_tiled(..., progress_cb=None)` — optional callback
  `progress_cb(stage: str, done: int, total: int)`; fired at render start,
  before each tile ("extracting tile r2c1"), at merge. `extract()` fires
  coarse stages. Callbacks never affect the returned facts (determinism).
- `Job` gains: `stage: str`, `progress_done/progress_total: int`,
  `started_at: float`, `tile_durations: list[float]`, `eta_seconds() -> float|None`.
  `public()` exposes `stage`, `progress: {done,total}`, `elapsed_s`, `eta_s`.
- ETA = mean(measured tile durations) x remaining tiles + 3 s engine/merge
  overhead; before the first tile completes, use a module-level rolling
  average from prior jobs (default seed 25 s/tile). Pure helper
  `estimate_eta(durations, remaining, seed_avg)` unit-tested.
- Upload thread wires the callback; final stages "running deterministic
  checks" then done.

## Task B+C+D — UI (single agent, after A lands)

**Files:** `ui/src/App.tsx`, `ui/src/api.ts`,
`ui/src/components/DetailDrawer.tsx`, `ui/src/components/EvidenceViewer.tsx`,
`ui/src/index.css`

- **B (verbose processing):** job polling UI shows stage text, tile progress
  bar (done/total), elapsed time, and "~Ns remaining" counting down locally
  between polls (clamp at "finishing up…" when exceeded). Types for the new
  job fields in api.ts.
- **C (resizable drawer):** left-edge drag handle on the drawer; width in px
  clamped to [380, 0.7*viewport]; persisted to localStorage
  `nbc.drawerWidth`; double-click handle resets to default.
- **D (larger locator):** EvidenceViewer default aspect 4:3 (taller) and an
  "Expand" toolbar button that re-renders the same viewer in a fixed overlay
  (~85vw x 85vh, Esc/close to dismiss). Zoom/highlight/pan behavior unchanged;
  higher dpi (200) image in expanded mode.

## Verification

- pytest suite green (progress callback ordering, ETA math, public() shape).
- Live browser check on nbc.dev.ecoworks.ca: upload sample PDF (Fast mode) —
  stages + ETA visible; drag drawer wider; expand evidence viewer; screenshots.
- Rebuild ui/dist, restart :3099, commit per task, push.
