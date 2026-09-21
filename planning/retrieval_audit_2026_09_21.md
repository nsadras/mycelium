# Retrieval audit — 2026-09-21

## Assessment

**Retrieval has a sound foundation and produces useful answers, but its evidence
handling needs simplification.** The highest-impact work is fixing source-tool
budgeting and separating searchable claims from their wiki presentation. The
configured model made sensible selections and answers in this audit; the two
confirmed correctness defects reproduce without any model call.

This follows the seven areas in [AUDIT.md](../AGENT_PROMPTS/AUDIT.md), scoped to
retrieval and its handoff to answering. Production revision: `9991447`. No
production code, prompts, configuration, or live memory was changed. Existing
user edits were preserved.

Evidence is in `benchmark_runs/retrieval-audit-20260921/`: the predeclared plan,
reproduction script, offline results, copied stores, frozen code/configuration,
native requests, per-call timings, answers, and successive snapshots. The native
allowance was **one run, 12 generation attempts / 360 seconds**, with no tuning,
re-encoding, alternate model, or judge. It completed three questions in six
calls and 49.99 seconds. Focused regressions: **60 passed, one opt-in integration
deselected**, in 5.53 seconds.

### Ranked priorities

| Priority | Severity | Finding | Concrete fix | Bounded validation and stopping criterion |
| --- | --- | --- | --- | --- |
| R1 | High | Source inspection can consume its allowance without adding excerpts, then remove already available excerpts from the model workspace. | Refresh the evidence already shown without opportunistically filling the entire workspace with more sources. Fit excerpts as complete segments inside the final workspace envelope. Track already served segments so source inspection advances and charges for newly admitted evidence. | Replay the saved audio case plus small tests for repeated reads, changed/retracted support, and a nearly full workspace. Valid excerpts must survive an unchanged refresh; a source read must add previously unseen evidence or explain that none can fit. Stay within the existing allowance. Stop after these invariants pass; no additional semantic stage or transcript-coverage target. |
| R2 | High | A matching claim is replaced by all supporting wiki items before admission. Large items can hide a small claim; shared membership defeats record-count limits. | Make the canonical claim, its interpretation state, identities and citations the primary retrieval unit. Add useful related/view context separately and within the same budget; deduplicate by exact IDs. A page edit or grouping change must not prevent the claim itself from fitting. | Check a short claim with/without a large view, one claim supporting multiple items, and a useful adjacent claim reached through a shared item. Preserve exact support and meaningful context; enforce the declared limit on the unit actually returned. Stop when presentation changes cannot hide a fitting claim. Do not prohibit shared view membership. |
| R3 | Medium | Current subject references and aliases do not reach claim indexing; unpresented claims lose explicit subject metadata. | Project existing active claim-to-entity references and canonical names/aliases into search documents and returned claim context. Invalidate affected documents on identity/reference edits. Preserve multiple roles/subjects without inferring ownership from the speaker or page destination. | Use a small person/project example, a rename/alias edit, and two distinct people with the same name. The assigned identity must be present before any view exists, edits must update discovery, and unrelated identities must remain separate. Stop at correct propagation; do not create another identity-resolution call or graph service. |
| R4 | Medium | The mandatory generative selection pass reads much more material than answering and can recursively split into more calls. Its current cost is not justified by a matched comparison. | After R2/R3, compare the existing selector with one compact shared selection input. Serialize claims/context once, retain bounded source support, and remove repeated whole-view expansion. Keep at most one selection pass for the normal bounded candidate set. Consider eliminating it only if a bounded comparison preserves useful answering and uncertainty. | Freeze four varied questions and their candidate evidence, including a source-dependent detail and an unsupported request. Compare baseline and one candidate under identical decoding, capped at 20 generations / five minutes. Accept materially lower input work with coherent grounded answers; record ordinary omissions. Stop after that comparison, including an inconclusive result. Do not add another reranker/model dependency to chase the sample. |

R1–R3 require **zero additional production model calls**. R2 and R4 should share
one implementation effort rather than create competing evidence formats. There
is no P0 finding in the inspected scope; R1 loses transient answer context, not
the durable recording or claims.

## 1. Architecture review

The implemented flow is:

`chat context → optional query rewrite → hybrid claim search → claim/view/source
expansion → model selection → budgeted evidence → answer with optional memory tools`.

