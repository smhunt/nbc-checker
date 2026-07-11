"""Tests for scripts/ab_extract_models.py::diff_facts — the ONLY function
from that script under test (per CLAUDE.md: the harness itself is a manual
diagnostic, never wired into pytest/CI, and makes real billed API calls when
actually run). `diff_facts` is pure (no I/O, no env reads, no network), so
these tests exercise it directly with in-memory facts dicts — no mocking, no
subprocess, no anthropic import, and nothing here can make a network call
even by accident (`scripts/ab_extract_models.py` only imports `anthropic`
inside `extractors.runners.make_api_runner`, which these tests never call).
"""

from scripts.ab_extract_models import diff_facts


def _stair_entity(riser=190, tread_run=255):
    return {
        "entity_type": "stair_flight",
        "id": "stair-01",
        "name": "Main stair, ground to second floor",
        "attributes": {
            "riser_height_mm": {"value": riser, "confidence": 1.0, "source": "x"},
            "tread_run_mm": {"value": tread_run, "confidence": 1.0, "source": "x"},
        },
    }


def test_ab_diff_matches_within_tolerance():
    expected = {"entities": [_stair_entity(riser=190, tread_run=255)]}
    # Extracted values are off by <= 1mm (default tolerance) — still a match.
    extracted = {"entities": [_stair_entity(riser=190.4, tread_run=254.6)]}

    result = diff_facts(extracted, expected)

    assert result == {
        "found": 2,
        "matched": 2,
        "wrong_value": 0,
        "hallucinated": 0,
        "missing": 0,
    }


def test_ab_diff_flags_wrong_value_outside_tolerance():
    expected = {"entities": [_stair_entity(riser=190, tread_run=255)]}
    # riser is off by 5mm (outside the default 1mm tolerance); tread_run matches.
    extracted = {"entities": [_stair_entity(riser=195, tread_run=255)]}

    result = diff_facts(extracted, expected)

    assert result["found"] == 2
    assert result["matched"] == 1
    assert result["wrong_value"] == 1
    assert result["hallucinated"] == 0
    assert result["missing"] == 0

    # A wider tolerance absorbs the same 5mm difference.
    result_loose = diff_facts(extracted, expected, tolerance_mm=5.0)
    assert result_loose["matched"] == 2
    assert result_loose["wrong_value"] == 0


def test_ab_diff_flags_hallucinated_and_missing():
    expected = {
        "entities": [{
            "entity_type": "stair_flight",
            "id": "stair-01",
            "name": "Main stair, ground to second floor",
            "attributes": {
                "riser_height_mm": {"value": 190, "confidence": 1.0, "source": "x"},
                "headroom_mm": {"value": 2050, "confidence": 1.0, "source": "x"},
            },
        }],
    }
    # Extraction found riser_height_mm (matched) but never reported headroom_mm
    # (missing), and invented a fact on an entity the expected file never
    # mentions at all (hallucinated).
    extracted = {
        "entities": [
            {
                "entity_type": "stair_flight",
                "id": "stair-01",
                "name": "Main stair, ground to second floor",
                "attributes": {
                    "riser_height_mm": {"value": 190, "confidence": 0.8, "source": "y"},
                },
            },
            {
                "entity_type": "window",
                "id": "window-99",
                "name": "Phantom window",
                "attributes": {
                    "overall_height_mm": {"value": 1200, "confidence": 0.6, "source": "y"},
                },
            },
        ],
    }

    result = diff_facts(extracted, expected)

    assert result == {
        "found": 1,
        "matched": 1,
        "wrong_value": 0,
        "hallucinated": 1,
        "missing": 1,
    }


