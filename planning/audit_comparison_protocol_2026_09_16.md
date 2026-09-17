# Audit comparison protocol

This records the E1 comparison inputs and current call inventory. Benchmarks are
guideposts; none of these measurements prescribes page titles, page counts or an
exact prose layout. Production baseline before the regrouping: `01ac86d`.

## Inputs and holdout

- Development: `daily_driver_v2`, all nine declared checkpoints and its explicit
  review/retraction actions. The paraphrased and unrelated v2 fixtures, all
  existing probes, and LoCoMo samples 1–9 are development/regression evidence.
- Reserve **LoCoMo sample 10 (`conv-50`)** for V1. Do not inspect its conversation,
  questions, or answers during prompt development. Selection used sample IDs
  only. The saved run manifests, store directory inventory, DEVLOG and planning
  search found no prior run/reference for this case; samples 1–9 all had prior
  stores. This is evidence of non-use in this repository, not a claim about model
  pretraining contamination or uses outside it.
- Before each comparison, freeze the exact source/fixture bytes, code revision
  and any patch, model digests, effective config, rubric/prompt/schema version,
  and ordered review actions. Existing run recording supplies code/environment,
  configuration, model inventory, requests and snapshots. Record fixture and
  evaluator digests in the same manifest. Never overwrite prior output roots.
- Build Memory is required before extraction/search. Keep the configured model,
  temperature/context, retrieval budget, source timestamps and review choices
  the same in matched arms. Report deviations explicitly.
- E2 uses one full development sequence and a simple extraction/retrieval arm.
  This is a mechanism comparison with attribution of losses at extraction,
  organization, retrieval and answering, not a claim that more wiki pages win.
  Stage cost includes failed attempts, retries, cached work and cancellation.
- Review sources and successive snapshots for evidence fidelity, useful recall,
  retained conditions, identity/date correctness, review burden and readability.
  An incomplete run can show a local failure; it cannot establish a full-run win.
- Freeze each accepted proposal before V1. Failures found there are evidence of
  generalization limits; once used to tune a prompt the case is regression data.

### V1 scope declared before inspecting the reserved sequence

On 2026-09-17, select the **first four chronological sessions of sample 10** as
the unused longitudinal encoding/view diagnostic. Use the ordinary recorded
LoCoMo runner, snapshot every session, and run zero dataset QA questions: the
remaining conversation is unencoded and must not supply a misleading full-sample
score. Review source fidelity, identity, time, conditional statements, provenance,
incremental page coverage and per-stage cost after execution. Do not tune on this
sequence or extend it just to obtain a desired outcome. This bounded diagnostic
does not establish full sample-10 accuracy or statistical generalization.

Then run all 32 sessions and 193 questions of sample 3 under the configured model
and current settings, preserving snapshots and failures. It is development/stress
data, not a second holdout. The prior `overnight-sample3-v1` completed 193 questions
but predates honest encoding-status reporting; it retains known encoding failures.
Compare matching settings where verifiable and explicitly report provenance,
prompt/evaluator and completion differences rather than treating its aggregate
score or 39,897s elapsed time as a clean causal baseline.

## Current inference inventory

Limits below are requested output tokens, not measured usage. Splits/retries may
multiply calls. Use actual saved requests for cost; this table describes where
complexity lives, so new work can report its delta without another profiler.

| Stage / label | Output contract | Requested tokens | Invocation/shape |
|---|---|---:|---|
| `claim-extraction-*` | extraction output | 8192 | Per source batch; exact segment accounting, bounded claims, cited time declarations |
| `dream-subject-discovery` | subject discovery | 8192 | Source cohort; bounded subject candidates and participant assignments |
| `dream-subject-review-bindings` | reviewed bindings | 2048 | Only applicable identity reviews; exact reviewed evidence domain |
| `dream-subject-identity` | subject identity | 2048 | Per subject; bounded known identities and one decision |
| `dream-page-admission` | page admission | 4096 | Subject candidates; exact candidate decisions |
| `dream-source-attribution` | claim attribution | 8192 | Bounded asserted content and claim/subject coverage |
| `dream-claim-routing` | routing | 8192 | Bounded evidence cohort, exact IDs and allowed content sections |
| `dream-truth-candidates` | eligible comparison matrix | 4096 | At most 48 search candidates per incoming claim (32 global + 16 entity); small histories exhaustive, each request chunk up to 12 |
| `dream-truth-comparison` | pair comparisons | 4096 | Up to 12 pairs; scope/relation/reason; only human review can apply truth changes |
| `dream-fact-candidate-selection` | prior fact candidates | 2048 | Per incoming/prior chunks when existing facts can be reused |
| `dream-fact-grouping` | bounded fact groups | 4096 | Exact partition; at most 12 members per group |
| `dream-fact-text` | one text string | 1024 | Multi-claim groups only; singletons use canonical text |
| `retrieval-query` | one query string | 512 | Only queries above 1024 tokens |
| `assistant-context-selection` / `assistant-context-merge` | selected IDs/aspects/gaps | 1024 | Candidate admission, optional budget splits and merge |
| `memory-correction` | replacement metadata | 2048 | User correction workflow; dates reviewed before saving |

Page prose, tool-assisted QA and benchmark judges have their own generation
calls. They belong in measured totals, separately labelled from memory encoding.
Native schema nesting is currently largest in extraction temporal alternatives,
attribution/routing and the truth-candidate matrix. C1/C2 clarify existing
decisions; S1 now bounds the truth search domain. Additional calls,
new decision layers or new persisted production records need explicit evidence.

## Decision record template

Record product need, simplest mechanism, call/token/latency/schema/artifact delta,
neutral counterexamples and native workflow evidence, then adopt/reject/limit.
Do not count mocked tests as model evidence. Do not create additional evaluation
layers merely to repair evaluator disagreement; source review remains necessary.
