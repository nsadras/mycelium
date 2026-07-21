#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

RUN_TAG="${RUN_TAG:-$(date +%Y%m%d-%H%M%S)}"
SAMPLE_INDEXES="${SAMPLE_INDEXES:-2}"
ABLATION_MODES="${ABLATION_MODES:-raw claims hybrid}"

for sample_index in ${SAMPLE_INDEXES}; do
  for evidence_mode in ${ABLATION_MODES}; do
    echo "Running LoCoMo ablation: sample=${sample_index}, evidence=${evidence_mode}, tag=${RUN_TAG}"
    SAMPLE_INDEX="${sample_index}" \
      EVIDENCE_MODE="${evidence_mode}" \
      RUN_TAG="${RUN_TAG}-${evidence_mode}" \
      "${SCRIPT_DIR}/benchmark-locomo-convo2.sh" mycelium
  done
done

uv run python -m benchmarks.mycelium_bench.ablation \
  --output-root "${OUTPUT_ROOT:-benchmark_runs}" \
  --run-tag "${RUN_TAG}"
