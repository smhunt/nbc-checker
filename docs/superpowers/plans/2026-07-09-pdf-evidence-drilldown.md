# PDF Evidence Drill-Down Implementation Plan

(Plan produced by dedicated planning agent, 2026-07-09. Executed same day.)

Goal: clicking a fact in the review UI opens the source PDF sheet and zooms
to the exact region the fact was extracted from, with a highlight rectangle.

Key design decisions:
- Optional `evidence: {doc, page, bbox?}` object on fact values; bbox is
  [x0,y0,x1,y1] normalized 0-1, top-left origin, y-down (fitz/raster space,
  NOT PDF user space). Engine passes evidence through untouched (EO1: it
  never influences status). Absent bbox degrades to page-level view; absent
  evidence degrades to source-string-only (today's behavior).
- Tile geometry is deterministic: render_page_to_tiles already computes each
  tile's clip rect in page points. The LLM only picks fractions within the
  tile image it saw -> hallucinated coords are geometrically confined to
  that tile. tile_bbox_to_page() is a pure, unit-tested transform with
  range/degeneracy validation (reject -> page-level fallback).
- Whole-PDF (non-tiled) mode asks for page number only, never bboxes
  (no controlled raster geometry).
- Serving: server-rendered PNGs via PyMuPDF (same library that tiled ->
  same coordinate space by construction; no pdf.js dependency). Endpoints:
  GET /api/jobs/{job_id}/pdf, /api/jobs/{job_id}/page/{page}.png?dpi=,
  GET /api/documents/{name}/pdf, /api/documents/{name}/page/{page}.png?dpi=.
  basename-only doc resolution against whitelist (samples/**, reports/uploads),
  dpi whitelist {96,150,200}, PNG cache in reports/page_cache/.
- Overrides copy the current fact's evidence into the override record so
  human confirmation keeps the drawing link (audit story).
- UI: EvidenceViewer component - viewport div + transformed wrapper
  (img + absolutely-positioned highlight divs), animated translate/scale
  zoom to focused bbox, all same-page facts highlighted, fit-page reset,
  drag pan. DetailDrawer gains "view on drawing" buttons.
- No separate bbox confidence channel: the bbox is a pointer, not a fact;
  sub-0.9 fact confidence already routes to human review.

Task order:
1. Engine passthrough + schema docs (checker.py FactLookup.evidence,
   facts_used includes evidence; CLAUDE.md/docs/README/CHANGELOG)
2. Extractor geometry + transform (tile descriptors carry clip/page size;
   tile_bbox_to_page; prompt additions; evidence stamping; page-level in
   whole-PDF mode)
3. Backend rendering + serving (server/pdfrender.py, routes, traversal tests)
4. Override evidence preservation (post_override/job_override copy evidence)
5. UI types + drawer affordance (api.ts Evidence, pageImageUrl, jobId thread)
6. EvidenceViewer component (zoom/highlight/pan)
7. Demo data (hand-measured evidence boxes in sample facts) + visual verify

Risks and mitigations, full endpoint specs, and test list: see the planning
agent output preserved in progress.md session notes and the tests themselves.

Report-hash note: adding evidence to facts_used changes report_sha256 for
identical inputs vs pre-feature builds (code change, not nondeterminism) -
CHANGELOG entry required.
