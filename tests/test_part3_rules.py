"""Expected-status tests for the NBC 2020 Part 3 ruleset against the sample facts.

Every (rule_id, entity_id, status) row below is an intentional fixture:
pass/fail/info_not_available/uncertain paths are all exercised. If an engine
or ruleset change flips any of these, that is a behavioural change requiring
review — not a test to silently update.
"""
import json

import pytest

from engine.checker import run_ruleset

RULESET = "rules/nbc2020_part3_core.json"
FACTS = "samples/sample_part3_facts.json"

# (rule_id, entity_id, expected status)
EXPECTED = [
    # fire separations
    ("NBC-3.1.3.1-separation-C-D", "fs-C-D-01", "pass"),
    ("NBC-3.1.3.1-separation-C-E", "fs-C-E-01", "fail"),          # 1 h provided, 2 h required
    ("NBC-3.3.1.4-corridor-separation-restricted-occ", "fs-corr-01", "info_not_available"),
    ("NBC-3.1.3.1-separation-A2-C", "fs-A2-C-01", "pass"),
    # sprinklered storey waives the rating via the Sentence (3) exception
    ("NBC-3.3.1.4-corridor-separation-general", "fs-corr-02", "pass"),
    ("NBC-3.1.8.4-closure-2h-separation", "door-2h-01", "pass"),
    ("NBC-3.1.8.13-door-self-closing", "door-2h-01", "pass"),
    ("NBC-3.1.8.4-closure-1h-separation", "door-1h-01", "uncertain"),   # 0.85 confidence
    ("NBC-3.1.8.13-door-self-closing", "door-1h-01", "info_not_available"),
    # occupancy / occupant load
    ("NBC-3.1.17.1-occupant-load-office", "fa-office-200", "pass"),
    ("NBC-3.1.17.1-occupant-load-assembly-non-fixed-seats", "fa-restaurant-100", "fail"),
    ("NBC-3.1.17.1-occupant-load-mercantile-first-storey", "fa-retail-main", "info_not_available"),
    ("NBC-3.1.17.1-occupant-load-classroom", "fa-classroom-12", "uncertain"),
    ("NBC-3.1.17.1-occupant-load-dwelling-sleeping-rooms", "fa-unit-301", "pass"),
    ("NBC-3.1.2.1-major-occupancy-classification", "fa-office-200", "pass"),
    ("NBC-3.1.2.1-major-occupancy-classification", "fa-classroom-12", "info_not_available"),
    ("NBC-3.1.17.1-2-occupant-load-posting", "fa-restaurant-100", "pass"),
    ("NBC-3.1.17.1-2-occupant-load-posting", "fa-retail-main", "info_not_available"),
    ("NBC-3.1.17.1-2-occupant-load-posting", "fa-classroom-12", "fail"),
    # exits (3.4)
    ("NBC-3.4.3.2-exit-stair-min-width", "STAIR-EX-1", "pass"),
    ("NBC-3.4.6.3-max-vertical-rise-and-landings", "STAIR-EX-1", "pass"),
    ("NBC-3.4.6.4-landing-width", "STAIR-EX-1", "pass"),
    ("NBC-3.4.6.5-handrail-height-exit", "STAIR-EX-1", "pass"),
    ("NBC-3.4.6.6-guard-height-exit", "STAIR-EX-1", "pass"),
    ("NBC-3.4.6.8-tread-run-riser-height", "STAIR-EX-1", "pass"),
    ("NBC-3.4.3.4-headroom-clearance-exit", "STAIR-EX-1", "pass"),
    ("NBC-3.4.3.2-exit-stair-min-width", "STAIR-EX-2", "fail"),
    ("NBC-3.4.6.3-max-vertical-rise-and-landings", "STAIR-EX-2", "fail"),
    ("NBC-3.4.6.4-landing-width", "STAIR-EX-2", "pass"),
    ("NBC-3.4.6.5-handrail-height-exit", "STAIR-EX-2", "uncertain"),
    ("NBC-3.4.6.6-guard-height-exit", "STAIR-EX-2", "fail"),
    ("NBC-3.4.6.8-tread-run-riser-height", "STAIR-EX-2", "fail"),
    ("NBC-3.4.3.4-headroom-clearance-exit", "STAIR-EX-2", "info_not_available"),
    ("NBC-3.4.3.2-exit-doorway-min-width", "DOOR-EX-1", "fail"),
    ("NBC-3.4.3.2-exit-corridor-min-width", "CORR-EX-1", "pass"),
    ("NBC-3.4.2.1-min-number-of-exits", "FLOOR-2", "fail"),
    # barrier-free / accessibility (3.8)
    ("NBC-3.8.2.2-bf-entrance-required", "ENT-01", "pass"),
    ("NBC-3.8.3.2-bf-path-clear-width", "COR-01", "uncertain"),
    ("NBC-3.8.3.5-bf-ramp-clear-width", "RMP-01", "pass"),
    ("NBC-3.8.3.5-bf-ramp-max-slope", "RMP-01", "pass"),
    ("NBC-3.8.3.5-bf-ramp-landings", "RMP-01", "pass"),
    ("NBC-3.8.3.5-bf-ramp-handrail-height", "RMP-01", "pass"),
    ("NBC-3.8.3.6-bf-door-clear-width", "DR-03", "fail"),
    ("NBC-3.8.3.6-bf-door-operating-device-height", "DR-03", "info_not_available"),
    ("NBC-3.8.3.12-wc-stall-dimensions", "WCS-01", "pass"),
    ("NBC-3.8.3.12-wc-stall-grab-bar", "WCS-01", "info_not_available"),
]


@pytest.fixture(scope="module")
def report():
    with open(RULESET) as f:
        ruleset = json.load(f)
    with open(FACTS) as f:
        facts = json.load(f)
    return run_ruleset(ruleset, facts)


@pytest.fixture(scope="module")
def by_key(report):
    return {(r["rule_id"], r["entity_id"]): r["status"] for r in report["results"]}


@pytest.mark.parametrize("rule_id,entity_id,expected", EXPECTED,
                         ids=[f"{r}~{e}" for r, e, _ in EXPECTED])
def test_expected_status(by_key, rule_id, entity_id, expected):
    assert (rule_id, entity_id) in by_key, "expected a result for this rule/entity pair"
    assert by_key[(rule_id, entity_id)] == expected


def test_every_part3_rule_fires_at_least_once(report):
    with open(RULESET) as f:
        rule_ids = {r["rule_id"] for r in json.load(f)["rules"]}
    fired = {r["rule_id"] for r in report["results"]}
    assert rule_ids == fired, f"rules never exercised by sample facts: {rule_ids - fired}"


def test_all_four_statuses_exercised(report):
    statuses = {r["status"] for r in report["results"]}
    assert statuses == {"pass", "fail", "info_not_available", "uncertain"}
