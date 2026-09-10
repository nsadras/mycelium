# Compact Gemma memory contracts — 2026-09-09

Gemma remains the configured model. The changes simplify the model's output and preserve exact evidence IDs, explicit uncertainty, identity review, complete extraction accounting, and complete synthesis membership.

## Contract changes

| Stage | Change |
|---|---|
| Extraction | 13 fields become 9 (plus context citations when supplied). Remove generated confidence, speaker, slot and duplicate evidence-type classification. Require statement-relative entity roles. Restrict predicate to the one consumed distinction, `project_role`, or null. Replace arbitrary facets with `when`, `deadline`, and `inference_basis`. |
| Identity | Replace repeated 11-field branches with 7-field existing/new identities, 8-field unresolved identities and a 4-field explicitly bound user. The application assigns local IDs and copies known types. A nullable existing-identity title preserves evidence-backed renaming. |
| Routing | Each claim returns selected pages, primary owner and a nullable deferral reason. Each destination contains only section and explanation. Empty destinations explicitly defer; review blockers remain binding. |
| Truth | Return one decision for the one incoming statement, with exact older-target comparisons and changed targets. Remove repeated incoming IDs, disposition, generated confidence and restated before/after values. Before/after review text comes from the actual claims. |
| Synthesis | One 5-field object replaces two largely duplicated 7-field variants. A singleton has null text and uses the stored claim verbatim. Multi-claim text must be supplied; every claim is represented exactly once. |
| Retrieval admission | Keep each candidate's include/exclude decision and explanation; remove its unused generated confidence. |

Artifact confidence fields retain existing source/member confidence or the existing extraction default (0.8); these are not newly calibrated probabilities. Meaning is still decided by the model. No name matching, vocabulary rules, semantic fallbacks or automatic truth-review acceptance were added.

## Prompt and schema size

`contract-metrics.json` records small, identical-ID schema fixtures. Counts use the repository's tokenizer estimate, not Gemma's exact tokenizer. These are schema and system-template sizes, excluding evidence.

| Stage | Schema tokens before → after | System template tokens before → after |
|---|---:|---:|
| Extraction | 846 → 946 | 1,591 → 534 |
| Identity | 1,922 → 1,181 | 1,132 → 276 |
| Routing | 501 → 378 | 280 → 152 |
| Truth | 906 → 304 | 357 → 182 |
| Synthesis | 622 → 290 | 410 → 166 |
| Retrieval admission | 266 → 231 | unchanged |

Extraction's schema is slightly larger because its details and roles now have a defined contract. The system prompt is much shorter. All structured calls now show the JSON Schema in the user message with an explicit instruction to return the completed result, including native-format calls. This improves schema grounding but means schema-size reductions alone are not measured input-token or latency reductions. Preflight budgeting counts the same grounded schema once.

## Direct model validation

Requests, responses, timings and failed attempts are preserved under `benchmark_runs/contract-simplification-20260909/`. Host Gemma `gemma4:12b`, 64K context, 32K reasoning output reserve, seed 17 in the evaluation transport, configured Gemma sampling.

- Truth: explicit repainting produces a change; separate bicycles and different people produce no change. Synthesis separates dated events, combines related details, preserves an undecided plan, and leaves a singleton verbatim.
- Identity: distinguishes namesakes by evidence, retains an unresolved identity with both candidate IDs, separates a project from its coordinator, and respects a declared user. Follow-up rename/retain probes establish the nullable title field.
- Routing: a listener does not receive another person's personal statement; a shared activity reaches both pages; an unknown visitor's statement is deferred.
- Retrieval: selects the relevant preference and excludes unrelated records; an unrelated question selects none.
- Extraction: initial shortened versions lost proposal details or confused scheduled times with deadlines. These versions were rejected. The final version retains neutral facts, uncertainty, referenced acceptance and refusal, with cited prior context and null deadlines for a scheduled day. Context-dependent batches use reasoning; independent extraction remains native-format without reasoning. Batching reserves the larger reasoning allowance before making the call.

The natural 48-segment extraction probe still compresses several related statements into fewer claims and misses minor details (including an announced research intention). It preserves the main workload, support-group experience, education/career interests, and painting details. This is a remaining recall limitation, not proof of complete extraction coverage. Exact segment accounting ensures every segment has a disposition; it does not establish that every useful assertion was extracted.

A parser bug discovered during the probes removed required null fields after validation. The client and persisted extraction responses now preserve them, so a valid result remains valid through serialization and retry.

## Integrated validation

The first three-build neutral run finished in 532.7 seconds with nine claims. Artifact review found only eight represented in the wiki: truth review incorrectly proposed replacing the job statement with a compatible tenure detail. Review guardrails preserved the original fact and held the incoming claim; they did not make that decision correct. Both the initial run and its `coverage-audit.json` are retained.

The truth prompt was then clarified, without adding fields: comparisons always covers every target; `targets` contains only actual review changes; supersession requires evidence that a condition or decision ended or was replaced. Direct replays of the actual tenure and preference requests returned no change, while an explicit repainting counterexample still returned supersedes. See `truth-clarity-v7/probes/`. The fresh cumulative rerun completed in 327.8 seconds: nine claims, five facts, nine represented members, no unknown members, no pending truth proposals, and correct bicycle retrieval. Its final wiki preserves tenure, possession details, the painting preference, the undecided plan, and the directions preference. Requests and artifacts are in `cumulative-final/`. This is slower than the earlier 270.7-second baseline in the previous model comparison; no general speed improvement is claimed.

An owned-object detail was temporarily deferred during the second build and admitted on the third. A further one-sentence routing clarification makes explicit ownership sufficient for including object attributes on a person's page. Direct replay of the actual request routes all three claims to You; a listener receives no other person's possession, and an unrelated public object is deferred (`routing-clarity-v8/`). The production-router replay (`routing-in-situ/`) retained all three claims but created an allowed artifact identity for the object and chose that destination. Its initial You-only assertion failed; manual audit records that broader organization outcome. This isolated replay omitted existing profile facts, so it is not equivalent to the cumulative run's context. Separate-object destinations remain a model-dependent organization variation; no deterministic override was added.

The fresh one-session LoCoMo run completed in 273.0 seconds (251.1 seconds for encoding/consolidation). Eleven claims are all represented across eight facts on Caroline's and Melanie's pages. It preserves the support-group event/date/emotions, career/education interests, workload, painting details and motivations, and swimming plan. There was one recovered synthesis validation failure; no generation hit its output limit. This small run is not a long-span quality result or a controlled speed comparison.

QA scored 1/2. The support-group date is correct. The painting answer says “last year” rather than 2022: the claim retains the relative phrase and May 2023 source anchor, but calendar-year normalization remains unresolved and QA chose the relative wording. Minor recall omissions and a low-value generic self-care belief also remain. The benchmark's source/claim evidence-recall metrics should not be confused with the exact 11/11 artifact membership check.

Artifact paths: `benchmark_runs/contract-simplification-20260909-locomo/` (`summary.json`, `predictions.jsonl`, `artifact-audit.json`, and `stores/conv-26/wiki/`). No commit or model switch.


Final validation: 429 tests passed, 87 opt-in integrations skipped; the host-model probes and runs above were executed separately. Ruff and whitespace checks passed. The final routing wording was checked directly and through the router after the cumulative run; the full cumulative run was not repeated again for that one sentence.
