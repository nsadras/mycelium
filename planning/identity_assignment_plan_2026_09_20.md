# Identity assignment: discovery and implementation plan

Date: 2026-09-20. Baseline: `016ba80`.

**Status: implementation validated; native comparison partly incomplete.** Shared
retention (A v2), durable bindings, and correction UI are implemented. The fixed
44-request budget is closed. The control exhausted most of the integration
allocation, so no completed matched integration comparison is claimed. See
[results and remaining limits](identity_assignment_result_2026_09_20.md).
The original plan below records the agreed scope and stopping rules.

## Goal and agreed tradeoffs

Produce coherent, source-backed memory about people and their projects at practical
local cost. Choose the most likely identity supported by the available context,
and make mistakes easy to correct. Uncertainty alone should not force a duplicate
identity or block Build. A genuinely unidentified person can remain unidentified;
choosing a likely identity does not require inventing a name or relationship.

Use one shared model pass where possible. Allow one batched follow-up when its
benefit is demonstrated. The preferred small-source path remains **one retention
call plus one presentation call**. Large sources need bounded batches; report
their actual calls rather than promising two calls for every recording.

“Consistent” has two meanings:

- **Enforceable:** exact identity links, source provenance, and user corrections
  survive later batches, restarts, and view refreshes.
- **Probabilistic:** the model identifies who a statement concerns and whether
  that person is already known. Evaluate usefulness and recurring mistakes here;
  perfect extraction and identical prose across runs are not acceptance criteria.

## What the current implementation establishes

1. [Retention](../mycelium/retention.py) already shares extraction and identity
   decisions in one call. It now receives adjacent source context, recent claims,
   speaker provenance, and aliases. Another prompt-only speaker reminder is not
   a sufficiently different hypothesis to justify another tuning loop.
2. Identity candidates mostly come from retrieved claims. A topic change can hide
   the right person before the model gets a choice. A source-local tail helps but
   does not establish durable participant bindings.
3. [The recording adapter](../engram/memory_adapter.py) passes reviewed display
   names correctly. It replaces the original speaker label and does not carry a
   typed binding between a recording participant and a canonical person.
4. [The retention contract](../mycelium/memory_contract.py) combines discovering
   subjects, assigning claims, and selecting canonical identities. It requires
   redeclaring existing subjects and forbids a flagged uncertain match from using
   an existing ID. That last restriction conflicts with the agreed best-guess policy.
5. [Identity review](../mycelium/organization.py) only accepts decisions marked
   `review_required`. Reassigning references does not repair a wrong name embedded
   in claim text. Selecting an existing entity can also change its title. The
   current UI exposes scope/page choices during identity review and displays a
   hard-coded confidence value as a percentage.

The previous 20-request experiment demonstrated substantially smaller requests,
but did not establish reliable identity behavior. The recording produced a person
page in one comparison and omitted it in the final integrated run. Missing-antecedent
attribution also remained wrong. See [DEVLOG](../DEVLOG.md), entry
“Carry source context between memory stages with compact references,” and
`benchmark_runs/memory-context-20260920/review.json`. Those results justify a
contract comparison, not a claim that more context alone solved identity.

## Lessons from existing frameworks

Sources inspected on 2026-09-20; repository `main` is mutable. These are architecture
references, not matched speed or accuracy benchmarks against Mycelium.

