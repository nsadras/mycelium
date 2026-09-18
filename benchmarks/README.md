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

Current QA rows report `retrieval_seconds`: the initial memory retrieval before
answer generation. `query_time_len` measures answering, including any subsequent
tool searches. Offline ingestion/build time is recorded separately by the run
and operation traces. LoCoMo protocol 6 rejects earlier checkpoints; use a fresh
run directory. Historical `memory_construction_time` values in Mycelium QA rows
measured initial retrieval, despite their name. Do not compare those values with
offline construction costs. Saved results are not rewritten.

Daily-driver runs save the loaded `fixture.json` and its digest, including source
timestamps and ordered review actions, plus the answer judge's version and prompt/
schema digests. Judge version 2 separately checks answering the question and
unsupported assertions within the same flat response. It accepts concise answers;
source review is still required to interpret model-judged results. The first-build
application-form probe requires the requested form; privacy/purpose have separate
questions. Prior scores with broader requirements are not matched comparisons.

## Setup and configuration

Install the environment with `uv sync --group dev --group benchmark`. External
LoCoMo data defaults to `../locomo/data/locomo10.json`; MAB requires its checkout
at `../MemoryAgentBench`, its dependencies, and dataset downloads. Obtain those
projects/data separately. Have Ollama running with the requested models before
starting model-backed evaluations; the benchmark does not start the server.

Pass `--config-path mycelium.toml` explicitly for LoCoMo/MAB to use project memory
settings, including reasoning. CLI overrides take precedence over this file;
unspecified fields use dataclass defaults. Without a file, both models default
to `gemma4:12b`. `--qa-model` and `--memory-model` override their respective roles
independently. Daily-driver defaults to `mycelium.toml`.

Each run captures and validates its configuration once; edits to the input file
do not alter later cases or daily-driver trials. LoCoMo records effective memory
and QA settings in its manifest and rejects resumes with changed settings. MAB
and daily-driver write `configuration.json`; daily-driver also includes the
configuration in `run.json`. These files describe settings, not completion or
quality. A requested config file that is missing or invalid fails explicitly.

This storage version requires fresh runs; old JSON stores remain offline artifacts and
cannot be resumed or used as replay stores. New runs write beneath `benchmark_runs/`. `--output-root` changes that location;
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
Replay carries retained claims and their subject references into a new view Build. For exact-store QA:

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

### Optional reference-based semantic scoring

Add `--semantic-scoring` to a LoCoMo QA run to evaluate saved predictions with the
configured QA model. It compares answer meaning against the dataset reference;
it does not audit source conversations or verify retrieval grounding. The legacy
token score remains unchanged. The scorer reports correct/partial/incorrect and
ungradable judgments, grading coverage, and strict accuracy among gradable
answers. Failed and ungradable judgments are excluded from that denominator and
reported explicitly. A partially correct answer does not count as fully correct.

Answers are checkpointed before scoring. A matching resume retries unfinished
judgments without regenerating saved answers or successful judgments. The
manifest records separate `qa_status` and `scoring_status`, scorer prompt/schema,
settings and model digest. A run can finish QA with incomplete scoring. Individual
judgments live in `questions/*.json` and `predictions.jsonl`; the aggregate is
`summary.json.semantic_scoring`. Per-attempt scoring costs and failures are in
`diagnostics/scoring-calls.jsonl`, linked to the question and invocation. Scoring
time is separate from `mean_query_time` and included in total invocation time.

Compare runs only with matching scorer specifications and coverage. Small direct
probes do not establish scorer reliability on every benchmark question; the
reference itself may be incomplete, and using the QA model as judge can introduce
correlated errors. Manual source/artifact review remains necessary.

## Daily-driver scenarios

All three scenarios use the same runner and evaluator:

| Fixture directory | Role |
| --- | --- |
| `daily_driver_v2` | Primary cumulative memory, ownership, correction, and retraction scenario. |
| `daily_driver_paraphrased_v2` | Renamed/rephrased transfer case for generalization. |
| `daily_driver_unrelated_v2` | Transfer case in a home-renovation setting. |

