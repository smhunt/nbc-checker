"""
IFC -> building facts extractor (deterministic path, EO2/EO3).

Facts extracted directly from IFC geometry/attributes carry confidence 1.0
and cite the source IFC GlobalId. This is the "trusted" ingestion path;
PDF/drawing extraction (LLM-assisted) produces the same facts schema but
with confidence < 1.0, forcing UNCERTAIN status until human-verified.

v1 scope: IfcStairFlight (RiserHeight/TreadLength attributes),
IfcSpace heights, IfcWindow dimensions. Property-set fallbacks included
because authoring tools vary in where they put these values.
"""

from __future__ import annotations

import json
import sys

import ifcopenshell
import ifcopenshell.util.element as el
import ifcopenshell.util.unit


def _psets(entity) -> dict:
    try:
        return el.get_psets(entity)
    except Exception:
        return {}


def _find_prop(psets: dict, names: list[str]):
    for pset in psets.values():
        for key, val in pset.items():
            if key in names and isinstance(val, (int, float)):
                return val
    return None


def _mm(value, unit_scale: float):
    """Convert model length units to mm."""
    if value is None:
        return None
    return round(value * unit_scale * 1000.0, 1)


def extract(ifc_path: str) -> dict:
    model = ifcopenshell.open(ifc_path)
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(model)  # -> metres

    entities = []

    for flight in model.by_type("IfcStairFlight"):
        psets = _psets(flight)
        riser = flight.RiserHeight if hasattr(flight, "RiserHeight") else None
        tread = flight.TreadLength if hasattr(flight, "TreadLength") else None
        riser = riser if riser is not None else _find_prop(psets, ["RiserHeight"])
        tread = tread if tread is not None else _find_prop(psets, ["TreadLength"])

        attrs = {"service": "private"}  # v1 assumption for Part 9 dwellings; TODO: derive from occupancy
        src = f"{ifc_path}#{flight.GlobalId}"
        if riser is not None:
            attrs["riser_height_mm"] = {"value": _mm(riser, unit_scale), "confidence": 1.0, "source": src}
        if tread is not None:
            attrs["tread_run_mm"] = {"value": _mm(tread, unit_scale), "confidence": 1.0, "source": src}

        width = _find_prop(psets, ["ClearWidth", "Width", "NominalWidth"])
        if width is not None:
            attrs["clear_width_mm"] = {"value": _mm(width, unit_scale), "confidence": 1.0, "source": src}

        entities.append({
            "entity_type": "stair_flight",
            "id": flight.GlobalId,
            "name": flight.Name or "Unnamed stair flight",
            "attributes": attrs,
        })

    for space in model.by_type("IfcSpace"):
        psets = _psets(space)
        height = _find_prop(psets, ["Height", "CeilingHeight", "FinishCeilingHeight", "NetCeilingHeight"])
        attrs = {}
        src = f"{ifc_path}#{space.GlobalId}"
        long_name = (getattr(space, "LongName", "") or "").lower()
        name = (space.Name or "").lower()
        for token, use in [("living", "living_room"), ("dining", "dining_room"), ("bed", "bedroom")]:
            if token in long_name or token in name:
                attrs["room_use"] = use
                break
        if height is not None:
            attrs["ceiling_height_mm"] = {"value": _mm(height, unit_scale), "confidence": 1.0, "source": src}
        entities.append({
            "entity_type": "room",
            "id": space.GlobalId,
            "name": space.LongName or space.Name or "Unnamed space",
            "attributes": attrs,
        })

    for window in model.by_type("IfcWindow"):
        attrs = {}
        src = f"{ifc_path}#{window.GlobalId}"
        oh = getattr(window, "OverallHeight", None)
        ow = getattr(window, "OverallWidth", None)
        if oh is not None and ow is not None:
            h_mm, w_mm = _mm(oh, unit_scale), _mm(ow, unit_scale)
            attrs["overall_height_mm"] = {"value": h_mm, "confidence": 1.0, "source": src}
            attrs["overall_width_mm"] = {"value": w_mm, "confidence": 1.0, "source": src}
            # NOTE: unobstructed OPEN area depends on operation type (casement vs
            # slider etc.) — deliberately NOT derived here. Left absent so the
            # engine reports INFO_NOT_AVAILABLE rather than guessing. (EO1)
        entities.append({
            "entity_type": "window",
            "id": window.GlobalId,
            "name": window.Name or "Unnamed window",
            "attributes": attrs,
        })

    return {
        "project": {"name": model.by_type("IfcProject")[0].Name if model.by_type("IfcProject") else ifc_path,
                    "sources": [ifc_path]},
        "entities": entities,
    }


if __name__ == "__main__":
    import ifcopenshell.util.unit  # noqa: E402
    print(json.dumps(extract(sys.argv[1]), indent=2))
