# Mycelium Wiki-Quality and Architecture Audit — 2026-08-13

## Executive verdict

Mycelium has a strong and distinctive foundation:

```text
immutable source evidence
    → source-linked atomic claims
    → explicit semantic decisions
    → deterministic, rebuildable wiki views
```

That foundation is worth preserving. Exact segment provenance, plaintext canonical records, reviewable
reconsolidation, typed entity pages, and deterministic Markdown projection are all better aligned with a
trustworthy personal memory system than opaque rolling summaries.

The current wiki is not yet reliable enough to be a daily-driver picture of what the system knows. Its
Markdown is concise, but much of that concision comes from omission rather than successful organization. In
the exact-code Daily Driver run performed for this audit, the system produced useful Lantern, Priya, Luis,
and You pages, but it:

- kept the obsolete September 22 pilot date authoritative and failed to extract the September 28 correction;
- omitted the Family Oral History and Grandmother entities;
- put project and family-project facts on You;
- terminally classified many important project decisions, research findings, status updates, and completed
  work as `source_only`;
- put semantically equivalent consent and build-deadline claims into Needs Review as proposed supersessions;
- used coarse or incorrect sections and failed to expose several person–project relationships;
- displayed relative dates such as “next Thursday,” “by Friday,” and “tomorrow” even though normalized dates
  exist in the claim artifacts.

The main quality ceiling is therefore not Markdown formatting or retrieval. It is the semantic control plane
between claims and pages. Retention, entity discovery, ownership, truth resolution, fact grouping, and
presentation are currently spread across overlapping mechanisms, some of which make semantic decisions using
string similarity despite the repository's stated design rules.

The most impactful next step is to make claim scope revisable and typed, then replace the overlapping
deduplication/reconsolidation/fact-grouping mechanisms with one owner-scoped fact-resolution plan. Section
selection and current-versus-history state should be outputs of that semantic plan; Markdown should remain a
deterministic projection.

## Scope and baseline

This audit covers the current working tree, not only `HEAD`. The checkout was based on commit `32eff4a` and
contained a large in-progress change set (25 tracked files changed, approximately 2,575 insertions and 570
deletions) plus the new fixture and planning files. I did not modify or discard any of that work.

Reviewed areas included:

- source ingestion and claim extraction;
- short-term queueing and Dream orchestration;
- cohort entity discovery and claim ownership;
- deterministic section mapping;
- reconsolidation and fact synthesis;
- entity/fact curation and organization proposals;
- wiki materialization, retrieval-facing rendering, and the Wiki UI;
- artifact persistence and auditability;
- current tests, prior audits, design documents, and the Daily Driver fixture.

Verification performed:

- `uv run pytest -q`: **240 passed, 2 skipped**;
- default Ruff checks: **passed**;
- optional Ruff complexity checks: **37 findings**, including `DreamProcess.run`, temporal normalization,
  retrieval, materialization, and organization paths;
- `uv run mypy mycelium`: blocked by the untyped `frontmatter` dependency rather than code errors, so the
  project does not currently have a clean reproducible type-check command;
- `npm run build`: **passed**, with an 829 kB JavaScript chunk warning;
- `npm run lint`: **failed with 11 errors and 6 warnings**, primarily React effect/callback issues;
- a clean full Daily Driver run against the current checkout and `gemma4:12b`, written to
  `benchmark_runs/daily-driver-v1-audit-20260813`.

No server process was started or stopped.

## What is working well

### 1. The canonical/derived boundary is fundamentally sound

Sources and claims remain canonical, while pages are rebuildable views. `MemoryClaim` retains exact
provenance (`mycelium/artifacts.py:101-124`), and `ConsolidatedFact` retains all member claim IDs
(`mycelium/artifacts.py:268-303`). Page materialization consumes those records instead of rewriting source
memory (`mycelium/materialization.py:153-238`). This is the right authority model.

### 2. Provenance and inspectability are excellent

Generated fact records expose canonical owner, member claims, source IDs, exact segment IDs, synthesis
origin, confidence, and rationale (`mycelium/materialization.py:491-575`). The Wiki UI can expand from a fact
to its scope decision, canonical claims, and source segments. The Daily Driver run retained an evidence-linked
candidate for every one of the 45 gold claims, even when the extracted semantics were incomplete.

### 3. Structured cohort planning is a meaningful improvement

The current planner requires exact claim and participant alias coverage and validates all cited references
(`mycelium/consolidation.py:91-158`). Participant occurrences are resolved explicitly to You, an existing
Person, or a declared Person candidate. This produced Priya and Luis correctly in the current run without
fixture vocabulary or deterministic name matching in the main routing path.

### 4. The sparse typed page vocabulary is useful

