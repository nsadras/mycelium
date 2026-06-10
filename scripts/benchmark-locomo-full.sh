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

if [ "$#" -gt 0 ]; then
  SYSTEMS=("$@")
else
  SYSTEMS=(mycelium null full_context)
fi

for system in "${SYSTEMS[@]}"; do
  run_id="locomo-${system}-full-${RUN_TAG}"
  echo "Running LoCoMo full benchmark: system=${system}, run_id=${run_id}"
  uv run python -m benchmarks.mycelium_bench locomo \
    --locomo-path "${LOCOMO_PATH}" \
    --system "${system}" \
    --qa-model "${QA_MODEL}" \
    --memory-model "${MEMORY_MODEL}" \
    --ollama-url "${OLLAMA_URL}" \
    --output-root "${OUTPUT_ROOT}" \
    --dream-policy "${DREAM_POLICY}" \
    --run-id "${run_id}"
done
