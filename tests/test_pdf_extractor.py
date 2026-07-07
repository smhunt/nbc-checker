"""PDF extractor tests — lock the EO1 confidence cap and schema normalization.

All tests use a fake runner; no `claude` CLI calls happen here.
"""
import json

import pytest

from extractors.pdf_extractor import MAX_LLM_CONFIDENCE, EXTRACTION_PROMPT, extract

PDF = "samples/A-201_stair_section.pdf"


def fake_runner_for(payload_text: str):
    """Return a runner that ignores the prompt and replies with payload_text."""

    def runner(prompt: str, pdf_path: str) -> str:
        assert prompt == EXTRACTION_PROMPT
        assert pdf_path == PDF
        return payload_text

    return runner


def model_payload(confidence=None, include_confidence=True):
    attr = {"value": 190, "source": "A-201 stair section, riser leader"}
    if include_confidence:
        attr["confidence"] = confidence
    return {
        "entities": [
            {
                "entity_type": "stair_flight",
                "id": "stair-01",
                "name": "Main stair",
                "attributes": {"riser_height_mm": attr},
            }
        ]
    }


def extract_one_fact(payload_text: str):
    facts = extract(PDF, runner=fake_runner_for(payload_text))
    return facts["entities"][0]["attributes"]["riser_height_mm"]


def test_confidence_1_0_is_capped_below_engine_threshold():
    """THE EO1 test: a model claiming certainty 1.0 must be capped at 0.89."""
    fact = extract_one_fact(json.dumps(model_payload(confidence=1.0)))
    assert fact["confidence"] == MAX_LLM_CONFIDENCE == 0.89
    assert fact["confidence"] < 0.9  # engine CONFIDENCE_THRESHOLD


def test_modest_confidence_passes_through():
    fact = extract_one_fact(json.dumps(model_payload(confidence=0.7)))
    assert fact["confidence"] == 0.7


def test_missing_confidence_defaults_to_0_5():
    fact = extract_one_fact(json.dumps(model_payload(include_confidence=False)))
    assert fact["confidence"] == 0.5


def test_invalid_confidence_defaults_to_0_5():
    fact = extract_one_fact(json.dumps(model_payload(confidence="very sure")))
    assert fact["confidence"] == 0.5


def test_no_fact_ever_exceeds_cap():
    for claimed in (0.89, 0.9, 0.95, 1.0, 2.0):
        fact = extract_one_fact(json.dumps(model_payload(confidence=claimed)))
        assert fact["confidence"] <= MAX_LLM_CONFIDENCE


def test_markdown_fenced_json_is_parsed():
    fenced = "```json\n" + json.dumps(model_payload(confidence=0.8)) + "\n```"
    fact = extract_one_fact(fenced)
    assert fact["value"] == 190
    assert fact["confidence"] == 0.8


def test_junk_text_raises_value_error():
    with pytest.raises(ValueError, match="unparseable JSON"):
        extract(PDF, runner=fake_runner_for("I could not find any dimensions, sorry!"))


def test_valid_json_wrong_shape_raises_value_error():
    with pytest.raises(ValueError, match="unparseable JSON"):
        extract(PDF, runner=fake_runner_for(json.dumps({"facts": []})))


def test_output_schema_and_attribute_wrapping():
    payload = {
        "entities": [
            {
                "entity_type": "stair_flight",
                "id": "stair-01",
                "name": "Main stair",
                "attributes": {
                    # bare value from the model -> wrapped at confidence 0.5
                    "service": "private",
                    # dict missing source -> default source injected
                    "headroom_mm": {"value": 2050, "confidence": 0.85},
                },
            }
        ]
    }
    facts = extract(PDF, runner=fake_runner_for(json.dumps(payload)))

    assert facts["project"]["name"] == "A-201_stair_section.pdf (drawing extraction)"
    assert facts["project"]["sources"] == [PDF]
    assert isinstance(facts["entities"], list) and len(facts["entities"]) == 1

    attrs = facts["entities"][0]["attributes"]
    assert attrs["service"] == {
        "value": "private",
        "confidence": 0.5,
        "source": "A-201_stair_section.pdf (LLM extraction)",
    }
    assert attrs["headroom_mm"]["value"] == 2050
    assert attrs["headroom_mm"]["confidence"] == 0.85
    assert attrs["headroom_mm"]["source"] == "A-201_stair_section.pdf (LLM extraction)"
    # every fact is a proper wrapped dict with all three keys
    for fact in attrs.values():
        assert set(fact) == {"value", "confidence", "source"}
        assert fact["confidence"] <= MAX_LLM_CONFIDENCE