The seven page types and their ordered section contracts are understandable and appropriate for a personal
wiki (`mycelium/models.py:5-84`). Empty sections disappear. The page taxonomy is presentation metadata rather
than the retrieval ontology, which is consistent with the project's current direction.

### 5. Reconsolidation no longer rewrites pages

Contradictions and supersessions are pairwise claim proposals; approval updates canonical claim state and
regenerates derived pages (`mycelium/reconsolidation.py:262-367`). This now aligns with the source-grounded
architecture, even though candidate selection and classification still need work.

### 6. Several older audit concerns are resolved

- LLM INFO logs contain metadata and sizes rather than full prompts/responses, and the in-memory call log is
  bounded to 100 records (`mycelium/ollama.py:20`, `mycelium/ollama.py:700-758`).
- Web tools use the async Ollama client (`mycelium/ollama.py:362-371`).
- Repository-wide `git add -A` behavior is gone.
- The project now has an MIT license.
- No production Daily Driver or LoCoMo entity vocabulary was found in the active cohort-routing mechanism.

## Fixture effectiveness review

### Exact-code run summary

The run's automated diagnostics reported:

| Layer | Result |
| --- | ---: |
| Claim-bearing source segments marked covered | 41 / 41 |
| Gold claims with an evidence-linked generated candidate | 45 / 45 |
| Provisional semantic claim matches | 33 / 45 |
| Required entities present | 4 / 6 |
| Extra entities | 0 |
| Provisional final wiki facts represented | 15 / 29 |
| Active generated claims placed/rendered | 30 / 65 |
| Final pages | 4 |

The similarity-based claim and fact counts are diagnostic only. Some visible facts are missed by the matcher,
and a fact appearing on the wrong page is not a quality success. The actual pages and claim dispositions are
more informative.

Final claim dispositions were 30 placed, 32 `source_only`, 2 deferred, and 1 assistant claim excluded. The
system created You, Lantern, Priya Raman, and Luis Ortega. Family Oral History and Grandmother were missing.

### Page-by-page quality

#### Lantern

Strengths:

- short and easy to scan;
- correctly identifies Lantern and its local desktop direction;
- captures the pilot metrics, WhisperX decision, local-storage requirement, and WhisperX benchmark result;
- retains exact evidence in structured page metadata.

Problems:

- September 22 remains the sole authoritative next deadline even though September 28 is the current date;
- there is no People & Organizations section or link to Priya, Luis, or Maya's role;
- project objective and requirements are placed under Decisions;
- prototype features, consent blocker/status, bug history, review date, and other useful status/history are
  absent;
- WhisperX benchmark evidence is placed in Overview instead of Research & References or Timeline.

#### Priya Raman

Strengths:

- useful compact record of recruitment/evaluation responsibilities and diarization concern;
- meeting encounter is source-grounded;
- no unrelated personal information is invented.

Problems:

- the Lantern role appears under Relationship to You rather than Shared Projects;
- there is no Lantern link;
- the page says Priya cannot recruit by September 22 but omits the later completion of recruitment and the
  evaluation rubric, leaving her current status misleading.

#### Luis Ortega

Strengths:

- correctly captures ownership of the local transcription and WhisperX packaging work;
- remains concise and source-grounded.

Problems:

- there is no Shared Projects link to Lantern;
- two claims that normalize to the same September 11 deadline are withheld under Needs Review because one
  was classified as superseding the other rather than supporting it;
- normalized dates are not displayed.

#### You

Strengths:

- the profile is sparse and correct;
- Memory Map provides an understandable entry point to known entities;
- it avoids copying every fact from linked pages.

Problems:

- it contains Family Oral History details because that Project was never created;
- it contains Lantern requirements, decisions, prototype tasks, and technical follow-ups that belong on the
  Project page;
- the Memory Map and Recent Changes repeat the same three links, and Recent Changes does not describe changes;
- prose alternates between “The user,” “The User,” and “User” despite a configured Maya Chen alias;
- two equivalent consent claims are withheld in Needs Review while a third equivalent consent fact is already
  authoritative elsewhere on the same page;
- page confidence is `1.0` despite these omissions, stale facts, and unresolved proposals.

### The coverage metric masks a critical extraction failure

The source sentence:

> Priya cannot recruit the pilot teams by September 22, so move Lantern's first pilot to September 28.

produced only the claim that Priya could not recruit by September 22. Because that one claim cited the source
segment, the entire segment counted as covered. The state-changing September 28 decision was never extracted,
so reconsolidation had no incoming correction to review.

This demonstrates that segment accounting is not proposition accounting. A “41/41 covered” result can still
omit one of multiple independent assertions in a segment. This is more important than improving benchmark
answer wording or token-overlap scores.

