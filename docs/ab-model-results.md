# A/B model results

Measured comparison of PDF-extraction models (`extractors/runners.py`'s API
runner) on cost, latency, and accuracy — the evidence base for changing
`DEFAULT_EXTRACT_MODEL` away from `claude-sonnet-4-6`. See
`scripts/ab_extract_models.py` (the harness that produces the tables below)
and CLAUDE.md's "PDF extraction: runners, caching, concurrency" section for
the env vars involved.

**No runs recorded yet.** This machine's provisioned `ANTHROPIC_API_KEY`
currently returns `401 Unauthorized` against the real API, so no A/B run has
happened — this file is a template until that's resolved. `DEFAULT_EXTRACT_MODEL`
stays `claude-sonnet-4-6` until a run here says otherwise (see
`docs/superpowers/plans/subplans/C-api-runner.md`, Wave 5 task C6).

## How to run it

```bash
# 1. Cost estimate only, no network calls:
python3 scripts/ab_extract_models.py --dry-run \
    --models claude-sonnet-4-6,claude-haiku-4-5-20251001 \
    --pdf samples/A-201_stair_section.pdf \
    --expected samples/sample_dwelling_facts.json

# 2. Real run (needs a valid ANTHROPIC_API_KEY):
python3 scripts/ab_extract_models.py \
    --models claude-sonnet-4-6,claude-haiku-4-5-20251001 \
    --pdf samples/A-201_stair_section.pdf \
    --expected samples/sample_dwelling_facts.json \
    --runs 2 --out docs/ab-model-results.md
```

`--out` (default: this file) is appended to, never overwritten — history
accumulates as a sequence of "Run recorded ..." sections below, one per
invocation of the script.

## Known risk to watch for (unmeasured until a real run happens)

The Anthropic API downscales images with a long edge over 1568px before the
model sees them. A large multi-view sheet's 3x3-grid tile renders at ~200 DPI
can be ~2600px on the long edge — so the API path could read small dimension
annotations **worse** than the `claude` CLI path (which has no such
documented downscale step), even though the API path is faster and avoids
CLI subprocess/auth overhead. `scripts/ab_extract_models.py` records tile
pixel dimensions (`estimate_tile_pixel_dims`, grid+DPI math) alongside the
accuracy diff specifically so this tradeoff is visible per model, not
assumed.

## Ground truth used

`samples/A-201_stair_section.pdf` is a synthetic drawing whose printed
annotations are documented verbatim in `samples/generate_sample_drawing.py`'s
module docstring (RISER 190mm, TREAD RUN 255mm, CLEAR WIDTH 910mm, HANDRAIL
920mm ABOVE NOSING, HEADROOM 2050mm). The harness filters
`samples/sample_dwelling_facts.json` (a whole-project facts file that also
contains IFC-only facts a PDF extraction could never produce) down to exactly
that subset via `scripts/ab_extract_models.py::filter_pdf_sourced_facts` /
`A201_EXPECTED_FACTS` before diffing.

A real-corpus pairing (a hand-reviewed sheet from `docs/casestudy-real-permit.md`,
following the same reviewed-facts pattern) is a documented follow-up once the
sample-drawing pairing establishes the harness works end to end — not
required to unblock the C6 model decision, but a stronger signal than one
synthetic sheet before flipping the production default.

## Results

_No runs recorded yet — see `scripts/ab_extract_models.py`._

<!-- scripts/ab_extract_models.py appends "## Run recorded <timestamp>" +
     results table sections below this line on every real (non-dry-run)
     invocation. Do not hand-edit below this point; the script only appends. -->
