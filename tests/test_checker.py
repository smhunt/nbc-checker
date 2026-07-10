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


def vf_rule():
    return mk_rule(requires={"all": [
        {"fact": "depth_mm", "op": ">=", "value_fact": "run_mm", "offset": 0},
        {"fact": "depth_mm", "op": "<=", "value_fact": "run_mm", "offset": 25}]})


def test_value_fact_pass():
    assert one(vf_rule(), mk_entity(depth_mm=260, run_mm=255)).status == Status.PASS


def test_value_fact_fail():
    assert one(vf_rule(), mk_entity(depth_mm=290, run_mm=255)).status == Status.FAIL


def test_value_fact_ref_absent():
    assert one(vf_rule(), mk_entity(depth_mm=260)).status == Status.INFO_NOT_AVAILABLE


def test_value_fact_ref_uncertain():
    e = mk_entity(depth_mm=260, run_mm={"value": 255, "confidence": 0.5, "source": "pdf"})
    assert one(vf_rule(), e).status == Status.UNCERTAIN


def test_value_fact_comparison_recorded():
    res = one(vf_rule(), mk_entity(depth_mm=260, run_mm=255))
    assert any("run_mm+25" in c for c in res.comparisons)


def test_in_operator_pass():
    r = mk_rule(requires={"all": [{"fact": "grp", "op": "in", "value": ["C", "D", "E"]}]})
    assert one(r, mk_entity(grp="D")).status == Status.PASS


def test_in_operator_fail():
    r = mk_rule(requires={"all": [{"fact": "grp", "op": "in", "value": ["C", "D", "E"]}]})
    assert one(r, mk_entity(grp="Z9")).status == Status.FAIL


def test_not_in_operator():
    r = mk_rule(requires={"all": [{"fact": "grp", "op": "not_in", "value": ["F1"]}]})
    assert one(r, mk_entity(grp="C")).status == Status.PASS
    assert one(r, mk_entity(grp="F1")).status == Status.FAIL


def test_evidence_passes_through_to_facts_used_untouched():
    ev = {"doc": "A-201.pdf", "page": 1, "bbox": [0.41, 0.31, 0.47, 0.33]}
    e = mk_entity(x_mm={"value": 150, "confidence": 0.95, "source": "pdf", "evidence": ev})
    res = one(mk_rule(), e)
    used = [f for f in res.facts_used if f["fact"] == "x_mm"]
    assert used and used[0]["evidence"] == ev


def test_absent_evidence_yields_none_in_facts_used():
    res = one(mk_rule(), mk_entity(x_mm=150))
    assert all(f["evidence"] is None for f in res.facts_used)


def test_report_hash_stable_with_evidence():
    import hashlib
    rs = {"ruleset_id": "t", "code_edition": "t", "rules": [mk_rule()]}
    ev = {"doc": "d.pdf", "page": 2}
    f = {"project": {}, "entities": [mk_entity(
        x_mm={"value": 150, "confidence": 1.0, "source": "s", "evidence": ev})]}
    h = [hashlib.sha256(json.dumps(run_ruleset(rs, f), sort_keys=True).encode()).hexdigest()
         for _ in range(2)]
    assert h[0] == h[1]


def test_determinism():
    rs = {"ruleset_id": "t", "code_edition": "t", "rules": [mk_rule()]}
    f = {"project": {}, "entities": [mk_entity(x_mm=150)]}
    assert json.dumps(run_ruleset(rs, f)) == json.dumps(run_ruleset(rs, f))


# --- Renovation scope (new_work_only) + jurisdiction ---

def test_scope_skips_existing():
    r = mk_rule(scope="new_work_only")
    assert check_rule(r, [mk_entity(x_mm=50, work_status="existing")]) == []


def test_scope_checks_new():
    r = mk_rule(scope="new_work_only")
    assert one(r, mk_entity(x_mm=50, work_status="new")).status == Status.FAIL


def test_scope_default_in_scope_when_absent():
    r = mk_rule(scope="new_work_only")
    assert one(r, mk_entity(x_mm=150)).status == Status.PASS


def test_no_scope_still_checks_existing():
    r = mk_rule()  # no scope declared
    assert one(r, mk_entity(x_mm=50, work_status="existing")).status == Status.FAIL


def test_scope_existing_as_confidence_object():
    r = mk_rule(scope="new_work_only")
    e = mk_entity(x_mm=50, work_status={"value": "existing", "confidence": 1.0, "source": "plan note"})
    assert check_rule(r, [e]) == []


def test_jurisdiction_surfaced():
    rs = {"ruleset_id": "t", "code_edition": "t", "rules": [mk_rule()]}
    f = {"project": {"jurisdiction": "Ontario"}, "entities": [mk_entity(x_mm=150)]}
    assert run_ruleset(rs, f)["jurisdiction"] == "Ontario"


def test_jurisdiction_absent_is_none():
    rs = {"ruleset_id": "t", "code_edition": "t", "rules": [mk_rule()]}
    f = {"project": {}, "entities": [mk_entity(x_mm=150)]}
    assert run_ruleset(rs, f)["jurisdiction"] is None