### `source_only` is the dominant recall failure

The cohort planner sent 32 of 65 active claims to `source_only`. Appropriate exclusions included the dentist
appointment, TranscribeCloud pricing, Northstar data awaiting retraction, and a cosmetic dark-mode ticket.
However, the same disposition also removed:

- the desktop-not-browser decision and the sensitive-client rationale;
- local transcription and WhisperX research evidence;
- the oral-history interview time and place;
- Priya's completed rubric and recruitment;
- the Lantern prototype's speaker-correction and source-link features;
- the consent release blocker and LANTERN-42 resolution;
- the September 28 build-readiness status;
- several research and local-only decisions.

These are not edge cases. They are core project knowledge. A system whose wiki goal is “as concise as possible
without omitting information” should compress these claims into facts or history, not terminally remove them
from the wiki layer.

### Current-history handling fails the fixture's most important truth test

The September 28 correction failed before reconsolidation, while the September 22 claim had no useful open
predicate or stable slot. Separately, the two repeated consent claims and the two equivalent build-deadline
claims were classified as supersessions even though each pair expressed the same state. The result is the
worst combination for a personal daily driver: an obsolete date remains authoritative while repeated support
for true facts creates unnecessary uncertainty.

## Architectural and code-quality findings

Findings are ordered by their expected effect on trust and wiki quality, not by ease of implementation.

### P0 — Retention and page scope are conflated

`NoncanonicalScopeAssignmentOutput` combines `deferred` and `source_only` in the same routing decision
(`mycelium/structured_outputs.py:171-181`). Both become a nullable `ClaimRoute`; both are persisted as a
`ClaimPlacement(status="deferred")` (`mycelium/consolidation.py:528-539`). A `ClaimScopeDecision` has no field
that distinguishes the two (`mycelium/artifacts.py:225-252`). Only the claim's Dream disposition retains the
difference.

This creates several conceptual problems:

- “useful but not yet placeable” and “valid but intentionally excluded from the wiki” share a placement type;
- organization review scans all deferred placements, including `source_only`, and can propose putting them
  back into the wiki;
- `memory_tier()` calls `source_only` claims canonical even though they have no canonical page/fact placement
  (`mycelium/artifacts.py:902-910`);
- the same LLM call must decide both long-term value and page ownership;
- a free-form reason is the only explanation of why valuable evidence disappeared.

The extraction stage already rejects conversational debris and excludes assistant/system assertions
structurally. For admitted user and meeting claims, the normal outcomes should be canonical ownership or
temporary deferral. Source retention should be a separate, typed policy based on provenance and explicit
source handling—not an open-ended page-routing judgment.

### P0 — Scope decisions are effectively terminal

Dream builds evidence only from claims in the short-term queue (`mycelium/dream.py:350-394`). That queue
contains pending, failed, and deferred claims, but not claims previously routed to You or marked
`source_only` (`mycelium/artifacts.py:880-900`). Once Lantern or Family Oral History becomes clear, earlier
decisions are not reconsidered.

Normal Dream runs reopen at most 24 deferred claims using token overlap, exact slot equality, exact predicate
equality, and free-form `about` strings (`mycelium/short_term.py:74-149`). This both violates the semantic
decision policy and fails to revisit already routed/source-only facts.

The observed consequence is predictable: the missing Family Oral History page leaves interview facts on You,
and early Lantern requirements cannot migrate from You/source history after Lantern matures. Append-only scope
audits imply that scope should be revisable; the implementation does not yet realize that model.

### P0 — Truth resolution is split across overlapping mechanisms

Today, relatedness and equivalence are decided in at least four places:

1. `ClaimReconciler` fuzzily merges extracted claims using `SequenceMatcher`, surface entity equality, and
   predicate equality (`mycelium/artifacts.py:1367-1424`).
2. `ClaimReconsolidator` selects candidates using normalized free-form `about` strings, owner, slot, predicate,
   and temporal-role equality, then asks the model for a pairwise relation
   (`mycelium/reconsolidation.py:132-259`).
3. `FactConsolidator` asks another model call to group compatible claims and synthesize presentation text
   (`mycelium/facts.py:209-253`).
4. Legacy projection code still contains token-overlap display deduplication and main/detail selection, though
   almost all of it is now production-dead (`mycelium/projection.py:86-342`).

These stages answer overlapping semantic questions with different evidence and different failure behavior.
The fixture's false consent/build supersessions are a concrete symptom. The architecture should have one
intended owner-scoped fact-resolution mechanism that groups support, identifies genuine conflicts or
replacements, assigns current/history state, and creates review proposals.

### P0 — Semantic string matching remains in production decisions

The main cohort router no longer hard-codes fixture terms, which is good. Other production paths still violate
the same design principle:

- deferred reactivation uses lexical overlap and exact free-form labels (`mycelium/short_term.py:122-149`);
- reconsolidation candidate selection normalizes and intersects free-form entity strings
  (`mycelium/reconsolidation.py:132-175`, `mycelium/reconsolidation.py:253-259`);
- extraction deduplication uses fuzzy text similarity (`mycelium/artifacts.py:1367-1424`);
- `OrganizationAuditor` creates merge and assignment proposals from normalized title/alias/`about` string
  equality (`mycelium/organization.py:480-543`);
- encoder validation uses regex entity occurrence checks and may rewrite subjectless canonical text with
  templates such as “User reported that …” (`mycelium/encoder.py:381-456`).

Organization proposals are still semantic decisions even when a human must approve them. Retrieval may use
FTS/BM25 and lexical matching; identity, ownership, contradiction, consolidation, and organization may not.
These paths should be removed rather than expanded with more aliases or thresholds.

### P1 — Claim type is too coarse to choose a human-facing section

`default_section()` maps only `(entity_type, claim_type)` to a section
(`mycelium/wiki_schema.py:8-77`). It cannot distinguish:

- a project objective from a decision;
- a requirement from a decision;
- a resolved issue from a current state;
- a project role from a generic relationship when extraction misses one open predicate;
- current truth from historical context.

The cohort prompt is shown the full section contract, but its output cannot select a section. The fact
consolidator receives the already-fixed section and is forbidden to correct it. Section semantics belong on
the consolidated presentation fact, chosen explicitly from the page's typed schema by the semantic planner
and then deterministically validated.

### P1 — The canonical entity model is still surface-form based

Claims retain free-form `about` strings instead of stable entity references. Ownership decisions produce an
owner and vague linked IDs, but do not persist subject/object/reference roles back into a semantic claim layer.
Candidate creation rationale and participant-resolution confidence/reason are not stored on the entity or
encounter record (`mycelium/artifacts.py:168-198`, `mycelium/artifacts.py:255-265`). This limits:

- reliable rerouting when an entity matures;
- relation-driven Person/Project views;
- contradiction candidate selection;
- transparent identity review;
- distinction between knowing an entity exists and deciding it deserves a page.

Entity identity and page admission are also the same event. Every active entity gets a page. A durable entity
registry should be able to retain a resolved mention or provisional entity before it has enough useful facts
to materialize a page.

### P1 — Fact synthesis silently falls back and its failures disappear

When fact synthesis or grounding fails, `FactConsolidator` silently emits one display fact per claim
(`mycelium/facts.py:245-253`). `DreamProcess` never copies `fact_result.failures` into the Dream report
(`mycelium/dream.py:228-240`, `mycelium/dream.py:334-345`). This is exactly the kind of fallback path the
repository guidance warns against: the intended synthesis mechanism can fail while the run reports success
and a noisier page appears.

The fallback should be removed. A failed fact-resolution scope should preserve the previous derived page,
leave the new claims visibly pending, and report the exact failed contract stage. It should not invent a
second presentation behavior.

### P1 — Temporal data is normalized but not compiled into the wiki

Relative-time normalization is extensive, but materialization uses fact creation time for ordering and does
not add normalized temporal qualifiers (`mycelium/materialization.py:491-575`). Timeline items are therefore
not ordered by event time, and page text can remain permanently relative to an old meeting.

The older projection module contains temporal qualifier code, but the current fact renderer does not use it.
This is both dead-code drift and a lost user-facing capability. The page compiler should render normalized
dates, preserve the original wording in evidence metadata, and order timelines by normalized valid/event time.

### P1 — Confidence and recency metadata are misleading

Page confidence is the mean confidence of owned active claims, or `1.0` when there are none
(`mycelium/materialization.py:380-405`). It does not account for source-only omissions, deferred claims,
pending conflicts, stale current facts, extraction partiality, or encounter-only pages. In the fixture, every
page showed `1.0` despite serious quality failures.

Recent Changes is just the five entities with the latest `updated_at` value
(`mycelium/materialization.py:591-610`). It often duplicates Memory Map and says nothing about what changed.
Either derive meaningful coverage/freshness and actual fact diffs, or remove these signals until they are
honest.

### P1 — Manual “correction” edits only presentation text

The Wiki UI labels a fact-text edit as “Manual wiki fact correction,” but
`FactCurationService.edit()` changes only `ConsolidatedFact.text` and sets confidence to `1.0`
(`mycelium/organization.py:321-339`; `ui/src/components/WikiExplorer.tsx:167`). The canonical claim remains
unchanged and can still drive reconsolidation or reappear after later curation.

Presentation editing is useful, but it must be labeled as presentation editing. A factual correction needs a
claim-level operation with source/user provenance and explicit supersession review.

