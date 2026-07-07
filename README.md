# NBC Compliance Checker (ISC Challenge Prototype)

Deterministic AI-assisted compliance checking of building permit applications
against NBC 2020 Part 9. Prototype for NRC ISC Phase 2 challenge (closes Aug 4 2026).

## Quick start
    pip install ifcopenshell --break-system-packages
    python3 run_check.py rules/nbc2020_part9_core.json samples/sample_dwelling_facts.json
    python3 run_check.py rules/nbc2020_part9_core.json --ifc samples/smoke_test.ifc

## Layout
    rules/       machine-readable NBC rules (JSON, provision-cited, RASE-inspired)
    engine/      deterministic 4-status rule engine (pure function, audit trail)
    extractors/  IFC -> facts (confidence 1.0); PDF/LLM extractor planned (conf < 1.0)
    samples/     sample facts + IFC generator
    reports/     JSON audit reports

See prompt_plan.md for the July sprint plan and progress.md for the session log.
