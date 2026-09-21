# Retrieval fixes: adopted safeguards and rejected candidate

## Outcome

**Ship the source-budget fixes and existing identity-context propagation. Keep the
shared-selection and identity-index experiments out of production.** They passed
structural tests but failed the bounded quality/cost gate. This tranche does not
close every issue in the [retrieval audit](retrieval_audit_2026_09_21.md).

| Priority | Status | Result |
|---|---|---|
| R1: source budgeting | Adopted | Refresh only inspected excerpts/citation links, advance explicit reads through unseen segments, charge new evidence, and fit complete segments. |
| R2: independent claims and bounded related views | Open; candidate rejected | Candidate preserved small claims and bounded actual records in tests. Its shared selection still lost useful available context in native answering. |
| R3: identity context | Partly adopted | Direct claim evidence, the inspector, page links and revisions now carry existing active names, aliases and roles. The index projection remains unchanged. |
| R4: selection cost | Open; candidate rejected | Shared input did not reduce aggregate input and produced a worse answer. Do not replace the existing selector with this candidate. |

The source fix was committed as `1a65c0f`. The unadopted, mechanically repaired
shared candidate is preserved on local branch
`experiment/retrieval-shared-20260921`, commit `89d412b`. Its earlier identity-index
variant is saved with the initial native candidate's complete source manifest.
Neither experimental variant is merged into the production path.

## What changed in the release

- Refresh updates source text/status and removes invalid citation links while
  preserving the associations already inspected. It does not discover additional
  excerpts or silently expand citation links across other displayed segments.
- `memory_sources` requests unseen segments and charges the increase in the
  accumulated evidence. A repeated request either advances or explicitly reports
  that no further excerpt is available or fits. Previously shown evidence remains.
- Final fitting can retain part of a source as whole transcript segments, with
  corresponding citations, instead of discarding its entire excerpt group.
- Direct claim evidence projects existing active claim-to-entity references into
  names, aliases, entity IDs and roles. It preserves distinct people with the same
  name and does not turn a contextual participant into the subject or owner.
  A person does not need a wiki page for these bindings to reach the answer.
- Entity-reference and identity-review revisions now invalidate evidence. Reference
  edits made during selection cause the established bounded reselection, and
  reference-only changes refresh an existing workspace. The inspector displays
  these bindings; navigation includes only real materialized pages.

These are deterministic data and budgeting changes. They add no generation call,
identity-resolution decision, semantic retry, taxonomy or model-output field.
The new evidence fields copy information already held in canonical artifacts.

## Release validation

The final release was assembled and validated independently of the rejected
experiment, in `/tmp/mycelium-retrieval-release-20260921`, before promotion.

- **632 Python tests passed**, one skipped, four native integration tests deselected.
- **Nine focused UI tests passed**; TypeScript and frontend production build passed.
  The existing bundle-size warning remains.
- Ruff and whitespace checks passed.
- Tests cover retraction, changed source text/support, partial source fitting,
  repeated reads, cumulative budgets, distinct identity roles/namesakes,
  reference-only revision changes and concurrent edits with and without a view.
- A zero-generation replay used a copied version of the actual recording store.
  All valid previously shown excerpts survived both source reads:

| Initial evidence allowance | Initial segments | Segments after first read | Segments lost across both reads | Additional allowance left |
|---|---:|---:|---:|---:|
| 6,000 tokens | 87 | 185 | 0 | 39 tokens |
| 26,768 tokens | 390 | 484 | 0 | 1,173 tokens |

The second read added nothing, charged nothing, and returned an explicit reason.
The final rendered workspaces stayed within their budgets. Replay artifacts:
`benchmark_runs/retrieval-fixes-20260921/release/`.

The final release's identity propagation is validated mechanically; the native
experiment below evaluated broader candidate paths. It is not a native quality
comparison of this narrower final release. Browser/device checks were not run,
services were not started, and the live store was not modified.

## Bounded native comparison

### Method and completion

Frozen evidence: the encoding audit's final three-Build workshop snapshot,
166 claims and 32 pages. No re-encoding or wiki edits. The four questions covered
spending/keyholders, opening-date history, an unsupported laptop purchase, and a
visitor-outreach detail present only in the cited conversation.

The four baseline/candidate pairs used **identical ordered initial search hits**.
Each used the app chat prompt, its memory tools, no web tools or judge, and the
configured model/decoding: `gemma4:12b`, digest starting `4eb23ef187e2`, reasoning
off, temperature 1, top-p .95, top-k 64, 65,536-token context. Embeddings used
`embeddinggemma:latest`, digest starting `85462619ee72`. Initial allowance was
26,768 tokens, with 6,000 additional evidence tokens, at most three searches and
six records per tool search. Configuration and full model digests are saved.

The experiment completed:

- Four paired questions: 16 generation attempts.
- One ordinary, unpinned candidate retrieval check: two attempts.
- One mechanical handoff repair diagnostic: the remaining two attempts.
- **20 total generation attempts, all completed first attempt**, with no transport
  failures, semantic retries, deadline cancellations or unfinished model records.
- **154.25 seconds of native execution across two invocations**: 127.14 seconds for
  the original comparison/check, then 27.10 seconds for the repair diagnostic.
  This is aggregate execution time, not one continuous five-minute wall interval;
  offline diagnosis and code changes occurred between them.
- None of these native answers called a memory tool. Therefore they do not validate
  autonomous tool exploration. Source-tool behavior was exercised separately by
  the release replay and regression tests.
- Canonical exports before/after every answer were unchanged. No native snapshot
  represents a successive encoding build; all use the same frozen evidence.