### P2 — Failure accounting and persistence are not transactional

A routing failure does not keep its source in `pending_source_ids`; the source can be marked consolidated while
its claims remain retryable. The audit run demonstrated this at `cp6_wrong_import`: all four claims failed
routing and the source was still reported completed. A later Dream recovered them, but the intermediate audit
record was misleading.

Materialization persists entities, placements, fact deletions, facts, pages, index, log state, and the Dream
audit in separate operations (`mycelium/materialization.py:126-145`; `mycelium/dream.py:280-347`). A process
failure can leave a partial cross-file state. `ConsolidatedFact` supports `retired`, but normal replacement
deletes the record instead of retaining that lifecycle state.

For a single-user local app, a small SQLite operation journal or staged manifest would be sufficient. Markdown
and JSON can remain canonical and transparent.

### P2 — The current cohort call is unbounded

Dream sends every ready claim through one dynamically expanded schema with an 8,192-token output budget
(`mycelium/consolidation.py:91-113`). There is no hard bound on queued claims, no Dream context-budget planner,
and candidate/support arrays have fixed limits. A large manual backlog can fail as one batch. The current
server usually runs near the threshold, but the library API permits arbitrarily large manual Dreams.

Bounded cohorts should be a first-class semantic unit with persisted continuity, not an emergency fallback
after a large plan fails.

### P2 — Large modules and legacy paths obscure the intended mechanism

Current sizes include:

- `mycelium/artifacts.py`: 1,435 lines;
- `mycelium/ollama.py`: 758 lines;
- `server/api/memory.py`: 754 lines;
- `mycelium/materialization.py`: 667 lines;
- `mycelium/organization.py`: 592 lines;
- `mycelium/consolidation.py`: 539 lines;
- `mycelium/dream.py`: 472 lines.

Size alone is not a defect, but these files mix distinct authority boundaries. `artifacts.py` contains domain
records, filesystem persistence, temporal parsing, query parsing, and fuzzy claim reconciliation. Dream still
has a 104-statement orchestration method. The server and direct-library session paths render memory context
differently; only the library path deduplicates shared project roles. Old entity-discovery/placement schemas
and prompts remain test-covered but production-unused, as does most of `projection.py`. The
`main_page_claim_limit` setting is documented and parsed but unused.

Decomposition should follow the final pipeline boundaries after the semantic redesign, not precede it as a
mechanical cleanup.

### P2 — Tests strongly cover mechanics but not semantic behavior

The 240 passing tests provide good coverage of exact alias contracts, persistence, manual curation, review,
and deterministic rendering. However:

- most LLM behavior is mocked with hand-authored ideal responses;
- obsolete discovery/placement contracts remain directly tested;
- a test explicitly codifies title/alias string matching for deferred assignment;
- the Daily Driver tests validate fixture consistency, not generated output against lifecycle gates;
- there are no metamorphic tests that rename every person/project and paraphrase the sources;
- no test fails when a “covered” segment omits one of two propositions;
- fact-resolution failures are not asserted in Dream reports;
- current/history correctness and cross-page ownership are not enforced end to end.

The fixture rubric asks for per-dimension metrics, gates, ownership confusion, duplicate facts, retrieval
required/forbidden facts, and qualitative page diffs. The runner currently emits useful heuristics and
snapshots, but explicitly does not execute QA probes or most rubric gates. It is not yet an automated product
specification.

### P2 — Documentation has drifted across several architectures

`DESIGN.md` still describes LLM page routing, old claim partitioning, and no backend lifecycle scheduler even
though current production uses page FTS, consolidated facts, and a lifecycle task. `planning/memory-information-flow.md`
describes an older raw-log/page-rewrite pipeline. README's prose is closer to the current implementation, but
its sample queue threshold is 50 while code and `mycelium.toml` use 20, and it documents the unused
`main_page_claim_limit`.

This drift makes it hard to tell which mechanism is intended and increases the risk of reviving obsolete
paths.

## Non-wiki release blockers found during the full audit

These do not change the wiki roadmap, but they remain important for the stated daily-driver/LAN use case:

- FastAPI has wildcard CORS, no authentication, destructive memory endpoints, and a `0.0.0.0` default bind
  (`server/main.py:29-52`; `server/api/memory.py:507-514`). LAN exposure of recordings and personal memory is
  unsafe in this state.
- `.llm-debug/` is not generally ignored. It currently exists as an untracked directory and structured debug
  dumps can contain complete prompts, source evidence, and responses (`mycelium/ollama.py:590-685`). Only two
  individual historic files are listed in `.gitignore`. Any personal store/debug-output convention should be
  ignored by default.
