# Model contract experiments

The maintained benchmark CLI is `python -m benchmarks`; see the [benchmark guide](../README.md). These standalone scripts are opt-in experiments, not automatically executed tests.

| Script | Purpose |
| --- | --- |
| `contract_simplification_probes.py` | Probe compact production contracts with Gemma. Select extraction, identity, rename, or context cases with the existing flags; the default covers truth and synthesis. |
| `model_contract_comparison.py` | Compare Gemma and Qwen on direct contracts and a small cumulative workload. `--natural-only` requires the historical source artifact named in the script. |
| `reasoning_contract_probes.py` | Compare native constraints and schema-prompted reasoning on small cases. Its explicit SDK settings are experimental; they do not configure production. |
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
.venv/bin/python -m benchmarks.experiments.contract_simplification_probes --identity
.venv/bin/python -m benchmarks.experiments.contract_simplification_probes --rename
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
