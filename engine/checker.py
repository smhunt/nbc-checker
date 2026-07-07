"""
Deterministic NBC compliance rule engine.

Design principles (aligned with ISC challenge EO1-EO7):
- No probabilistic judgment. Every result is a pure function of
  (rule definition, extracted facts). Same inputs -> same outputs, always.
- Four-status output per check:
    PASS                 - all requirements satisfied
    FAIL                 - a requirement is violated by a confident fact
    INFO_NOT_AVAILABLE   - a required fact is absent from the extracted model
    UNCERTAIN            - a required fact exists but below confidence
                           threshold (e.g. LLM-extracted from a PDF), or
                           applicability could not be determined
- Full audit trail: every check records the provision, the facts used,
  the comparison performed, and the source of each fact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

CONFIDENCE_THRESHOLD = 0.9  # facts below this are UNCERTAIN, never PASS/FAIL


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INFO_NOT_AVAILABLE = "info_not_available"
    UNCERTAIN = "uncertain"


OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

# Status dominance within a single check: a violation must never be masked by
# a missing or low-confidence fact in another requirement of the same rule.
_SEVERITY = {"pass": 0, "uncertain": 1, "info_not_available": 2, "fail": 3}


def _worse(a: "Status", b: "Status") -> "Status":
    return a if _SEVERITY[a.value] >= _SEVERITY[b.value] else b


@dataclass
class FactLookup:
    name: str
    value: Any = None
    confidence: float | None = None
    source: str | None = None
    present: bool = False


@dataclass
class CheckResult:
    rule_id: str
    provision: str
    title: str
    entity_id: str
    entity_name: str
    status: Status
    detail: str
    facts_used: list[dict] = field(default_factory=list)
    comparisons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


def _lookup(entity: dict, fact_name: str) -> FactLookup:
    """Facts may be plain values or {value, confidence, source} objects."""
    attrs = entity.get("attributes", {})
    if fact_name not in attrs:
        return FactLookup(name=fact_name)
    raw = attrs[fact_name]
    if isinstance(raw, dict) and "value" in raw:
        return FactLookup(
            name=fact_name,
            value=raw["value"],
            confidence=raw.get("confidence", 1.0),
            source=raw.get("source"),
            present=True,
        )
    return FactLookup(name=fact_name, value=raw, confidence=1.0, present=True)


def _matches_where(entity: dict, where: dict) -> Status | bool:
    """True/False if determinable; UNCERTAIN/INFO_NOT_AVAILABLE status if not."""
    for fact_name, condition in where.items():
        fl = _lookup(entity, fact_name)
        if not fl.present:
            return Status.INFO_NOT_AVAILABLE
        if fl.confidence is not None and fl.confidence < CONFIDENCE_THRESHOLD:
            return Status.UNCERTAIN
        if isinstance(condition, dict) and "op" in condition:
            if not OPS[condition["op"]](fl.value, condition["value"]):
                return False
        elif isinstance(condition, list):
            if fl.value not in condition:
                return False
        else:
            if fl.value != condition:
                return False
    return True


def _exception_applies(entity: dict, exceptions: list[dict]) -> bool:
    for exc in exceptions:
        if "fact" not in exc:
            continue
        fl = _lookup(entity, exc["fact"])
        if fl.present and fl.confidence and fl.confidence >= CONFIDENCE_THRESHOLD:
            if OPS[exc["op"]](fl.value, exc["value"]):
                return True
    return False


def check_rule(rule: dict, entities: list[dict]) -> list[CheckResult]:
    results: list[CheckResult] = []
    target_type = rule["applies_to"]["entity_type"]
    where = rule["applies_to"].get("where", {})

    new_work_only = rule.get("scope") == "new_work_only"

    for entity in entities:
        if entity.get("entity_type") != target_type:
            continue

        # Renovation scoping: a rule marked "new_work_only" does not apply to
        # existing-to-remain elements. work_status is treated like any fact.
        # Absent work_status => in scope (greenfield default), so unscoped
        # projects behave exactly as before. Present-but-low-confidence still
        # evaluates — a reviewer can correct the status.
        if new_work_only:
            ws = _lookup(entity, "work_status")
            if ws.present and ws.value == "existing":
                continue

        applicability = _matches_where(entity, where)
        base = dict(
            rule_id=rule["rule_id"],
            provision=rule["provision"],
            title=rule["title"],
            entity_id=entity.get("id", "?"),
            entity_name=entity.get("name", "?"),
        )

        if applicability is False:
            continue  # rule simply does not apply to this entity
        if isinstance(applicability, Status):
            results.append(CheckResult(
                **base, status=applicability,
                detail=f"Applicability could not be determined "
                       f"({applicability.value}) for conditions {where}",
            ))
            continue

        if _exception_applies(entity, rule.get("exceptions", [])):
            results.append(CheckResult(
                **base, status=Status.PASS,
                detail="Requirement waived by a satisfied exception clause",
            ))
            continue

        status = Status.PASS
        detail_parts: list[str] = []
        facts_used: list[dict] = []
        comparisons: list[str] = []

        for req in rule["requires"]["all"]:
            fl = _lookup(entity, req["fact"])
            facts_used.append({
                "fact": fl.name, "value": fl.value,
                "confidence": fl.confidence, "source": fl.source,
                "present": fl.present,
            })
            if not fl.present:
                status = _worse(status, Status.INFO_NOT_AVAILABLE)
                detail_parts.append(f"'{req['fact']}' not found in extracted model")
                continue
            if fl.confidence is not None and fl.confidence < CONFIDENCE_THRESHOLD:
                status = _worse(status, Status.UNCERTAIN)
                detail_parts.append(
                    f"'{req['fact']}'={fl.value} extracted at confidence "
                    f"{fl.confidence:.2f} < {CONFIDENCE_THRESHOLD} — requires human review"
                )
                continue

            # Comparison target: a literal value, or another fact on the same
            # entity (value_fact) plus an optional offset — e.g. tread depth
            # must be >= run and <= run + 25 (NBC 9.8.4.2.(2)). The reference
            # fact is gated exactly like the primary fact.
            if "value_fact" in req:
                ref = _lookup(entity, req["value_fact"])
                facts_used.append({
                    "fact": ref.name, "value": ref.value,
                    "confidence": ref.confidence, "source": ref.source,
                    "present": ref.present,
                })
                if not ref.present:
                    status = _worse(status, Status.INFO_NOT_AVAILABLE)
                    detail_parts.append(
                        f"'{req['value_fact']}' (comparison reference) not found in extracted model")
                    continue
                if ref.confidence is not None and ref.confidence < CONFIDENCE_THRESHOLD:
                    status = _worse(status, Status.UNCERTAIN)
                    detail_parts.append(
                        f"'{req['value_fact']}'={ref.value} (comparison reference) extracted "
                        f"at confidence {ref.confidence:.2f} < {CONFIDENCE_THRESHOLD} — requires human review")
                    continue
                offset = req.get("offset", 0)
                target = ref.value + offset
                target_desc = f"{req['value_fact']}{f'+{offset}' if offset else ''} ({target})"
            else:
                target = req["value"]
                target_desc = str(target)

            ok = OPS[req["op"]](fl.value, target)
            comparisons.append(
                f"{req['fact']} ({fl.value}) {req['op']} {target_desc} -> "
                f"{'OK' if ok else 'VIOLATION'}"
            )
            if not ok:
                status = _worse(status, Status.FAIL)  # FAIL dominates all other statuses
                detail_parts.append(
                    f"VIOLATION: {req['fact']}={fl.value}, "
                    f"required {req['op']} {target_desc} per {rule['provision']}"
                )

        if status == Status.PASS and not detail_parts:
            detail_parts.append("All requirements satisfied")

        results.append(CheckResult(
            **base, status=status, detail="; ".join(detail_parts),
            facts_used=facts_used, comparisons=comparisons,
        ))
    return results


def run_ruleset(ruleset: dict, facts: dict) -> dict:
    entities = facts.get("entities", [])
    all_results: list[CheckResult] = []
    for rule in ruleset["rules"]:
        all_results.extend(check_rule(rule, entities))

    summary = {s.value: 0 for s in Status}
    for r in all_results:
        summary[r.status.value] += 1

    return {
        "ruleset_id": ruleset["ruleset_id"],
        "code_edition": ruleset["code_edition"],
        "jurisdiction": facts.get("project", {}).get("jurisdiction"),
        "project": facts.get("project", {}),
        "summary": summary,
        "results": [r.to_dict() for r in all_results],
        "engine": {
            "deterministic": True,
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "note": "Results are a pure function of ruleset + facts. "
                    "No generative model participates in pass/fail judgment.",
        },
    }


def main(ruleset_path: str, facts_path: str) -> dict:
    with open(ruleset_path) as f:
        ruleset = json.load(f)
    with open(facts_path) as f:
        facts = json.load(f)
    return run_ruleset(ruleset, facts)


if __name__ == "__main__":
    import sys
    report = main(sys.argv[1], sys.argv[2])
    print(json.dumps(report, indent=2))