- The UI build passes, but lint does not. CI should have one documented Python check set and one clean UI
  check set before changes are treated as release-ready.

## Supplemental LoCoMo end-to-end check

After the static and Daily Driver audit, I ran a fresh end-to-end LoCoMo `conv-30` comparison using
`gemma4:12b`, all 19 sessions, all 105 questions, per-batch Dream, and retained retrieval contexts. The run
did not use `--frozen-store` or `--replay-store`; it rebuilt the memory from the original conversation and is
stored at `benchmark_runs/locomo-mycelium-convo-2-current-e2e-20260813`.

The comparison checkpoint was the prior fresh full-session run
`benchmark_runs/locomo-mycelium-convo-2-taxonomy-final-e2e-20260810`:

| Metric | Prior checkpoint | Current | Change |
| --- | ---: | ---: | ---: |
| Overall | 0.5620 | 0.5562 | -0.0057 |
| Category 1 | 0.3963 | 0.3475 | -0.0488 |
| Category 2 | 0.5987 | 0.5553 | -0.0434 |
| Category 4 | 0.3654 | 0.4351 | +0.0696 |
| Category 5 | 0.9583 | 0.8750 | -0.0833 |
| Mean QA input | 5,479 tokens | 4,337 tokens | -20.8% |

The `-0.0057` aggregate movement is not a precipitous regression and is smaller than the `0.02` variance
tolerance used by the retrieval iteration protocol. Per-question movement was also sparse: 75 answers were
within 0.01 of the prior score, 12 improved, and 18 declined.

The retained evidence diagnostics are more informative for architecture work:

| Layer containing all labeled evidence | Rate | Mean evidence recall |
| --- | ---: | ---: |
| Canonical source | 100.0% | 100.0% |
| Extracted claims | 70.5% | 74.9% |
| Materialized wiki | 64.8% | 68.7% |
| Final retrieved context | 75.2% | 78.2% |

Questions with complete retrieved evidence scored 0.6218 on average, versus 0.3569 when evidence was
incomplete. Category 1 remains the clearest retrieval/representation failure: eight of its eleven questions
were missing at least one cited turn in final context. Typical losses required accumulating several facts,
such as all ways Gina promoted her store, every event Jon used to promote his venture, or all facilities and
services his studio offered. The source layer retained every cited turn, so these are downstream claim,
fact/page, and retrieval-composition losses rather than ingestion loss.

The qualitative answers also reinforce two cautions about treating the headline score as truth:

- Two category-5 answers penalized as hallucinations were directly supported and useful: “a temp job” for
  Jon's temporary work and “a trophy” for what Gina received from a dance contest. Giving those technically
  correct answers credit would raise the aggregate to approximately 0.5753. By contrast, answering a question
  about “Jon's store” with a generic statement about his business was a genuine tangential-answer failure.
- Several low-scoring temporal answers returned faithfully retrieved relative expressions such as “last
  week,” “yesterday,” and “next month” instead of resolving them against the source conversation timestamp.
  The wiki itself also displayed these unresolved expressions. This is a real daily-driver defect even where
  the underlying evidence was present, and it independently confirms the temporal-compilation finding above.

The generated view was compact but not well consolidated. Retrieval loaded only the Jon and Gina Person
pages, plus the short-term page on 99 questions. The Person pages contained useful facts, but repeated
near-equivalent ownership and goal statements, retained relative dates in Timeline, and accumulated 14 Jon
and six Gina items under Needs Review. The short-term page held eight overlapping dance-studio claims. This is
consistent with the Daily Driver result: current code preserves inspectable source evidence and can answer
many questions, but the semantic control plane is not yet grouping, resolving, and compiling that evidence
into a concise authoritative wiki.

## Recommended implementation roadmap

### Milestone 0 — Make the evaluation loop authoritative

Do this before another large semantic change.

**Implemented 2026-08-13.** The Daily Driver runner now emits independent artifact-level dimensions,
declarative hard gates, checkpoint diffs, proposition completeness, ownership/duplication/page diagnostics,
and retrieval plus post-answer semantic probe results. It supports extraction-only replay and isolated
multi-trial runs, and the fixture suite now includes renamed/paraphrased and unrelated-domain transfer cases.
See the corresponding Devlog entry and fixture README for the exact protocol. These changes make failures
visible; they do not claim that the current memory implementation passes the gates.

1. Extend the Daily Driver runner to emit the rubric's structured dimensions and hard gates rather than one
   fact-similarity summary.
2. Evaluate owner, linked entities, section, lifecycle state, provenance, duplication, and forbidden facts
   directly from artifacts.
3. Add an explicit proposition-completeness diagnostic for multi-assertion segments; do not treat segment
   citation alone as semantic coverage.
