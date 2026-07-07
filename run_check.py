#!/usr/bin/env python3
"""Run a compliance check and print a reviewer-friendly report.

Usage:
  python3 run_check.py rules/nbc2020_part9_core.json samples/sample_dwelling_facts.json
  python3 run_check.py rules/nbc2020_part9_core.json --ifc path/to/model.ifc
  python3 run_check.py rules/nbc2020_part9_core.json --pdf path/to/drawing.pdf
Append --export-pdf and/or --export-xlsx to also write reports/last_report.{pdf,xlsx}.
"""

import json
import sys
sys.path.insert(0, ".")

from engine.checker import run_ruleset, Status  # noqa: E402

ICONS = {
    "pass": "PASS ",
    "fail": "FAIL ",
    "info_not_available": "NOINF",
    "uncertain": "REVIEW",
}


def main():
    ruleset_path = sys.argv[1]
    with open(ruleset_path) as f:
        ruleset = json.load(f)

    if sys.argv[2] == "--ifc":
        from extractors.ifc_extractor import extract
        facts = extract(sys.argv[3])
    elif sys.argv[2] == "--pdf":
        from extractors.pdf_extractor import extract
        facts = extract(sys.argv[3])
    else:
        with open(sys.argv[2]) as f:
            facts = json.load(f)

    report = run_ruleset(ruleset, facts)

    print("=" * 78)
    print(f"NBC COMPLIANCE CHECK — {report['project'].get('name', '?')}")
    print(f"Ruleset: {report['ruleset_id']} ({report['code_edition']})")
    print("=" * 78)

    for r in report["results"]:
        tag = ICONS[r["status"]].strip()
        print(f"\n[{tag}] {r['rule_id']} — {r['title']}")
        print(f"       Provision: {r['provision']}")
        print(f"       Element:   {r['entity_name']} ({r['entity_id']})")
        print(f"       Finding:   {r['detail']}")
        for c in r.get("comparisons", []):
            print(f"         · {c}")

    s = report["summary"]
    print("\n" + "=" * 78)
    print(f"SUMMARY: {s['pass']} pass | {s['fail']} fail | "
          f"{s['info_not_available']} info not available | {s['uncertain']} require human review")
    print("Deterministic engine — identical inputs always produce identical results.")
    print("=" * 78)

    with open("reports/last_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Full audit trail written to reports/last_report.json")

    if "--export-pdf" in sys.argv:
        from engine.export import to_pdf
        to_pdf(report, "reports/last_report.pdf")
        print("PDF report written to reports/last_report.pdf")
    if "--export-xlsx" in sys.argv:
        from engine.export import to_xlsx
        to_xlsx(report, "reports/last_report.xlsx")
        print("Excel report written to reports/last_report.xlsx")


if __name__ == "__main__":
    import os
    os.makedirs("reports", exist_ok=True)
    main()
