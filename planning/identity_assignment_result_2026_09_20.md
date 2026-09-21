# Identity assignment: implementation and bounded evaluation

Date: 2026-09-20. Baseline: `016ba80`.
Plan: [identity_assignment_plan_2026_09_20.md](identity_assignment_plan_2026_09_20.md).
Evidence: `benchmark_runs/identity-assignment-20260920/review.json` and adjacent
frozen inputs, contracts, requests/responses, diagnostic logs and snapshots.

## Decision

Keep identity assignment within retention. Adopt candidate A v2: source-scoped
participants, distinguishing evidence for candidate identities, and a flat
`participant_ids` field on subject declarations. Existing identities can be cited
without redeclaring them. A separate batched resolver (B) did not recover people
omitted during extraction or demonstrate enough benefit to justify another call.

The concrete gains are persistent bindings and explicit corrections, with no
additional generation stage. The experiment does **not** establish a general
accuracy improvement. A v2's direct outputs were valid in five of seven cases;
the baseline was also valid in five of seven, with different failures. Useful
facts were omitted by both. These counts describe a small sample, not accuracy rates.

## Implemented behavior

- Preserve diarization speaker keys separately from reviewed display names.
  Participant IDs are scoped to their source; equal names alone never merge people.
- Supply participant bindings and up to two cited facts per identity candidate.
  Reuse source context and retrieved evidence. An unbound named participant gets
  a targeted embedding query, not a separate identity generation call.
- Persist binding, identity decision, citations and claims together. Later batches
  reuse exact bindings even without a repeated subject declaration. User review
  and explicit entity merges update them; stale model work cannot overwrite a
  concurrent correction.
- Allow correction of accepted model assignments from the memory inspector. Select
  an existing identity or create a distinct one, then edit affected identity wording.
  Selecting an existing person preserves their canonical name and aliases.
- Preserve original evidence and review history. Identity wording edits supersede
  the old statement, retain its date anchors and unrelated identity references, and
  save the exact reviewed replacement without an LLM identity decision. This is an
  identity-only edit; other factual/date corrections retain their existing workflow.
- Refresh affected views. If presentation fails, the correction stays saved and
  Build retries the pending view update without re-extraction. Search returns the
  new statement and labels the previous interpretation as superseded history.
- Show model-selected versus user-reviewed status instead of a constant confidence
  percentage. A no-page selection affects the reviewed evidence only.

## Native evidence and cost

Configured host `gemma4:12b`, digest
`4eb23ef187e2c5462566d6a1d3bbbc2f1346d0b4327cbb66d58fffbcc9b2b05c`;
temperature 1, top-p .95, top-k 64, context 65,536, reasoning off, output cap 8,192.
Direct probes use one attempt. Integrated Builds retain the existing retry policy.

| Work | Generation requests | Input / output tokens | Model server time | Completion |
|---|---:|---:|---:|---|
| Direct contract discovery | 24 | 56,385 / 6,704 | 117.14 s | Fixed budget completed; six invalid responses preserved |
| Baseline integration | 18 | 43,963 / 5,904 | 91.28 s | Canceled during presentation; preceding Builds partial |
| Production candidate excerpt | 2 | 7,705 / 1,192 | 23.12 s | Complete; both first attempts valid |
| Total | 44 | 108,053 / 13,800 | 231.54 s | Budget closed |

Client generation time totals 233.93 seconds. One request was intentionally canceled;
its unfinished response has no token/server-time totals. No transport outage occurred.

The integration harness should have enforced its planned seven-request control
allocation independently. Instead, subsequent Builds retried unfinished older
sources, consuming 18 requests, including eight automatic retry attempts and 12
validation failures. Stop the control and use the final two requests for a fresh
candidate Build. **This is not a completed matched comparison.** Candidate native
multi-batch, follow-on and correction runs were not performed within the cap.

Discovery included four neutral development cases, two held-out cases and the
familiar recording excerpt. A v2 correctly separated the account owner from a quoted
speaker and left an unidentified third party unspecified in the two held-out cases.
It preserved a known person's binding across a topic change. It also omitted useful
reported work, failed a context-only citation check, and attached the recording's
participant to a topic in one direct run; validation rejected that binding. The
separate resolver was structurally valid in its three cases but still omitted Hari
from the recording and invented a colleague relationship in the partial conversation.
One general contract adjustment was used; there was no subsequent tuning loop.

The final production Build used the frozen first 100 recording segments. Retention:
15.55 seconds, 6,086 input / 666 output tokens. Presentation: 7.57 seconds,
1,619 input / 526 output tokens. Retention included 5.79 seconds of model loading.
It retained seven statements, selected Hari's person identity and durable participant
binding, and rendered four sections on his page. A repeated Build made zero calls.
The seeded You page links to Hari; it does not own his work.

No embedding requests occurred in that fresh candidate store before or during Build;
the index is populated on demand. The partial baseline series made nine embedding
requests for 14 items: 1,992 tokens and 3.18 client seconds. Different stores and
workloads prevent an embedding-cost comparison. Targeted participant queries add
embedding work when prior memory exists; their steady-state cost is unmeasured.

## Source review and limits

Hari's page is readable and mostly coherent. It preserves the important qualification
that refresh automation is a goal and is not yet fully automatic. It retains teaching
approach, portal work, certification context and costs. There is **no project entity
or separate project page**: that omission begins in retention. Some wording is too
broad, especially “all content” beyond the demonstrated project and “AI tool operational
costs” from an unclear cost/scope passage. The personal requirement to maintain three
AWS certifications becomes a more generic industry observation. These are recorded
quality limits, not reasons to add more calls or rules now.

The previous context-handoff run used two calls, 6,499 input / 1,323 output tokens
and 26.49 server seconds on this excerpt, but omitted Hari's identity. The current
sample differs in seed IDs, contract, warm-up and stochastic output. It is useful
regression evidence, not proof of a speed or identity-accuracy gain. Retrieval/QA
was not evaluated by these generation runs.

Full 884-segment recording behavior, long-source candidate growth, native successive
Build quality and correction latency remain unmeasured. Candidate evidence and
source context are bounded locally, and the whole request is checked against its
context allowance; this does not establish long-recording reliability. Structural
tests establish persistence and retry behavior independently of model quality.

## Validation and next step

- Python: **588 passed**, four integration tests deselected, 23.90 seconds.
- UI: **27 passed**; ESLint and TypeScript/Vite build passed. Existing bundle-size
  warning remains.
- Ruff on changed Python files and whitespace checks passed.
- Focused checks cover source isolation, restart, exact binding reuse, stale writes,
  accepted corrections, unchanged canonical names, temporal anchors, search history,
  and recovery after a failed page refresh.

Native prompts/schema were unchanged after the final Build; later changes repaired
exact decision reuse and correction persistence/UI behavior. Browser/device checks
remain user-owned. The live store was not rebuilt and no app service was operated.

Return to ordinary product use. Use the correction workflow for concrete mistakes;
reopen identity work for recurring harmful behavior. Any future comparison should
enforce a separate per-variant request cap and select only the intended sources.
Do not reopen this experiment merely to obtain the missing project page or a perfect
coverage score.
