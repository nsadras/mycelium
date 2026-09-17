# Model contract experiments

The maintained benchmark CLI is `python -m benchmarks`; see the [benchmark guide](../README.md). These standalone scripts are opt-in experiments, not automatically executed tests.

| Script | Purpose |
| --- | --- |
| `truth_scope_probes.py` | Exercise current owner-independent truth candidate and pair comparison contracts. |
| `fact_group_probes.py` | Exercise current bounded grouping and per-group rendering contracts. |
| `fact_group_pipeline.py` | Check those contracts in successive native builds, including cached reuse. |
| `selection_merge_probes.py` | Use configured production prompts/model settings to compare selections across neutral batches. `--pipeline` constrains only the selector's planning envelope to exercise production budget splitting; actual model context remains configured. |
| `reference_judgment_probes.py` | Probe the optional reference scorer with paraphrases, negation, partial answers, refusal/guess counterexamples and absent references, using the configured host model. |
| `historical/reasoning_comparison.py` | Historical September 9 reasoning investigation. It relies on dated input/output paths and reuses saved results. Retained for interpreting the original experiment, not as a current-contract validation runner. |

Current scripts allocate fresh output directories under `benchmark_runs`; never
substitute earlier results for current validation. `probe_support.py` provides
request recording, JSON writing, and fresh paths. Use the configured host Ollama
access described in `AGENTS.md`.

The retired `contract_simplification_probes.py`, `reasoning_contract_probes.py`,
and `model_contract_comparison.py` tested an obsolete truth/synthesis pipeline.
Their source remains in Git at `3a48d39`; their saved outputs remain historical
evidence. Use an isolated checkout of that revision to inspect or reproduce them.
They are deliberately absent from current-contract runners and do not justify
keeping unused production prompts or schemas. September 10 results are described
in `DEVLOG.md` and `planning/unused_cleanup_2026_09_10.md`.

## Commands

Run from the repository root with the host Ollama server already running:

```bash
.venv/bin/python -m benchmarks.experiments.truth_scope_probes
.venv/bin/python -m benchmarks.experiments.fact_group_probes
.venv/bin/python -m benchmarks.experiments.fact_group_pipeline
```

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

Required source-participant assignments have direct and native routing probes:

```bash
.venv/bin/python -m benchmarks.experiments.participant_subject_probes
.venv/bin/python -m benchmarks.experiments.participant_subject_probes --pipeline \
  --case reporting_only_speaker --case same_speaker_two_sources \
  --case different_people_same_name
```

`--replay-failure PATH` accepts a retained discovery failure request. Completion
means the schema validated and routing finished; inspect `results.json` against
the source to assess assignment, identity and ownership separately.

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

## Source-grounded retrieval controls

`source_grounding_controls` compares claim-only, cited-source and oracle inputs
with controlled tools. `source_selection_probes` tests the production selection
contract with bounded source-backed candidates. `source_grounding_pipeline` uses
real indexing, selection and paired QA in fresh stores with deliberately seeded
claims. All use `mycelium.toml`, retain native requests and report execution
separately from source-reviewed answer quality. They do not measure extraction
quality or retrieval recall in a large corpus.

## Frozen daily-run ranked-claims control

After a terminal daily-driver run with frozen fixture/evaluator inputs:

```bash
.venv/bin/python -m benchmarks.experiments.ranked_claims_baseline \
  benchmark_runs/<production-run> --output benchmark_runs/<ranked-control> \
  --config-path mycelium.toml
```

The control clones each checkpoint and preserves admitted claims, source policy,
canonical reviews and identity metadata. It uses the same hybrid candidate ranker,
candidate/context budgets, source-backed renderer, QA model and judge, with direct
ranked claims instead of generative admission and generated fact prose. It makes
no changes to the production store. Ranked claims fill the token budget without
the production five-fact cap: a generated fact may bundle many claims, so equal
record counts would give the simple arm less evidence by construction. Effective settings, model weights and judge
identity must match. Raw requests, per-call timing, exact input database hashes
and terminal status are recorded.

This is a conditional retrieval/presentation comparison, **not a standalone Mem0
implementation or an independent ingestion benchmark**. Shared extraction and
organization/review work must be accounted separately. Indexes are rebuilt for
frozen snapshots; compare their document/query embedding traces before drawing
latency conclusions. Any source run with incomplete encoding remains diagnostic.

### Calendar-date contract

`python -m benchmarks.experiments.calendar_date_probes --pipeline` runs neutral
clock/date/range/relative/undated inputs against the production extraction
schema, then a native Build and retrieval check. Optional repeated
`--saved STORE SOURCE_ID comma_separated_expected_dates` replays preserved source
failures without changing production prompts. Requests, model digests, timings,
and pipeline snapshots are retained.