The repair was a structural correction, not a prompt sweep: selected records went
unchanged into answering, canonical assertion rendering was deduplicated, and the
unsuccessful index change was removed. Its ordinary retrieval produced the same
ordered hits as the first baseline question. It was tested on that one question
only; it is not a second four-question comparison.

### Quality against source conversations

| Question | Baseline | Initial shared candidate | Repair diagnostic |
|---|---|---|---|
| Fund, expenses, keys | £420 original, £250 remaining, all four expenses; Amal/shop-owner keys | Correct money/expenses; says keys unspecified | Correct money/expenses; still says keys unspecified |
| Opening history | June 22 → June 29, inspection condition, actual June 29 opening | Same useful chronology | Not repeated |
| Unsupported purchase | Appropriate unknown | Appropriate unknown, plus unnecessary project context | Not repeated |
| Source-only outreach | Three visitors heard through the library board | Same supported detail | Not repeated |

The source July 2 conversation explicitly identifies both keyholders. The shared
selection's recorded support report claimed to cover keys but selected different
records. In the initial variant, shared view evidence was visible to selection
without being an independently selectable result. The repair made those views
selectable, but the model still chose unrelated records despite adequate source
information. Both an interface problem and a remaining selection mistake are
visible; this is not evidence that the recording was unusable or that another
encoding/identity call is needed.

In the separate ordinary retrieval check, adding identities/aliases to indexed
documents pushed the funding claim outside the top 20. The answer then omitted
both money and keys. Alias FTS lookup, rename, reassignment, deletion and embedding
reuse tests had passed; they did not establish that the changed ranking was better.
Hold that projection rather than compensate with question-specific routing.

### Computation and per-call evidence

Selection input tokens and model-reported seconds:

| Question | Baseline tokens / seconds | Initial candidate tokens / seconds |
|---|---:|---:|
| Money and keys | 22,676 / 16.35 | 24,134 / 8.92 |
| Opening history | 25,069 / 8.86 | 22,423 / 8.25 |
| Unsupported purchase | 20,284 / 6.00 | 24,140 / 7.43 |
| Source-only outreach | 24,017 / 7.57 | 22,965 / 7.18 |
| **Selection input total** | **92,046** | **93,662 (+1.8%)** |

All-generation input for the four pairs was 98,886 versus 103,564 tokens. Model
server time was 48.61 versus 39.50 seconds, but baseline included 8.41 seconds of
model loading versus .02 seconds for the candidate. Excluding reported load gives
about 40.20 versus 39.48 seconds: **no convincing speed benefit**, especially with
the worse money/key answer and no repetitions to estimate variation.

The repair's single selection consumed 23,677 input tokens, versus 22,676 for the
matched baseline question (+4.4%). Its two calls consumed 28,135 input tokens and
18.86 server seconds, including 7.68 seconds loading. It also fails the cost gate.
Deduplicating assertions let the shared builder admit more source material under
the same large allowance; a shared representation alone was not a compact input.

Embeddings were recorded separately: candidate-list preparation used 11 requests
(166 documents in seven batches plus four queries), 6.14 client seconds. The
initial ordinary candidate check used eight requests/2.63 seconds; the repair
used eight/5.74 seconds. Cold table construction is included in these checks, so
these are not steady-state per-query embedding latencies.

All request inputs, responses, per-call load/prompt/generation timings, snapshots,
configurations and source hashes are under
`benchmark_runs/retrieval-fixes-20260921/native/`. The compact timing export is
`call-summary.json`; `completion.json` covers the original 18 calls and
`repair-completion.json` records the final total of 20.

### Setup and validation limits

A worktree setup hit an approval-review timeout; isolated filesystem copies with
local Git metadata were used instead. Missing metadata initially caused benchmark
provenance tests to fail. One test invocation without required host access stalled
and was cancelled. A repair harness startup resolved the virtualenv interpreter
symlink incorrectly and failed imports **before any model request**; its corrected
launch is included in the 20-attempt total. These are environment/harness failures,
not model retries. Saved failed replays also caught a real citation-refresh growth
bug, which the release fixes and covers with a regression test.

The sample is small, stochastic and drawn from one frozen memory store. Matched
initial candidates isolate admission/answering from index recall; the two ordinary
checks have different code and do not constitute an index-quality benchmark.
Older encoding/QA runs used different settings or revisions and add no clean
causal quality/cost comparison here. No aggregate accuracy score is claimed.

## Remaining work, in priority order

1. **R2 and R4 together: make the selectable unit and useful evidence agree.**
   Keep a fitting canonical claim available independently of wiki grouping. Link
   related view/source support directly to selectable IDs, preserve the chosen
   evidence in answering, and bound actual records. The experiment branch contains
   useful structural tests, not an adopted semantic design. Next validation should
   include a large/shared view, an unrelated same-person record, source-only support
   and one multi-part question. Require useful grounded answers and materially less
   selection work; do not add a verifier, repair loop, or another generation stage.
2. **Finish R3 discovery without assuming longer identity-enriched embedding text
   improves ranking.** Test a separate identity/alias search field or another small
   projection change while preserving the canonical claim's semantic content.
   Check name/alias discovery, edits/deletions, an unpresented claim and an ordinary
   non-identity query. Stop after a small comparison; keep the current index if the
   tradeoff remains unfavorable.

Do not fix the inherited retention omissions, temporal wording, wiki repetition,
or every QA miss in this tranche. They are distinct issues and did not prevent the
baseline from answering these bounded questions usefully. The present comparison
has reached its stopping point; there is no additional tuning run queued.