| Project | Applicable method | Implication for this plan |
|---|---|---|
| [mem0](https://github.com/mem0ai/mem0/blob/main/mem0/memory/main.py) | Its current vector-memory path retrieves prior memories, includes recent session messages, uses short IDs, and makes one extraction generation call. | A shared pass is a credible starting point. Its user/agent scoping does not solve every multiparty attribution problem. |
| [Graphiti resolution](https://github.com/getzep/graphiti/blob/main/graphiti_core/utils/maintenance/node_operations.py) | Retrieves identity candidates and batches unresolved matches with current and previous episode context plus candidate attributes. | Test a shared resolver with the actual conversation and distinguishing evidence when extraction-time candidates are inadequate. |
| [Graphiti extraction](https://github.com/getzep/graphiti/blob/main/graphiti_core/utils/maintenance/combined_extraction.py) | Combines entity and relationship extraction; its implementation also has a timestamp call, and other stages add work. | Combine closely related decisions; do not infer a one-call end-to-end pipeline from a single combined operation. |
| [Hindsight](https://hindsight.vectorize.io/blog/2026/06/29/entity-resolution-agent-memory) | Supplies explicit participant context to extraction; documented resolution uses name similarity, co-occurrence, and recency without another LLM call. | Adopt the participant-context discipline. Its fuzzy matching rules conflict with this project's semantic guardrails and will not be copied. |

## Proposed decision boundary

Separate these concepts in the information passed between stages:

| Concept | Meaning and authority |
|---|---|
| Source participant | Who supplied these words. Preserve a source-scoped speaker ID, display name, and any explicit user binding. A display name alone is not a global identity ID. |
| Subject of a statement | Who or what the statement concerns. The model determines this from the conversation; it can differ from the speaker. |
| Canonical identity | The persistent person/project/etc. selected for a subject. Reuse exact user bindings; otherwise make a model decision with evidence. |
| Page placement | Which useful view contains the statement. Presentation consumes the identity result; page admission does not define who a person is. |

This is a logical stage boundary, not a requirement for another model call.

### Context supplied to the decision

- Current source text with exact segment references, speaker IDs, source type,
  and timestamps; enough neighboring turns to interpret reported speech and
  references. Preserve existing compact request IDs and their diagnostic mapping.
- A participant table carrying reviewed names and explicit canonical bindings
  when available. Account-owner status must come from the capture contract or
  user review. Do not infer it from being the uploader or the only speaker.
- Established source-local bindings from earlier completed batches, including
  whether they were model-selected or user-confirmed. Supply relevant bindings
  directly rather than hoping topic retrieval returns them again.
- Bounded candidate records: ID, name, aliases, and distinguishing cited evidence.
  An ID plus a name is weak evidence for deciding between namesakes.
- Explicit user corrections relevant to these bindings. Older generated text must
  not silently undo a reviewed identity decision.

Build candidate context from stored evidence without a new profile-writing LLM.
First reuse the existing index, source references, and targeted embedding queries
for known participants. Embeddings retrieve possibilities; they do not decide
identity. Add an entity-specific index only if measured candidate availability
remains the limiting problem. Keep this as a separate justified decision.

Measure the serialized prompt and schema against the context/output allowance.
Bound candidate evidence and surrounding turns; log what was omitted. Loading the
whole store or repeatedly summarizing the conversation is outside this tranche.

### Two candidates, one eventual production path

| Candidate | Model work | Small-source Build cost |
|---|---|---|
| **A — shared retention, preferred** | One call extracts useful statements and makes identity assignments using the context above. Make the identity result explicit and reusable. | Normally 2 generation calls, including presentation. |
| **B — extraction then shared resolution** | Retention identifies source-local subjects and their statements. Once those subjects are known, retrieve appropriate candidates and resolve them together in one call. | Normally 3 generation calls, including presentation; skip resolution when all required bindings are already explicit. |

Both use a flat decision table connecting source-local subjects to an existing or
new identity, with cited support. Prototype the smallest representation; justify
each added field. Remove redundant existing-subject declarations where possible.
No relation taxonomy, compulsory explanation tree, or numerical confidence ladder
is needed for this experiment.

Candidate B owns canonical matching once; it does not ask a second model to grade
and repeat an earlier canonical decision. It must receive useful additional
context or simpler work. If the failure is that retention omitted a person or
misunderstood the actor, a later matching pass may not help—measure that separately.

An ordinary source gets at most one shared resolution follow-up, never one call
per person, claim, or candidate pair. For an oversized source, freeze the bounded
work units before running and disclose the resulting call budget. Keep existing
model bindings reusable but correctable; explicit user bindings take precedence
within their reviewed scope.

## Work sequence and acceptance criteria

### 1. Freeze the comparison and diagnose failure location

- Pin code, configured `gemma4:12b` digest/options, prompts, schemas, seed store,
  source text, segmentation, and cold/warm model state.
- Freeze four small development scenarios and two additional scenarios held out
  from prompt changes. Cover own work versus reported work; named speakers whose
  names are absent from speech; aliases and namesakes across topics; batch-boundary
  references; missing context; and account-owner versus meeting-participant roles.
- For each failure distinguish: missing candidate, wrong local attribution, wrong
  canonical match, lost persisted binding, or presentation-only omission.

**Acceptance:** the comparison can explain where a bad assignment started and
what evidence that stage received. Ambiguous examples permit a defensible best
guess; a hidden “correct answer” is not evidence available to the model.

### 2. Prove the contracts outside production

- Probe A against the frozen baseline using the configured host model and actual
  candidate schemas. Probe B only if A leaves a recurring problem that separation
  could address. Give B its own extraction input; stripping IDs from A's answer
  would not be a fair test of a different division of work.
- Start with neutral short conversations, then counterexamples. Keep all scenario
  vocabulary and expected outputs out of production prompts.
- Use at most **24 generation requests**, including failed attempts and repeats.
  A full allocation is four scenarios × (baseline 1 + A 1 + B 2) = 16 requests;
  two held-out baseline/winner comparisons use at most 6; 2 remain for a repeat or
  one general contract adjustment. Unused requests are not a reason to keep tuning.
- Direct probes use one attempt so schema failures remain visible. Record input
  and output tokens, generation and embedding work, wall/server times, and errors.

**Acceptance:** valid, interpretable outputs; useful identity assignments on ordinary
sources; and no recurring tendency to assign reported work to the speaker or
account owner. Check citation support and ambiguity by source inspection, without
an LLM judge. Prefer A when usefulness is comparable. B needs benefits on more
than one independent example, including a held-out example, to justify another
pass. A particular page appearing once is insufficient evidence.

### 3. Implement the selected mechanism and durable bindings

- Integrate the proven contract in retention and source ingestion. Persist the
  identity decision, evidence, and source-local binding together with its claims.
- Use exact IDs for propagation across later batches and presentation. A fresh
  source still needs evidence or a user binding before sharing an identity.
- Preserve resumable completed work, stale-read checks, source retraction, and
  visible failures. If B is selected, make its unfinished work resumable without
  repeating successful extraction or silently substituting guessed matches.
- Replace the displaced contract and prompt rules. Keep one implementation of
  identity assignment; avoid a runtime chain of old/new resolvers and repair calls.

**Acceptance tests:** same source speaker IDs cannot become different bindings
solely because a topic changes; source-scoped IDs cannot leak across recordings;
restart and no-op Build preserve IDs and make no redundant model calls; stale
updates cannot overwrite user corrections; unknown IDs and invalid citations are
rejected before persistence. These are structural tests, separate from model quality.

### 4. Make a best guess easy to correct

- Allow correction of automatically accepted assignments as well as flagged ones.
  Start from the affected memory or identity detail, select an existing person or
  create a distinct one, and inspect the supporting source and affected statements.
- Scope the correction to the selected binding/evidence. Preserve other references
  in the same claim, unrelated evidence about that person, and the selected
  canonical entity's name unless the user explicitly edits it.
- Include editable affected claim wording in the correction flow. Use the existing
  correction lifecycle for exact user text where a mistaken identity was embedded
  in prose. Reference reassignment alone is insufficient. Avoid global name replacement.
- Refresh affected views and search entries; preserve source originals and review
  history. Reuse explicit corrected bindings in later batches within their scope.
- Simplify the identity form around the person and affected evidence. Keep page
  admission independent. Show model-selected versus user-confirmed status instead
  of presenting the existing constant `0.8` as a calibrated probability.

**Acceptance tests:** correct an accepted mistake end to end; current references,
claim wording, search evidence, and refreshed views agree with the correction;
unrelated namesakes and other evidence are unchanged; later Build does not undo it;
failure leaves consistent state or a visible pending refresh. An explicit identity
selection needs no LLM judgment. Count any existing correction/presentation calls
in the workflow's measured cost.

### 5. Validate ordinary Builds and stop

- Run isolated matched baseline/candidate Builds with a ceiling of **20 additional
  generation requests**, counting retries and correction work. Plan the allocation
  before launch. Include a source spanning multiple batches, a follow-on conversation,
  the already-used recording excerpt as a regression case, and one correction.
- Include at least one fresh ordinary scenario. The familiar recording is not a
  holdout. Freeze source segmentation and seed state across the comparison.
- Review successive retained claims, identity links, and person/project views
  against source conversations. Assess main relationships, coherent attribution,
  unnecessary duplication, and whether useful context remains accessible.
- Run focused Python/API/UI tests, then the relevant full checks once. Record
  exact run paths, completion state, failures, and limitations in `DEVLOG.md`.

**Acceptance:** the selected design produces broadly coherent artifacts at its
declared call budget, preserves the structural guarantees above, and supports the
correction workflow. Person/project pages are assessed when the source supports
useful independent context; every speaker or mentioned noun need not get a page.
Do not make complete fact coverage, exact headings, or perfect benchmark scores gates.

## Selection and stopping rules

- Maximum **44 generation requests across discovery and integration**, or **20
  minutes of native-run wall time**, whichever is reached first. Record incomplete
  runs honestly; do not silently extend the budget to get a favorable result.
- Compare total generation attempts, embedding cost, input/output tokens, and
  latency per completed Build and per amount of source text. A pipeline that simply
  drops most useful memory is not an efficiency win. Report warm-up and stochastic
  limits; these small samples do not establish population accuracy or p95 latency.
- Choose the fewest calls that meet the practical quality bar. If an additional
  pass fixes only an isolated example, keep the simpler design and record the miss.
- One general contract adjustment is allowed within the probe budget. New failure
  categories go into the findings, not immediately into new prompts or stages.
- If neither candidate is adequate, report the limiting evidence/context problem
  and the measured tradeoff before another design tranche. Do not integrate an
  unproven resolver just because its scaffolding is complete.
- After a passing implementation, remove displaced code, document residual errors,
  commit validated work, and return to ordinary product use. Reopen identity work
  for recurring harmful behavior, not a desire to make these examples perfect.

No production code, model probes, live-store rebuild, or service operation was
performed while preparing this plan. No further goal clarification is currently
needed; the architecture choice is the bounded experiment's job.
