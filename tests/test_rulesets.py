"""Schema + verification-contract tests for every ruleset in rules/.

These are the machine-enforced guardrails behind the project's core claim:
no rule is marked verified without verbatim quote + sources, and every rule
is structurally executable by the engine.
"""
import glob
import json

import pytest

from engine.checker import OPS

RULESET_PATHS = sorted(glob.glob("rules/*.json"))
VALID_STATUS_FIELDS = {"rule_id", "provision", "title", "applies_to", "requires",
                       "exceptions", "unit_system", "verified_against_code_text",
                       "verification_notes"}


def rulesets():
    for path in RULESET_PATHS:
        with open(path) as f:
            yield path, json.load(f)


def all_rules():
    for path, rs in rulesets():
        for rule in rs["rules"]:
            yield path, rule


@pytest.mark.parametrize("path", RULESET_PATHS)
def test_ruleset_loads_and_has_header(path):
    with open(path) as f:
        rs = json.load(f)
    assert rs["ruleset_id"]
    assert rs["code_edition"]
    assert isinstance(rs["rules"], list) and rs["rules"]


def test_rule_ids_unique_within_each_ruleset():
    for path, rs in rulesets():
        ids = [r["rule_id"] for r in rs["rules"]]
        assert len(ids) == len(set(ids)), f"duplicate rule_id in {path}"


@pytest.mark.parametrize("path,rule", list(all_rules()),
                         ids=lambda v: v if isinstance(v, str) else v.get("rule_id", "?"))
def test_rule_structure(path, rule):
    assert set(rule) >= VALID_STATUS_FIELDS - {"verification_notes"}, \
        f"{rule.get('rule_id')} missing required fields"
    assert rule["applies_to"]["entity_type"]
    assert isinstance(rule["applies_to"].get("where", {}), dict)
    reqs = rule["requires"]["all"]
    assert reqs, f"{rule['rule_id']} has no requirements"
    for req in reqs:
        assert req["op"] in OPS, f"{rule['rule_id']} bad op {req['op']}"
        assert ("value" in req) != ("value_fact" in req), \
            f"{rule['rule_id']} must have exactly one of value/value_fact"
        assert req["fact"], f"{rule['rule_id']} requirement missing fact"
    for exc in rule.get("exceptions", []):
        assert "description" in exc
        if "fact" in exc:
            assert exc["op"] in OPS and "value" in exc


@pytest.mark.parametrize("path,rule", list(all_rules()),
                         ids=lambda v: v if isinstance(v, str) else v.get("rule_id", "?"))
def test_verification_contract(path, rule):
    """verified_against_code_text: true requires quote + sources evidence."""
    notes = rule.get("verification_notes", {})
    if rule["verified_against_code_text"]:
        assert notes.get("quote"), f"{rule['rule_id']} verified without quote"
        assert notes.get("sources"), f"{rule['rule_id']} verified without sources"
        assert notes.get("verified_date"), f"{rule['rule_id']} verified without date"


def test_where_conditions_reference_ops_correctly():
    for path, rule in all_rules():
        for fact, cond in rule["applies_to"].get("where", {}).items():
            if isinstance(cond, dict) and "op" in cond:
                assert cond["op"] in OPS and "value" in cond, \
                    f"{rule['rule_id']} bad where-condition on {fact}"