SQLite remains authoritative, LanceDB is rebuildable derived state, and retrieval
does not rewrite memory. Unpresented retained claims are searchable. The exact
source IDs, review state, and optimistic snapshot validation are valuable parts
of the design.

Two architectural tensions remain:

- **Claims are independent in storage but dependent on views during retrieval.**
  [retrieval.py](../mycelium/retrieval.py) builds the full rendered evidence for
  each candidate. [retrieval_context.py](../mycelium/retrieval_context.py),
  `_memory_evidence`, replaces a claim with all its valid consolidated facts and
  their support. This matches the older retrieval section of `DESIGN.md`, but
  conflicts with the newer goal that presentation should not determine whether
  source-backed memory is usable.
- **Refreshing and discovering evidence are mixed.**
  [refresh_evidence](../mycelium/retrieval.py) calls `builder.build` with the whole
  workspace budget. It can therefore discover substantially more source text
  while ostensibly refreshing already selected evidence. The subsequent workspace
  fitter treats each source group as indivisible and can discard the whole group.
  This contradicts the documented accumulation behavior.

The app and benchmark answer paths also differ: the app fits chat history and
uses its response prompt; older benchmarks can use terse static answer contracts.
These are different evaluation conditions, not interchangeable accuracy scores.
The direct library `Session` exposes retrieved evidence but delegates answering
and tool use to its caller, which is a reasonable separate contract.

## 2. Core algorithm critique

**Keep the hybrid search foundation.** Vector similarity plus BM25 and reciprocal
rank fusion is an established approach. Searching retained claims rather than
requiring published pages was the right decision: the new audit correctly recalls
the £250 balance from a deferred claim.

### Confirmed presentation dependence

The neutral offline reproduction records:

- A short claim and source fit in **166 estimated tokens**. Adding a large view
  supported by that claim makes retrieval return **zero records** at the same
  1,024-token allowance, with only `more_available=True`.
- A single claim supporting eight view items returns **eight records despite a
  five-record limit**, and reports `more_available=False`. `distinct_hits` checks
  the limit before adding a hit's entire set of views.

These are structural reproductions, not measured frequencies in ordinary use.
The long-view example exercises the renderer's accepted data contract; it does
not claim that a native model produced that exact oversized item.

View expansion also has demonstrated value. In the native balance/keyholder
question, the balance claim ranked tenth; the keyholder claim was **outside the
top 20**, but a sixth-ranked shelving claim led to a shared view containing the
correct keys information. The final answer was supported. Removing all related
context, or replacing admission with the first five raw hits, would lose useful
evidence in this case. R2 preserves bounded exact relationships while making the
matching claim independently available.

### Identity information stops before retrieval

[claim_index.py](../mycelium/claim_index.py), `_claim_records`, indexes claim text,
legacy `about`, optional predicate and temporal facets. It does not use the active
`ClaimEntityReference` records or entity names/aliases; all index owner fields are
empty. Index invalidation watches claims and embedding weights, not identities
or references. `current_hit` also clears owner metadata, and the unpresented-claim
branch does not replace it from current references.

All 23 newly retained workshop claims have empty `about` fields. In the neutral
reproduction, an explicitly assigned person, followed by a canonical rename and
alias addition, leaves the search document byte-identical and the returned
claim's subject unset. A name already written in claim prose still works; the
defect is loss of independently available identity context. Its effect on broad
corpus recall has not been quantified. Fix the handoff before adding identity
inference to retrieval.

### Applicable established methods

