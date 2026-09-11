# Benchmarks

Run all commands from the repository root. The maintained entrypoint is
`.venv/bin/python -m benchmarks`; use `--help` after any command for its options.

## Choose an evaluation

| Evaluation | Purpose |
| --- | --- |
| `locomo` | External long-conversation QA; inspect cumulative memory and retrieval alongside scores. |
| `mab` | External MemoryAgentBench datasets for retrieval, conflicts, long-range understanding, and learning. |
| `daily-driver` | Controlled cumulative scenarios with gold evidence, wiki expectations, lifecycle actions, and checkpoint probes. |
| [Model experiments](experiments/README.md) | Opt-in contract and reasoning investigations; not acceptance benchmarks. |

Code lives in `suites/`, shared adapters/scoring in `shared/`, and custom scenarios
in `suites/daily_driver/fixtures/`. Focused unit-test inputs remain in `tests/fixtures/`.

## Setup and configuration

Install the environment with `uv sync --group dev --group benchmark`. External
LoCoMo data defaults to `../locomo/data/locomo10.json`; MAB requires its checkout
at `../MemoryAgentBench`, its dependencies, and dataset downloads. Obtain those
projects/data separately. Have Ollama running with the requested models before
starting model-backed evaluations; the benchmark does not start the server.

Pass `--config-path mycelium.toml` explicitly for LoCoMo/MAB to use project memory
settings, including reasoning. Their QA model defaults to `gemma4:latest` and
memory model defaults to the QA model; examples pin both to `gemma4:12b`.
Daily-driver defaults to `mycelium.toml` and uses its configured models.

New runs write beneath `benchmark_runs/`. `--output-root` changes that location;
`--run-id my-experiment-v1` supplies a custom name. Otherwise names include a local
timestamp: `<benchmark>-<system>-YYYYMMDD-HHMMSS`, or
`daily-driver-<fixture>-YYYYMMDD-HHMMSS`. Choose distinct names for concurrent runs.

## LoCoMo

A small encoding run with per-session snapshots and no QA:

```bash
.venv/bin/python -m benchmarks locomo \
  --config-path mycelium.toml \
  --qa-model gemma4:12b --memory-model gemma4:12b \
  --sample-index 3 --max-sessions 2 --max-questions 0 \
  --snapshot-sessions
```

Remove `--max-questions 0` to answer all questions; use `--max-questions 5` for a
small QA smoke run. Questions are not filtered to the ingested session limit,
so partial-session QA is diagnostic, not a full coverage score. Sample indexes
are 1-based. Remove sample/session/question limits for a full dataset run:

```bash
.venv/bin/python -m benchmarks locomo \
  --config-path mycelium.toml \
  --qa-model gemma4:12b --memory-model gemma4:12b \
  --snapshot-sessions
```

Invoke separately with `--system null`, `full_context`, `full_wiki`, or
`gold_evidence` for controls. Store snapshots require a Mycelium-backed system.
The default `--dream-policy per-batch` builds after each session; `per-case`
builds after ingestion and its session snapshots reflect that difference.

Use `--questions-per-category N` for a balanced diagnostic QA panel.
`--replay-store <case-store>` reuses extraction artifacts;
`--replay-assignments` additionally preserves assignments. For exact-store QA:

```bash
.venv/bin/python -m benchmarks locomo \
  --config-path mycelium.toml --qa-model gemma4:12b \
  --sample-index 3 --max-questions 5 \
  --frozen-store benchmark_runs/BASELINE/stores/conv-41 \
  --dream-policy none --run-id frozen-qa-v1
```

Replace the store path and select its matching sample. Frozen QA cannot create
session snapshots. `--include-retrieval-context` saves rendered answer context
for inspection. `--wiki-baseline --sample-index 3 --max-sessions 2` is a separate
fresh encoding-only mode with checkpoint snapshots and optional `--user-speaker`.

Ordinary LoCoMo supports resuming a matching run via the same `--run-id` and
settings. Existing session snapshots stay intact. Enabling snapshots on an old
run changes settings, so use a fresh ID. Wiki-baseline requires a fresh directory.

## Daily-driver scenarios

All three scenarios use the same runner and evaluator:

| Fixture directory | Role |
| --- | --- |
| `daily_driver_v1` | Primary cumulative memory, ownership, correction, and retraction scenario. |
| `daily_driver_paraphrased_v1` | Renamed/rephrased transfer case for generalization. |
| `daily_driver_unrelated_v1` | Transfer case in a home-renovation setting. |

