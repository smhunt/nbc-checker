"""Engine regression tests — lock the four-status contract."""
import json

from engine.checker import run_ruleset, check_rule, Status


def mk_rule(**over):
    r = {
        "rule_id": "T-1", "provision": "TEST", "title": "t",
        "applies_to": {"entity_type": "thing", "where": {}},
        "requires": {"all": [{"fact": "x_mm", "op": ">=", "value": 100}]},
        "exceptions": [], "unit_system": "mm",
    }
    r.update(over)
    return r


def mk_entity(**attrs):
    return {"entity_type": "thing", "id": "e1", "name": "E1", "attributes": attrs}


def one(rule, entity):
    rs = check_rule(rule, [entity])
    assert len(rs) == 1
    return rs[0]


def test_pass():
    assert one(mk_rule(), mk_entity(x_mm=150)).status == Status.PASS


def test_fail():
    assert one(mk_rule(), mk_entity(x_mm=50)).status == Status.FAIL


def test_absent_fact():
    assert one(mk_rule(), mk_entity()).status == Status.INFO_NOT_AVAILABLE


def test_low_confidence():
    e = mk_entity(x_mm={"value": 150, "confidence": 0.8, "source": "pdf"})
    assert one(mk_rule(), e).status == Status.UNCERTAIN


def test_fail_dominates():
    r = mk_rule(requires={"all": [
        {"fact": "x_mm", "op": ">=", "value": 100},
        {"fact": "y_mm", "op": ">=", "value": 100}]})
    assert one(r, mk_entity(x_mm=50)).status == Status.FAIL


def test_where_skips():
    r = mk_rule(applies_to={"entity_type": "thing", "where": {"kind": "a"}})
    assert check_rule(r, [mk_entity(x_mm=150, kind="b")]) == []


def test_where_absent_fact_reports_info_not_available():
    r = mk_rule(applies_to={"entity_type": "thing", "where": {"kind": "a"}})
    assert one(r, mk_entity(x_mm=150)).status == Status.INFO_NOT_AVAILABLE


def test_where_list_membership():
    r = mk_rule(applies_to={"entity_type": "thing", "where": {"kind": ["a", "b"]}})
    assert one(r, mk_entity(x_mm=150, kind="b")).status == Status.PASS


def test_exception_waives():
    r = mk_rule(exceptions=[{"description": "d", "fact": "waived", "op": "==", "value": True}])
    res = one(r, mk_entity(x_mm=50, waived=True))
    assert res.status == Status.PASS


def test_description_only_exception_ignored():
    r = mk_rule(exceptions=[{"description": "informational note, no fact"}])
    assert one(r, mk_entity(x_mm=50)).status == Status.FAIL


def test_fail_dominates_low_confidence():
    r = mk_rule(requires={"all": [
        {"fact": "x_mm", "op": ">=", "value": 100},
        {"fact": "y_mm", "op": ">=", "value": 100}]})
    e = mk_entity(x_mm=50, y_mm={"value": 150, "confidence": 0.5, "source": "pdf"})
    assert one(r, e).status == Status.FAIL


def test_missing_dominates_low_confidence():
    r = mk_rule(requires={"all": [
        {"fact": "x_mm", "op": ">=", "value": 100},
        {"fact": "y_mm", "op": ">=", "value": 100}]})
    e = mk_entity(y_mm={"value": 150, "confidence": 0.5, "source": "pdf"})
    assert one(r, e).status == Status.INFO_NOT_AVAILABLE


def test_fail_dominates_regardless_of_order():
    r = mk_rule(requires={"all": [
        {"fact": "y_mm", "op": ">=", "value": 100},
        {"fact": "x_mm", "op": ">=", "value": 100}]})
    assert one(r, mk_entity(x_mm=50)).status == Status.FAIL


def test_determinism():
    rs = {"ruleset_id": "t", "code_edition": "t", "rules": [mk_rule()]}
    f = {"project": {}, "entities": [mk_entity(x_mm=150)]}
    assert json.dumps(run_ruleset(rs, f)) == json.dumps(run_ruleset(rs, f))
