#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

MAB_ROOT="${MAB_ROOT:-../MemoryAgentBench}"
SYSTEM="${SYSTEM:-mycelium}"
QA_MODEL="${QA_MODEL:-gemma4:latest}"
MEMORY_MODEL="${MEMORY_MODEL:-${QA_MODEL}}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
OUTPUT_ROOT="${OUTPUT_ROOT:-benchmark_runs}"
RUN_TAG="${RUN_TAG:-$(date +%Y%m%d-%H%M%S)}"
DREAM_POLICY="${DREAM_POLICY:-per-case}"

CONFIGS=(
  "configs/data_conf/Accurate_Retrieval/EventQA/Eventqa_full.yaml"
  "configs/data_conf/Accurate_Retrieval/LongMemEval/Longmemeval_s.yaml"
  "configs/data_conf/Accurate_Retrieval/LongMemEval/Longmemeval_s_star.yaml"
  "configs/data_conf/Conflict_Resolution/Factconsolidation_sh_6k.yaml"
  "configs/data_conf/Conflict_Resolution/Factconsolidation_sh_32k.yaml"
  "configs/data_conf/Conflict_Resolution/Factconsolidation_sh_64k.yaml"
  "configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml"
  "configs/data_conf/Conflict_Resolution/Factconsolidation_mh_32k.yaml"
  "configs/data_conf/Conflict_Resolution/Factconsolidation_mh_64k.yaml"
  "configs/data_conf/Long_Range_Understanding/Detective_QA.yaml"
  "configs/data_conf/Long_Range_Understanding/InfBench_sum.yaml"
  "configs/data_conf/Test_Time_Learning/ICL/ICL_banking77.yaml"
  "configs/data_conf/Test_Time_Learning/ICL/ICL_clinic150.yaml"
  "configs/data_conf/Test_Time_Learning/ICL/ICL_nlu.yaml"
  "configs/data_conf/Test_Time_Learning/ICL/ICL_trec_coarse.yaml"
  "configs/data_conf/Test_Time_Learning/ICL/ICL_trec_fine.yaml"
)

for rel_config in "${CONFIGS[@]}"; do
  config="${MAB_ROOT}/${rel_config}"
  name="$(basename "${config}" .yaml)"
  run_id="mab-${SYSTEM}-${name}-${RUN_TAG}"
  echo "Running MemoryAgentBench: config=${rel_config}, system=${SYSTEM}, run_id=${run_id}"
  uv run python -m benchmarks.mycelium_bench mab \
    --mab-root "${MAB_ROOT}" \
    --dataset-config "${config}" \
    --system "${SYSTEM}" \
    --qa-model "${QA_MODEL}" \
    --memory-model "${MEMORY_MODEL}" \
    --ollama-url "${OLLAMA_URL}" \
    --output-root "${OUTPUT_ROOT}" \
    --dream-policy "${DREAM_POLICY}" \
    --run-id "${run_id}"
done