Set a fixture path and validate it without model calls:

```bash
fixture=benchmarks/suites/daily_driver/fixtures/daily_driver_v1
.venv/bin/python -m benchmarks daily-driver validate "$fixture"
.venv/bin/python -m benchmarks daily-driver run "$fixture" \
  --config-path mycelium.toml --run-id daily-driver-v1-baseline
```

Substitute either other directory to run its scenario. Add `--trials 3` for
independent acceptance trials or `--skip-probe-answers` to skip answer generation
and judging while retaining retrieval checks. New runs require empty/fresh output
directories; they do not resume. Each trial has its own subdirectory.

Replay extraction while rerunning downstream memory work:

```bash
.venv/bin/python -m benchmarks daily-driver run "$fixture" \
  --replay-extraction-store benchmark_runs/daily-driver-v1-baseline/store \
  --run-id daily-driver-v1-replay
```

Refresh deterministic comparisons of an existing run without model calls:

```bash
.venv/bin/python -m benchmarks daily-driver compare "$fixture" \
  --output-dir benchmark_runs/daily-driver-v1-baseline
```

For repeated trials, compare a specific trial directory. See the
[primary fixture guide](suites/daily_driver/fixtures/daily_driver_v1/README.md)
for checkpoint expectations and acceptance details.

## MemoryAgentBench

Run an explicit dataset configuration:

```bash
.venv/bin/python -m benchmarks mab \
  --config-path mycelium.toml \
  --qa-model gemma4:12b --memory-model gemma4:12b \
  --mab-root ../MemoryAgentBench \
  --dataset-config ../MemoryAgentBench/configs/data_conf/Accurate_Retrieval/EventQA/Eventqa_full.yaml \
  --max-contexts 1 --max-queries 3
```

Remove the limits for the configuration's full workload. Invoke separately for
each configuration/system; there is no batch orchestrator. Use fresh IDs for MAB:
it does not implement the LoCoMo resume protocol. The former runner's curated
configuration list, relative to the MAB checkout, is:

```text
configs/data_conf/Accurate_Retrieval/EventQA/Eventqa_full.yaml
configs/data_conf/Accurate_Retrieval/LongMemEval/Longmemeval_s.yaml
configs/data_conf/Accurate_Retrieval/LongMemEval/Longmemeval_s_star.yaml
configs/data_conf/Conflict_Resolution/Factconsolidation_sh_6k.yaml
configs/data_conf/Conflict_Resolution/Factconsolidation_sh_32k.yaml
configs/data_conf/Conflict_Resolution/Factconsolidation_sh_64k.yaml
configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml
configs/data_conf/Conflict_Resolution/Factconsolidation_mh_32k.yaml
configs/data_conf/Conflict_Resolution/Factconsolidation_mh_64k.yaml
configs/data_conf/Long_Range_Understanding/Detective_QA.yaml
configs/data_conf/Long_Range_Understanding/InfBench_sum.yaml
configs/data_conf/Test_Time_Learning/ICL/ICL_banking77.yaml
configs/data_conf/Test_Time_Learning/ICL/ICL_clinic150.yaml
configs/data_conf/Test_Time_Learning/ICL/ICL_nlu.yaml
configs/data_conf/Test_Time_Learning/ICL/ICL_trec_coarse.yaml
configs/data_conf/Test_Time_Learning/ICL/ICL_trec_fine.yaml
```

## Inspect results

LoCoMo writes `summary.json`, predictions, and per-case `stores/`; ordinary
snapshots are under `snapshots/<sample-id>/session_N/`. MAB writes `results.json`
and its summary alongside adapter artifacts. Daily-driver retains checkpoint
stores/wiki, probe results, `comparison.json`, and `evaluation.json`; repeated
trials also produce `trial_summary.json`.

Inspect useful evidence coverage, attribution and correctness, concise wiki prose,
page organization, preserved uncertainty/history, and retrieval of concrete details.
Check diagnostics for failed/retried calls, stage timings, and output tokens.
Claim membership alone does not establish semantic completeness or correct synthesis.
Compare matched inputs/settings; partial runs and transfer scenarios are diagnostics,
not interchangeable aggregate scores. See [iteration protocol](../BENCHMARK_ITERATION.md).
