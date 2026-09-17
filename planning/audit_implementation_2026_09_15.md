# Consolidated audit implementation plan

**Updated:** 2026-09-17. **Reviewed production baseline:** `01ac86d`.

This is the authoritative forward priority list. It incorporates the
[regrouping audit](mycelium-audit-2026-09-16-regroup.md) and the useful methods
identified in Mem0, Graphiti, and Hindsight. It replaces the earlier rollout
order in this file. The historical implementation record remains below;
`DEVLOG.md` and saved runs retain the detailed evidence.

**Current state:** E1 and focused C1–C3 fixes are implemented. E2 completed both
comparison arms and source review. S1 bounded truth discovery, S2 dependency
maintenance, and measured date/name/attribution fixes are implemented. Longitudinal
replay completed with residual quality failures; held-out validation remains open. Existing
storage, review, configuration, retrieval-consistency, and UI fixes remain the
foundation. The latest recorded structural suite is 822 passed, one skipped,
75 integration tests deselected; that is not full semantic acceptance.

### Implementation progress after resuming

- **E1 implemented:** accurate retrieval timing with versioned checkpoints
  (`3a48d39`); removed obsolete production contracts and migrated probes
  (`bbb4320`); question-scoped answer judgment, flat support flag, frozen fixture
  and evaluator identity. The [comparison protocol](audit_comparison_protocol_2026_09_16.md)
  records current call/contract complexity and reserves LoCoMo sample 10 for V1.
- Validation: 782 structural tests passed after retiring redundant old-contract
  tests; 27/28 migrated native cases passed. The failing relative-date event
  distinction remains visible under C1. The evaluator's proposed support contract
  passed 45/45 direct cases, then 15/15 through the maintained native runner.
- **C1 implemented provisionally:** `68498fa` clarifies the existing weekday
  field without changing its shape or adding calls. Four mixed-source checks,
  14 isolated production controls and the native correction/retrieval workflow
  passed. The matched direct arm also passed; a broad accuracy gain is unproven.
  The earlier event-scope diagnostic remains visible. E2 reopened absolute-date
  syntax/kind failures: exposing the existing date format and clarifying the
  absolute kind passed7/7direct and native date/range Build→retrieval checks,
  with no extra call or field. Longitudinal replay/V1 remain gates.
- **C2 implemented:** `57c0a86` separates identity matching from a source-backed
  preferred-name update in the existing call. Direct proposal 14/14, maintained
  production controls 12/12, native routing 8/8; zero failed requests. E2 exposed
  an unguarded new-title typo; a flat source-name/description declaration now
  validates new adopted spelling. Accepted13/13direct, integrated12/12 and
  native8/8,0failures. Broader transitions, external-user identity, pending truth
  review and cumulative quality remain replay/V1 gates.
- **C3 implemented:** `742196c` rejects incomplete exact citations before
  routing/fact projection. Projection now resolves links against the complete
  planned page set, refreshes references on destination changes, and coverage
  uses source/segment pairs (`60766e2`). Partial retraction now compares active
  source assertions directly, preserving canonical history and manual bindings;
  three direct and three integrated semantic controls passed. Latest structural
  suite: 799 passed, one skipped, 75 integration deselected.
- **S2 focused mechanism implemented:** page promotion now follows exact active
  entity references and respects caller source/deferred filters. A neutral native
  comparison reduced15to12calls while retaining old claims/facts; a promotion
  counterexample retained earlier page evidence. Structural67passed. Broad
  longitudinal acceptance remains open. Production native addition and page
  promotion also passed: old unrelated claims/facts stayed identical, and earlier
  referenced evidence appeared on the newly admitted page.
- **S1 implemented:** frozen cap 48 (32 global semantic plus 16 entity neighbors).
  All four annotated changes survived search in a paired 104-record control;
  model calls fell 28→16 and model time 368→153s. Native review preserves canonical
  claims and produces pending proposals. Fixed B=4 stays below 192 eligible pairs
  at 100/1,000/10,000 records; warm search 0.070/0.223/3.486s. Compact semantic
  inputs reuse decisions across regenerated reference IDs; evidence, role,
  identity, time and human-review changes invalidate reuse. Historical-event and
  ambiguous-identity false proposals remain visible in both comparison arms;
  search is approximate, and these measurements do not establish full-workload
  quality or cost.
- **W1 attribution cost reduced:** removed the repeated explanation field from
  each attribution cell. Both direct arms14/14; output tokens fell33.5% and
  measured time21.6%. Integrated13/13 and native page-review3/3 passed. This
  simplifies existing work; cumulative page usefulness remains a replay gate.
- **W1 source context implemented:** carry existing identity interpretations into
  attribution with exact supporting IDs. The narrower contract passes 20/20
  direct controls and a native successive-build positive/counterexample; no new
  model calls or output fields. An earlier native discovery miss remains recorded.
  Stale current-state summaries and missed truth proposals remain quality limits.
- **R1 evaluated; additional retrieval machinery not selected:** seven frozen
  evidence controls show app prompts recovering several answers without any
  memory-tool calls. Temporal interpretation still fails with the relevant source
  already present. No new index, entity/time branch or reranker is warranted by
  these observations. See the [follow-through report](audit_followthrough_observations_2026_09_17.md).
