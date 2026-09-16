# Model contract experiments

The maintained benchmark CLI is `python -m benchmarks`; see the [benchmark guide](../README.md). These standalone scripts are opt-in experiments, not automatically executed tests.

| Script | Purpose |
| --- | --- |
| `contract_simplification_probes.py` | Probe compact production contracts with Gemma. Select extraction or context cases with the existing flags; the default covers truth and synthesis. |
| `model_contract_comparison.py` | Compare Gemma and Qwen on direct contracts and a small cumulative workload. `--natural-only` requires the historical source artifact named in the script. |
| `reasoning_contract_probes.py` | Compare native constraints and schema-prompted reasoning on small cases. Its explicit SDK settings are experimental; they do not configure production. |
| `selection_merge_probes.py` | Use configured production prompts/model settings to compare selections across neutral batches. `--pipeline` constrains only the selector's planning envelope to exercise production budget splitting; actual model context remains configured. |
| `reference_judgment_probes.py` | Probe the optional reference scorer with paraphrases, negation, partial answers, refusal/guess counterexamples and absent references, using the configured host model. |
| `historical/reasoning_comparison.py` | Historical September 9 reasoning investigation. It relies on dated input/output paths and reuses saved results. Retained for interpreting the original experiment, not as a current-contract validation runner. |

The first three scripts now allocate a fresh timestamped output directory under `benchmark_runs` and print its path. Existing results are never silently substituted for a new evaluation. `CONTRACT_PROBE_REVISION` is no longer used. Keep earlier results for comparisons rather than overwriting them.

`probe_support.py` contains the shared request recorder, JSON writer, and fresh output-path helper. The model comparison collects the reasoning probe cases through an explicit callback instead of temporarily replacing a module function.

Validation results for the September 10 cleanup are recorded in `planning/unused_cleanup_2026_09_10.md` and `DEVLOG.md`. Run host-dependent checks with the host Ollama access described in the repository's `AGENTS.md`.

## Commands

Run from the repository root with an already running host Ollama server. These
scripts use explicit experimental models/settings, not the benchmark CLI config.
They are opt-in and may take substantial model time.

```bash
.venv/bin/python -m benchmarks.experiments.contract_simplification_probes
.venv/bin/python -m benchmarks.experiments.contract_simplification_probes --context
.venv/bin/python -m benchmarks.experiments.reasoning_contract_probes
.venv/bin/python -m benchmarks.experiments.model_contract_comparison
```

The contract probe's `--extraction` mode and model comparison's `--natural-only`
mode require the saved source under
`benchmark_runs/reasoning-policy-20260909-locomo/stores/conv-26/artifacts/sources/source-ed6698b588b14e40.json`.
Model comparison requires both `gemma4:12b` and `qwen3.5:9b`; other probes use Gemma.
These are retained investigations, not proof that current production contracts pass.

The historical reasoning runner lives under `historical/`:

```bash
.venv/bin/python -m benchmarks.experiments.historical.reasoning_comparison --help
```

Its modes (`probes`, `diagnose`, `recommended`, `grounded`, `natural`,
`unconstrained`, `builds`) depend on dated paths/settings in that file and can reuse
prior results. Inspect those prerequisites before invoking a mode; it is not a
fresh current-pipeline benchmark. Existing historical artifacts were not migrated.

Current selection merge probes use `mycelium.toml`, retain exact requests and
timings in fresh directories, and perform three trials per neutral case:

```bash
.venv/bin/python -m benchmarks.experiments.selection_merge_probes
.venv/bin/python -m benchmarks.experiments.selection_merge_probes --pipeline
.venv/bin/python -m benchmarks.experiments.reference_judgment_probes
```

These small contract probes do not establish benchmark recall, QA accuracy or
compute improvements on large stores.

## Current source attribution and page review

These probes use the configured host model in `mycelium.toml` and retain fresh
requests, responses, config, model inventory, per-call timings and completion:

```bash
.venv/bin/python -m benchmarks.experiments.attribution_contract_probes
.venv/bin/python -m benchmarks.experiments.agent_user_role_probes
.venv/bin/python -m benchmarks.experiments.page_review_pipeline
```

Attribution is assessed independently from page admission. An unplaced described
subject must retain its reference; a source reporter is not automatically a
subject. Page presentation must cover the eligible described subjects using their
own section domains. The direct contract also scores the primary page choice
separately. The role probe exercises both configured-user and no-user profiles,
including both endpoints of an explicit relationship. The page-review pipeline
checks evidence-scoped exclusions, other supporting evidence and combined-fact
projection across rebuilds. These tests do not establish overall page usefulness,
longitudinal wiki coherence or a whole-benchmark compute improvement.
