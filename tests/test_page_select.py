"""Page classification/selection — pure functions, fixtures mirror the real
corpus probe (progress.md session 5c / multipage plan):
- Ottawa checklist pages: checklist keywords AND drawing keywords, prose-dense
- Calgary notes sheets: vector-y but word-heavy — must NOT be skipped
- Calgary secondary suite: pure scans, zero text signal — fail-open include
"""
import pytest

from extractors.page_select import (
    DEFAULT_MAX_TILED_PAGES,
    PageStats,
    classify_page,
    parse_pages_spec,
    select_pages,
)


def ps(page, words=0, drawing_kw=0, checklist_kw=0, vector_items=0, images=0):
    return PageStats(page=page, width=612, height=792, words=words,
                     drawing_kw=drawing_kw, checklist_kw=checklist_kw,
                     vector_items=vector_items, images=images)


# Corpus-shaped fixtures
OTTAWA = [
    ps(1, words=204, drawing_kw=2, checklist_kw=3, vector_items=9),    # cover/checklist
    ps(2, words=262, drawing_kw=4, checklist_kw=4, vector_items=175),  # checklist w/ drawing words
    ps(3, words=230, drawing_kw=3, checklist_kw=3, vector_items=7),
    ps(4, words=162, drawing_kw=2, checklist_kw=2, vector_items=30),
    ps(5, words=40, drawing_kw=3, checklist_kw=0, vector_items=23),    # site plan
    ps(6, words=245, drawing_kw=4, checklist_kw=0, vector_items=75),   # floor plan
    ps(7, words=120, drawing_kw=3, checklist_kw=0, vector_items=60),   # elevations
    ps(8, words=180, drawing_kw=2, checklist_kw=0, vector_items=44),   # section
]
SCANNED = [ps(i, words=0, vector_items=0, images=1) for i in range(1, 8)]
CALGARY_NOTES = ps(18, words=617, drawing_kw=1, checklist_kw=0, vector_items=1631)


def test_checklist_page_with_drawing_keywords_still_skipped():
    label, reason = classify_page(OTTAWA[1])  # p2: 4 drawing kw AND 4 checklist kw
    assert label == "text"
    assert "checklist" in reason


def test_drawing_page_selected():
    assert classify_page(OTTAWA[5])[0] == "drawing"


def test_scanned_no_signal_page_included():
    label, _ = classify_page(SCANNED[0])
    assert label == "no_signal"
    sel = select_pages(SCANNED, "auto")
    assert sel.selected == [1, 2, 3, 4, 5, 6, 7]  # fail-open
    assert sel.skipped == []


def test_vector_dense_notes_page_not_skipped():
    # Calgary notes sheets are word-heavy but carry dimension facts.
    assert classify_page(CALGARY_NOTES)[0] == "drawing"


def test_selection_reports_reason_for_every_skip():
    sel = select_pages(OTTAWA, "auto")
    assert sel.selected == [5, 6, 7, 8]
    assert [s["page"] for s in sel.skipped] == [1, 2, 3, 4]
    assert all(s["reason"] for s in sel.skipped)
    assert set(sel.labels) == set(range(1, 9))  # every page labelled


def test_page_cap_truncates_and_reports_page_cap_reason():
    many = [ps(i, drawing_kw=2, vector_items=500) for i in range(1, 21)]
    sel = select_pages(many, "auto", max_pages=12)
    assert sel.selected == list(range(1, 13))
    capped = [s for s in sel.skipped if "page_cap" in s["reason"]]
    assert [s["page"] for s in capped] == list(range(13, 21))


def test_selection_is_deterministic():
    a = select_pages(OTTAWA, "auto")
    b = select_pages(OTTAWA, "auto")
    assert a == b


def test_explicit_all_spec_overrides_classifier():
    sel = select_pages(OTTAWA, "all")
    assert sel.selected == list(range(1, 9))
    assert sel.skipped == []


def test_explicit_list_spec():
    sel = select_pages(OTTAWA, [5, 7])
    assert sel.selected == [5, 7]


def test_parse_pages_spec_list_ranges_all_auto():
    assert parse_pages_spec("auto") == "auto"
    assert parse_pages_spec("all") == "all"
    assert parse_pages_spec("1,3-5") == [1, 3, 4, 5]
    assert parse_pages_spec(" 2 , 4 ") == [2, 4]


def test_parse_pages_spec_rejects_junk_and_out_of_range():
    for junk in ("", "0", "1,x", "5-3", "-2", "1;2"):
        with pytest.raises(ValueError):
            parse_pages_spec(junk)
    with pytest.raises(ValueError):
        parse_pages_spec("9", page_count=8)


def test_default_cap_constant():
    assert DEFAULT_MAX_TILED_PAGES == 12