Version 2 requires durable capture before Build Memory; extraction and search begin
at Build. Useful independent context can justify a page from one conversation.
The original v1 fixtures and results remain historical evidence with different
acceptance rules. The paraphrased v2 also repairs a truncated YAML source sentence;
its input comparison with v1 is unmatched.

Set a fixture path and validate it without model calls:

```bash
fixture=benchmarks/suites/daily_driver/fixtures/daily_driver_v2
.venv/bin/python -m benchmarks daily-driver validate "$fixture"
.venv/bin/python -m benchmarks daily-driver run "$fixture" \
  --config-path mycelium.toml --run-id daily-driver-v2-baseline
```

Substitute either other directory to run its scenario. Add `--trials 3` for
independent acceptance trials or `--skip-probe-answers` to skip answer generation
and judging while retaining retrieval checks. New runs require empty/fresh output
directories; they do not resume. Each trial has its own subdirectory.

Claim/entity associations based on wording are **unreviewed diagnostics**. Their
derived coverage and organization values can be wrong, and matching evidence
labels do not prove source support. Reports therefore record
`assessment_status: requires_source_review`; `diagnostic_thresholds_pass` is not
a release decision. Proposition candidates and distinct claim count are reported
separately because one sentence can preserve several facts.

Export complete source-linked candidates and changes across successive snapshots
without model calls or changes to the original run:

```bash
.venv/bin/python -m benchmarks daily-driver review "$fixture" \
  --run-dir benchmark_runs/daily-driver-v2-baseline \
  --output-dir benchmark_runs/daily-driver-v2-source-review
```

The output directory must be new. Each pack includes the full source/wiki state,
exact input hashes, all evidence-linked claim candidates, and additions, removals
and changes since the preceding available checkpoint. Missing checkpoints and
reference evidence that has not appeared yet are explicit. Inspect actual wording,
conditions, ownership, usefulness and successive-build coherence before judging
quality or compute value. The exporter does not make those semantic decisions.

Replay extraction while rerunning downstream memory work:

```bash
.venv/bin/python -m benchmarks daily-driver run "$fixture" \
  --replay-extraction-store benchmark_runs/daily-driver-v2-baseline/store \
  --run-id daily-driver-v2-replay
```

Refresh deterministic comparisons of an existing run without model calls:

```bash
.venv/bin/python -m benchmarks daily-driver compare "$fixture" \
  --output-dir benchmark_runs/daily-driver-v2-baseline
```

For repeated trials, compare a specific trial directory. See the
[primary fixture guide](suites/daily_driver/fixtures/daily_driver_v2/README.md)
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

Each store contains canonical `memory.sqlite3`, generated `wiki/` and `logs/`, and
model diagnostics. Export inspectable JSONL with `python -m mycelium.snapshots STORE EXPORT_DIR`.
Snapshots use SQLite backup and exclude live locks and rebuildable indexes.

LoCoMo writes `summary.json`, predictions, and per-case `stores/`; ordinary
snapshots are under `snapshots/<sample-id>/session_N/`. MAB writes `results.json`
and its summary alongside adapter artifacts. Daily-driver retains a complete `store/` backup and wiki at every checkpoint, plus probe results, `comparison.json`, and `evaluation.json`; repeated
trials also produce `trial_summary.json`.

Inspect useful evidence coverage, attribution and correctness, concise wiki prose,
page organization, preserved uncertainty/history, and retrieval of concrete details.
Check diagnostics for failed/retried calls, stage timings, and output tokens.
Claim membership alone does not establish semantic completeness or correct synthesis.
Compare matched inputs/settings; partial runs and transfer scenarios are diagnostics,
not interchangeable aggregate scores. See [iteration protocol](../AGENT_PROMPTS/BENCHMARK_ITERATION.md).
