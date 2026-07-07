"""PDF extractor tests — lock the EO1 confidence cap and schema normalization.

All tests use a fake runner; no `claude` CLI calls happen here.
"""
import json

import pytest

from extractors.pdf_extractor import (
    MAX_LLM_CONFIDENCE,
    EXTRACTION_PROMPT,
    extract,
    extract_tiled,
    merge_tile_facts,
)

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


# --------------------------------------------------------------------------
# Tiled extraction — fake tile runners only, no CLI and no real rendering.
# --------------------------------------------------------------------------

TILED_PDF = "samples/A-201_stair_section.pdf"


def fake_tiles(*labels):
    """Synthetic tile descriptors so extract_tiled skips PyMuPDF rendering."""
    out = []
    for label in labels:
        row = int(label[1])
        col = int(label[3])
        out.append({"path": f"/tmp/{label}.png", "label": label, "row": row, "col": col})
    return out


def tile_runner(label_to_payload):
    """Runner keyed by the tile PNG basename -> per-tile JSON text."""

    def runner(prompt: str, image_path: str) -> str:
        assert EXTRACTION_PROMPT in prompt  # tiled prompt reuses the base prompt
        label = image_path.rsplit("/", 1)[-1].replace(".png", "")
        assert label in prompt  # prompt tells the model which crop it sees
        payload = label_to_payload[label]
        return payload if isinstance(payload, str) else json.dumps(payload)

    return runner


def _stair(name, riser_conf, **extra_attrs):
    attrs = {"riser_height_mm": {"value": 190, "confidence": riser_conf, "source": "leader"}}
    attrs.update(extra_attrs)
    return {
        "entities": [
            {"entity_type": "stair_flight", "id": "s1", "name": name, "attributes": attrs}
        ]
    }


def test_tiled_merges_duplicate_entity_and_keeps_highest_confidence():
    # The same stair is annotated in two tiles at different confidences, and
    # tile r1c2 additionally sees the tread run.
    payloads = {
        "r1c1": _stair("Main stair", 0.6),
        "r1c2": _stair(
            "main  stair",  # different spacing/case -> must still dedupe
            0.85,
            tread_run_mm={"value": 255, "confidence": 0.7, "source": "leader"},
        ),
    }
    facts = extract_tiled(
        TILED_PDF, runner=tile_runner(payloads), tiles=fake_tiles("r1c1", "r1c2")
    )
    ents = facts["entities"]
    assert len(ents) == 1  # deduped to a single stair
    attrs = ents[0]["attributes"]
    # highest-confidence instance of the shared fact wins
    assert attrs["riser_height_mm"]["confidence"] == 0.85
    # attributes are unioned across tiles
    assert attrs["tread_run_mm"]["value"] == 255
    # provenance records the winning tile
    assert attrs["riser_height_mm"]["source"] == "A-201_stair_section.pdf tile r1c2 (LLM extraction)"
    assert attrs["tread_run_mm"]["source"] == "A-201_stair_section.pdf tile r1c2 (LLM extraction)"
    assert facts["project"]["tiles"] == ["r1c1", "r1c2"]


def test_tiled_caps_confidence_even_when_a_tile_claims_1_0():
    payloads = {
        "r1c1": _stair("Main stair", 1.0),  # a tile claims certainty
        "r1c2": _stair("Egress stair", 0.5),
    }
    facts = extract_tiled(
        TILED_PDF, runner=tile_runner(payloads), tiles=fake_tiles("r1c1", "r1c2")
    )
    assert len(facts["entities"]) == 2  # distinct stairs kept separate
    for ent in facts["entities"]:
        for fact in ent["attributes"].values():
            assert fact["confidence"] <= MAX_LLM_CONFIDENCE == 0.89
    main = next(e for e in facts["entities"] if e["name"] == "Main stair")
    assert main["attributes"]["riser_height_mm"]["confidence"] == 0.89


def test_tiled_records_tile_source_for_every_fact():
    payloads = {
        "r1c1": _stair("Main stair", 0.6),
        "r2c1": _stair("Egress stair", 0.7),
    }
    facts = extract_tiled(
        TILED_PDF, runner=tile_runner(payloads), tiles=fake_tiles("r1c1", "r2c1")
    )
    seen = {
        f["source"]
        for e in facts["entities"]
        for f in e["attributes"].values()
    }
    assert seen == {
        "A-201_stair_section.pdf tile r1c1 (LLM extraction)",
        "A-201_stair_section.pdf tile r2c1 (LLM extraction)",
    }


def test_tiled_tolerates_prose_wrapped_json_and_skips_pure_prose_tiles():
    payloads = {
        # a real preamble before the JSON object (matches observed model output)
        "r1c1": "The only annotated fact in this crop is the stair note.\n"
        + json.dumps(_stair("Main stair", 0.8)),
        # pure prose, no JSON at all -> tile is skipped, run continues
        "r1c2": "No dimensions are visible in this region of the sheet.",
    }
    facts = extract_tiled(
        TILED_PDF, runner=tile_runner(payloads), tiles=fake_tiles("r1c1", "r1c2")
    )
    assert len(facts["entities"]) == 1  # r1c1 parsed, r1c2 skipped
    assert facts["entities"][0]["attributes"]["riser_height_mm"]["value"] == 190
    assert facts["project"]["tiles_unparsed"] == ["r1c2"]


def test_merge_tile_facts_pure_dedupe_and_highest_confidence():
    # Exercise the merge policy directly, without rendering or a runner.
    tile_facts = [
        {
            "tile": "r1c1",
            "entities": [
                {
                    "entity_type": "stair_flight",
                    "id": "a",
                    "name": "Stair 1",
                    "attributes": {
                        "riser_height_mm": {"value": 190, "confidence": 0.5, "source": "r1c1"}
                    },
                }
            ],
        },
        {
            "tile": "r1c2",
            "entities": [
                {
                    "entity_type": "stair_flight",
                    "id": "b",
                    "name": "Stair 1",  # same entity, different tile
                    "attributes": {
                        "riser_height_mm": {"value": 190, "confidence": 0.8, "source": "r1c2"},
                        "clear_width_mm": {"value": 900, "confidence": 0.6, "source": "r1c2"},
                    },
                },
                {
                    "entity_type": "window",
                    "id": "w",
                    "name": "Bedroom window",
                    "attributes": {
                        "overall_height_mm": {"value": 1000, "confidence": 0.7, "source": "r1c2"}
                    },
                },
            ],
        },
    ]
    merged = merge_tile_facts(tile_facts)["entities"]
    assert len(merged) == 2  # one stair (deduped) + one window
    stair = next(e for e in merged if e["entity_type"] == "stair_flight")
    assert stair["attributes"]["riser_height_mm"]["confidence"] == 0.8  # highest kept
    assert stair["attributes"]["riser_height_mm"]["source"] == "r1c2"
    assert stair["attributes"]["clear_width_mm"]["value"] == 900  # unioned
    # deterministic, stable ids in first-seen order
    assert [e["id"] for e in merged] == ["pdf-entity-1", "pdf-entity-2"]