- **Longitudinal replay complete with failures:** `e4cfc9d` uses 198 model attempts
  / 1,404.580s versus 321 / 2,732.122s at `fdcc767`, with the same 10/19 raw QA
  passes. The new run has five routing failures; both miss the pilot-date review.
  Full extraction and valid citations do not establish complete page organization.
  Cost reduction is measured; full quality acceptance remains unproven.
- **E2 diagnostic complete:** nine production checkpoints and 19/19 probes in
  both arms. The ranked control recovers three answers but uses 8.23× the context
  characters. Final extraction is complete; a missing truth proposal blocks the
  intended approval action. [Source review and cost](audit_e2_observations_2026_09_16.md)
  distinguish evaluator disagreements, encoding failures, and QA errors. Product
  acceptance and the remaining longitudinal/held-out gates remain open. No new
  product LLM stages or nested
  response structures have been added. Evaluation improvements and focused
  correctness checks do not establish longitudinal memory quality or cost.

## Objective and fixed product decisions

Build a useful local memory system that preserves evidence, retrieves relevant
information, and maintains readable views at a sustainable incremental cost.
The next milestone is one complete, source-reviewed quality/cost comparison.

**Benchmarks are guideposts, not the targets.** Optimize for useful daily recall,
trustworthy evidence, understandable memory, manageable review work, and local
resource cost. A perfect benchmark score or a wiki matching a reference layout
is not a completion requirement. Benchmark failures identify questions to
investigate; their importance depends on the real product failure they reveal.

- Durable capture is immediate; extraction and cross-session search start with
  **Build Memory**.
- Useful independent context may justify a page after one conversation.
- Relative-date corrections show interpreted dates for review before saving.
- “No page” applies to the reviewed evidence/entity pair.
- Canonical contradictions and replacements require human review. Pending
  alternatives must remain inspectable and visibly unresolved.
- Claims/sources are evidence; wiki prose is a derived view. View ownership
  must not decide identity or truth.
- Meaning comes from structured model decisions or explicit review. Exact IDs,
  citations, declared schema values, and calendar operations can be validated
  deterministically. No lexical semantic repairs or fixture-specific rules.

## Priority and execution order

Severity describes impact; execution order also accounts for dependencies.
P1 items address trust, unbounded work, or missing decision evidence. P2 items
address measured quality gaps and maintenance. No new P0 storage-loss defect
was demonstrated in the audit.

| Order / ID | Priority | Work item | Method and decision | Depends on |
|---|---|---|---|---|
| 1 — **E1** | P1 | Make evaluation and tests describe the current product | Fix rubric overreach; retire obsolete production probes; freeze comparison inputs | None |
| 2 — **C1** | P1 | Correct relative-date interpretation | Separate weekday occurrence from deadline relation; preserve reviewed correction behavior | E1 test contract |
| 3 — **C2** | P1 | Ground names and preserve identity through transitions | Separate identity matching from evidence-backed property updates | E1 test contract |
| 4 — **C3** | P2 | Close exact provenance and page-link gaps | Shared citation validation and validation against the projected page set | Independent of semantic proposals |
| 5 — **E2** | P1 | Complete a longitudinal comparison and simple baseline | Mem0-inspired extraction/retrieval control; attribute quality and cost to stages | E1, C1–C3 |
| 6 — **S1** | P1 | Bound truth comparisons and stabilize semantic cache inputs | Graphiti-inspired search-first candidates, then structured comparison | E2; candidate-recall proof |
| 7 — **S2** | P2 | Update only affected derived views | Hindsight-inspired incremental maintenance using existing records | E2 evidence; C2/C3 |
| 8 — **R1** | P2 | Improve retrieval where measured losses occur | Hindsight-inspired entity/time candidates and reranker comparison; source-index experiment if needed | E2 coverage analysis; C1/C2 |
| 9 — **W1** | P2 | Make cumulative pages useful and coherent | Hindsight-inspired page purpose and source-backed scope | C2/C3, S2; E2 page review |
| 10 — **V1** | P1 release gate | Demonstrate generalization and full-workload behavior | Genuinely held-out sequence, then matched stress/regression runs | Accepted changes above |
| 11 — **O1** | P2 rollout gate | Validate browser/device/network behavior | Finish existing UI, audio, and private-network acceptance | Relevant changes; user-started services |

S2, R1, and W1 are conditional improvements, not instructions to add every
available method. An item can close by demonstrating that the existing mechanism
already meets its acceptance criteria. Rejected proposals need a recorded result,
not a replacement subsystem. Small independent correctness fixes may proceed
while comparison artifacts are being prepared.

## Guardrails against overfitting and unnecessary complexity

Every proposed semantic change must have a short decision record answering:

1. **Product need:** which real user workflow or invariant fails, described
   without referring to fixture names, expected wording, or a benchmark score?
2. **Simplest mechanism:** can we fix the existing input, decision boundary, or
   representation; remove a decision; or reuse evidence before adding a stage?
3. **Complexity cost:** what changes in LLM calls, input/output tokens, retries,
   latency, schema nesting/branches, and persisted artifacts for the same input?
4. **Generalization evidence:** what neutral counterexamples, native workflow,
   and unused evidence support the benefit beyond the cases used to develop it?
5. **Adoption or stopping decision:** is the useful gain worth the cost, and what
   result would make us reject the proposal or accept a documented limitation?

