#!/usr/bin/env bash
# Determinism demonstration (challenge EO1 / feasibility evidence T6).
# Runs the engine on identical inputs N times and shows the report hashes
# are byte-for-byte identical. A generative model cannot make this guarantee;
# our deterministic engine can, and that is the product's core claim.
set -euo pipefail
cd "$(dirname "$0")/.."

RULES=rules/nbc2020_part9_core.json
FACTS=samples/sample_dwelling_facts.json
N=${1:-5}

echo "Deterministic NBC engine — running identical inputs ${N}x"
echo "Ruleset: ${RULES}"
echo "Facts:   ${FACTS}"
echo "------------------------------------------------------------"
for i in $(seq 1 "$N"); do
  # engine/checker.py prints the raw report JSON to stdout (pure function)
  sha=$(python3 engine/checker.py "$RULES" "$FACTS" | shasum -a 256 | cut -d' ' -f1)
  echo "run ${i}: ${sha}"
done
echo "------------------------------------------------------------"
uniq_count=$(for i in $(seq 1 "$N"); do
  python3 engine/checker.py "$RULES" "$FACTS" | shasum -a 256 | cut -d' ' -f1
done | sort -u | wc -l | tr -d ' ')
if [ "$uniq_count" -eq 1 ]; then
  echo "PASS: all ${N} runs produced one identical SHA-256 — deterministic."
else
  echo "FAIL: ${uniq_count} distinct hashes — NON-deterministic!"
  exit 1
fi
