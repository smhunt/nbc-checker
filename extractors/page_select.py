"""Deterministic page classification/selection for multi-page permit PDFs.

Real permit sets mix checklist/cover pages with drawing sheets, and tiled
extraction costs real time per page — so `pages="auto"` picks drawing pages
with a PURE, deterministic classifier (a function of PyMuPDF text/vector
stats; identical input bytes -> identical selection -> identical report).

The failure modes are asymmetric: a wrongly-skipped page means missed facts
(invisible to the engine), a wrongly-included page only costs extraction
time. So skipping requires STRONG negative evidence (checklist prose), pages
with no signal at all (scans) are INCLUDED, and every decision — including
cap truncation — is reported so the reviewer sees exactly what was not read.
No LLM is involved in selection (it shapes what gets read; keeping it
deterministic preserves the identical-inputs claim).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

DEFAULT_MAX_TILED_PAGES = 12

# Strong negative signal: prose pages telling applicants what to submit.
CHECKLIST_KEYWORDS = (
    "checklist",
    "building permit",
    "application",
    "required inspections",
    "submission requirements",
    "how to apply",
    "permit fee",
)

# Positive signal: sheet furniture on real drawings.
DRAWING_KEYWORDS = (
    "scale",
    "site plan",
    "floor plan",
    "elevation",
    "section",
    "detail",
    "foundation plan",
    "roof plan",
)

_VECTOR_DRAWING_MIN = 300   # vector items that alone indicate a CAD sheet
_PROSE_WORDS_MIN = 100      # checklist pages are word-dense
_SKIP_CHECKLIST_HITS = 2    # distinct checklist keywords needed to skip


@dataclass(frozen=True)
class PageStats:
    page: int            # 1-based
    width: float
    height: float
    words: int
    drawing_kw: int      # distinct DRAWING_KEYWORDS present
    checklist_kw: int    # distinct CHECKLIST_KEYWORDS present
    vector_items: int
    images: int


@dataclass
class PageSelection:
    selected: list       # 1-based page numbers, ascending
    skipped: list        # dicts: {"page", "label", "reason"}
    labels: dict         # page -> (label, reason), for ALL pages


def collect_page_stats(pdf_path: str) -> list[PageStats]:
    """Gather deterministic per-page stats via PyMuPDF."""
    import fitz  # lazy: unit tests use synthetic stats

    stats = []
    doc = fitz.open(pdf_path)
    try:
        for i, page in enumerate(doc):
            text = page.get_text().lower()
            words = len(text.split())
            stats.append(PageStats(
                page=i + 1,
                width=page.rect.width,
                height=page.rect.height,
                words=words,
                drawing_kw=sum(1 for k in DRAWING_KEYWORDS if k in text),
                checklist_kw=sum(1 for k in CHECKLIST_KEYWORDS if k in text),
                vector_items=len(page.get_drawings()),
                images=len(page.get_images()),
            ))
    finally:
        doc.close()
    return stats


def classify_page(stats: PageStats) -> tuple[str, str]:
    """Pure classifier -> (label, human-readable reason).

    Order matters: the skip rule runs first and requires strong negative
    evidence, because checklist pages ALSO mention drawing keywords
    ("floor plan drawing to include...").
    """
    detail = (f"checklist keywords x{stats.checklist_kw}, "
              f"drawing keywords x{stats.drawing_kw}, "
              f"{stats.vector_items} vector items, {stats.words} words")
    if (stats.checklist_kw >= _SKIP_CHECKLIST_HITS
            and stats.vector_items < _VECTOR_DRAWING_MIN
            and stats.words >= _PROSE_WORDS_MIN):
        return "text", detail
    if stats.drawing_kw > 0 or stats.vector_items >= _VECTOR_DRAWING_MIN:
        return "drawing", detail
    return "no_signal", f"no text/vector signal (scan?) — included fail-open ({detail})"


def parse_pages_spec(spec: str, page_count: int | None = None):
    """'auto' | 'all' | '1,3-5' -> 'auto' | 'all' | sorted 1-based list.

    Raises ValueError on malformed specs or out-of-range pages.
    """
    s = str(spec).strip().lower()
    if s in ("auto", "all"):
        return s
    if not s or not re.fullmatch(r"[\d\s,\-]+", s):
        raise ValueError(f"invalid pages spec: {spec!r} (use auto, all, or e.g. 1,3-5)")
    pages: set[int] = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"invalid pages spec: {spec!r}")
        if "-" in part:
            lo_s, _, hi_s = part.partition("-")
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError:
                raise ValueError(f"invalid range in pages spec: {part!r}")
            if lo < 1 or hi < lo:
                raise ValueError(f"invalid range in pages spec: {part!r}")
            pages.update(range(lo, hi + 1))
        else:
            n = int(part)
            if n < 1:
                raise ValueError(f"invalid page number: {part!r}")
            pages.add(n)
    if page_count is not None:
        bad = [p for p in pages if p > page_count]
        if bad:
            raise ValueError(f"pages {bad} beyond document ({page_count} pages)")
    return sorted(pages)


def select_pages(stats: list[PageStats], spec="auto",
                 max_pages: int | None = None) -> PageSelection:
    """Resolve the final page list; every non-selected page gets a reason."""
    if max_pages is None:
        max_pages = int(os.environ.get("NBC_MAX_TILED_PAGES", DEFAULT_MAX_TILED_PAGES))

    labels = {s.page: classify_page(s) for s in stats}
    if spec == "all":
        wanted = [s.page for s in stats]
    elif spec == "auto":
        wanted = [s.page for s in stats if labels[s.page][0] != "text"]
    else:  # explicit 1-based list
        known = {s.page for s in stats}
        wanted = [p for p in spec if p in known]

    skipped = [{"page": s.page, "label": labels[s.page][0], "reason": labels[s.page][1]}
               for s in stats
               if s.page not in wanted and (spec == "auto")]
    if spec not in ("auto", "all"):
        skipped = [{"page": s.page, "label": labels[s.page][0],
                    "reason": f"not in requested pages {list(spec)}"}
                   for s in stats if s.page not in wanted]

    selected = wanted[:max_pages]
    for p in wanted[max_pages:]:
        skipped.append({"page": p, "label": labels[p][0],
                        "reason": f"page_cap (max {max_pages})"})
    skipped.sort(key=lambda d: d["page"])

    return PageSelection(selected=list(selected), skipped=skipped, labels=labels)