Default implementation choices:

- Prefer flat decisions and small bounded lists. Nest structured outputs only
  when the domain relationship requires it; do not require explanations or
  claim/entity matrices merely to make every intermediate decision look complete.
- Separating semantic concerns does not automatically require separate LLM calls.
  First try a clearer contract in the existing call. Extra calls, verification
  loops, or retries need measured product value and an explicit resource budget.
- Preserve exact ID/citation/schema checks and human-review boundaries. These
  are product invariants, not benchmark optimization. Proper names must be
  evidence-backed; descriptive titles and page layouts can vary legitimately.
- Keep fixtures, ideal wiki prose, expected answers, and evaluation-specific
  logic out of production prompts and code. No lexical reconstruction of a
  benchmark expectation; no widening schemas just to encode another fixture case.
- Use a frozen development set plus distinct counterexamples; evaluate unused
  scenarios without tuning on them. Repeated successes on one case are not new
  evidence of generalization, and paraphrases are not independent holdouts.
- Prefer a simpler measured design when added complexity has no material user
  benefit. Document minor editorial imperfections and acceptable tradeoffs.
  Critical evidence/identity/date failures still need a general mechanism or
  explicit uncertainty; a higher aggregate score cannot excuse them.
- Do not add infrastructure, memory layers, or model dependencies without a
  demonstrated gap. Use existing benchmark recording and reporting rather than
  building a new evaluation framework for this plan.

These checks apply to competitor-inspired methods too. Each is a hypothesis,
not an obligation to reproduce the other project's architecture.

## Work items and acceptance criteria

### E1 — Reliable evaluation and current production contracts

**Work**

- Align answer rubrics with the question actually asked. Accept equivalent
  concise answers and useful alternative page layouts; keep factual omissions,
  unsupported assertions, identity errors, and lost conditions separate.
- Migrate useful tests from obsolete truth/synthesis builders to current
  production prompts/schemas; remove unused production APIs and clearly label
  historical experiments. Preserve their saved outputs.
- Separate execution completion, extraction coverage, organization quality,
  retrieval, QA, and human-review burden. Rename the misleading per-question
  `memory_construction_time` metric to describe retrieval.
- Inventory current calls and structured-output shapes from existing production
  builders/traces so each later proposal can show its complexity delta.
- Freeze a development corpus, scorer/rubric version, model digests, effective
  settings, source timestamps, and explicit review actions before comparisons.
  Select the future held-out sequence without using it for prompt development.

**Acceptance**

- A correct concise answer passes; a superficially similar wrong answer fails.
  Unknown judgment IDs, unsupported verdicts, and incomplete output fail visibly.
- Each maintained native probe calls the current production decision builder.
  Structural tests exercise that builder's exact constraints.
- Reports distinguish terminal failed/incomplete runs from successful encoding
  and QA. Timings include retries and identify shared/cached work and cancelled
  calls; retrieval time is not reported as offline construction time.
- Known fixtures are development/regression data. **LoCoMo sample9 is not a
  fresh holdout**: it already has extensive runs and audits in this repository.
  See [its prior audit](locomo_sample9_audit_2026_09_08.md).

### C1 — Dates that preserve the source's intended relationship

**Work**

- Prove a structured distinction between which weekday occurrence is meant and
  the deadline/condition imposed on that occurrence. Keep the source expression,
  its cited reference, target, and role inspectable.
- Start within the existing extraction/correction calls; two semantic concepts
  do not by themselves justify two new stages or a deeper response hierarchy.
- Calculate dates only from validated declared operations. When the source does
  not establish a relationship, preserve explicit uncertainty; do not repair
  the sentence with keyword rules.
- Keep correction-date preview, stale checks, and idempotent saving intact.

**Acceptance**

- Direct configured-model cases cover future/past/same-day/cross-week references,
  reported historical speech, multiple time targets, missing dates, and ambiguity.
  Clear cases resolve correctly; answering “unresolved” to every case is not a pass.
- Native extraction → claim → wiki → QA retains correct dates, conditions, and
  source anchors. No unsupported resolved dates in the frozen critical cases.
- Ambiguous cases remain visibly unresolved. Reviewed corrections retain their
  chosen reference across retries, source edits, and delayed saves.

### C2 — Evidence-backed naming and stable identity

**Work**

- Separate “same identity?” from “does its preferred name change?” Treat first
  naming, spelling correction, rename, descriptive labels, and ambiguity as
  explicit supported outcomes.
- Prefer a compact change to the existing identity contract. A separate naming
  call needs evidence that the simpler contract cannot meet the product need
  and that the improvement warrants its cost.
- Ground adopted spelling in an exact source occurrence or explicit user review.
  Preserve the evidence for the name transition and relevant aliases.
- Carry the resolved identity into truth review so obsolete naming states can
  produce an appropriate proposal without automatically changing canonical truth.
- Retain source-role attribution and exact human-review constraints. The current
  unaccepted name-options draft is evidence to learn from, not an approved patch.

**Acceptance**

- Direct positive/counterexample cases preserve distinct namesakes and identify
  unambiguous first naming, correction, and renaming correctly. Unsupported names
  are never silently adopted; descriptive titles allow equivalent wording.
