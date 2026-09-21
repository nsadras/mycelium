# Encoding audit — 2026-09-21

Audited commit: `cb24112`. Criteria: [AGENT_PROMPTS/AUDIT.md](../AGENT_PROMPTS/AUDIT.md).
Scope: capture, retention, identity assignment, prior context used during Build,
view organization, publication, recovery, encoding cost and source-backed quality.
Retrieval ranking, agent answers and device acceptance are outside this audit.

## Assessment

**Keep the two-pass architecture. Encoding is useful and substantially simpler,
but its incremental organization still needs a few focused fixes and validation.**
The remaining work should be a small, bounded tranche, followed by a decision to
move on. More identity stages, a required project-owner ontology, exhaustive fact
coverage and automatic semantic repair are not justified by this evidence.

The strongest improvement is mechanical: the recent passage representation cuts
the recording's native retention input by 70.7%, preserves the original evidence,
and keeps the usual one-retention/one-presentation path. The strongest remaining
problem is also mechanical: prior context supplied for interpretation becomes
permission to rewrite a large portion of the wiki. Presentation then introduces
another opportunity to strengthen or change already retained statements.

This audit additionally reproduced an identity-admission defect and a stale
checkpoint overwrite. Neither requires another model call to address.

You confirmed that another program was using the GPU during the new replay.
Its slow wall time is therefore confounded by resource contention, not evidence
of a pipeline performance regression. Runtime diagnosis is not a remaining task.

### Evidence and limits

- Code, current prompts/contracts, configuration and persistence paths inspected.
- **141 focused Python regressions passed in 14.20 seconds**, covering capture,
  whole-conversation Build, passages, identity context, views, lifecycle,
  citations and the model adapter. These largely mocked tests establish mechanics,
  not semantic quality. The previous full suite result was 608 passed; that full
  suite was not rerun here.
- Latest completed passage experiment: twelve saved native requests, their exact
  inputs/outputs, source recording, retained evidence, wiki and completion records.
- Earlier product experiment: source conversations, successive snapshots and
  failure/recovery results. Its pipeline predates the current identity and passage
  changes, so it supplies recurrence evidence, not a matched current quality score.
- New current-code encoding-only replay:
  [encoding-audit-20260921](../benchmark_runs/encoding-audit-20260921/plan.json).
  Frozen three-conversation sequence, read-only copy of the same 143-claim seed,
  six-generation/600-second maximum, no prompt variants, judge, QA or retry run.
  **Stopped incomplete during the first presentation at the time limit.**
- [Offline reproductions](../benchmark_runs/encoding-audit-20260921/offline-checks.json)
  establish scope amplification, binding admission, a schema/storage mismatch,
  candidate truncation and a simulated competing-commit race. Their temporary
  stores do not touch live memory.
- No production changes or service operations. The native replay is closed;
  sources two and three and the no-op check were not reached. There is no current
  three-Build success claim.

## 1. Architecture review

### What matches the intended design

The actual path is coherent:

`durable capture → retain cited statements + identities → organize cited items → render wiki`

Capture uses no semantic call. Retention and presentation have separate durable
outputs, and one retained statement can support multiple view items. Source text
is preserved independently of what the model selects. SQLite transactions,
optimistic read validation and the publication outbox protect canonical state and
allow projection recovery without repeating extraction.

Whole conversations are considered together when the complete request fits.
Adjacent speech fragments are compacted by exact attribution/adjacency boundaries,
with reversible citation expansion. No linguistic heuristics decide identity or
ownership. This is an appropriate foundation for a solo-maintained local product.

### Where the boundaries leak

**Interpretation context becomes a write set.**
[ViewOrganizer.input](../mycelium/views.py:17) unions incoming and retrieved prior
claims, selects every item touching that union, adds all its supporting claims,
and expands the affected subjects. [persist](../mycelium/views.py:76) deletes all
supplied unprotected items before inserting the model's replacement.

