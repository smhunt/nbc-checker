"""Server-side PDF page rendering for the evidence drill-down UI.

Renders single pages to PNG via PyMuPDF — the same library the tiled
extractor rasterizes with, so served images share its coordinate space
(top-left origin, y-down) by construction. Rendered pages are cached on
disk; identical (pdf, page, dpi) requests re-serve the same file.

Document resolution is basename-only against a fixed whitelist of
directories (reports/uploads, samples/** recursively) — path separators
and '..' are rejected outright so no request can escape the whitelist.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent

# Basenames only: any of these in a requested name means path traversal.
FORBIDDEN_NAME_TOKENS = ("/", "\\", "..")

# Searched in order; first match wins. samples/ is searched recursively so
# nested sample sets (e.g. samples/casestudy/) resolve too.
_SEARCH_DIRS = (
    ROOT / "reports" / "uploads",
    ROOT / "samples",
)


def resolve_document(name: str) -> Path | None:
    """Resolve a bare PDF filename against the whitelist, or None.

    Rejects empty names and any name containing a path separator or '..'.
    """
    if not name or any(tok in name for tok in FORBIDDEN_NAME_TOKENS):
        return None
    for base in _SEARCH_DIRS:
        if not base.is_dir():
            continue
        # sorted() makes the first match deterministic across filesystems.
        for match in sorted(base.rglob(name)):
            if match.is_file():
                return match
    return None


def render_page_png(pdf_path: Path, page: int, dpi: int, cache_dir: Path) -> Path:
    """Render one page (1-based) of a PDF to a cached PNG and return its path.

    Re-serves the cached file without re-rendering when it already exists.
    Raises ValueError if the page number is out of range.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{pdf_path.stem}_p{page}_{dpi}.png"
    if out.exists():
        return out

    doc = fitz.open(pdf_path)
    try:
        if page < 1 or page > doc.page_count:
            raise ValueError(
                f"page {page} out of range (document has {doc.page_count} page(s))"
            )
        pix = doc[page - 1].get_pixmap(dpi=dpi)
        pix.save(str(out))
    finally:
        doc.close()
    return out
