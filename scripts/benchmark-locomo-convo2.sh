#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

LOCOMO_PATH="${LOCOMO_PATH:-../locomo/data/locomo10.json}"
QA_MODEL="${QA_MODEL:-gemma4:latest}"
MEMORY_MODEL="${MEMORY_MODEL:-${QA_MODEL}}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
OUTPUT_ROOT="${OUTPUT_ROOT:-benchmark_runs}"
RUN_TAG="${RUN_TAG:-$(date +%Y%m%d-%H%M%S)}"
DREAM_POLICY="${DREAM_POLICY:-per-batch}"
SAMPLE_INDEX="${SAMPLE_INDEX:-2}"

if [ "$#" -gt 0 ]; then
  SYSTEMS=("$@")
else
  SYSTEMS=(mycelium)
fi

extra_args=()
if [ -n "${MAX_QUESTIONS:-}" ]; then
  extra_args+=(--max-questions "${MAX_QUESTIONS}")
fi
if [ -n "${REPLAY_STORE:-}" ]; then
  extra_args+=(--replay-store "${REPLAY_STORE}")
fi
if [ "${REPLAY_ASSIGNMENTS:-0}" = "1" ]; then
  extra_args+=(--replay-assignments)
fi

for system in "${SYSTEMS[@]}"; do
  run_id="locomo-${system}-convo-${SAMPLE_INDEX}-${RUN_TAG}"
  echo "Running LoCoMo quick benchmark: system=${system}, sample_index=${SAMPLE_INDEX}, run_id=${run_id}"
  uv run python -m benchmarks.mycelium_bench locomo \
    --locomo-path "${LOCOMO_PATH}" \
    --sample-index "${SAMPLE_INDEX}" \
    --system "${system}" \
    --qa-model "${QA_MODEL}" \
    --memory-model "${MEMORY_MODEL}" \
    --ollama-url "${OLLAMA_URL}" \
    --output-root "${OUTPUT_ROOT}" \
    --dream-policy "${DREAM_POLICY}" \
    --run-id "${run_id}" \
    "${extra_args[@]}"
done