- Native successive builds preserve IDs through supported transitions and keep
  people/products distinct. A name change does not create a duplicate identity.
- Old/new state has a correctly directed pending review where required; approval
  updates current views while retaining history. Manual identity decisions and
  evidence-specific no-page reviews survive subsequent builds.

### C3 — Exact integrity boundaries

**Work**

- Share exact source/segment validation across formatting, fact construction,
  truth review, and retrieval. Replace silent missing-evidence skips with an
  explicit integrity result at the appropriate boundary.
- Validate wiki links against the complete projected page set, including pages
  removed in the same build. A valid non-page identity can be shown as a
  non-clickable reference without losing its canonical ID.

**Acceptance**

- Missing/inactive sources, missing segments, singleton facts, and multi-source
  claims cannot silently publish unsupported derived content. Canonical data is
  preserved and the error identifies the broken reference.
- Every generated page link resolves after publication; identities with no page
  remain inspectable. Creating/removing pages in different processing orders has
  the same valid link result.
- Existing transaction, review, retraction, and retrieval-consistency regressions
  pass. Add focused tests for these invariants, not a new recovery framework.

### E2 — One complete comparison before further optimization

**Work**

- Freeze the corrected production revision and complete one longitudinal daily
  scenario, including all nine checkpoints and early/middle/final page review.
- Add a benchmark-only extraction/retrieval control using the same admitted
  claims, exact source evidence, embedding model, QA model, and context budget,
  with direct ranked evidence and no generated wiki presentation requirement.
  Preserve source policy and explicit review actions in both arms.
- Reuse extraction artifacts when isolating retrieval/organization effects;
  account for shared extraction/indexing costs separately. Measure production
  extraction and organization independently rather than rerunning expensive
  upstream stages merely to compare answer assembly.
- Compare source → claim → candidate → admitted → rendered evidence, grounded
  answers, page utility, review burden, generation time, and incremental build
  cost. Hide arm labels during source review where practical.

**Acceptance**

- Both arms finish the declared workload or produce an honest terminal failure
  report. A failed diagnostic can be complete evidence; it is not product acceptance.
  QA on incomplete encoding remains explicitly diagnostic, never a normal pass.
- Product acceptance requires no unexplained extraction/publication backlog,
  exact evidence integrity, the critical correctness gates above, and reviewed
  answers/pages. Deferred/source-only decisions and pending human reviews are
  reported separately from execution failures.
- Every quality/cost claim identifies its denominator, data/model/configuration,
  shared work, and uncertainty. One completed run is a baseline, not a reliability
  estimate. Stage measurements determine the next optimization.

### S1 — Bounded truth discovery and stable decision reuse

**Work**

- Retrieve a bounded union of semantically related claims and candidates from
  established entity relationships. Keep a global semantic route across owners
  and unresolved identity boundaries; page ownership cannot exclude a conflict.
- Ask the structured comparison model only about these candidates, including
  relevant same-batch claims. Proposed canonical changes still require review.
- Construct semantic cache inputs from evidence, roles, identities, temporal
  meanings, and reviews. Keep recreated UUIDs and build bookkeeping outside the
  inference payload while retaining them in the audit record.

**Acceptance**

- Compare candidate recall with exhaustive comparison on a small annotated
  control, using source review to adjudicate disagreements. Include cross-owner,
  same-batch, unplaced, renamed, and ambiguous-identity cases.
- Before held-out testing, freeze candidate cap `K` and the acceptable recall/cost
  tradeoff using E2. Investigate critical missed changes as product defects and
  report every miss; do not keep expanding work solely to obtain a perfect score.
  Exhaustive model comparison is also fallible, so source annotations adjudicate
  disagreements. Approximate retrieval does not acquire exhaustive guarantees.
- With fixed incoming batch `B` at 100/1,000/10,000 historical claims, model pair
  work is capped by `B × K` plus bounded same-batch work. Measure search/index
  overhead separately. Do not run the exhaustive model control at 10,000 claims.
- Semantically identical references with new bookkeeping IDs reuse decisions;
  changed evidence, role, identity, time, or human review invalidates them.
  Measure reuse during actual rerouting as well as unchanged rebuilds.

### S2 — Incremental derived views and independently usable evidence

**Work**

- Use the existing claim/fact/page records and exact dependency IDs to update
  only views affected by changed evidence, identity, placement, or review.
- Verify that extracted/indexed claims remain searchable when organization is
  incomplete, with accurate stage status. Capture remains unsearchable before Build.
- Reuse existing publication and decision-cache mechanisms. Make additional
  separation of model work only where E2 demonstrates unnecessary coupling.

**Acceptance**

- A new unrelated source does not regenerate unchanged fact prose/pages or
  repeat their semantic decisions. Compare canonical content while allowing
  operational audit timestamps to change.
- Relevant edits, retractions, identity changes, and approved reviews refresh
  all affected views; unrelated views stay stable. Restart/cancellation preserves
  searchable extracted evidence and honest unfinished-organization status.
- Measure fixed additions against increasing history and a real rerouting case.
  Existing zero-generation empty rebuilds alone do not satisfy this gate.
- Retain the change only if it reduces measured work without worsening grounded
  answers, review behavior, or page correctness.

### R1 — Retrieval improvements selected by observed loss

**Work**

