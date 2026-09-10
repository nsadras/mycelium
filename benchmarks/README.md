# Model contract experiments

The normal benchmark CLI lives in `mycelium_bench`. These standalone scripts are opt-in experiments, not automatically executed tests.

| Script | Purpose |
| --- | --- |
| `contract_simplification_probes.py` | Probe compact production contracts with Gemma. Select extraction, identity, rename, or context cases with the existing flags; the default covers truth and synthesis. |
| `model_contract_comparison.py` | Compare Gemma and Qwen on direct contracts and a small cumulative workload. `--natural-only` requires the historical source artifact named in the script. |
| `reasoning_contract_probes.py` | Compare native constraints and schema-prompted reasoning on small cases. Its explicit SDK settings are experimental; they do not configure production. |
| `reasoning_comparison.py` | Historical September 9 reasoning investigation. It relies on dated input/output paths and reuses saved results. Retained for interpreting the original experiment, not as a current-contract validation runner. |

The first three scripts now allocate a fresh timestamped output directory under `benchmark_runs` and print its path. Existing results are never silently substituted for a new evaluation. `CONTRACT_PROBE_REVISION` is no longer used. Keep earlier results for comparisons rather than overwriting them.

`probe_support.py` contains the shared request recorder, JSON writer, and fresh output-path helper. The model comparison collects the reasoning probe cases through an explicit callback instead of temporarily replacing a module function.

Validation results for the September 10 cleanup are recorded in `planning/unused_cleanup_2026_09_10.md` and `DEVLOG.md`. Run host-dependent checks with the host Ollama access described in the repository's `AGENTS.md`.
