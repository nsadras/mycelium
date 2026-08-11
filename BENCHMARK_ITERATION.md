# LoCoMo Benchmark Iteration Protocol

## Goal

Use LoCoMo to diagnose and improve a faithful, concise memory system for local LLMs. Optimize for
useful memory across LoCoMo, meetings, and user–agent conversations—not for the scorer itself.

## Run

Hold models and configuration fixed, and use a unique hypothesis-based tag:

```bash
RUN_TAG=<hypothesis> SAMPLE_INDEX=2 scripts/benchmark-locomo-convo2.sh
```

Inspect `summary.json`, `predictions.jsonl`, and `stores/*/{artifacts,wiki}` under the resulting
`benchmark_runs/locomo-mycelium-convo-<index>-<tag>/` directory.

For retrieval and answer-context experiments, set `FROZEN_STORE` to an exact completed case store and
`DREAM_POLICY=none`. This skips ingestion and consolidation so only retrieval and answering can vary.
Use `INCLUDE_RETRIEVAL_CONTEXT=1` only for synthetic or otherwise approved data; it intentionally writes
the rendered memory context into benchmark metadata for qualitative inspection.

For fast hypothesis screening, set `QUESTIONS_PER_CATEGORY` to run the same balanced panel while preserving
source question indices. Graduate promising changes to all questions before retaining them.

## Iteration Loop

1. Record the tag, git state, models/configuration, sample, scores, coverage, failures, and wiki size.
2. Read failed and low-scoring examples; separate real failures from scorer false negatives.
3. Trace representative failures through:

   `source → segments/coverage → claims → wiki → retrieved context → answer`

4. Classify the earliest failing stage: ingestion, extraction/attribution, reconciliation, projection,
   retrieval, answering, or scoring.
5. State one cause, one proposed change, and its expected observable effect.
6. Add a focused test and make the smallest general change that tests the hypothesis.
7. Rerun with otherwise identical settings. Keep the change only if the evidence supports the
   hypothesis; otherwise revert it. Do not stack unverified changes.
8. Log the result and commit validated major changes. After one or two promising changes, rotate to
   other sample indexes.

## Evaluate

Treat scores as symptoms, not objectives. Categories are multi-hop (1), single-hop (2), temporal (3),
commonsense/open-domain (4), and adversarial (5). Compare:

- official and manually corrected scores;
- coverage, failed/partial episodes, attribution, dates, provenance, contradictions, and unsupported
  or duplicate claims;
- wiki completeness, concision, organization, and readability;
- whether correct memory existed but retrieval or answering failed.

Prefer the shortest wiki that preserves useful, answerable information. High coverage alone does not
imply good memory, and score movement is not causal when multiple variables or conversations changed.

For source/claim/wiki information-loss questions, compare `raw`, `claims`, and `hybrid` with
`scripts/benchmark-locomo-ablation.sh`. Run broader or full evaluations only after a change survives
several conversations.

## Guardrails

- Never encode LoCoMo people, answers, wording, categories, or scorer quirks into the system.
- Every prompt rule or heuristic must make sense for real memory; avoid dataset-specific regex.
- Preserve canonical source evidence and make information loss visible.
- Use deterministic code for validation, provenance, accounting, and formatting; use LLMs for
  semantic interpretation.
- Do not mix model/configuration changes with memory-system changes in one comparison.

## Devlog and Git

Append each meaningful experiment to the current-date entry in `DEVLOG.md`: hypothesis, change, run
tag/sample, score and quality deltas, conclusion, and whether it was kept or reverted. Record failed
experiments too when they teach something useful.

After a major change is tested and retained, make one focused commit:

- review the diff and stage only files belonging to that iteration;
- include tests and documentation with the mechanism they validate;
- use a message describing the mechanism, not merely the score;
- do not commit generated benchmark stores/results unless intentionally preserving an artifact.

Small exploratory edits may remain uncommitted until they form one validated change. Do not combine
multiple unverified hypotheses in a single commit.

## Stop and Report

Stop when there is no coherent failure pattern, three hypotheses produce no meaningful quality gain,
or further work requires a product decision. Report the before/after scores, corrected interpretation,
dominant failure stage, hypothesis and change, coverage/wiki impact, cross-conversation results, and
remaining structural risks.
