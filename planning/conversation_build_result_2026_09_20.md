# Whole-conversation Build: results and error attribution

Baseline: `53a8ac5`. Completed 2026-09-20. Evidence:
`benchmark_runs/conversation-build-20260920/`, especially `review.json`, each
case's `completion.json`, exact `requests/`, and integration `snapshot.json`.

## What changed

- Build groups pending chat captures from the same session. A recording or grouped
  conversation uses one retention request when the compacted prompt, schema and
  output reserve fit. Capture IDs, timestamps and original citations remain separate.
- Completed turns provide interpretation context without being extracted again.
  Their participant roster and established bindings accompany their text. Oversized
  input splits at complete segment boundaries; omitted optional context is recorded.
- Retention accepts independent valid records. Invalid references, bindings and
  dependent records are rejected visibly, without inferring a replacement meaning.
  Duplicate local IDs reject all conflicting declarations. Persistence remains atomic.
- Invalid completed responses no longer trigger automatic regeneration. Only
  transient transport failures retain bounded retries. Presentation remains atomic:
  an invalid replacement leaves existing pages intact and valid claims pending
  for a later explicit Build.
- Reports distinguish input capacity, output capacity, transport/service errors,
  model-output contract violations, pipeline failures and cancellation. These are
  observed failure locations, not an automatic verdict on semantic correctness.
- Exact retention/presentation requests and completed responses are saved locally.
  Episode batch details expose request budgets and rejected records in the inspector;
  Build details expose warnings. Successful JSON parsing is explicitly distinguished
  from schema validation in call metadata.
- One short prompt clarification makes an existing invariant explicit: participant
  IDs identify speakers and may bind only to person/You subjects. The flat schema
  and two-stage pipeline are unchanged.
- Clear Memory now clears participant bindings and identity-review history along
  with their referenced artifacts. This fixes a leftover-state bug from the preceding
  identity implementation; the live store was not cleared or rebuilt.

## What caused the observed errors?

| Observation | Attribution and action |
| --- | --- |
| Twelve earlier identity-control validation failures for references to undeclared existing identities | The IDs were already supplied. This was an overly restrictive validator, fixed in baseline `53a8ac5`, not twelve independent identity mistakes. Eight automatic extra generations made that problem more expensive. |
| The 884-segment recording previously planned seven retention batches | The batcher measured large canonical ID envelopes against a quarter-window allowance before compaction. The new complete-request estimate permits one call. |
| Older context turns could refer to participants absent from the roster | A pipeline handoff gap. All supplied conversation turns now carry corresponding roster entries and known bindings; focused tests check this. |
| First full-recording output bound Hari's participant ID to a project | The input included Hari's name and all 884 segments. The output violated a valid person-only invariant, but the prompt left that type constraint implicit. Reject only the binding; explicitly state the existing rule after a neutral direct probe. One final recording run had no invalid bindings, but omitted the person identity entirely. This does not prove the identity problem solved. |
| Follow-on chat returned two records citing only older turns | The distinction between new and context-only evidence was present and explicit. These are model contract violations under the intended no-re-extraction rule, not necessarily factually false statements. Both were rejected; the valid new update persisted on the first attempt. |
| First full-recording retention described automated content updates as established functionality | Source index 29 says the process is not fully automatic and index 30 calls it an eventual goal. Both reached the model. This is a retention meaning error with relevant context present; presentation repeated it. It was not caused by retrieval or dropping a batch. |
| Architecture claims named technologies missing from their cited segments | Wider source inspection finds Next.js at index 244 and DynamoDB at 392. The technology names were not invented: the narrower problem is incomplete citation support. Inspect the full submitted context before attributing hallucination. |
| Final recording produced overlapping project identities and repetitive IaC statements on linked pages | Retention split overlapping subjects; presentation added near-duplicate view items from the same evidence. Both pass structural validation. These are organization/selection limitations, not storage corruption. |

The recording is one-sided and contains transcription noise. Complete delivery
of its text cannot recover the absent side of the conversation. For uncertain
meanings, preserve that limit instead of claiming the model had every relevant fact.

## Bounded native results

Configured host model: `gemma4:12b`, digest
`4eb23ef187e2c5462566d6a1d3bbbc2f1346d0b4327cbb66d58fffbcc9b2b05c`.
Temperature 1.0, top-p .95, top-k 64, 65,536 context, 8,192 output tokens,
reasoning off. Config/model inventories and per-call load, prompt and generation
timings are saved. No LLM judge was used.