4. Use frozen extraction for ownership/fact/presentation iterations, then run at least three end-to-end trials
   for accepted candidates to expose model variance.
5. Add a renamed/paraphrased scenario and at least one unrelated domain scenario. The same invariants should
   pass without new prompt vocabulary or production rules.

Acceptance condition: the benchmark can identify the stale pilot date, You contamination, missing Family
project, false supersession proposals, and source-only loss as separate failures without relying on reference
wording.

### Milestone 1 — Separate retention, identity, and revisable scope

This is the highest-impact wiki-quality change.

**Implemented 2026-08-13.** Ownership no longer exposes `source_only`; source/extraction exclusions use
typed retention records with closed reasons; entity records distinguish provisional identity from a
materialized page; entity creation, participant resolution, structured claim endpoints, and scope cohorts
are persisted; and newly materialized identities trigger an explicit evidence-neighborhood scope revision.
The lexical deferred-neighbor and `OrganizationAuditor` proposal paths were removed. Daily Driver replay
showed the intended recall improvement (47 placed claims versus 30 at the audit baseline, with no fixture
`source_only` segment rendered) and a much fuller Lantern page. It also showed that the semantic model still
misses Family Oral History/Grandmother in some runs and may leave person/project links incomplete; those are
fixture-visible follow-ups, not hidden fallbacks. Source retraction remains deliberately outside this
milestone.

1. Remove `source_only` from the model-authored ownership choice for admitted user/meeting claims. The ownership
   planner chooses an entity or `deferred`; structurally excluded assistant/control/tool material gets a
   separate typed retention record before routing.
2. Give non-wiki retention a closed reason enum and provenance policy. It must be inspectable and must not
   masquerade as a deferred placement or canonical memory tier.
3. Persist structured entity references for each claim—at minimum subject, object/value entity, contextual
   entity, and canonical owner IDs—while preserving extracted surface mentions.
4. Persist entity-creation and participant-resolution decisions, support, confidence, and review state.
5. Separate “known/resolved entity” from “materialized page.” A provisional entity or mention may exist before
   it has enough durable facts for a page.
6. Make scope revision first-class. When a candidate becomes an entity, re-plan prior claims in its persisted
   evidence neighborhood, including claims routed to You or excluded from page presentation. Select that
   neighborhood from explicit source/cohort/entity-reference records, never token overlap.
7. Remove lexical `OrganizationAuditor` assignment/merge proposals and lexical deferred-neighbor selection.

Acceptance conditions:

- Family Oral History and Grandmother emerge without fixture vocabulary;
- family-project facts leave You once the Project exists;
- earlier unnamed Lantern facts migrate to Lantern after its identity matures;
- Priya/Luis/Lantern relations use stable IDs and render on both intended endpoints;
- every admitted claim is either in a fact, in a typed history/reference record, under review, or explicitly
  deferred—never silently pruned by a free-form value judgment.

### Milestone 2 — Unify truth resolution, fact grouping, and presentation semantics

Replace the current fuzzy `ClaimReconciler`, pairwise `ClaimReconsolidator`, and bucket-level
`FactConsolidator` semantic overlap with one owner-scoped `FactResolutionPlan`.

For all affected claims and existing facts for one owner, the plan should return exact claim coverage with:

- support/equivalence groups;
- additive facts;
- genuine contradiction or replacement relations;
- current, history, superseded-history, or needs-review state;
- one typed section key from the owner's schema;
- concise entailed display text;
- stable linked entity roles;
- confidence and rationale.

Deterministic code should validate IDs, exact coverage, provenance, allowed sections, temporal/quantitative
anchors, active lifecycle, and relation cardinality. It should not decide semantic equivalence from strings.
Conflicts and replacements still create human-review proposals. Equal normalized dates should not be accepted
as a replacement of one another. A rejected plan should leave previous pages intact and new claims visibly
pending; there should be no singleton synthesis fallback.

Acceptance conditions:

- September 28 becomes a reviewable replacement and then current truth; September 22 moves to history;
- repeated consent/build claims consolidate as support without false review;
- metrics appear under Objective, constraints under Requirements & Constraints, resolved issues under Timeline,
  and project roles under People & Organizations/Shared Projects;
- synthesis failures appear in Dream reports and do not silently change presentation behavior.

### Milestone 3 — Compile genuinely useful pages from resolved facts

Once semantic ownership and truth state are reliable, improve deterministic presentation:

1. Render normalized dates and sort timelines by semantic time, retaining original relative wording in evidence.
2. Use entity-aware display language so You does not alternate among “User” variants. Prefer concise
   subject-elided bullets or the configured display name without rewriting canonical claims.
3. Keep You focused on profile, cross-cutting preferences, actual priorities/roles, and navigation. Project
   requirements and tasks belong on Project pages.
