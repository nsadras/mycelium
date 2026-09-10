# Audit remediation and validation — 2026-09-09

## Implemented and checked

- [x] Preserve pending review relationships and matched canonical assertions in retrieval; limit distinct facts rather than raw member hits.
- [x] Budget complete LLM requests, including output reserves, structured schemas, tools, retries, and subsequent tool rounds. Split placement/admission/extraction at complete record boundaries. Reject oversized current chat requests explicitly.
- [x] Let the model select synthesis groups; copy singleton text in application code using an explicit singleton schema branch.
- [x] Replace whole-table search-index rebuilds with incremental merge/delete, reuse vectors for metadata-only changes, and embed bounded batches. Detect external file edits through metadata revisions.
- [x] Cache bounded decoded artifacts with independent copies; index exact-ID/state lookups and filter unfinished commits. Filesystem metadata scans remain.
- [x] Replace the placement claim-by-page output matrix with sparse, evidence-backed destinations, after proving relationship endpoint coverage.
- [x] Preserve persisted extraction boundaries for resume; supply bounded contiguous prior source segments as context-only evidence.
- [x] Fit coherent chat turns; render the initial current request once; bound the thread supplied to retrieval. Model-formulate a compact query when input exceeds the embedding budget, retaining the original request for admission.
- [x] Reuse original ASR text for diarization; construct transcribers off the event loop and serialize meeting processing. Live speech quality was not tested because optional speech dependencies are absent.
- [x] Persist atomic per-question LoCoMo checkpoints and a compatible-settings/completion manifest.
- [x] Remove session GET-time metadata rewrites while preserving create/update writes.
- [x] Record individual chat rounds, embedding calls, and meeting summaries. Aggregate chat metadata no longer describes only the last round.
- [x] Run configured-model contract probes, native index tests, a three-build cumulative replay, two fresh bounded LoCoMo samples, and manual artifact inspection.

## Validation evidence

Configured models: `gemma4:12b`, `embeddinggemma:latest`; configured host accessed with escalation. No server started or stopped.

| Check | Result |
| --- | --- |
| Backend suite | 417 passed, 87 opt-in skipped |
| Ruff / whitespace | Passed |
| Sparse placement | Five direct cases passed after correcting missing endpoint coverage in the first candidate |
| Singleton synthesis | Explicit union and one-member-only contracts passed; nullable-only candidate failed and was withheld |
| Adjacent extraction context | New assertion retained proposition, time, and context citation |
| Query formulation | Reference resolution and topic-switch cases passed; larger grammar was rejected, compact schema proved before integration |
| Native long-query retrieval | Compact residence/move query retrieved pending-review evidence |
| Native review-aware answer | Did not treat the pending Lisbon move as accepted |
| Meeting summary | Preserved room decision, Mira's Friday action, and unresolved projector availability |
| Three-build public replay | 152.89s; 28 model attempts, zero failed attempts; retention and retrieval semantic checks passed |
| Fresh LoCoMo sample 9 | Two sessions: 146.7s and 166.2s; three QA answers completed |
| Fresh LoCoMo sample 1 | One session: 134.5s; one QA answer completed |

Artifacts:
- `benchmark_runs/audit-fixes-20260909/`: contracts, cumulative replay, native review, and final native checks.
- `benchmark_runs/audit-fixes-20260909-locomo-small/`: sample 9, two sequential builds, three questions, completed manifest/checkpoints.
- `benchmark_runs/audit-fixes-20260909-locomo-second/`: sample 1, one build/one question, completed manifest/checkpoint.
- Prior comparison replay: `benchmark_runs/consolidation-efficiency-20260909/paired-replay/`.

The previous integrated three-build replay took 174.80s with 31 attempts; this replay took 152.89s with 28. This is encouraging, but single runs with evolving prompts do not isolate timing variance or establish session-25 behavior. The short LoCoMo prefix cannot validate late-history scaling.

## Artifact quality

**Coverage:** Sample 9 accounts for all 114 segments and represents all 24 extracted active claims in 14 facts. No pending extraction, unresolved provenance, repeated fact membership, or review-held claims. This verifies bookkeeping and claim retention, not complete source-level coverage. Sam's never having visited Jasper was marked source-only; the earlier overnight prefix retained it. That prefix had 27 claims versus 24 here, but is not a paired extraction experiment. The improvements do not establish higher extraction recall.

**Correctness:** Inspected statements preserve the old-car repair/sale decision, family trips, painting background, and dated medical check-up. Native pending-review evidence remains unresolved. Sample 1 preserves Caroline's support-group experience and career intentions and Melanie's painting/childcare/swimming statements under the correct person. Its support-group date answer is May 7, 2023, matching the dated source. Source image captions sometimes differ from speaker descriptions; the lake-sunrise statement follows Melanie's explicit words.

**Concision:** Sample 9 made six synthesis calls without retry; singleton echo failures disappeared in this run. Some hobby-update prose remains vague or repetitive, including multiple statements about keeping Evan informed. Canonical membership coverage alone does not prove good synthesis.

**Organization:** Person ownership is sensible in the inspected pages. Some casual updates still land in Shared Projects, and temporary enthusiasm appears in Profile. These are remaining semantic placement/granularity issues, not fixed by the sparse schema alone.

**QA:** Sample 9 answers Prius, old Prius, and Rockies/Jasper. The full-dataset broken-car answer includes a later event outside the ingested prefix. The scoring function gives the correct but verbose destination answer low overlap credit. Neither the prefix scores nor one correct sample-1 answer establish corpus-wide QA quality.

## Larger unresolved audit items

These remain explicit follow-ups; this remediation must not be described as eliminating every whole-codebase inefficiency:

1. Identity grounding still sends a broad registry and uses selected historical grounding. Deferred/rerouted cohorts and broad prior-fact selection can grow with history. A bounded semantic dependency/coverage contract needs separate native proof; no lexical shortlist or arbitrary semantic cutoff was substituted.
2. Truth and synthesis can still receive a large selected canonical group. The final request guard prevents silent context overflow, but does not supply a lossless multi-call truth/synthesis protocol. Retry feedback and generic web-tool results also remain subject to the guard rather than a new compression protocol.
3. Staging and commit still regenerate page projections separately; changes must preserve recovery and the final placement/review state.
4. Session storage still rewrites its JSON file on mutation. Session/history and artifact-inspector pagination, browser virtualization, and a storage migration are not implemented here.
5. Speech text preservation has structural coverage, not a live speaker-accuracy comparison. Meeting-summary collection limits and coordination with other GPU users need separate evaluation.
6. Token estimates use cl100k plus headroom. They are not exact Gemma token counts. Native traces make deviations inspectable; model-specific calibration remains open.

Semantic decisions remain model-owned. Exact IDs, declared states, request/record boundaries, and canonical singleton rendering are structural invariants. Failed model probes and validation corrections are recorded in `DEVLOG.md`.