In the new replay, nine new statements produced a presentation request containing
**94 statements: nine new and 85 old; 31 existing items; 20 affected subjects**.
All 31 items were supported entirely by seed evidence. They include prior people,
school funding and other subjects independent of the new workshop conversation.
The older product run actually rewrote 20 seed-only items in its first presentation.
This is unnecessary semantic work with a visible opportunity for page churn.

**The view stage cannot repair an identity omitted from its allowed choices.**
Retention declared Amal, Theo and Ruth in the new replay, but none was offered as
a presentation subject. Their memories reference the project/artifacts/topics,
and their participant bindings were discarded by the admission defect below.
The presentation receives speaker labels in provenance, but its owner/link enums
exclude these people. More emphatic presentation instructions cannot overcome
that contract. Supplying a relevant identity as an optional choice must remain
distinct from asserting that the speaker owns everything discussed.

## 2. Core encoding algorithm

### Sound choices

- Select useful, contextual statements rather than sentence-level exhaustive facts.
- Preserve original evidence and exact references separately from generated pages.
- Use prior memory as bounded context; ask the same retention pass for identities
  and proposed changes instead of running an identity cascade.
- Keep supersession/contradiction proposals reviewable; keep incomplete views
  distinguishable from missing extraction.
- Accept omissions and some ambiguity. Person-plus-project organization is useful,
  but a fixed required page count is not a sound invariant.

### Material limitations

1. **A second paraphrase can change meaning.** In the recording, retained memory
   correctly calls the centralized course-generation chat a *vision*. The view
   lists it among current features. In the prior successive run, a requirement to
   confirm an insurance quote by June 24 becomes a quote already confirmed by that
   date. These are presentation errors with sufficient retained context.
2. **Retention also makes substantive interpretation mistakes.** The recording's
   senior-versus-junior hiring distinction is reversed in a retained statement.
   The new audit calls outright-donated bicycle tools borrowed. Both source inputs
   contain the relevant distinction. These are not evidence of lost source text.
3. **Selection varies substantially.** On the long synthetic passage comparison,
   one project overview replaces thirteen baseline statements and loses much
   useful technical detail; the reserved mixed example improves. This supports
   input-efficiency adoption, not a general claim of improved semantic quality.
4. **Prior candidate selection favors the beginning of a conversation.**
   [related_claim_ids](../mycelium/retention.py:52) searches every 1,200-token chunk,
   concatenates the results, then keeps the first 48 distinct IDs. In a deterministic
   three-chunk reproduction, selection is 24/24/0 despite searching all three.
   The last chunk's prior identity or change target can never reach the model in
   this case. This concerns encoding's context selection, not answer retrieval.

### Comparison with established frameworks

These are current source/documentation comparisons, not matched model/hardware
benchmarks. Call counts depend on version, settings and input.