| Case | Calls | Retention / presentation client seconds | Outcome |
| --- | ---: | --- | --- |
| Combined-conversation direct probe | 1 | 10.12 / — | Valid shape; omitted later qualifications and project identity. |
| Unresolved-reference direct probe | 1 | 5.05 / — | Valid shape; retained uncertainty, but wording blurred reported and personal work. |
| Full recording, original prompt | 2 | 36.70 / 8.27 | Ten memories, one project page plus You's map. One invalid binding rejected; no regeneration. |
| Two pending chat captures | 2 | 5.72 / 1.78 | One retained statement and Petra page. Correct design/reviewer distinction; omitted the later condition, explicit repair refusal and hobby. |
| Follow-on Build on that chat store | 2 | 6.61 / 3.92 | One new statement, previous identity and claim preserved. New prototype status, pending corrections and repair boundary appear across project/person/You pages. Two context-only records rejected. Some view duplication and lost original ownership wording remain. |
| Speaker-type clarification, direct counterexample | 1 | 2.50 / — | Correctly binds Rowan while retaining Sora's separate kayak work and Rowan's bicycle work. Does not force the described project onto the speaker. |
| Frozen full recording, clarified prompt | 2 | 28.97 / 8.93 | Seven memories, six subject pages plus You's map; no rejected records. Useful roadmap distinction, but missing Hari, overlapping subjects and repetitive views remain. |

All four production Builds completed; all subsequent no-op Builds made zero calls.
All eleven generation requests completed on attempt one, with no transport failures
or automatic regeneration. Total: **97,799 input / 5,041 output tokens, 118.54 server
seconds, 118.58 client generation seconds**. The follow-on Build also made five
embedding requests (five items, 113 tokens, 4.02 client seconds); its trace lives in
the shared chat store. Final code avoids repeated identical participant-name queries.

The final full-recording request contained all **884 segments in order**, with
matching canonical text and complete participant references. It estimated 39,705
input tokens against a 55,296 allowance; Ollama reported 40,884 input tokens. No
optional context was omitted. Retention plus presentation took 38.32 seconds
including local Build work.

### Comparison limits

- Seven old retention batches versus one actual new batch is a verified planning
  change, not a measured sevenfold latency or quality improvement. Old batch sizes:
  141, 143, 138, 143, 144, 143, 32.
- The two full-recording cases use the same frozen source and model settings, but
  are single stochastic samples. The first retention call loaded the model for
  8.06 seconds; the final one was warm. Their time difference mostly reflects loading.
  The short contract clarification removed the observed invalid binding in this
  sample, but does not establish a general quality gain.
- Earlier 100-segment runs used a different workload. Their call totals and artifact
  quality are not a controlled comparison with the full recording.
- The combined-chat and follow-on cases preceded the final speaker-type wording.
  Grouping, roster handoff and partial admission used the production implementation;
  the final prompt received its separate direct and full-recording checks.
- These checks evaluate encoding and organization. They do not establish retrieval/QA
  accuracy, performance at a large store size, or a general identity-error rate.

## How to investigate a future failure

1. Inspect Build warnings/failures and the episode's extraction batches. Valid
   records may already be saved even when individual records were rejected.
2. Find the matching batch/call in `diagnostics/llm-calls.jsonl`. Capacity failures
   before inference and transport failures should not be counted as semantic decisions.
3. Inspect `diagnostics/decisions/` or `diagnostics/failures/` for the exact prompt,
   schema, response, options and reversible request IDs. Check the batch's omitted
   context list. Diagnostics contain source text and grow with usage.
4. First verify input delivery and the stated contract. Then compare the selected
   statement to its citations and wider supplied context. Follow the first wrong
   representation: source input, retained memory, or presentation.

Do not add an extra judging call, a repair cascade or keyword-based correction to
make this evaluation perfect. Record ordinary omissions. The remaining owner/person
selection and page duplication problems should be judged through normal use, with
bounded experiments only if they recur enough to make the artifacts misleading.

## Validation and stop

- 594 Python tests passed; four native integration tests deselected. Focused checks
  cover necessary splitting with no lost/repeated source segments, grouped captures,
  restart/no-op behavior, source-specific bindings, complete context rosters,
  concurrent retraction, partial admission, transport-only retries and diagnostics.
- 27 UI tests passed, plus Ruff, ESLint, TypeScript/Vite and whitespace checks.
  The existing large-bundle warning remains. Device/browser checks remain with the user.
- Stop after **11 of 12 permitted generation requests** and less than two minutes
  of generation-request time. No further prompt tuning in this tranche.