| Framework | Relevant method | Application here |
| --- | --- | --- |
| Mem0 | Its documented search can use an optional local cross-encoder, while an LLM reranker is a separate option. Graph relations supplement vector results. | Generative admission is a choice whose value should be measured. Reuse current references as context before considering a new graph backend. [Reranker search](https://docs.mem0.ai/open-source/features/reranker-search), [Graph Memory](https://docs.mem0.ai/open-source/features/graph-memory). |
| Graphiti | Official recipes combine BM25/vector search with RRF; separate recipes add node-distance, graph expansion, or cross-encoder ranking. | Mycelium already uses the basic hybrid method. Borrow bounded expansion through declared relationships where useful; a full Graphiti deployment is not warranted by these findings. [Search recipes](https://github.com/getzep/graphiti/blob/main/graphiti_core/search/search_config_recipes.py). |
| Hindsight | It separates recall from generative reflection, documents recall without a generative LLM, and exposes retrieval breadth, output size and source chunks separately. | Keep finding evidence distinct from synthesizing an answer. Make source access a real bounded operation, with explicit progress. [Recall versus reflect](https://hindsight.vectorize.io/blog/2026/07/24/recall-vs-reflect), [Recall API](https://hindsight.vectorize.io/developer/api/recall). |

These establish useful architectural and call-count reference points, not a
matched speed or accuracy comparison. Embeddings and cross-encoders still cost
compute; graph and optional LLM configurations differ. Mycelium's exact-source
inspection and human-editable views also impose additional requirements.

## 3. LLM calls, prompts and structured outputs

The selection prompt is general and reasonably concise. It asks for complementary
evidence, permits no matches, and distinguishes relevance from merely mentioning
the same person. Its output is flat: selected IDs, supported aspects, and gaps.
IDs are schema-constrained, duplicates rejected, extra fields forbidden, and
selection is capped. This is **not a deeply nested schema problem**.

The problem is the input. Each candidate is a JSON string containing a full
rendered evidence block, including view text, matched canonical text, metadata,
citations and source excerpts. The same related record can appear under several
candidate aliases. One short list of claims becomes tens of thousands of input
tokens before selection.

Across the new three-question run:

- Selection: **3 calls, 68,029 input / 347 output tokens, 33.99 server seconds**.
- Answering: **3 calls, 4,758 input / 199 output tokens, 7.79 server seconds**.
- Selection consumes **93.5% of generation-input tokens and 81.4% of model server
  time**. The first selection includes 8.52 seconds of model loading; excluding
  reported loading from both stages, selection still accounts for about 76.6%.

An offline inspection of the same candidate IDs estimates 309–480 tokens of claim
text versus 14,563–18,308 tokens of expanded candidate evidence per question.
These are the repository estimator's counts, not the native model-token counts
above. Extra context is not all waste, as the keys example demonstrates.

The normal native path used one selection and one answer per question. Longer
queries add a query-rewrite call. Oversized candidate collections recurse into
selections plus a final merge in
[context_selection.py](../mycelium/context_selection.py); the final merge can
still reject the request for exceeding budget. Existing tests prove this path,
but it was not triggered in the new native run. Compacting the evidence is the
first intervention, rather than making the split tree more elaborate.

There were **no retries, invalid structured outputs, failed requests, or
cancellations** in this run. Current structured decisions do not retry completed
invalid model output. Transport retries and one reselection after a concurrent
canonical edit serve different purposes and should remain separately observable.
Selection failures reach the app as typed HTTP 503 responses, not successful empty
searches. Follow-up `memory_search` already works without another admission call.

Supported-aspect/gap prose is retained in the trace rather than passed into the
answer workspace. That is useful diagnostically, but does not justify growing
this contract. No prompt repair campaign is indicated by these results.

## 4. Code quality and test coverage

The retrieval modules have recognizable responsibilities, typed evidence objects,
strict tool arguments, and meaningful tests for concurrent edits, source
retractions, invalid citations, model-weight changes and evidence merging. The
focused suite passed unchanged.

The missing tests are important boundary contracts:

- A source-tool result near the actual workspace limit must preserve previously
  admitted valid excerpts.
- Repeated reads of a broad citation must make progress or terminate explicitly.
- Shared view membership must not invalidate the configured result limit.
- A view edit must not make an otherwise fitting canonical claim disappear.
- Current entity references and reviewed aliases must reach search independently
  of page publication.

Several owner fields and `_search_document`'s owner-title argument now describe
an older ownership model; current production indexing fills none of them. Rework
or remove those placeholders as part of R3, rather than layering another owner
abstraction onto them.

I found no fixture vocabulary or lexical semantic repair in the inspected
retrieval prompts. The overengineering concern is the recursively expanding
evidence/selection machinery and its interactions with multiple budget layers,
not an overly specific prompt. Tests that only assert each layer's independent
size bound do not establish useful accumulated evidence.

## 5. Data and correctness risks

### Reproduced source-workspace loss

On a copy of the saved Hari recording store, select its most broadly cited claim
by citation count and retrieve with a 6,000-token allowance:

1. Initial evidence contains one view, three supporting claims and **87 transcript
   segments**, occupying 5,978 estimated tokens.
2. `memory_sources` for that already visible claim returns essentially the same
   prefix and charges **5,978 of the 6,000 additional tokens**.
3. Workspace refresh independently expands source text to **185 segments**.
   Its evidence fits the inner evidence allowance but exceeds the final workspace
   envelope. Whole-source fitting discards the entire group.
4. The model-visible workspace now contains **zero source segments**. A second
   read fails for exhausted allowance; only 22 tokens remain. The raw first tool
   result is still inspectable, but the model receives the fitted workspace.

Files: `offline-results.json`, `audio-initial.json`, `audio-tool-1.json`,
`audio-tool-2.json`, and `source-budget-details.json` in the audit evidence root.
The direct production methods reproduce this without a model or canonical edit.

**Limit:** a separate offline check using five claims and the app's 26,768-token
initial allowance preserved the source group: 390 segments became 478. Thus the
deletion is a budget-boundary defect, not a claim that every recording or default
chat loses its sources. That check still spent 5,980 tool tokens on a source
result largely overlapping existing evidence. There is no cursor or exclusion of
already served segments to make repeated source reads deliberate progress.

Other correctness protections are solid: optimistic admission snapshots detect
intervening changes; superseded interpretation and pending reviews are explicit;
failed tools refresh current evidence; exact citation errors fail visibly. The
source/group budget problem does not require weakening these protections.

No durable data loss was observed. All 19 canonical export collections were
byte-identical before and after the new native retrieval run. Its inherited four
repeated-item wiki warnings remain; the store was not represented as wholly
integrity-clean.

## 6. Scalability and solo-developer maintainability

The immediate measured cost is generative input processing, not vector search.
Warm query embedding took 33–45 ms in the new run. Offline preparation of each
20-candidate evidence list took roughly 0.10–0.13 seconds at 166 claims. These
small-store measurements do not establish large-store performance.

Growth risks worth recording, without opening another implementation tranche:

- `build_incomplete` scans sources, episodes and claims during each candidate
  build. Identity-review enumeration also repeats inside record rendering.
  Reuse exact request-local data if profiling shows this matters.
- The index lock includes synchronization, embeddings and search; the first
  query after model/index changes pays rebuild cost. Document embeddings are
  bounded into batches and unchanged vectors are reused, which is good.
- Below 10,000 rows vector search is exhaustive; above that, IVF_FLAT probes all
  100 partitions. An earlier 10k/200-query experiment reported exact recall and
  faster vector lookup, but did not establish full retrieval/QA scaling. Do not
  trade recall for approximate search just because an ANN index exists.
- Source packing repeatedly renders trial groups as it admits segments. Long
  recordings and shared-item expansion increase both payload and preparation
  work even at a modest claim count.

R1/R2 reduce several interacting paths at once. Prefer that simplification over
new services, caches with complex invalidation, an automatic query planner, or
additional semantic verification. Profile after these fixes; stop there unless
ordinary-use latency remains materially problematic.

## 7. Benchmark and source review

### Latest retrieval check

Store: the final deterministic handoff replay from the September 21 encoding
fixes, preserving the recorded native retention/presentation decisions. It has
**166 active claims and 32 pages**, built from the prior 143-claim seed plus three
successive workshop conversations. No encoding occurred in this audit. Snapshot
exports before and after every answer remain unchanged.

Settings: `gemma4:12b`, digest `4eb23ef187e2…`; `embeddinggemma:latest`, digest
`85462619ee72…`; temperature 1, top-p .95, top-k 64, reasoning disabled; 65,536
model context, 32,768 app input allowance, 26,768 initial allowance after reserving
6,000 for memory tools; candidate/initial/tool limits 20/5/6 and three searches.
The check uses production chat prompts and the memory-tool loop with empty chat
history. Web tools are omitted. It is not a browser or multi-turn app test.

| Question | Retrieval wall seconds | Selection input tokens / call seconds | Answer input tokens / call seconds | Source-grounded result |
| --- | ---: | ---: | ---: | --- |
| Remaining fund, spending, keys | 24.43 | 22,676 / 17.64 | 2,104 / 3.09 | Correct £250 balance, all four spending amounts, Amal/shop-owner keys. |
| Opening history | 9.85 | 25,069 / 9.69 | 2,041 / 2.16 | Correct June 22 → June 29 plan and actual June 29 opening. Repeats retained “land inspection” typo instead of source “landing inspection.” |
| Unsupported laptop purchase | 6.85 | 20,284 / 6.67 | 613 / 2.54 | Selects no memory and appropriately says the information is unavailable. |

All six generation requests finished on their first attempts; usage totals are
complete. Total **72,787 input / 546 output tokens, 41.77 model server seconds**.
Ten successful embedding requests took **6.50 client seconds**, including seven
batches rebuilding vectors for all 166 copied claims and three query embeddings.
The first selection's 8.52-second model load is included, not misreported as
generation throughput. No memory tools were called by the model: these examples
validate initial recall/answering, not autonomous recovery from missing context.

### Successive artifacts against source conversations

I checked all three workshop sources and the project, opening and shelving views
across Builds 1–3, then followed the new questions from sources through claims,
candidate ranks, admission, final evidence and answers.

- Build 1 retains only a project overview. Missing responsibilities/equipment
  details at this point are encoding omissions, not failed search.
- Build 2 retains the conditional revised opening. Build 3 adds the completed
  event, spending and keyholder update. The opening page combines plans and
  outcomes in one somewhat repetitive item; answering still distinguishes them.
- The spending record is absent from views but present as a deferred claim, and
  retrieval correctly uses it. Keyholder information is present in the shelving
  item and Theo's shared view, not in the main project overview. The earlier
  encoding report's broad wording about omitted keyholder details should not be
  read as absence from every page.
- The source says June's insurance quote was extended conditionally, whereas a
  retained statement calls it accepted. The presentation faithfully preserves
  that imperfect claim. This is an upstream retention issue; it is not evidence
  that retrieval should add a fact-checking model stage.
- The source's “landing inspection” becomes “land inspection” in retention and
  is repeated by the new answer despite correct wording in supplied excerpts.
  This is a small upstream error carried through QA, not failed candidate recall.
- Initial ranking misses the direct keyholder claim; bounded view expansion
  recovers it. Initial ranking finds the balance at tenth; admission selects it.
  These successes matter more than enforcing a prescribed page organization.

### Relevant prior results and comparison limits

The September 18 product run and its recorded continuation are the relevant
earlier same-project production artifacts. The original ended incomplete after
a correction transaction-order error; the continuation completed the remaining
work. Together: **14 generations / 334.27 seconds**, including encoding, injected
publication failure/recovery, correction and two answers. This total must not be
compared with the new retrieval-only total.

Its pending-view answer took two calls / 8.43 seconds and correctly recovered the
new date and inspection responsibility from retained claims. Its final constraints
answer took two calls / 29.74 seconds; selection alone read **50,273 tokens** in
19.39 seconds. The answer omitted an available insurance deadline and repeated
an upstream overstatement about pocket-mending. Neither answer used memory tools.
Source snapshots and request bodies confirm these observations.

The new run uses the same model digests and decoding, but adds a third source,
uses different retained statements/views, asks different questions and uses the
app response style. Therefore **no isolated retrieval speedup or accuracy
improvement is established**. Both runs show useful recall and substantial
selection overhead. The latest encoding fixes improve presentation fidelity and
reduce generated output in their own frozen comparison; they do not yet establish
lower retrieval cost.

Earlier September 17 controls held initial evidence fixed across static,
tool-enabled and app-style answers. Some unnecessary abstentions disappeared
with the app prompt, without any tool calls, while a wrong interview date
persisted despite contrary source evidence. That is evidence to distinguish
answer-contract problems from retrieval failures, not a reason to import their
raw benchmark score as product accuracy. Earlier seeded source-backed controls
also favored providing source excerpts; R4 must not assume claim-only evidence
is equivalent. See [the follow-through report](audit_followthrough_observations_2026_09_17.md)
and [the prior implementation evidence](audit_implementation_2026_09_15.md).

The GPU-contended encoding audit remains incomplete and supplies no latency
baseline. The broader older LoCoMo/daily runs have different pipelines, encoding
failures and reference-quality limits; their aggregate scores cannot establish
the current retriever's quality. This audit is also not a broad recall-rate,
multi-turn, concurrency-load or large-store evaluation.

## Recommended next step and stopping point

Fix R1 first, then implement R2/R3 together as a compact, source-backed retrieval
handoff. Run the single bounded R4 comparison after those mechanics are correct.
Keep current hybrid search, exact citations, human edits and consistency checks.
Success means useful grounded answers with predictable local work and functioning
source inspection. Perfect recall, ideal pages, universal tool use and a clean
benchmark score are not prerequisites for moving on to ordinary use.