| Framework | Relevant method / compute | Implication for Mycelium |
| --- | --- | --- |
| Mem0 | The inspected current OSS `main` vector-memory path gathers recent messages and a small prior-memory set, then performs one extraction call and batches embedding/storage. Its IDs are compacted for the request. | Mycelium's one retention call is already in the same broad range. A second call has to earn its cost by producing useful human-readable organization. Keep prior context bounded; do not assume older descriptions of Mem0's two-call update flow describe every current version. [Source](https://github.com/mem0ai/mem0/blob/main/mem0/memory/main.py) |
| Graphiti | `add_episode` separates node extraction/resolution, edge work and attribute/summary extraction, with optional community updates. Cost depends on the extracted graph and resolution needs. | Borrow contextual entity candidates, episode provenance and explicit change handling. Copying the entire graph-building cascade would expand the call budget without demonstrated benefit here. [Source](https://github.com/getzep/graphiti/blob/main/graphiti_core/graphiti.py) |
| Hindsight | Retention preserves contextual facts and distinguishes speakers; observations are consolidated separately. Its performance guidance describes batching and additional consolidation work, and warns that cloud defaults can overload local runtimes. | Preserve evidence versus synthesis, process changed evidence incrementally, and measure all work. Its published provider latencies are not an appropriate local-PC target. Its documented fuzzy-name resolution conflicts with this repository's semantic guardrails and should not be imported. [Retention](https://hindsight.vectorize.io/developer/retain), [observations](https://hindsight.vectorize.io/developer/observations), [performance](https://hindsight.vectorize.io/developer/performance) |

There is no finding here that justifies migrating frameworks. The differentiator
is an inspectable human-and-agent memory view; the underlying extraction does not
need a novel many-stage inference architecture.

## 3. LLM calls, prompts and structured output

**The semantic stage count and flat outputs are reasonable.** The retention prompt
already discusses roles, conditions, uncertainty, relative dates, speaker names,
identity reuse and source grounding. Presentation already asks to preserve context
and uncertainty. The observed mistakes are not all caused by absent instructions.
Adding further example-specific rules would risk recreating the previous complexity.

| Stage | Information supplied | Important boundary |
| --- | --- | --- |
| Retention | New conversation, participant roster/bindings, source timing/roles, optional original context, up to 48 prior memories, existing identity candidates with short supporting evidence | New evidence stays whole when it fits; optional context is trimmed under pressure. Prior candidates can still be biased or irrelevant. |
| Presentation | Retained text, subject references, speaker/time provenance, existing items and pending changes | No original conversation; only supplied subjects can own/link a view. It should not infer new source facts from a compressed summary. |

Exact ID enums and post-generation structural validation are helpful. They do not
prove that a statement follows from a citation. Passage citations are also broader:
the recording candidate's 27 passage references expand to 651 original references
across claims, with overlap. This is not a coverage score.

Completed malformed outputs are not regenerated automatically. Bounded transport
attempts remain. Partial retention admission keeps independent valid records and
reports rejections. Two gaps undermine that otherwise sensible design:

- [Binding admission](../mycelium/memory_admission.py:48) counts all participant
  assignments before excluding assignments to non-person subjects. The new native
  response binds each speaker to both a project and the correct person. All six
  bindings are rejected as conflicts. Offline removal of only the structurally
  illegal project bindings leaves three valid person bindings with no conflict.
  Valid person-to-person ambiguity must still be rejected, not guessed away.
- The [generation/admission contract](../mycelium/memory_contract.py:73) permits
  a newly allocated ID with type `you`; [EntityRecord](../mycelium/artifact_models.py:189)
  requires the singleton ID `you`. An offline response passes admission but fails
  persistence, rolling back the whole batch. This is a reproducible contract
  mismatch, not a native error observed in the replay.

## 4. Code quality and test coverage

The central orchestration is now compact and understandable. Diagnostics save
native requests, outputs, request-ID maps and passage memberships. Cancellation,
retraction and publication failures have meaningful tests; this audit's focused
suite passes.

The missing tests are at boundaries: invalid versus valid binding admission,
schema versus storage invariants, interpretation context versus writable items,
and failure checkpoints after an optimistic conflict. Green mocked tests did not
detect those gaps.

There is still residue from the retired architecture. The 648-line
[ontology](../mycelium/ontology.py) includes fixed section mappings and routing
helpers that the new Build does not call; its comment still refers to removed
`page_admission.py`. `IdentityWorkUnit`, scope cohorts, encounters and historical
decision fields remain in models/repositories and curation/integrity paths.
Some have live consumers, so they must not all be labeled dead or deleted blindly.
Remove unreachable producers/helpers first and simplify their consumers only
where an actual feature no longer uses them. This is cleanup, not a release gate.

No fixture vocabulary or lexical identity repair was found in the current
retention/presentation decision path. Most overfitting risk now lies in extending
investigations around individual misses rather than in the two production prompts.

## 5. Data and correctness risks

### Protections that worked

The cancelled native presentation preserves all seed source, claim, entity, view
and wiki records unchanged at the exported-record level. Nine new statements
remain committed and the source stays visibly pending presentation. No source
or accepted-claim loss was observed in this run.

The seed has four repeated-item integrity findings inherited from an older
pipeline. The same four findings remain after the failed Build; all other integrity
issue lists are empty. Calling this a newly corrupted or fully healthy store would
both misrepresent the evidence.

### Reproduced stale-checkpoint risk

The [mutation lock](../mycelium/lifecycle_transaction.py:14) is per process. A
second process can commit a completed extraction during another process's model
call. Read validation correctly rejects the stale result, but
[the exception handler and finalization](../mycelium/retention.py:306) save the
old in-memory episode again.

A deterministic simulated competing commit leaves the winning claim in storage
while replacing its episode's completed checkpoint with `failed` and an empty
claim list. That breaks manifest consistency and can cause repeated extraction.
This is an emulated interleaving, not an actual two-process load test or evidence
that ordinary single-process UI use hits it. Fix checkpoint ownership/revision
handling rather than adding a distributed task system.

Semantic correctness remains a separate issue: valid IDs and preserved evidence
do not prevent a page from making an unsupported commitment. Human correction
and source inspection remain important, but should not excuse systematic new
distortions during presentation.

## 6. Scalability and solo-dev maintainability

The first priority is reducing the work a Build owns. A two-call pipeline can
still be expensive if one call repeatedly regenerates unrelated memory.

Other growth risks are present but are not demonstrated current user bottlenecks:

- Build/capture and materialization load broad source/episode/claim collections;
  materialization also expands connected page sets. See
  [dream.py](../mycelium/dream.py:33) and
  [materialization.py](../mycelium/materialization.py:105).
- [fit_retention](../mycelium/memory_budget.py:32) recompacts and measures the
  whole request after removing each optional row. Large over-budget context can
  make preparation disproportionately expensive. Prefer bulk or binary-search
  fitting if measured, preserving whole evidence and exact budget checks.
- Page-support expansion can make a single presentation unit exceed the budget;
  splitting incoming claims cannot always solve a large connected existing item.
  This fails visibly, but remains a scaling boundary.
- Retained passages broaden citations. Range rendering fixed display explosion,
  while stored evidence membership remains larger. Do not mistake broad citation
  counts for more precise extraction.

Avoid a generic graph engine, a taxonomy redesign or a background verifier to
solve these. Exact dirty-item selection, fewer rewrites and simpler existing
structures are the lower-maintenance direction.

## 7. Benchmark and source-artifact review

### Latest completed representation comparison

[Passage results](evidence_passages_result_2026_09_21.md), baseline `108ba53`;
same model digest, sampling, prompts and source in the paired recording runs.

| Recording metric | Previous representation | Passages |
| --- | ---: | ---: |
| Original fragments / model passages | 884 / 884 | 884 / 36 |
| Native retention input tokens | 40,882 | 11,983 |
| Retention request seconds | 35.49 | 13.15 |
| Presentation request seconds | 13.03 | 7.08 |
| Generation calls | 2 | 2 |
| Retained statements | 8 | 8 |
| No-op generation calls | 0 | 0 |

All twelve experiment calls completed on attempt one, without transport errors,
truncation or rejected rows. Total generation request time: 159.49 seconds.
The recording candidate binds Hari correctly and gives him a compact readable
page, but does not declare a separate project identity. The baseline binds Hari
to canonical You and spreads technical information across eight subject pages.
The candidate improves that particular attribution/organization outcome, not all
quality dimensions. Neither artifact is perfectly faithful.

Full source input is preserved. The stage-level examples are independently
checked against recording indices 573–586 (future centralized chat) and 859–863
(senior/junior hiring). Practice-exam generation is already happening in indices
116–123; it should not be falsely grouped with future-only features.

Output lengths and selected content differ, so the entire elapsed improvement
cannot be attributed solely to representation. The direct input saving is much
stronger evidence than the differing semantic outputs.

### New audit replay: incomplete under confirmed GPU contention

Configuration: `gemma4:12b`, digest
`4eb23ef187e2c5462566d6a1d3bbbc2f1346d0b4327cbb66d58fffbcc9b2b05c`,
temperature 1, top-p .95, top-k 64, context 65,536, output reserve 8,192,
reasoning off; `embeddinggemma:latest`. Model inventory and exact code/configuration
are frozen in the run directory.

| Request | Native input / output | Client seconds | Outcome |
| --- | --- | ---: | --- |
| First retention | 11,182 / 1,413 | 273.16 | Complete; nine memories, ten subjects; six rejected bindings; no regeneration |
| First presentation | No final API usage; server log reports 16,096 prompt tokens and about 1,961 generated tokens before cancellation | 314.89 | Cancelled by the fixed experiment deadline; no accepted view output |

Total generation client time is **588.05 seconds**. Embedding work is separate:
**11 requests / 10.44 seconds**, including rebuilding the seed's index. The complete
run, including snapshots/cleanup, took 601.22 seconds. Two generation attempts were
made, both first attempts; the experiment was not extended to consume its unused
four-call allowance.

The generic recorder labels the cancelled request as a `transport_failure`, and
the Build adapter labels the resulting `TimeoutError` as `pipeline`. The recorded
exception and service log establish a **benchmark deadline cancellation**. This is
not evidence of a spontaneous network fault, malformed presentation or output-token
exhaustion. API token/server totals in `completion.json` omit the unfinished call;
they must not be presented as the full computation spent.

Retention alone used 23.20 seconds loading, 13.55 seconds processing the prompt and
236.02 seconds generating 1,413 tokens: **5.98 output tokens/second**. The earlier
recording candidate generated at 75.88 tokens/second. Service logs show all 49/49
model layers on the GPU during this audit. You subsequently confirmed that another
program was using the GPU. Treat this as a contention-affected run and do not infer
a code regression or pursue runtime diagnosis. The 94-statement/31-item rewrite
scope is independently verified and remains an avoidable-work finding.

Source review of the nine accepted statements finds a useful project outline,
budget, access restrictions, inspection dependency and volunteer context. It also
finds donated tools described as borrowed, a possible pocket-repair activity made
firm, missing person references and omitted delivery/availability details. These
are recorded observations, not a proposed fact-count score or another prompt loop.

### Successive-build evidence

The [older product run](compact_product_result_2026_09_18.md) completed two source
Builds plus injected-failure recovery. It demonstrates useful continuity, retained
conditions, preserved evidence and reuse of unfinished work, alongside namesake
confusion, repeated protected text and qualification loss. The two source Builds
used two generation calls each; view recovery used one more. Its 334.27-second /
14-request total also includes correction and answers, so it is not encoding-only
cost.

The current replay did not reach source two. Therefore current identity continuity,
page coherence across all three sources and a completed seeded-store cost remain
unvalidated. The old 60-call control also failed to finish its first Build and
cannot establish equivalent-quality speedup. Further full-suite benchmark running
would not resolve these causal limitations by itself.

## Ranked priorities, fixes and stopping criteria

Severity here means product impact, not a requirement to finish every backlog
item before retrieval. No critical source-destruction defect was observed.

### P1 — A. Limit which view items a Build can rewrite

**Fix:** Separate read-only prior context from writable items. Select affected
items using exact incoming subject references, explicitly changed claims and
existing support/endpoint links. Preserve all support for the items actually
selected. Mere similarity to a prior claim must not authorize rewriting its page.
No extra selector call is needed.

**Bounded validation:** Two structural cases: an independent new subject leaves
seed items byte-identical; an update to an existing subject refreshes its relevant
items while preserving manual/protected/shared support. Then one bounded native
successive-Build check. Acceptance is useful continuity and substantially less
unrelated rewrite work, not an exact number of pages or claims.

**Stop:** Adopt the scoped mechanism after those checks. Do not redesign the
entire wiki or tune arbitrary relevance thresholds against the workshop fixture.

### P1 — B. Reduce meaning changes introduced by presentation

**Fix to test:** Make presentation primarily select, group, label and link retained
statements. Test reusing their text instead of freely paraphrasing each selected
item; this can remove output fields/work rather than add a verifier. If synthesis
remains useful, its benefit must outweigh repeated loss of conditions and status.
The two existing prompts already state the desired fidelity, so another growing
instruction list is not the first choice.

**Bounded validation:** One candidate, two frozen evidence sets with current versus
proposed actions and independent information, plus one counterexample where
uncombined repetition would harm readability; at most six presentation calls,
counting comparisons. Review whole artifacts for unsupported new commitments,
concision and useful organization. Source retention stays frozen.

**Stop:** Choose the simpler result if it preserves useful qualifications without
making pages unusably repetitive. Otherwise keep the existing approach, record
the limitation and seek recurrence in ordinary use; no second candidate campaign.

### P2 — C. Preserve valid identity information at stage boundaries

**Fix:** Validate binding eligibility before counting conflicts; exclude structurally
illegal project bindings, then reject genuine remaining person conflicts. Align
the singleton-You and nonempty-title invariants between admission and storage.
Pass relevant declared/bound people to presentation as optional choices, including
their explicit speaker relationship, without adding them to every claim or
requiring a page. Keep semantic identity decisions in the existing shared pass.

**Bounded validation:** Offline tests for invalid project plus valid person,
two genuinely conflicting people, fixed reviewed bindings, invalid singleton IDs
and independent valid rows. One own-project and one third-party-project native
counterexample pair only when validating the changed stage handoff; both must
keep builder and speaker distinguishable. Reuse existing frozen inputs.

**Stop:** Valid information survives and illegal structures are rejected locally.
Do not require Hari, a project, or every speaker to receive a particular page.

### P2 — D. Prevent stale failure handling from overwriting completed batches

**Fix:** Failure status updates must check that the current batch/checkpoint is
still the attempt being failed. Discard stale episode objects after an optimistic
conflict, including finalization. Preserve a competing completed manifest and its
claim membership. This does not need a new distributed scheduler.

**Bounded validation:** The reproduced competing-commit interleaving plus a real
isolated two-handle/process regression and ordinary failure recovery. Assert that
the winning claim and completed checkpoint agree and that the next Build does not
repeat completed extraction. No LLM calls are necessary.

**Stop:** Those state invariants hold; do not broaden this into general concurrency
infrastructure. Ordinary single-process UI use is already serialized.

### P2 — E. Give all source chunks a fair prior-context shortlist

**Fix:** Merge learned per-chunk rankings before truncation, such as rank-wise
interleaving with exact ID deduplication. Preserve deliberate recent/bound identity
context. Keep the candidate budget bounded and avoid additional model decisions.

**Bounded validation:** Three chunks with disjoint ranked candidates, overlapping
candidates and a late prior target. The end of a conversation must be represented
when the budget permits. Verify exact budget/context diagnostics; one existing
late-update case is enough if native confirmation is needed.

**Stop:** The mechanical prefix bias is removed. Do not turn this into the
out-of-scope retrieval-quality project.

### P3 — F. Remove retired scaffolding and clarify diagnostics when touched

**Fix:** Remove unused routing/default-section helpers and stale documentation;
trace consumers before removing historical artifact types. Distinguish cancelled
benchmark work from transport failures, and identify incomplete usage totals.
Keep performance telemetry descriptive rather than adding semantic scores.

**Bounded validation:** Static call-site review, relevant curation/schema tests,
and one cancelled-recorder fixture. No native calls. No compatibility framework
or redesign of the artifact store.

**Stop:** The touched surface matches the current architecture; defer unrelated
cleanup and collection-scan optimization until actual timing justifies it.

## Decision gate before shifting focus

1. Address scoped view refresh and the reproduced admission/checkpoint defects.
2. Evaluate one presentation-fidelity simplification with the bounded comparison
   above. Record ordinary omissions rather than extending it.
3. Complete one small current-code successive-Build check with source review,
   practical token/time costs, visible pending work and a zero-call no-op. No
   exhaustive fact checklist, ideal wiki match or aggregate accuracy target.
   Use an uncontended GPU for a meaningful timing observation. No separate runtime
   investigation or rerun of this closed audit is needed.

Once the artifacts remain largely coherent, important conditions survive, prior
unrelated pages are stable and cost is practical, freeze encoding and move on to
retrieval. The remaining individual omissions, imperfect headings and occasional
reasonable identity mistakes do not justify holding the entire product here.
