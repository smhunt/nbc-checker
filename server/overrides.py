"""Reviewer overrides: persisted human confirmations/corrections of facts.

Overrides file shape:

    {
      "<entity_id>": {
        "<fact_name>": {
          "value": <confirmed value>,
          "confidence": 1.0,
          "source": "human review: <note> (<date>)"
        }
      }
    }

Applying overrides never mutates the input facts document — the engine stays
a pure function of (ruleset, facts+overrides), preserving determinism.
"""

from __future__ import annotations

import copy
import json
import os


def load_overrides(path: str) -> dict:
    """Load overrides from `path`; an absent file means no overrides."""
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_overrides(path: str, overrides: dict) -> None:
    """Persist overrides as pretty-printed, key-sorted JSON."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        json.dump(overrides, f, indent=2, sort_keys=True)
        f.write("\n")


def apply_overrides(facts: dict, overrides: dict) -> dict:
    """Return a NEW facts document with overrides merged into entity attributes.

    The entity may lack the fact entirely — that is the
    info_not_available -> resolved flow (reviewer supplies a value the
    extractor could not derive). Entities named in overrides but absent from
    the facts document are ignored.
    """
    merged = copy.deepcopy(facts)
    for entity in merged.get("entities", []):
        entity_overrides = overrides.get(entity.get("id"))
        if not entity_overrides:
            continue
        attrs = entity.setdefault("attributes", {})
        for fact_name, override in entity_overrides.items():
            attrs[fact_name] = copy.deepcopy(override)
    return merged
