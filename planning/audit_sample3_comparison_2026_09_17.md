# Full sample-3 comparison

**Status: preparation; new full run pending.** This is development/stress data,
not an unused holdout. The separate sample-10 frozen attempt preserves the
held-out evidence.

## Prior run

`benchmark_runs/overnight-sample3-v1` retained all 32 session snapshots and
completed 193 questions. Its manifest says complete, but it predates independent
execution/encoding/QA status reporting. Known encoding failures prevent treating
it as complete, clean memory construction.

- Dataset SHA-256:
  `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`.
- Sample 3, `conv-41`; per-batch Build, no memory profile, no replay/frozen store.
- Memory and QA model names: `gemma4:12b`; session context budget 32,768.
  Recorded model calls use a **65,536-token model context window**. These are
  different settings; do not infer a 32,768 model window from the session budget.
- Old manifest has a config hash but lacks current model-digest, effective-config,
  code/evaluator provenance and honest encoding completion fields. Matching model
  names and context limits do not establish equal weights or all settings.
- Reported elapsed: 39,897.412s. Memory-store diagnostic trace: 2,004 attempts,
  440 failed attempts, 36,923.269 model seconds, 37,084,408 input tokens and
  2,302,068 output tokens. These totals include the 193 context-selection calls;
  they are not pure offline encoding. No per-stage total should be conflated
  with overall elapsed or unrecorded QA calls.
- Large traced stages: claim routing 428 attempts / 9,495.0s / 139 failures;
  identity planning 506 / 8,887.9s / 205; truth 123 / 5,950.5s / 0;
  fact synthesis 278 / 4,242.7s / 95; fact candidate selection 412 / 3,170.8s / 0;
  context selection 193 / 2,032.8s / 0. Architecture and stage boundaries changed.
- Lexical mean score: 0.468809. Reported reference-evidence recall: source 1.0,
  claim 0.633869, wiki 0.412487, retrieved context 0.284941. Source coverage does
  not prove extraction correctness or supported answers. The old mean
  `memory_construction_time` (11.557s) actually describes retrieval work and uses
  the earlier measurement contract.

## Current run and interpretation

Pending the frozen held-out run, bounded direct checks and any accepted fixes.
Record the final code/config/model provenance, all session snapshots, stage
latencies including retries, failures, coverage and QA separately. Preserve
incomplete encoding as incomplete even when diagnostic QA is allowed to finish.
Use source review to distinguish evidence loss, identity/temporal mistakes,
retrieval misses and answering failures. Aggregate lexical scores are guideposts;
this comparison is not a single-change ablation or proof of model generalization.