- Start with E2's stage losses. Existing semantic/full-text retrieval is the
  control; avoid rebuilding what already works.
- Test bounded candidates from resolved entity relationships and model-declared
  temporal constraints. Fuse candidate rankings and compare a small neural
  reranker with the current generative admission step.
- Treat search depth and returned evidence tokens as separate budgets. Keep
  exact citations and source excerpts in both arms.
- If extraction omissions dominate, test a post-Build source-segment index as a
  separate evaluation arm. Expanding the sources behind an already retrieved
  claim does not solve missing candidates. Production adoption must explicitly
  preserve source-only exclusions and assistant/tool authority boundaries.

**Acceptance**

- Use the same frozen stores, queries, QA model, source policy, and context
  budget. Change one retrieval mechanism at a time; report recall, grounded
  correctness/abstention, tool work, and warm/cold latency.
- Include complementary multi-part evidence, negation, conditions, different
  people, current/historical states, missing claims, and no-support queries.
- Candidate scores only propose/order evidence; they never determine identity,
  ownership, contradiction, or canonical replacement. New semantic contracts
  still require configured-model proof before production integration.
- Predeclare acceptable quality loss (if any), latency/cost improvement, and
  additional local resource use from E2 before selection. Do not add a reranker
  dependency or source-index feature merely because another project has one.

### W1 — Useful page scope and longitudinal coherence

**Work**

- Give existing page kinds a clear purpose. A project view should make its
  purpose, relevant constraints, responsibilities, and current state accessible
  when supported by evidence.
- Include relevant established relationships even where another entity owns
  the underlying claim. Preserve canonical ownership and source provenance.
- Refresh within that evidence scope. Read claims/facts and exact sources;
  prevent page prose from becoming evidence for other page prose.
- Evaluate attribution verbosity and grouping cost using E2/S2 timings before
  changing output contracts. Seek fewer decisions/less output for equal useful
  coverage; do not add a separate page-purpose generation stage by default.

**Acceptance**

- Review early/middle/final pages against sources for coverage, correctness,
  concision, organization, and transitions. Permit equivalent layouts and useful
  first-conversation pages; exact title/page/fact counts are not release gates.
- Pending changes remain visibly unresolved; approved changes update current
  views and retain history. Critical conditions and tentative commitments survive.
- Names, synthesized assertions, and links meet the evidence/integrity gates.
  Record repetition, leaked local labels, and awkward organization separately
  from factual errors; fix their mechanisms proportionately. Minor editorial
  differences do not justify additional model stages or block a useful release.
- Useful cross-entity context is accessible without blanket page sharing or
  creating one page for every incidental assertion. Record page-review findings
  alongside compute cost, rather than collapsing them into a lexical score.

### V1 — Held-out evidence, then stress/regression validation

**Work and acceptance**

- Evaluate a genuinely unused longitudinal sequence before another cycle of
  tuning familiar fixtures. Check historical run/audit use when selecting it;
  paraphrases of the same scenario are not independent held-out evidence.
- Once inspected and used to change prompts, that sequence becomes regression
  data. Record this explicitly; never relabel it held out on the next run.
- Run full sample3 (32 sessions / 193 questions) with pinned settings and honest
  stage completion. Use sample9 and the remaining daily variants as additional
  regression/stress data. Repetitions estimate variability after a complete run;
  nine familiar scenario repeats are no longer a prerequisite to held-out work.
- Compare accepted production and the frozen baseline under matched settings.
  Separate encoding failures, retrieval losses, answer errors, and wiki defects.
  Manually review successive source/wiki snapshots and retain per-call evidence.
- Run appropriate focused tests for each change and the full structural suite
  once per coherent validated tranche. Run UI checks when affected. Do not rerun
  expensive model suites solely because an unchanged structural suite passed.
- Release readiness requires all applicable correctness, integrity, workload,
  and rollout gates, plus explicitly documented residual limitations. Passing a
  narrow probe or spending the experiment budget does not complete this item.
  It does not require every benchmark answer, page, title, or section to match
  its reference. Report the remaining semantic error profile and user impact.

### O1 — Finish existing rollout checks

**User decision (2026-09-16):** leave real browser, microphone, and Wi-Fi/Tailscale
checks to the user after implementation is ready. Do not start application
services for these checks. Automated validation continues independently; the
handoff will include the checks below, with manual results explicitly unverified.

**Acceptance:** with user-started services, verify Wi-Fi/Tailscale chat, source
inspection, audio upload/playback, transcript review/admission, correction review,
and navigation during pending requests. Confirm failed actions preserve drafts
and show actionable errors. Record device/browser/network results and any
unverified cases. Existing same-origin networking and the user's authentication
preference remain in force; this plan does not require new infrastructure.

## Measurement and experiment rules

- Every semantic change follows AGENTS.md: direct configured-host-model proof
  on small neutral cases and counterexamples, then the smallest in-situ change,
  focused structural tests, native pipeline validation, and a DEVLOG entry.
- Before a model experiment, record the hypothesis, cases, call/time budget,
  comparison arm, and adoption criterion. Afterward record accepted, rejected,
  or inconclusive. Do not grow the contract repeatedly to rescue one fixture.
- Freeze the development set; separate distinct situations from repeated trials.
  Preserve failed hypotheses and input/scorer changes in the comparison record.