4. Derive stakeholder, shared-project, and relationship views from typed entity relations.
5. Group Memory Map by page type. Replace Recent Changes with actual fact-level diffs, or remove it.
6. Make provenance available as compact footnotes/links in Markdown as well as expanded UI metadata.
7. Replace or remove the current confidence number. A future score should reflect source support, unresolved
   conflict, extraction completeness, age/currentness, and scope confidence—not the mean of model claim
   confidences.

### Milestone 4 — Add canonical correction and source retraction

This remains the next trust milestone after the semantic model:

1. A user correction creates a user-authored source/claim and a reviewable replacement relation.
2. Fact-text editing is explicitly presentation editing, not correction.
3. Source retraction tombstones the source, removes support from claims, retracts claims with no remaining
   support, re-resolves affected facts, and regenerates pages and disposable indexes.
4. Audit tombstones remain inspectable while ordinary wiki/retrieval paths cannot expose retracted content.

The Daily Driver Northstar gate should become executable at this milestone.

### Milestone 5 — Consolidate the code around the final architecture

After the new records and authority boundaries stabilize:

- split artifact models, filesystem storage, temporal normalization, and semantic resolution;
- decompose Dream into explicit prepare → scope → resolve facts → stage → commit → audit stages;
- split the memory API into inspection, lifecycle, curation, and review routers;
- make direct-library and server prompt rendering use the same implementation;
- delete obsolete entity-discovery/placement prompts and schemas, legacy projection compaction, dead routing
  index code, and unused configuration;
- add a small operation journal/staged commit for cross-file consistency;
- fix UI lint and document one reproducible check suite;
- secure the API and ignore sensitive debug/store outputs before recommending LAN access.

## What not to do next

- Do not add more fixture phrases, aliases, regexes, token-overlap thresholds, or fuzzy identity rules.
- Do not improve the 15/29 diagnostic by changing answer/fact wording to resemble gold text.
- Do not render every extracted claim directly; preserve concision through semantic fact grouping and history,
  not terminal omission.
- Do not ask an LLM to rewrite whole Markdown pages. Keep page generation deterministic.
- Do not add another fallback path when a semantic contract fails. Preserve prior state, expose the failure,
  and retry the intended mechanism later.
- Do not prioritize vector retrieval while the wiki itself contains stale, missing, and misowned truth.

## Bottom line

The current implementation proves that the architecture can produce readable, source-grounded pages, and the
recent structured participant/entity work is promising. The exact fixture run also shows that renderer polish
alone cannot close the gap. The system first needs a single, transparent semantic layer that can revise scope,
resolve stable entities, group supporting claims, distinguish current truth from history, and assign a fact's
human-facing section.

The Milestone 1 mechanism described above is now present, but the milestone remains acceptance-incomplete until
the declared entity-emergence, ownership-migration, and stable-relation conditions pass the required repeated
primary and transfer trials. Finish that bounded acceptance closure first. The next major architectural
milestone is then **Milestone 2: one owner-scoped fact-resolution plan**; do not add another semantic fallback or
begin renderer/retrieval polish while the identity/scope or truth-resolution gates remain open.

### 2026-08-26 closure check

Repository stabilization is complete: the architecture and lifecycle documentation now match production,
generated stores/debug output are ignored, Python and UI lint are clean, the UI builds, all three semantic
fixtures validate, and the full Python suite passes with 249 tests and 2 skips.

The bounded M1 diagnostic did identify and fix two general data-flow defects. Scope revision now receives all
first-pass identities, including provisional ones, so it cannot rediscover the same identity under a duplicate
slug. The scope planner also receives the extraction layer's structured mention roles and existing stable
entity references. Regression tests cover both paths.

Fixed-extraction replay `daily-driver-v1-m1-closure-simple-20260826` completed without the former duplicate-slug
failure and did not create Lantern prematurely. It still selected a scheduled-interview Event instead of the
continuing Family Oral History Project. It passed 3/17 dimensions and 2/5 release gates. A proposed lifecycle
variation that exposed first-pass materialized identities to revision as provisional was tested once and
rejected: `daily-driver-v1-m1-closure-provisional-20260826` still made the same scope error and increased
deferral variance. Extra continuity/event evidence fields were also removed after an earlier trial showed that
the larger schema did not improve the small model's decision.

Accordingly, M1 is **not complete** and no three-trial or transfer acceptance run was started. Repeating a known
primary-gate failure would not constitute acceptance evidence. Further fixture-shaped prompt/schema tuning is
out of scope. The next decision is architectural: either adopt a small, independently evaluated identity-type
adjudication step, or make ambiguous Project/Event proposals explicit user-review items and revise the M1
acceptance contract accordingly.