- Complete diagnostic workloads despite semantic/editorial misses when continued
  execution is meaningful. Stop on resource limits, user direction, or errors
  that make continuation invalid; retain an honest incomplete result.
- Existing targets of construction ≤5.2h, failed-model time <5%, retrieval
  median ≤5s/p95 ≤8s, and context recall +20% are **provisional**. E2 must establish
  workload/hardware baselines and define +20% as relative or percentage-point
  improvement before considering them as acceptance thresholds. Adopt targets
  only where they represent useful product behavior; they do not automatically
  become goals because they appeared in the earlier plan. Keep citation coverage
  separate from proposition coverage and answer correctness.
- Report source-supported correctness, useful coverage, review burden, stage
  latency/retries, token/model work, and incremental cost. A system that always
  abstains or requests review does not pass merely by avoiding false assertions.

## Methods adopted as hypotheses

| Source | Useful method | Planned application | Boundary |
|---|---|---|---|
| [Mem0](https://github.com/mem0ai/mem0) | Current documented ADD-only extraction and retrieval emphasis | E2's simple control; S2's independently usable evidence | Keep Mycelium's source authority and review semantics; published managed scores are not our baseline |
| [Graphiti edge resolution](https://github.com/getzep/graphiti/blob/main/graphiti_core/utils/maintenance/edge_operations.py) | Search candidates before duplicate/contradiction resolution | S1 | Retain cross-owner discovery and test misses; candidate retrieval does not establish truth |
| [Graphiti temporal model](https://github.com/getzep/graphiti) | Historical validity and provenance | C2/W1 state transitions | Human approval remains required; temporal storage does not fix C1's interpretation bug |
| [Hindsight observations](https://hindsight.vectorize.io/developer/observations) | Derived knowledge with supporting evidence | C2 property evidence; S2 incremental views | Reuse our existing records; evidence counts alone do not prove correctness |
| [Hindsight recall](https://hindsight.vectorize.io/developer/retrieval) | Multiple retrieval signals, reranking, separate search/token budgets, source expansion | R1 | Source expansion and independent source search are different experiments |
| [Hindsight knowledge pages](https://hindsight.vectorize.io/developer/knowledge-pages) | Purposeful page scope and incremental refresh | W1 | Keep deterministic publication and source-grounded decisions; no page-to-page evidentiary feedback |

These are bounded adaptations within the existing system. Whole-framework or
graph-database migration, automatic semantic merges, a default model switch,
and additional generic orchestration layers are outside this plan. Hindsight's
documented fuzzy entity matching is not adopted under our semantic guardrails.

## Coverage of the previous audit plan

| Previous area | Where remaining acceptance now lives |
|---|---|
| A — Benchmark integrity | E1, E2, V1 |
| B — Configuration | Preserve existing fixes; matched configuration/provenance in E2/V1 |
| C/D — Retrieval/workspace consistency | Preserve existing fixes; C3, R1, V1 |
| E/F/G — Errors, Engram, networking, UI races | Preserve existing fixes; C3, O1 and relevant regression tests |
| H/I — Extraction and temporal representation | C1, C3, E2 stage coverage, conditional R1 source experiment, V1 |
| J — Identity | C2; S1/S2 growth and invalidation tests |
| K — Page admission/organization | C2/C3, S2, W1, V1 |
| L — Truth scope | C1/C2, S1, V1 |
| M — Incremental consolidation | S1 cache inputs, S2, W1 |
| N — Retrieval quality | E2, R1, V1 |
| O — Scale | S1/S2/R1 measurements, V1 |
| P — Cleanup | E1 obsolete contracts, C3 integrity consistency |

**Next implementation action when resumed:** E1's rubric/current-contract cleanup
and preparation of the frozen comparison, followed by C1 and C2. Keep changes
small and validate them before combining optimization hypotheses.

## Historical implementation evidence

The following records describe earlier implementation and narrow validation.
They do not define the forward execution order or override the acceptance gates
above. Some intermediate failures below were fixed by later entries. The first
validated tranche was committed as `8139075`; subsequent work reached `01ac86d`.

### Implemented mechanisms and remaining acceptance work at the earlier checkpoint

| Area | Implementation in this change | Remaining work / acceptance gate |
|---|---|---|
| A. Benchmark integrity | Independent completion statuses; default QA block on incomplete LoCoMo encoding; invocation/config/code/model provenance; typed citation coverage; optional reference judgments; daily-driver timing/evidence/traces, strict judgment IDs, recorded native attempts, current transactional approval/retraction and transient-fact judging | Semantic scorer21 neutral trials and reporting/resume smoke passed; daily judge9/9. First full daily scenario exposed adapter and semantic failures; adapter regressions now pass. Longitudinal audit and comparable full quality/cost runs remain. Reference judging is not a source-grounding audit. |
| B. Configuration | Explicit overrides > requested TOML > dataclass defaults; missing requested files fail; full override validation before creating stores; one captured configuration for all benchmark cases/trials; effective QA/memory settings recorded and checked on resume | Command-path tests cover library, LoCoMo/MAB CLI and clients, daily-driver runs/trials, server runtime and Engram summary inheritance/overrides. Invalid strings and fractional/boolean budgets, edited/removed TOML files and changed-setting resumes are covered. |
| C. Retrieval consistency | Snapshot admission uses canonical ownership/tier and validates cited sources plus fact members; reselect once after owner/source/consolidation mutation, then typed error; missing provenance is an explicit integrity failure | Owner moves, consolidation, source retraction/deletion and repeated conflicts now tested. Recovery errors remain separately surfaced. |
| D. Workspace correctness | Revision-aware claim and source merges; canonical text/citation/status refresh on successful and failed tools; broken provenance clears stale evidence with an explicit error; whole-record budget and eight-operation history bounds | Source edits/deletions, citation promotion and stale replies now tested. Two browser component tests cover exact citation inspection, replaced text/status and elided failure history. |
| E. Errors and Engram | Retrieval errors reach HTTP 503 and tools; bounded uploads before parsing/copying; typed durable warning history; source admission freezes inputs; per-meeting operations and native-worker cancellation boundaries; deletion waits for resource release | Ten concurrency/recovery tests now cover active/queued deletion, repeated cancellation, upload cleanup, frozen admission, warning persistence and retryable file-deletion failure. Real device/network rollout remains a user-run check. |
| F. Private networking | Same-origin API/audio; allowlisted hosts; no wildcard CORS; loopback backend default; configurable Vite host with proxy; built UI mount; README deployment boundary | User-run Wi-Fi/Tailscale chat/audio/inspection checks. No authentication by explicit user preference. |
| G. UI races | Session-scoped chat drafts and pending requests; failed history loads preserve drafts and hide old transcripts; chat and wiki generation guards; correction reviews survive retries; shared selection/request scope for Engram and wiki; stale edit completions preserve current editors | Twenty-four component tests cover correction/evidence, Engram, chat and wiki request orders, including A→B→A switches, history failure/retry, concurrent session requests and stale mutation refreshes. Broader browser/device rollout remains unverified. |
| H. Extraction | Integrated the directly probed multiple-time contract and per-message timestamps described in I | Broader subject/citation/coverage gates remain open. Vague “recently” may remain text-only; one native run split a condition into a duplicate claim. No lexical repair or fixture vocabulary added. Daily-driver trials remain pending. |
| I. Temporal representation | Model-declared multiple temporal entries, exact citation IDs, distinct targets/roles, calendar-only arithmetic, unresolved vague/missing/overflow dates; schema 3 fresh stores (updated by identity review); user-confirmed reference-date review before saving relative corrections, with durable, stale-checked idempotent drafts; declared weekday relationships and recurring schedules | Direct metadata/encoding probes and three fresh-store temporal lifecycle runs completed; accepted weekday contracts30/30 extraction and30/30 correction, three native weekday lifecycles passed. Automatic correction-reference selection failed neutral and in-situ counterexamples and was rejected. Full semantic coverage, duplicate-condition lifecycle and organization gates remain open; small probes establish no general quality/cost improvement. |
| J. Identity scaling | Source-first discovery, separate exact human-review assignment, semantic candidates bounded to24 per subject across inferred types (declared speakers remain people-only), chunked changed-document embeddings and durable model/query reuse; source attribution sees resolved subjects without page/review metadata; page presentation receives only eligible described subjects; provisional identity matches retain pending review; explicit agent-chat user participants and a separately required declared-user output | Revised review sequence passed12 direct and12 native trials; larger-registry native12/12; six continuity scenarios across three builds retained identity/reviews and made zero generations on every third build. Required-user direct9/9 and native identity separation passed; one downstream placement counterexample remains. Cross-type and source-name follow-through passed24 direct boundary trials and12 source-reviewed native cases; required preferred titles passed12 direct cases. Raw native count11/12 includes one overly strict editorial-title assertion. Full longitudinal identity/coverage and growth-cost gates still apply. |
| K. Page admission and organization | Independent, cited admission for provisional subjects; actual per-entity section domains in native schemas; source ontology distinguishes bounded events from ongoing efforts; destinations require resolved source subjects; no-page human reviews exclude exact evidence/entity pairs and preserve other support; partial old-fact projection respects current placement | Direct15/15 admission and15/15 source-type trials, native15/15 admission trials passed. User-confirmed no-page scope passed12 direct and9 native checks. Separate source attribution now preserves described subjects independently of admitted pages; direct39/39 attribution/page sets, profile18/18 and final scoped-review9/9 native checks passed. Primary-page preference was38/39; occasional incidental page admission remains open. Page usefulness, successive-build event coherence and longitudinal source-to-wiki audit remain. |
| L. Truth scope | Global, evidence-backed comparison before owner presentation; exact per-candidate and per-pair decisions include same-batch and unplaced claims; current/persisted source-policy exclusions stay outside comparison; preserve both sides for review; approval invalidates overlapping reviews | 18 direct comparison,18 revised candidate and18 native pipeline trials passed. A daily scenario exposed an excluded-source leak, now covered by structural regressions. The retained older pilot-state failure passed3/3 independent native replays after that fix. Exact source reads and segment indexes are reused within each preparation; parity is verified at5000 shared-source claims. Broad semantic and growth-cost gates remain; bounded requests still scan admitted active history. |
| M. Incremental consolidation | Durable per-request reuse; persisted groups capped at12 canonical members; independent per-group text reuse; manual text retains exact evidence membership; native9/9 scenarios across27 builds and three persisted prose-reuse checks passed | Growing-store cost and longitudinal organization gates remain. Exact request reuse and bounded groups do not bound first-build history scans or every changed-input rebuild. |
| N. Retrieval quality | Complementary ordered selection and final global admission; strict tool argument schemas and exact source-ID checks; bounded exact source lines now accompany canonical records during selection, initial answering and follow-up search; revision-aware refresh retains current provenance | Direct source-backed selection27/27; native paired QA source review27/27 with sources versus19/27 claims-only. These neutral seeded stores isolate retrieval/QA, not extraction or corpus recall. Autonomous tools remain inconsistent; absent candidates, local pruning and large-corpus quality/cost gates remain open. |
| O. Scale | Indexed canonical lookups; changed-record vector updates with weight-digest invalidation; flat L2 index from10k records, probing all partitions |10k-claim/200-query measured index recall@20=100% for every query; vector median12.03ms→3.01ms. Indexed appends/deletes and weight/dimension changes tested. Broader ingestion/history costs and full retrieval/QA gates remain. |
| P. Cleanup | Public retrieval errors; config/network/architecture docs aligned with current contracts; retired work-unit/selection fields removed; database cleanup safely releases collector-thread resources while ordinary operations remain thread-affine | Removed the obsolete routing adapter/schema overlay; automatic references now replace exact successful claim scopes atomically, preserving manual decisions. Removed unused combined identity/review schemas and prompts; retained current source-first router/review tests and neutral probe inputs. |

### Earlier validation evidence

- Neutral complementary selection: first prompt failed all three no-support
  counterexamples; revised prompt and production schema passed 6/6 calls.
  Runs: `benchmark_runs/remediation-selection-probes-20260915T152626`,
  `...152753`, `...152926`.
- Production retrieval replay: `benchmark_runs/remediation-retrieval-replay-20260915T154449`.
  Read-only SQLite backup and copied derived index from the old sample3 store;
  three trials of the previously identified question 28. Education/infrastructure
  evidence survives in all three. Retrieval 2.80, 2.46, 1.92 seconds.
  Baseline question retrieval construction was 11.87 seconds. This is a narrow,
  warm, unmatched-time comparison; no revised QA answer was generated, and the
  baseline's encoding failures remain in the copied store. Do not extrapolate
  these timings or claim a benchmark score improvement.
- The first replay's production retrieval succeeded, but the harness attempted
  to print a nonexistent `context` property; corrected to `rendered_context`
  and reran into a new directory. Original result retained.
- Structural suite reached 475 passed, 87 integration tests deselected before
  the final config/Engram additions; final results are recorded in DEVLOG.
- UI build and lint passed after fixing a synchronous-effect lint failure;
  existing bundle-size warning remains. Five correction-editor component tests
  were subsequently added; other UI race acceptance remains outstanding.

### Historical follow-through findings

Latest diagnostic run `audit-daily-v2-source-grounded-20260917` stopped after three
checkpoints with complete source review packs. Its full-run acceptance is open:
identity continuity and name fidelity, independent page usefulness, stale unnamed
state, and clean fact prose failed despite earlier narrow probes. Benchmark
lexical metrics now explicitly require source review and cannot assert release
readiness. See DEVLOG for retained failures, source packs and validation.

Required speaker assignments now pass21 direct and9 native binding checks with
zero retries. The native same-name cases still expose a separate duplicate
canonical-user identity; source-role context must reach the matching stage.
Quoted-name experiments remain unaccepted and outside production.

Follow-through: source-role context now fixes the duplicate canonical user in all
three native counterexamples (12direct/9native identity checks), but downstream
attribution still omits the user's own part of that compound statement. Truth
comparison now receives current-build references (12native checks), and prose
rendering omits unused local claim labels (27native builds; persisted reuse holds).
The naming/reasoning proposals remain rejected; full longitudinal gates stay open.

Further follow-through: assertion-first attribution passed42 direct checks and9
native routing cases, including all3 formerly omitted named-user statements.
Removing inferred page categories from identity matching passed30/30 direct
identity decisions (paired control28/30) and12/12 native boundaries. Long-context
service spelling still fails; page admission/section choice still vary. These
changes pass their narrow acceptance gates, not full H–M or longitudinal acceptance.

The earlier numbered rollout has been replaced by E1–O1 above. In particular,
sample9 is regression data, the full set of familiar repeats no longer blocks a
held-out evaluation, and absolute performance targets remain provisional until
a matched baseline exists. User-run server/device checks remain distinct from
finite tests and benchmarks.

### Earlier follow-through validation

495 structural tests passed,87 integration tests deselected. Native `audit-provenance-tiny-v1` completed one source session and QA in15.50s, with all seven model/embedding timing rows linked and no failed attempts. This is a reporting smoke test, not a full quality comparison. See DEVLOG for failed semantic probes and remaining gates.

Temporal follow-through: three native reviewed-correction runs completed in
48.26/45.62/45.96 seconds, with encoded/corrected/final snapshots and exact model
requests retained. Final snapshots have no extraction/publication backlog.
One run retained a separately extracted old payment condition after correction
of the delivery claim, and section placement drifted between builds. These are
open H/K/L findings, not a passed longitudinal quality gate. See DEVLOG for exact
paths, per-call costs, structural/component results, and rejected experiments.
