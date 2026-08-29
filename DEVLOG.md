# Development Log

## 2026-08-28 — Make consolidated facts current presentation only

- Removed the unused active/retired lifecycle from consolidated facts and from their artifact API. A persisted fact
  now means that it belongs to the current wiki representation.
- Renamed the synthesis/materialization deletion set accordingly; obsolete synthesized facts continue to be deleted
  when Dream recomputes a grouping.
- Supersession approval now immediately deletes every display fact containing the superseded claim. Any other active
  claims from a deleted grouped fact are preserved as independent source-grounded display facts before pages are
  regenerated. Canonical claims and supersession links remain durable.
- Added focused coverage for immediate standalone cleanup and grouped-fact preservation. No prompt, ontology, or
  structured model decision changed, so no direct Ollama probe was required.
- Validation: Ruff passed; all 227 non-Engram tests passed; frontend lint and production build passed with the
  existing large-chunk warning; `git diff --check` passed.

## 2026-08-28 — Remove fuzzy ingestion reconciliation and dead recall routing

- Removed the pre-Dream `SequenceMatcher` claim reconciler. Every extracted occurrence now persists as a
  distinct claim with its own source provenance; semantic grouping remains the responsibility of structured
  Dream fact consolidation and reviewable reconsolidation.
- Added a focused encoding regression proving identical statements from separate episodes retain separate claim
  and source IDs.
- Removed the unused Markdown recall-section parser, its tests, and the unreachable `_routing_index()` facade.
  Production retrieval continues through the retained full-page FTS, temporal, short-term, and source-evidence
  paths.
- No production prompt, structured-output schema, or ontology changed, so this cleanup did not require a direct
  Ollama semantic-contract probe.
- Validation: Ruff passed; the 226-test non-Engram suite passed; focused encoding, Dream, reconsolidation,
  retrieval, source, session, and context coverage passed as part of that run.

## 2026-07-22 — Wiki and recorded-memory quality

Goal: improve the completeness, trustworthiness, and concision of recorded memory across varied
LoCoMo conversations without optimizing retrieval or adding benchmark-specific knowledge.

### Iterations 1–6 — Source-grounded claims and concise wiki projections

- Reworked the pipeline from lossy episodic summaries into an auditable intermediate artifact layer:
  canonical raw transcripts, source documents and segments, episode manifests, atomic claims, exact
  provenance, extraction status, and coverage reports.
- Added raw/claims/hybrid ablations. Hybrid dreaming used canonical claims plus exact supporting or
  unassigned source spans, so extraction failures remained visible instead of silently deleting memory.
- Added bounded extraction and repair passes, sentence-level segmentation, speaker-aware attribution,
  relative-time normalization, conservative claim reconciliation, and page assignment tracking.
- Replaced growing summary prose with deterministic main/timeline/detail/interaction projections.
  Main pages became bounded and diverse; redundant display records were compacted without deleting
  canonical claims, and large child views were split into stable linked shards.
- Runs progressed from repeated concision tests on conversation 2 to generalization checks on
  conversations 1, 3, and 4:

  | Run | Conversation | Score | Accounted coverage | Active claims | Wiki body words |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | v1 | 2 | `0.4884` | `99.46%` | 338 | 4,561 |
  | v2 | 2 | `0.4277` | `99.73%` | 226 | 3,000 |
  | v3 | 2 | `0.4238` | `95.26%` | 300 | 3,770 |
  | v4 | 1 | `0.4537` | `97.90%` | 351 | 4,991 |
  | v5 | 3 | `0.4190` | `95.17%` | 505 | 6,763 |
  | v6 | 4 | `0.4787` | `98.34%` | 664 | 8,547 |

- Learned: prompt-only summarization was the wrong place to enforce completeness and concision;
  retaining atomic claims while projecting bounded views worked better. V2 reduced wiki body text by
  roughly one third without improving QA, confirming that concise memory and retrieval performance are
  separate concerns. V3 changed coverage accounting from turns to atomic sentences, so v1–v2 coverage
  is not directly comparable. V5's failed episode and 106 unaccounted segments exposed local-model
  reliability as a first-class concern, motivating explicit repair and loss-visible hybrid evidence.
  Across v1–v6, high coverage still did not guarantee a high LoCoMo score; temporal reasoning,
  retrieval, and answer generation remained distinct bottlenecks. Scores on different conversations
  are generalization checks, not direct ablations.

### Iteration 7 — Traceable derived memory (LoCoMo index 5)

- Added a separate `*-insights` projection for inferred conclusions, with basis-claim provenance.
- Bounded derivation input and made benchmark finalization always run compaction.
- Result: score `0.4802`; accounted segment coverage `97.61%` (756 claims / 2,386 segments).
- Learned: full claim payloads could overflow local-model context, and the model often put claim IDs
  in prose while omitting required structured fields. Subjectless claims and synthetic participant
  labels also created noisy or incorrect pages. The first pass produced no reliable derived insights.

### Iteration 8 — Attribution and routing safety (LoCoMo index 6)

- Sent compact, bounded derivation batches; required standalone named subjects.
- Routed visual claims to details and multi-party claims through real source participants.
- Removed synthetic relationship pages and prevented unattributed claims from being stored.
- Result: score `0.4691`; accounted coverage `96.01%` (635 claims / 2,230 segments), with zero
  subjectless claims or stray participant pages.
- Learned: strict rejection improved trustworthiness but discarded useful first-person fragments;
  deterministic, single-speaker attribution recovery was needed. Local structured output must also be
  validated and safely repaired rather than assumed complete.

### Iteration 9 — Completeness, deduplication, and grounded synthesis (LoCoMo index 7)

- Added safe single-speaker attribution normalization, cross-kind exact deduplication, relative-year
  normalization, and unambiguous “recorded in N sessions” support qualifiers.
- Recovered basis IDs only when they referenced real claims; rejected unsafe count/trend derivations.
- Result: score `0.4601`; accounted coverage `97.39%` (627 claims / 2,072 segments), eight grounded
  inferred claims, zero subjectless claims, and zero exact or near-duplicate pairs.
- Learned: the extra wiki length mostly represented retained facts, but some overview placement and
  generic “insights” still depended on unreliable model labels. Scores across these iterations are not
  direct ablations because each used a different conversation; artifact audits were more informative.

### Post-iteration architectural hardening

- Replaced semantic prose matching with a structured claim envelope: `claim_type`, open `predicate`,
  `evidence_modality`, `temporal_status`, provenance, and open facets.
- Projection now uses structured fields; unknown claims fail closed into detail pages. Before merge,
  the old store migration and unstructured encoder fallback were removed in favor of a clean rebuild.
- Derived claims declare a reasoning operation. Counts, recurrence, temporal arithmetic, and
  cross-fact relationships are validated from structured prerequisites rather than phrase blacklists.
- Reduced overview capacity from 28 to 18 claims and projection shards from 80 to 60 records; all
  demoted information remains available in linked detail, timeline, interaction, or insight pages.
- Kept regex only for sanitation, temporal parsing, subject validation, grammar repair, and
  conservative presentation-level deduplication.
- Made source/episode/claim artifacts mandatory across encoding and dreaming, removed the unused
  episodic-summary field and direct raw-entry encoder, and taught **Clear Memory** to delete all
  derived artifacts while preserving UI conversation transcripts for re-encoding.
- Validation: 149 tests passed, 2 skipped; scoped lint and core schema/projection type checks passed.
  This final schema refactor has not yet been benchmarked.

## 2026-08-04 — Claims-only consolidation and code-quality simplification

Goal: reduce overlapping production mechanisms, make memory updates easier to audit, and address the
privacy and responsiveness risks identified by the code audit.

### One intended consolidation mechanism

- Reduced `mycelium/dream.py` from a roughly 2,500-line collection of competing workflows to a thin
  orchestration layer. Claim routing now lives in `mycelium/consolidation.py`, while deterministic page
  generation lives in `mycelium/materialization.py`.
- Standardized the pipeline on one path: source-grounded structured claims, semantic routing,
  deterministic page projection, then audit/index finalization. Removed raw and hybrid evidence modes,
  configurable conflict policies, LLM page rewriting, special-case routing, derived-insight generation,
  compaction, and their associated configuration and benchmark branches.
- Kept one structured router for every source type, with exact alias accounting, an eight-page limit,
  fail-closed validation, and a rule preventing named participants from being routed to the user profile.
  This makes routing behavior bounded and reviewable instead of relying on overlapping fallback paths.
- Made active assigned claims the source of truth for generated page content. Titles and creation dates
  remain stable for existing pages; page type, tags, confidence, importance, source IDs, and new titles
  are materialized deterministically. This avoids prose rewrites that could silently drift from evidence.
- Simplified Dream-run auditing around source outcomes, claim dispositions, page assignments, and
  failures. Strategy, conflict-policy, and evidence-mode fields were removed because they no longer
  describe real choices in the pipeline.
- Confirmed the earlier audit fixes remain in place: retrieval no longer reinforces a page before its
  usefulness is known, dead decay configuration has been removed, benchmark-specific production paths
  and lexical mappings are gone, and the unsafe Git integration was removed instead of staging the
  repository with `git add -A`.

### One-pass extraction and tool observations

- Claim extraction now makes one logical pass, batching segments only to preserve useful context. It no
  longer performs coverage-repair or final-normalization model calls. Model-declared ignored segments and
  programmatic conversational-furniture detection are recorded explicitly, while genuinely uncovered
  segments leave the episode partial.
- Partial episodes that contain useful claims may consolidate; partial episodes with no claims and failed
  episodes remain pending. There is no raw-text fallback. This accepts honest gaps instead of paying for
  repeated passes that can promote conversational debris into durable memory.
- Tool observations now use the same Encoder source, segment, and claim pipeline under a
  `tool_observation` source policy. Tool event logging is asynchronous, and the separate Dream-specific
  extraction path was removed so every durable claim follows the same validation rules.

### Private diagnostics and non-blocking web tools

- Bounded the in-memory LLM call log to 100 metadata-only entries. INFO logs now record operational data
  such as character counts, call metadata, result sizes, and argument keys rather than prompts, source
  evidence, responses, tool arguments, or tool results.
- Full structured diagnostic dumps are available only when `MYCELIUM_LLM_DEBUG_DIR` is explicitly set,
  and are documented as sensitive. Parse errors also avoid embedding model response content. This keeps
  normal logs useful without quietly creating another unbounded store of private memory.
- Removed the synchronous Ollama client from the asynchronous chat path. Web search and fetch tools now
  await the async client, preventing network calls from blocking the server event loop.

### Generated views, compatibility, and licensing

- Made the generated wiki view read-only by removing the page update/delete API routes and corresponding
  UI controls. Generated pages should change through claims and materialization, not through a second
  editing authority that can disagree with their evidence.
- Removed compatibility and migration paths for stores created by the retired evidence modes. Existing
  stores must be cleared and re-encoded, which keeps the new pipeline direct and avoids preserving the
  complexity this work was intended to remove.
- Added an MIT license, declared it in `pyproject.toml`, and documented it in the README so reuse and
  contribution terms are explicit.
- Updated documentation and benchmark tooling for the single claims pipeline, and removed evidence-mode
  ablation code that no longer represents a production choice.

### Validation and remaining security work

- A completed full test run passed 126 tests with 2 skipped. Final affected-area reruns, Ruff, MyPy over
  the 20 `mycelium` modules, the frontend production build, and `git diff --check` also passed. The frontend
  build retains its existing large-chunk warning.
- Wildcard CORS, authentication, destructive development endpoints, and documented LAN exposure were not
  changed in this iteration. They remain an open audit item under the current trusted-LAN/Tailscale
  deployment assumption and should be addressed before treating the API as safe on an untrusted network.

## 2026-08-05 — Claim-level reconsolidation and immediate review application

Goal: preserve reconsolidation as a distinct memory mechanism while making it consistent with the
claim-authoritative architecture, source provenance, deterministic projection, and human control.

### Evidence-triggered claim reactivation

- Removed retrieval-time prediction-error checks, page-level lability flags and snapshots, accumulated
  session signals, LLM-authored wiki rewrites, and the manual **Resolve Current** workflow. Retrieval is
  now entirely read-only: a query can select memory for context but cannot mutate it.
- Moved reconsolidation into Dream, where new source-grounded claims act as the reactivation cue. Each new
  routed claim is compared with a bounded, deterministically ranked set of related active claims using
  entity overlap, page assignment, structured slots, predicates, claim types, and recency.
- The classifier has four explicit outcomes. Additive information follows normal routing; supporting
  evidence creates reciprocal claim links automatically; contradictions and supersessions create durable
  pairwise proposals. Malformed or failed classifier output leaves the source pending instead of silently
  bypassing reconciliation.
- This interpretation keeps the biological sequence—new evidence, reactivation, prediction error,
  lability, and restabilization—without treating a search query as evidence or generated wiki prose as
  canonical memory.

### Durable proposals and human review

- Added reconciliation proposal artifacts with incoming and target claim IDs, proposed relationship,
  explanation, confidence, Dream-run provenance, affected pages, review state, reviewer note, timestamps,
  and application errors. A proposal must reference two distinct claims.
- A pending proposal is now the durable lability window. Both claims remain active and visible, and their
  generated wiki records receive a deterministic `pending reconciliation` qualifier. This avoids a single
  mutable lability flag that cannot represent concurrent proposals.
- Contradictions and supersessions require approval because they change the interpretation or active state
  of canonical memory. Rejection records the decision while leaving both claims active and unrelated.
  Approval creates reciprocal contradiction links or marks the older claim superseded with reciprocal
  lineage links.

### Immediate deterministic application

- Approval and rejection immediately invoke the same deterministic materializer used by Dream for every
  affected page. Users do not need to approve a proposal and then run a separate Dream pass, and review
  cannot introduce an alternative page-rewrite path.
- Application is idempotent and records partial failures so an approved operation can be retried safely.
  Proposals become stale rather than applying when referenced claims have disappeared or changed state.
- Added proposal overview, list, detail, approve, and reject API endpoints and a Reconciliation tab in the
  Memory Inspector with side-by-side claims, rationale, confidence, affected pages, optional reviewer
  notes, and **Approve and apply** / **Reject proposal** controls.
- Removed the retired reconsolidation configuration, labile storage, response fields, benchmark flags,
  examples, and dead UI activity states. This is intentionally a clean break; older stores must be cleared
  and re-encoded rather than migrated through another compatibility mechanism.

### Validation

- Added integration coverage for Dream proposal creation, pending annotations on both claims, fail-closed
  classifier behavior, automatic support links, supersession approval, rejection, artifact cleanup, and
  review API responses.
- The full backend suite passed 132 tests with 2 skipped. Ruff, MyPy, the frontend production build, and
  `git diff --check` passed. The frontend build retains its existing large-chunk warning.

### Benchmark impact check — LoCoMo `conv-30`

- Repeated the earlier 19-session, 105-question `conv-30` run with the same `gemma4:12b` memory and QA
  model, per-batch Dream policy, 32K context budget, dataset, and scorer. The new run is stored under
  `benchmark_runs/locomo-mycelium-convo-2-claims-reconsolidation-20260805`.
- The headline score fell from `0.4238` to `0.2380`. Multi-hop fell from `0.1959` to `0.0314`,
  single-hop from `0.4084` to `0.0000`, and commonsense/open-domain from `0.2438` to `0.0147`.
  Adversarial accuracy rose from `0.8750` to `1.0000`, but only because the empty memory made the model
  abstain almost universally; this is not a quality improvement.
- The earliest failure was extraction, before routing or reconsolidation. The one-pass model returned
  plausible claim text but supplied an empty `segment_ids` list for every claim. Grounding validation
  correctly rejected those claims, leaving all 19 sources pending, zero active claims, zero wiki pages,
  and 19 unconsolidated logs. Accounted segment coverage fell from `95.26%` to `72.28%`; the remaining
  coverage consisted only of segments the model marked ignored.
- A diagnostic repeat on a prior `conv-47` session generalized the result: the model returned eight
  plausible claims and zero claims with source-segment IDs. A second full QA run was therefore stopped
  before spending another 30–40 minutes measuring the same empty-memory state.
- Construction time fell from 838.4 to 691.1 seconds, but that apparent 17.6% improvement is invalid as
  an efficiency gain because no claims were persisted and no pages were routed. Mean query time likewise
  fell only because mean input shrank from 5,848 tokens to 24 tokens.
- Per-batch Dream retried every previously pending source, causing 19 unique failed episodes to appear as
  190 cumulative Dream-failure records. Benchmark reporting should separate unique failing sources from
  repeated attempts.
- Conclusion: this run does not yet measure the effect of claim-level reconsolidation. The blocking
  regression is the extraction/provenance contract. Follow-up probes showed that `segment_ids` was
  optional in the generated schema: the model omitted it and Pydantic silently supplied the default empty
  list. Adding `minItems` alone did not help because the field remained optional. Requiring a non-empty
  list and constraining its values to the current batch produced ten claims with ten valid full-ID
  citations, so short aliases are not required to fix the observed failure. The next iteration should
  strengthen the schema and exact accounting first, consider aliases only as a measured robustness or
  token-efficiency improvement, and then rerun `conv-30` unchanged.

### Strict one-pass provenance and comparison rerun

- Replaced the permissive extraction contract with a batch-scoped schema. Every claim must cite at least
  one full source-segment ID, every cited or ignored ID must be one of the exact IDs supplied in that
  batch, and the top-level claim and ignored-ID collections must be present even when empty. The Encoder
  validates the same contract again before persisting anything and rejects a batch if a segment is both
  claimed and ignored.
- Kept extraction deliberately single-pass. Invalid output leaves the episode partial and the loss
  visible; there is no retry over uncovered text, short-ID alias translation, fabricated provenance, or
  raw-text fallback. This fixes the intended evidence contract rather than adding another recovery path.
- Repeated the same `conv-30` benchmark as
  `benchmark_runs/locomo-mycelium-convo-2-strict-provenance-20260805`. The score recovered from the broken
  `0.2380` run to `0.5085`, and exceeded the prior healthy `0.4238` comparison by `0.0847` absolute
  (`20.0%` relative). Single-hop rose from `0.4084` to `0.5875`, multi-hop from `0.1959` to `0.2944`, and
  commonsense/open-domain from `0.2438` to `0.3154`; adversarial accuracy remained `0.8750`. Across the 105
  questions, 30 improved, 19 regressed, and 56 were unchanged.
- The new store contains 193 active claims and five wiki pages. It accounts for `91.66%` of 1,223 source
  segments, with no unresolved provenance IDs or failed episodes. This is lower than the healthy run's
  `95.26%` accounted coverage and 300 claims, but the smaller generated view still produced a higher QA
  score, reinforcing that raw coverage and retrieval quality are separate measures.
- The audit also found downstream reliability work that the aggregate score can obscure. Routing and
  reconsolidation generated 68 cumulative failure records across 11 sources, left 35 claims unassigned,
  and left three logs unconsolidated. Fifteen pending reconsolidation proposals were created; all were
  classified as `supersedes` with confidence `0.8`, including some pairs that appear merely additive,
  equivalent, or contradictory. The classifier contract and routing accounting therefore need their own
  general reliability pass before reconsolidation decisions should be trusted at scale.
- Memory construction took 1,549.3 seconds versus 838.4 seconds for the healthy comparison (`84.8%`
  slower), while mean query time increased from 1.267 to 2.384 seconds. The per-claim reconsolidation
  classifier is the likely construction bottleneck, but call-level timing should be instrumented before
  attributing the entire increase to it.
- Validation passed with 134 backend tests and 2 skips, plus Ruff, MyPy, and `git diff --check`. The host
  Ollama access procedure is now documented in `AGENTS.md`: sandboxed loopback failures must be verified
  with network escalation, and agents must not start a second server or silently change models.

### Source-scoped route-only consolidation and comparison rerun

- Removed the router's second durable-memory admission decision. Claim extraction remains responsible for
  deciding whether source material is substantive; every admitted active claim must now receive one wiki
  destination. The routing model no longer returns redundant `disposition` or `action` fields and cannot
  silently classify durable claims as semantically ignored.
- Replaced the permissive list response with a source-scoped, alias-keyed schema. Every supplied `C###`
  alias is a required top-level property, additional aliases are forbidden, and every value requires a
  non-empty page slug and explicit page type. Because this is the schema passed to `call_structured`,
  missing or extra assignments trigger its normal validation retries rather than becoming a later Dream
  failure. The router validates the same model again before materialization for mock and caller safety.
- Aligned LLM routing batches with Dream's source transaction boundary. A malformed response for one
  source can no longer reject claims belonging to another source that happened to share a 32-claim batch.
  Added tests for exact required aliases, rejection of extra and legacy-shaped output, required page
  fields, and isolation of one invalid source while another completes.
- Repeated LoCoMo `conv-30` with the same dataset index, `gemma4:12b` memory and QA models, per-batch Dream
  policy, context budget, and scorer as
  `benchmark_runs/locomo-mycelium-convo-2-strict-routing-20260805`. The score increased from the strict-
  provenance run's `0.5085` to `0.5310` (`+0.0225` absolute, `+4.4%` relative) and remains above the older
  healthy comparison's `0.4238`. Multi-hop rose from `0.2944` to `0.3339`, commonsense/open-domain from
  `0.3154` to `0.3463`, and adversarial from `0.8750` to `0.9167`; single-hop declined from `0.5875` to
  `0.5709`. Against strict provenance, 20 questions improved, 17 regressed, and 68 were unchanged.
- Previously missing facts became answerable, including the July 21 content collaboration, June 20 studio
  opening, Rome trip, Paris visit, and sentiment about the grand opening. This is consistent with the
  routing fix, though individual QA answers remain sensitive to extraction and retrieval variation.
- Routing itself left zero claims unassigned. The six remaining unassigned claims all came from the final
  source, which received valid page assignments but stayed pending after a reconsolidation decision failed
  closed. Unconsolidated logs fell from three to one. An earlier 17-claim source exceeded the eight-page
  routing limit twice before succeeding on a later Dream run; its 34 per-claim failure records therefore
  represent two source-level events, not 34 separate malformed responses. The page-limit invariant remains
  outside the structured contract and should be addressed without relying on later Dream runs.
- This fresh end-to-end run is not a perfectly isolated routing ablation. The local model extracted 162
  claims rather than 193, and accounted segment coverage fell from `91.66%` to `78.50%`. Six extraction
  batches were discarded because the model marked one or more segments as both claimed and ignored,
  compared with two such batches previously. Future stage-level comparisons should freeze or clone source,
  episode, and claim artifacts before routing so extraction variance cannot confound the result.
- Construction time increased from 1,549.3 to 1,597.1 seconds (`3.1%`) and mean query time from 2.384 to
  2.519 seconds (`5.6%`). The store has eight wiki pages. Reconsolidation produced ten pending proposals:
  eight `supersedes` and two `contradicts`, all at confidence `0.8`; relation and confidence calibration
  therefore remain unresolved and auto-approval would still be unsafe.
- The full backend suite passed 135 tests with 2 skipped. Affected tests passed 39/39, Ruff passed, MyPy
  found no issues across 26 source files, and `git diff --check` passed.

## 2026-08-05 — Typed wiki taxonomy and profile dashboard

Goal: make generated wiki pages genuinely useful as a concise, organized picture of what the agent
knows, while preserving canonical claims and avoiding new catch-all or duplicate-content mechanisms.

### Canonical page identities and sparse taxonomy

- Replaced the generic entity/topic/event split with seven explicit types: `you`, `person`, `project`,
  `topic`, `organization`, `place`, and `event`. The routing contract now requires a stable typed page
  ID, display title, and type for every claim destination.
- Added a durable page-definition registry containing stable ID, title, aliases, explicit related-page
  IDs, type, lifecycle status, and timestamps. Markdown remains a generated projection; page identity
  no longer depends on parsing a slug, `page-type-*` tag, or model-authored subject list.
- Adopted type-prefixed IDs such as `person-jon`, `project-mycelium`, and `topic-local-compute`. `you` is
  the only singleton exception. Generic catch-alls such as `topic-hobbies` and `topic-recent-work` are
  rejected, while routing guidance favors focused Topics and sparse Person, Place, and Event creation.
- Kept one primary page assignment per claim. Products and owned initiatives route to Projects;
  independent companies, employers, institutions, teams, and communities route to Organizations.
  A Topic that produces a concrete endeavor remains separate from its linked Project.
- Person pages can begin with a relationship role and later acquire a known name without changing the
  stable page ID; the old role becomes an alias. Named-participant safety is now claim-scoped, so an Ava
  claim cannot target You while an actual user claim from the same multi-party source still can.

### Typed projections, relationships, and interfaces

- Replaced the generic Memory/Timeline/Details layout with deterministic type-specific sections. The
  singleton **You** page provides a concise Profile, current priorities, preferences and working style,
  active-project links, important-person links, focused-topic links, and recent changes.
- Type renderers compact equivalent display records without dropping canonical claims, place each record
  in one primary section, isolate claims awaiting reconsolidation under **Needs Review**, and generate
  compact relationship links instead of copying another page's facts.
- Directly evidenced related-page IDs are stored symmetrically. This lets a focused Topic and a concrete
  Project coexist with distinct identities and reciprocal links without inferring an edge from shared
  subjects or source participation.
- Grouped the generated index and Wiki explorer as You, Projects, People, Topics, Organizations, Places,
  and Events. Added explicit `page_type` fields to Markdown frontmatter, list/detail API responses, and
  the frontend model, plus a page-type badge and a page-definition artifact endpoint.
- Extended artifact integrity reporting to detect pages without definitions, active definitions without
  pages, and definition/page type mismatches. Clear Memory now removes page definitions before reseeding
  You. This is a clean rebuild with no legacy `user-profile` or tag-derived compatibility path.

### Reasoning and validation

- A small explicit taxonomy makes pages navigable while avoiding the fragmentation of one page per named
  noun. Separating stable identity metadata from generated content permits safe title evolution and
  deterministic rebuilding. Keeping claims single-homed preserves auditability; links provide navigation
  without allowing the same fact to drift across multiple prose copies.
- Added acceptance coverage for typed stable IDs, registry validation, Topic/Project coexistence,
  reciprocal links, single-copy rendering, grouped dashboard/index output, role-to-name person updates,
  scoped participant routing, and catch-all rejection.
- The full backend suite passed 141 tests with 2 skipped. Ruff and MyPy over the core modules passed, the
  frontend production build passed, and `git diff --check` passed. The frontend retains its existing
  large-chunk warning.

### Typed-taxonomy benchmark — LoCoMo `conv-30`

- Repeated the strict-routing comparison with the same sample index, 19 sessions, 105 questions,
  `gemma4:latest` memory and QA models, per-batch Dream policy, 32K context budget, dataset, and scorer.
  The new run is stored under
  `benchmark_runs/locomo-mycelium-convo-2-typed-wiki-taxonomy-20260805`.
- The score fell from `0.5310` to `0.3485` (`-0.1824` absolute, `-34.4%` relative). Multi-hop fell from
  `0.3339` to `0.1655`, single-hop from `0.5709` to `0.0833`, and commonsense/open-domain from `0.3463`
  to `0.2184`; adversarial accuracy rose from `0.9167` to `0.9583`. Eleven questions improved, 43
  regressed, and 51 were unchanged.
- This was not a clean taxonomy ablation because extraction varied sharply. The run produced 118 claims
  versus 162, accounted for `48.98%` of source segments versus `78.50%`, and left all 19 episodes partial.
  Five unconsolidated sources had extraction batches rejected for marking segments as both claimed and
  ignored. Evidence tracing placed the earliest failure for 30 of the 43 regressed questions at
  extraction, seven at routing/reconsolidation, and six after the required evidence had been assigned.
- Routing assigned 79 claims and left 39 unassigned, versus 156 assigned and six unassigned previously.
  One 18-claim source repeatedly exceeded the eight-page limit, while two other sources failed closed on
  invalid reconsolidation targets. Eight logs remained unconsolidated, compared with one in the baseline;
  206 cumulative Dream failure records were emitted, compared with 65.
- The positive artifact result is that explicit typed IDs, grouped sections, stable page definitions,
  single primary claim placement, and deterministic rendering all operated end to end. The nine pages
  included focused Person and Project views, and useful claims were easier to scan within those pages.
- The semantic artifact result is not yet acceptable. The routing model interpreted `canonical_subjects`
  as participants rather than the identity represented by a page: Paris was registered with Jon as its
  subject, the ad campaign with Gina, and several Projects and Topics with both Jon and Gina. That made
  the relationship graph nearly indiscriminate: nine pages produced 48 directed related-page edges.
  `event-ad-campaign` combined an ad launch, a fair, social-media posting, and competition commentary;
  `topic-fashion` mixed fashion, dance preferences, and store operations; `topic-local-compute` was a
  one-claim misclassification of a visual scene; and the one-visit Paris page violated the intended
  sparse Place policy.
- Wiki body text fell from 2,302 to 1,617 words (`-29.8%`), but assigned claims fell almost twice as much,
  from 156 to 79. Relationship and section overhead therefore increased from roughly 14.8 to 20.5 wiki
  words per assigned claim. The output was shorter mainly because information was missing, not because
  organization became more efficient.
- Construction time fell from 1,597.1 to 1,461.9 seconds and mean query time from 2.519 to 1.221 seconds,
  but the smaller incomplete store explains much of that apparent gain. Several temporal facts were
  correctly normalized in claim facets and wiki date headings, yet answering still returned relative
  phrases such as “yesterday,” exposing a separate downstream use-of-memory issue.
- Conclusion: the typed storage, renderer, API, and UI mechanisms work, but this run does not validate the
  routing design or the benchmark score. The next architectural fix should make the registry identity
  deterministic from the chosen page ID/title rather than model-authored participant lists, derive sparse
  relationships from explicit page references instead of broad subject overlap, and prevent a large source
  from failing wholesale at the eight-page cap. Extraction reliability should be measured with frozen
  source/claim artifacts so it no longer obscures page-taxonomy comparisons.

### Post-benchmark routing hardening

- Removed `canonical_subjects` from both the LLM routing contract and the durable page-definition schema.
  A page now has one identity mechanism: its validated typed ID and display title, with aliases retained
  only for stable renames. This prevents a model-generated participant list from changing what a page
  represents or creating accidental semantic joins.
- Added explicit `related_page_ids` to routing decisions and the page registry. The router accepts only
  existing pages or accepted destinations in the same response, and the materializer stores each accepted
  connection reciprocally. Shared claim subjects, co-participation, and source overlap no longer create
  relationships, so the wiki graph reflects asserted connections rather than broad lexical coincidence.
- Removed the eight-destination source/batch rejection. Routing remains bounded by 32 claims per request,
  but a dense source can now create every justified focused destination instead of failing wholesale after
  the ninth page. This preserves the fail-closed response contract without turning page count into data loss.
- Added regression coverage for more than eight destinations from one source, unknown related-page targets,
  deterministic reciprocal references, and the absence of subject-overlap edges. These changes address the
  benchmark's routing failures directly; extraction variance remains a separate issue to evaluate with
  frozen source and claim artifacts.
- Validation passed with 144 backend tests (two skipped), Ruff across the backend, server, and tests,
  MyPy across 21 Mycelium source files, and `git diff --check`.

### Routing-hardening benchmark — LoCoMo `conv-30`

- Repeated the same 19-session, 105-question `conv-30` configuration with `gemma4:latest` for memory
  and QA, per-batch Dream, and the 32K context budget. The run is stored under
  `benchmark_runs/locomo-mycelium-convo-2-typed-wiki-routing-hardening-20260805`.
- The score fell from the preceding typed-taxonomy run's `0.3485` to `0.2930` (`-0.0555` absolute,
  `-15.9%` relative), and remains well below the strict-routing baseline of `0.5310`. Multi-hop fell
  from `0.1655` to `0.0522`, single-hop from `0.0833` to `0.0321`, commonsense/open-domain from `0.2184`
  to `0.1673`, and adversarial accuracy from `0.9583` to `0.9167`. Twelve questions improved, 15
  regressed, and 78 were unchanged relative to the preceding typed run.
- The intended routing mechanics did improve. No eight-page-limit failure occurred, routing failure
  records fell from 117 to 17, total Dream failure records fell from 206 to 142, accounted segment
  coverage rose from `48.98%` to `52.17%`, and unconsolidated logs fell from eight to seven. The first
  source nevertheless failed its initial Dream attempt because all 17 routes referenced unresolved
  related page IDs; a later per-batch retry happened to route it successfully. This exposes a bootstrap
  flaw in making secondary relationships part of the primary assignment contract.
- Assignment did not improve: the new run again assigned 79 claims, while total extracted claims rose
  from 118 to 126 and unassigned claims rose from 39 to 47. Extraction emitted the same 36 repeated
  claimed-and-ignored overlap failures, and reconsolidation failures increased from 53 to 89. A
  source-label evidence trace classified the earliest available-evidence gap as extraction for 63 of
  105 questions, consolidation for ten, retrieval for seven, and answering/scoring for 25; the preceding
  typed run classified 52, 20, seven, and 26 respectively. Because extraction changed between runs,
  this remains an end-to-end comparison rather than a clean routing ablation.
- Deterministic identity succeeded: all 22 page definitions use typed IDs and titles, with no
  model-authored subject field. Explicit references also removed the previous near-complete graph:
  directed edge density fell from `66.7%` (48 edges across nine pages) to `13.4%` (62 edges across 22
  pages). The absolute graph is still not useful enough. All 31 reciprocal relationships touch either
  Gina or Jon, giving the Person pages degrees 17 and 15 while producing no Project–Topic links.
- Artifact organization regressed. The router produced 22 pages for 79 assigned claims, including eight
  one-claim pages. One-off images became Places, isolated occurrences became Events, and conversational
  encouragement, compliments, and support became separate Topics despite the sparse-creation prompt.
  `event-job-loss-banker` also contains a studio-fair claim; `project-jon-business` contains Gina's store
  activity; and `project-gina-line` combines the store launch with a limited product line. Rendered page
  bodies grew from 1,398 to 1,620 words while preserving no more assigned claims.
- Several score losses reflect real missing evidence: the new extraction contains no claim for *The Lean
  Startup*, Rome, or Gina's ad campaign, and reduces Gina's favorite dance memory to generic competition
  participation. Other losses are downstream: the mentorship page has a normalized `2023-06-15` heading,
  but QA still answers “yesterday,” while a yes/no answer is returned as a longer descriptive fragment.
- Conclusion: keep deterministic page identity and the removal of the page-count cap, but do not treat
  this run as validation of the page-formation or relationship design. The next design pass should form
  pages from the resolved claim set so multi-claim sparsity and coherence can be enforced, then establish
  relationships only after both endpoint pages exist. Primary claim placement should not fail because a
  secondary edge is unresolved. Reconsolidation target aliases should also be constrained structurally,
  and future taxonomy comparisons should replay frozen extraction artifacts. This benchmark uses
  `memory_profile="none"`, so it does not exercise or evaluate the singleton You dashboard.

## 2026-08-10 — Page-level wiki taxonomy rebuilt from the strict-routing checkpoint

Goal: restore the readable seven-type wiki taxonomy without repeating the earlier regression in which
taxonomy expanded the routing contract, fragmented broad pages, and made secondary page relationships a
condition of primary claim placement.

### Architecture and presentation

- Kept the `dd1f60e` claim router and its broad, stable slugs as the only page-formation mechanism.
  Taxonomy now runs afterward over already-formed pages and can return only one of `you`, `person`,
  `project`, `topic`, `organization`, `place`, or `event`. It cannot create, rename, split, merge, route,
  or relate pages. The router's entity/topic/event value remains an internal advisory hint rather than a
  user-facing taxonomy.
- Added explicit nullable `page_type` metadata to `WikiPage`, Markdown frontmatter, API responses, and the
  frontend model. `null` is a deliberate pending state: classification failure is reported separately in
  Dream audits and benchmark stats, does not leave a source unconsolidated, and is retried by a later
  Dream. Once classified, a page's type is stable. `user-profile` is deterministically typed `you` and
  displayed as **You** without an LLM call.
- Chose a clean schema break. Wiki files missing `page_type` fail with an instruction to clear and rebuild
  the generated wiki from canonical artifacts; no tag-derived compatibility reader or migration fallback
  was added. Stable slugs remain unchanged, and no page-definition registry was reintroduced.
- Added deterministic type-specific section templates while retaining the existing claim projection and
  compaction. Person pages lead with Profile; Project pages organize Overview, Current Status, Design
  Choices, and Plans & Next Steps; other types receive similarly scoped headings. Identity records that
  the generic main-view cap demotes are promoted back into typed Key Facts and removed from Details, so
  every display record still appears exactly once.
- Added a You-page Memory Map and grouped the generated index and Wiki Explorer as You, Projects, People,
  Topics, Organizations, Places, Events, and Unclassified. Navigation links do not duplicate facts or
  create semantic relationships. Existing relationship generation remains deferred. Internal coarse
  routing tags are hidden in the UI, while ordinary tags remain visible.

### Reproducible benchmark comparisons

- Added `--replay-store` / `REPLAY_STORE` to replay exact source, episode, claim, and raw-log artifacts
  while resetting only downstream Dream assignments and links. Added `--replay-assignments` /
  `REPLAY_ASSIGNMENTS=1` for projection-only comparisons that preserve the fixture's claim-to-page map and
  skip routing and reconsolidation. This made extraction, routing, and rendering variance independently
  observable instead of attributing every score change to taxonomy.
- A fresh run of restored `dd1f60e` established the current baseline at `0.5329` on LoCoMo `conv-30` with
  `gemma4:12b`, 19 sessions, 105 questions, per-batch Dream, and a 32K context budget. It extracted 187
  claims at `94.03%` accounted segment coverage, produced 13 pages, left 18 claims and two logs pending,
  and recorded 85 cumulative Dream failure records.
- The metadata-only frozen-extraction run scored `0.5332`. It replayed the historical 162 claims at the
  exact `78.50%` accounted coverage, produced six broad pages, left one source pending, classified every
  page, and recorded zero taxonomy failures. Twelve claims were unassigned because routing was rerun; this
  motivated the assignment-preserving projection mode rather than being treated as a taxonomy effect.
- The exact-assignment generic projection baseline scored `0.5266`. An initial typed experiment also fed
  nested typed sections into the retrieval recall index; mean QA input rose from 5,673 to 6,526 tokens and
  score fell to `0.4746`. That retrieval coupling was rejected. Keeping retrieval behavior unchanged while
  applying typed presentation recovered to `0.5220`.
- The retained final projection, including ordered templates and Profile promotion, scored `0.5383`,
  `+0.0118` over the exact generic projection. Generic and typed stores contain the exact same 228 rendered
  fact bullets. Typed body size is 3,029 words versus 3,014 (`+0.5%`), so the readability gain comes from
  headings rather than duplicated facts or prose expansion.
- The final fresh end-to-end run is stored at
  `benchmark_runs/locomo-mycelium-convo-2-taxonomy-final-e2e-20260810`. It scored `0.5620`, `+0.0291`
  above the restored baseline and above the `0.48` acceptance floor. Multi-hop scored `0.3963`, single-hop
  `0.5987`, commonsense/open-domain `0.3654`, and adversarial `0.9583`. The run extracted 169 claims at
  `80.78%` accounted coverage, assigned 163 (`96.4%`), left one source pending, and produced five broad
  pages with no singletons, unclassified pages, taxonomy failures, or automatic relationships. Its 26
  cumulative Dream failure records all belong to the pre-existing routing/reconsolidation path.

### Validation and conclusion

- Backend validation passes with 144 tests and two skips. Ruff passes across production, benchmark, server,
  and test code; MyPy passes across 21 core files; the frontend production build passes with its existing
  large-chunk warning; and `git diff --check` passes.
- The earlier taxonomy failed because it made every claim participate in page identity, graph formation,
  and benchmark-sensitive routing. The retained design treats taxonomy as stable page metadata and a
  deterministic human view over the same canonical assignments. Retrieval remains intentionally unchanged
  for the later claim-first retrieval work.

## 2026-08-10 — Claim-first retrieval experiments rejected after frozen-store evaluation

Goal: replace page-gated recall with a structured local retrieval stack over canonical claims and source
segments while keeping the wiki independent as a human-readable generated view.

### Evaluation infrastructure

- Added `--frozen-store` / `FROZEN_STORE` to copy an exact completed case store and skip ingestion and
  Dream. This isolates retrieval and answering from extraction, routing, taxonomy, and materialization
  variance. Added `--include-retrieval-context` / `INCLUDE_RETRIEVAL_CONTEXT=1` for explicitly persisting
  rendered synthetic benchmark contexts during qualitative inspection. These general benchmark features
  were retained.
- Used the exact store from `locomo-mycelium-convo-2-taxonomy-final-e2e-20260810` with `gemma4:12b`, all
  105 `conv-30` questions, and the existing `0.5620` page-retrieval result as the production baseline.

### Experiments and results

- Implemented a disposable SQLite FTS5 projection over active claims and eligible source segments,
  semantic page candidate generation, reciprocal-rank fusion, a constrained claim/segment reranker,
  provenance-centered evidence windows, and a structured retrieval result. This implementation remained
  local and source-grounded; ignored conversational debris, inactive claims, and assistant-authored agent
  turns were excluded.
- Sparse claims plus exact evidence scored `0.4858` with only 242 mean QA input tokens. Single-hop improved
  to `0.6194`, but multi-hop fell to `0.2304` and open/conversational questions to `0.2356`. Candidate
  evidence recall was materially higher than selected-context recall, showing that the reranker often
  discarded complementary facts.
- Adding up to two supporting wiki pages scored `0.4389` at 1,268 mean input tokens. Pages added noise but
  did not repair selection, so the hybrid renderer was rejected.
- Forcing eight fused claims and four source hits raised selected evidence recall from `0.6340` to `0.7430`
  but lowered score further to `0.4270`. This confirmed that indiscriminate context expansion is not a
  substitute for precise multi-fact selection.
- Replacing page routing with one-to-four semantic search facets produced the strongest claim-first result:
  `0.5099`, candidate recall `0.8279`, selected recall `0.6768`, 385 mean input tokens, and single-hop
  `0.7271`. Multi-hop nevertheless collapsed to `0.1006`, leaving the run more than the agreed `0.02`
  absolute tolerance below the baseline.

### Qualitative conclusion

- The claim-first contexts were substantially shorter and often contained the necessary evidence. Some
  score losses were downstream answer/scorer failures: descriptive affirmative answers lost to exact
  `Yes`, and correctly retrieved facts were not always composed into lists, durations, or shared-property
  answers. Other failures were real retrieval omissions: lexical candidates favored generic business
  claims, query decomposition missed secondary events or cities, and benchmark entity aliases did not map
  to canonical names.
- Three general hypotheses failed the release gate: sparse LLM selection omitted complementary evidence,
  page supplementation diluted relevance, and deterministic expansion damaged precision. In accordance
  with the iteration protocol, the experimental production implementation and renderer switches were
  removed rather than preserved as fallback paths. The proven page retrieval remains the only production
  mechanism.
- The next attempt should improve semantic candidate generation—most plausibly local embeddings combined
  with FTS and explicit temporal/entity constraints—then evaluate candidate recall separately from answer
  synthesis. It should not increase page caps or context volume to compensate for weak ranking.

## 2026-08-11 — Retrieval quality iteration series

Goal: run ten isolated retrieval experiments against the exact completed `conv-30` store, using
`gemma4:12b` for both routing and answering. Every run retains rendered context so labeled source-evidence
recall can be separated from answer-model and scorer behavior. Experimental mechanisms are reverted before
the next cycle unless the evidence supports keeping them.

### Control

- Run `locomo-mycelium-convo-2-retrieval-control-20260811` used the frozen store from
  `locomo-mycelium-convo-2-taxonomy-final-e2e-20260810`. It scored `0.5458` across all 105 questions,
  compared with the historical `0.5620`; the `-0.0161` movement is within the existing `0.02` variance
  tolerance. Mean QA input was 5,463 tokens and 1.89 pages were loaded per question.
- Direct inspection of the retained contexts found `0.6546` mean labeled-evidence recall and `0.6286` of
  questions with all cited turns present. Recall by category was `0.7692` single-hop, `0.6591`
  open/common, `0.3394` multi-hop, and `0.6667` adversarial. The low multi-hop evidence ceiling makes
  candidate coverage the first problem to isolate.
- Added benchmark-only retrieval-evidence metrics. They are computed after answering and therefore cannot
  influence routing or QA; future summaries report mean evidence recall and complete-evidence question rate.

### Iteration 1 — all-page routing ceiling

- Hypothesis: if loading every eligible wiki page materially raises evidence recall and QA, page routing is
  the primary bottleneck. The temporary change completes any non-empty LLM route with all remaining pages.
- Next step: run the full frozen-store benchmark, inspect context size and multi-hop recall, then revert this
  diagnostic regardless of outcome because indiscriminate all-page loading does not scale.
- Result: `locomo-mycelium-convo-2-retrieval-i01-all-pages-20260811` scored `0.5361`, down `0.0098`
  from the fresh control. Mean labeled-evidence recall rose from `0.6546` to `0.6927`, but mean QA input
  grew from 5,463 to 6,566 tokens and adversarial score fell from `0.9583` to `0.8750`. The small recall
  gain did not improve multi-hop composition or justify the added noise.
- Conclusion: page routing does omit useful evidence, but retrieving all pages is neither precise nor
  scalable. The diagnostic was reverted. Next, expose more of each existing page's recall-oriented facts
  to the router without changing the rendered answer context.

### Iteration 2 — fuller routing recall index

- Hypothesis: the ten-line-per-page routing index hides useful later timeline and detail rows. Temporarily
  raise the routing recall allowance to 24 lines per page; page rendering and source selection remain
  unchanged.
- Next step: screen this on the fixed eight-per-category panel. Keep it only if evidence recall or QA rises
  without materially increasing rendered context, then confirm on the full set.
- Result: `locomo-mycelium-convo-2-retrieval-i02-fuller-route-index-20260811` scored `0.5836` on the
  panel versus `0.5711` for the control rows, while evidence recall was exactly unchanged at `0.5885`
  and mean input was effectively unchanged (5,434 versus 5,433 tokens). The score-only movement is answer
  variance over the same retrieved evidence, not support for the hypothesis.
- Conclusion: the router's failures are not explained by the ten-line index cap on this panel. The change
  was reverted. Next, remove redundant recall-section copies from rendered pages and measure whether a
  more concise context improves answer use without sacrificing evidence.

### Iteration 3 — remove duplicated recall rows

- Hypothesis: `page_recall_context()` repeats facts already present in the same page's Key Facts and Event
  Timeline. Removing that duplicate preamble should reduce prompt noise while preserving every fact.
- Next step: change production session rendering, benchmark rendering, and load budgeting together; screen
  on the balanced panel and retain only if evidence is preserved and answer quality does not regress.
- Result: `locomo-mycelium-convo-2-retrieval-i03-dedup-recall-20260811` was byte-for-byte equivalent
  to Iteration 2 for rendered contexts and metrics (`0.5836` score, `0.5885` recall, 5,434 tokens).
  Inspection showed `page_recall_context()` already returned empty for the generated pages: entering a
  nested `###` subsection cleared the enclosing `## Key Facts` or `## Event Timeline` state.
- Conclusion: the proposed duplicate did not exist in practice, so the rendering edits were reverted.
  More importantly, the same parser bug silently removed recall facts from the router index. Next, fix
  hierarchical section parsing and measure the actual routing/context effect.

### Iteration 4 — preserve nested recall subsections

- Hypothesis: nested headings should organize a recall section, not terminate it. Keep the active recall
  section across deeper headings and clear it only at a peer or higher non-recall heading.
- Next step: add a focused nested-section test and screen the fix. Inspect page choices and input growth as
  well as evidence recall; if the recall preamble becomes noisy, separate routing recall from rendering in
  the following cycle rather than undoing the parser correction.
- Result: `locomo-mycelium-convo-2-retrieval-i04-nested-recall-20260811` scored `0.6015` on the panel,
  with evidence recall `0.6042`, versus control `0.5711` / `0.5885`. Page choices changed on 21 of 32
  questions; notably, a formerly empty alias query now reached both person pages. Adversarial score rose
  from `0.8750` on the panel control to `1.0000`.
- Cost and conclusion: mean input grew by 908 tokens because the repaired parser also activated a recall
  preamble that repeats rows already present in each page. The hierarchical parser correction is kept;
  next, retain its routing index while eliminating duplicate page rendering.

### Iteration 5 — route with recall rows, render each fact once

- Hypothesis: the routing gain comes from the repaired recall index, not from repeating the same Key Facts
  and Event Timeline at the top of selected pages. Render only canonical page content while retaining the
  nested-section parser and routing index.
- Next step: screen on the same panel. Evidence recall should remain near Iteration 4 while input returns
  toward control; then run the combined parser/rendering change on all questions if the score is stable.
- Result: `locomo-mycelium-convo-2-retrieval-i05-route-recall-render-once-20260811` retained evidence
  recall `0.6042`, reduced mean input from Iteration 4's 6,342 to 5,652 tokens, and scored `0.6163`.
  Against the original panel control, recall is `+0.0156`, score is `+0.0452`, and input is only 218 tokens
  higher because the improved router sometimes loads more useful pages.
- Conclusion: keep hierarchical recall parsing for routing and render canonical page facts once. This is
  the best supported configuration so far. Next, improve ranking inside selected pages' canonical logs.

### Iteration 6 — IDF- and entity-weighted source windows

- Hypothesis: counting every overlapping query term equally lets common vocabulary dominate rare event
  cues. Rank source lines with corpus IDF, but boost capitalized query entities so a rare action cannot
  transfer evidence between people.
- Next step: add focused ranking tests and screen on the panel. Evidence recall is the primary measure;
  revert if IDF changes answers without increasing cited-turn coverage.
- Result: `locomo-mycelium-convo-2-retrieval-i06-idf-source-20260811` raised evidence recall from
  `0.6042` to `0.7500` and complete-evidence questions from `0.5312` to `0.6875`. Panel score was `0.5767`,
  below Iteration 5's unusually strong `0.6163` answer sample but still above the original `0.5711`
  control. Retrieval newly recovered cited turns for Gina's tattoo, business motivation, favorite dance
  memory, and festival participation.
- Qualitative finding: two score regressions were precision/use failures rather than missing evidence. A
  temporal answer returned `yesterday` despite available conversation time, and a broad mixed-speaker
  transcript window encouraged transfer of Gina's dance-piece fact to Jon. Keep IDF ranking provisionally;
  next reduce each source window's span without reducing the six-session candidate count.

### Iteration 7 — narrower canonical source windows

- Hypothesis: 2,200-character symmetric windows often contain several unrelated speaker turns. A
  900-character window should retain the matched evidence turn while reducing cross-person and adjacent-
  event contamination.
- Next step: screen the narrower windows on the same panel. Seek higher adversarial/QA precision with most
  of Iteration 6's evidence recall and lower prompt size; revert if cited-turn recall falls sharply.
- Result: `locomo-mycelium-convo-2-retrieval-i07-narrow-source-20260811` reduced mean input to 3,399
  tokens and scored `0.6202`, but evidence recall collapsed from `0.7500` to `0.5234`; complete-evidence
  questions fell from `0.6875` to `0.4375`, and multi-hop score fell to `0.2401`.
- Conclusion: the high QA score rewards concise contexts but masks unacceptable information loss. Reject
  the 900-character window. Next, test a 1,400-character midpoint to locate a better recall/precision
  balance while keeping IDF source ranking.

### Iteration 8 — medium canonical source windows

- Hypothesis: 1,400 characters may exclude distant unrelated turns while preserving most multi-turn
  evidence that 900 characters cut away.
- Next step: screen the midpoint on the same panel. Prefer direct evidence recall and multi-hop preservation
  over a score gain caused only by shorter prompts; retain only if it improves the tradeoff over both 900
  and 2,200 characters.
- Result: `locomo-mycelium-convo-2-retrieval-i08-medium-source-20260811` reached evidence recall
  `0.7031`, complete-evidence rate `0.6562`, score `0.5910`, and mean input 4,267 tokens. Relative to the
  2,200-character IDF run, it gives up 0.0469 recall while saving 1,400 tokens and improving score by
  `0.0143`; relative to the original control it gains 0.1146 recall while using 1,167 fewer tokens.
- Conclusion: retain 1,400-character source windows. Next, reduce page-gating misses with one conservative
  candidate derived from canonical active claims rather than broad page expansion.

### Iteration 9 — one claim-backed page candidate

- Hypothesis: an active claim whose text strongly overlaps at least two weighted query terms can identify a
  relevant assigned page that the LLM router omitted. Add at most one such page; do not expand on a single
  generic term and do not render claims separately.
- Next step: factor the proven lexical weighting into a shared helper, add a focused routing test, and screen
  the candidate augmentation. Keep it only if evidence recall improves without recreating all-page noise.
- Result: `locomo-mycelium-convo-2-retrieval-i09-claim-page-candidate-20260811` was identical to
  Iteration 8 in score (`0.5910`) and evidence recall (`0.7031`) while adding 152 mean tokens. It changed
  six page sets, frequently adding an adjacent but wrong-person page, without recovering any cited turn.
- Conclusion: reject and remove claim-to-page augmentation. Keep the shared lexical weighting because it is
  the retained source ranker's implementation. Next, remove the page gate at the evidence tier itself by
  searching canonical logs across the already-scoped memory store.

### Iteration 10 — store-scoped global source candidates

- Hypothesis: wiki pages should organize synthesized knowledge, but their backlinks should not be the only
  first-stage index for canonical evidence. Rank all logs in the configured store, retain the same six
  source windows, and attach them to the highest-priority loaded page for rendering.
- Next step: add a focused test proving an unlinked but relevant log can be selected, run the balanced panel,
  then either revert or promote the best retained configuration to a full 105-question confirmation.
- Result: `locomo-mycelium-convo-2-retrieval-i10-global-source-20260811` increased evidence recall only
  from `0.7031` to `0.7135`, left complete-evidence rate unchanged at `0.6562`, and used essentially the
  same input. Score fell from `0.5910` to `0.5632`, with adversarial score falling from `0.8750` to
  `0.7500` as globally similar evidence about the wrong person entered context.
- Conclusion: reject global raw-log candidates. Removing the page gate remains desirable, but direct
  evidence search needs structured subject/entity constraints rather than lexical relevance alone. Revert
  to page-scoped logs and run the best retained stack on all 105 questions.

### Full confirmation — best retained retrieval stack

- Configuration: nested recall sections are visible to the router; selected pages render canonical facts
  once; page-scoped source windows use IDF plus named-entity weighting; each of up to six windows is capped
  at 1,400 characters.
- Next step: run all questions against the exact frozen store, compare with the fresh full control, inspect
  category and evidence-recall deltas, then complete backend validation and record remaining retrieval risks.
- Result: `locomo-mycelium-convo-2-retrieval-best-full-20260811` scored `0.5547` across all 105
  questions, versus fresh control `0.5458` and historical checkpoint `0.5620`. Mean labeled-evidence recall
  rose from `0.6546` to `0.7029`, complete-evidence questions from `0.6286` to `0.6762`, and mean QA input
  fell from 5,463 to 4,281 tokens (`-21.6%`). The final score is `+0.0089` over the same-day control and
  only `-0.0073` from the historical run, within the established `0.02` variance tolerance.
- Retrieval gains were concentrated where they matter most: multi-hop evidence recall rose from `0.3394`
  to `0.4818`, with all cited turns present rising from `0.0909` to `0.2727`. Open/common recall rose from
  `0.6591` to `0.7159`, and adversarial recall from `0.6667` to `0.7500`. Single-hop recall fell from
  `0.7692` to `0.7308`, identifying the main regression to monitor on additional conversations.
- Qualitatively, the final stack recovered Gina's tattoo, favorite dancing memory, store status, business
  motivation, grand-opening comments, and complementary multi-person evidence. Six questions lost some
  cited-turn coverage, including a mentorship date and two multi-fact studio questions; shortening source
  windows remains a lossy tradeoff rather than a universally better ranker.

### Findings and next steps

- Kept: hierarchical recall-section parsing, routing-only recall summaries, single-copy page rendering,
  shared IDF/entity lexical weighting, 1,400-character page-scoped source windows, direct retrieval-evidence
  benchmark metrics, and balanced category panels.
- Rejected: all-page loading, raising an ineffective line cap, 900-character windows, claim-to-page lexical
  augmentation, and unconstrained global raw-log search. Rejected code paths were removed rather than kept
  as fallbacks.
- Highest-impact next retrieval experiment: use canonical claims to constrain candidate source segments by
  exact subject/entity and temporal status, then rank only the surviving evidence globally. This directly
  addresses the wrong-person failures from Iteration 10 without restoring page gating. Evaluate candidate
  and selected evidence recall separately, particularly for multi-hop questions.
- Separately, answer synthesis still leaves retrieved value unused: it sometimes returns relative dates,
  incomplete lists, or paraphrases despite complete evidence. Treat that as an answering-stage project,
  not as justification to expand retrieval context.

## 2026-08-11 — Wiki-page FTS retrieval iteration series

Goal: evaluate SQLite FTS5 as a page-level candidate index while preserving the wiki as the coherent
retrieval and human-facing unit. Use the same exact frozen `conv-30` store, `gemma4:12b`, direct labeled-
evidence metrics, and the fixed eight-per-category panel. Change one page-search decision per iteration,
remove rejected paths, and promote promising candidates to all 105 questions.

### Control

- SQLite FTS5 is available through Python's standard `sqlite3`; no package or external service is needed.
- `locomo-mycelium-convo-2-pagefts-control-20260811` exactly reproduced the retained panel behavior:
  score `0.5910`, evidence recall `0.7031`, complete-evidence rate `0.6562`, mean input 4,267 tokens, and
  mean retrieval construction time 3.19 seconds.

### Iteration 1 — augment the LLM route with one full-page FTS hit

- Hypothesis: full-page FTS can repair a page omitted by semantic routing without losing the router's
  coherent multi-page choices. Add at most one missing FTS page; source retrieval remains page-scoped.
- Next step: implement a lazily refreshed in-memory FTS5 page index, test rebuild/search behavior, and run
  the balanced panel. Revert augmentation if it adds context without evidence-recall benefit.
- Result: `locomo-mycelium-convo-2-pagefts-i01-augment-fullpage-20260811` was identical to control in
  score (`0.5910`) and evidence recall (`0.7031`) while mean input rose from 4,267 to 4,472 tokens. Seven
  page sets changed, each by adding a broad adjacent person page without recovering any cited turn.
- Conclusion: reject LLM-route augmentation. Keep the tested FTS index as experimental infrastructure and
  next evaluate FTS as the sole first-stage router, where it can reduce latency rather than duplicate pages.

### Iteration 2 — full-page FTS-only routing, top three

- Hypothesis: three BM25-ranked full pages can preserve coherent context while eliminating the query-time
  LLM routing call. Exact entity/title fallback remains as a deterministic safeguard within page retrieval.
- Next step: replace LLM routing with FTS top three on the panel. Compare evidence recall, page count, input,
  and memory-construction latency; reject if removing semantic routing causes a material quality loss.
- Result: `locomo-mycelium-convo-2-pagefts-i02-only-top3-20260811` preserved evidence recall
  `0.7031` and complete-evidence rate `0.6562` exactly. Retrieval construction time fell from 3.19
  seconds to 0.012 seconds, but average loaded pages rose from 2.16 to 3.22, mean input grew from 4,267
  to 5,044 tokens, and score fell from `0.5910` to `0.5712`.
- Conclusion: FTS-only page routing is promising for latency and direct evidence, but top three
  over-retrieves. Next, test two full pages to reduce noise without reintroducing an LLM call.

### Iteration 3 — full-page FTS-only routing, top two

- Hypothesis: two BM25-ranked pages will preserve the relevant parent pages on this store while returning
  context volume toward the LLM-router baseline.
- Next step: run the same panel with a two-page FTS cap. Retain as the working candidate if evidence recall
  remains stable and the score/input tradeoff improves over top three.
- Result: `locomo-mycelium-convo-2-pagefts-i03-only-top2-20260811` preserved evidence recall
  `0.7031` and complete-evidence rate `0.6562`, scored `0.5937` versus control `0.5910`, and used
  4,661 mean tokens. Retrieval construction averaged 0.011 seconds versus control 3.19 seconds.
- Conclusion: top-two FTS is the first promising page-index candidate. Promote it immediately to all 105
  questions before further tuning; retain it as the working base only if full-run quality holds.

### Iteration 3 long confirmation — full-page FTS top two

- Hypothesis: the panel's exact evidence preservation and approximately 293-fold routing latency reduction
  will hold across the full question set without a precipitous score or multi-hop regression.
- Next step: run all 105 frozen-store questions, inspect category-level evidence recall and score, then
  continue page-index iterations from this base only if it passes the established `0.02` score tolerance.
- Result: `locomo-mycelium-convo-2-pagefts-i03-top2-full-20260811` scored `0.5953`, versus the
  retained LLM-router full run's `0.5547` and historical checkpoint `0.5620`. Evidence recall rose from
  `0.7029` to `0.7314`, complete-evidence rate from `0.6762` to `0.7048`, and retrieval construction
  fell from 2.56 seconds to 0.011 seconds. Mean input was 4,650 tokens versus 4,281.
- Category evidence recall improved for single-hop (`0.7308 → 0.7692`), open/common
  (`0.7159 → 0.7386`), and adversarial (`0.7500 → 0.7917`), while multi-hop held at `0.4818`.
- Conclusion: full-page FTS top two passes the long-run gate and becomes the working mechanism. Continue
  optimizing its precision and context cost without restoring the LLM router.

### Iteration 4 — full-page FTS-only routing, top one

- Hypothesis: one BM25 page plus deterministic exact entity/title matches may retain most evidence while
  reducing the 369-token input increase and extra broad pages seen with top two.
- Next step: screen top one on the balanced panel. Revert if evidence recall or multi-hop coverage falls
  materially; otherwise promote the smaller configuration to a long run.
- Result: `locomo-mycelium-convo-2-pagefts-i04-only-top1-20260811` preserved evidence recall
  `0.7031` and complete-evidence rate `0.6562`, scored `0.6138`, used 4,235 mean tokens, and averaged
  0.010 seconds retrieval construction. Exact entity/title matches still add explicitly named pages, so
  top one is the lexical relevance seed rather than an absolute page ceiling.
- Conclusion: top one improves the panel tradeoff over top two and merits an immediate full confirmation.

### Iteration 4 long confirmation — full-page FTS top one

- Hypothesis: one FTS seed plus exact entity/title pages will retain the full-run evidence improvement of
  top two while reducing unrelated second-page context.
- Next step: run all 105 questions and compare especially multi-hop evidence recall, empty-context rate,
  and adversarial score before choosing the retained page cap.
- Result: `locomo-mycelium-convo-2-pagefts-i04-top1-full-20260811` scored `0.5691`, with evidence
  recall `0.7124`, complete-evidence rate `0.6857`, and 4,256 mean input tokens. Compared with top two,
  score fell `0.0263` and evidence recall fell `0.0190`.
- Conclusion: reject top one despite its strong panel result. The second FTS-ranked page contributes useful
  long-tail evidence. Restore top two and improve page precision through section-level indexing.

### Iteration 5 — section-level FTS with parent-page retrieval

- Hypothesis: full-page BM25 can combine unrelated terms from distant sections and favor broad pages.
  Index each Markdown section independently, rank section-local matches, then return the two best distinct
  parent pages.
- Next step: add deterministic Markdown-section tests and screen top-two parent aggregation on the panel.
  Keep only if it improves evidence or context precision over full-page top two.
- Result: `locomo-mycelium-convo-2-pagefts-i05-sections-top2-20260811` kept evidence recall
  `0.7031` and complete-evidence rate `0.6562`, but score fell to `0.5527` and mean input rose to
  4,746 tokens. Retrieval construction remained fast at 0.011 seconds.
- Conclusion: reject section indexing. The generated wiki headings are useful presentation structure but
  not reliable independent retrieval boundaries; useful query facets often span sections on one coherent
  page. Restore full-page FTS and next remove the redundant exact entity/title expansion to see whether
  the title-weighted index can enforce the two-page cap by itself.

### Iteration 6 — full-page top two without entity expansion

- Hypothesis: FTS already indexes page titles at eight times the body weight, so the separate token-overlap
  entity expansion may add adjacent pages beyond the validated two-page cap without recovering evidence.
- Next step: make the title-weighted full-page index the sole page-selection mechanism and run the panel.
  Restore explicit entity expansion only if direct evidence coverage or answer quality materially declines.
- Panel result: `locomo-mycelium-convo-2-pagefts-i06-no-entity-expansion-20260811` preserved evidence
  recall `0.7031`, scored `0.6067`, and reduced mean input to 4,226 tokens. This was promising enough for
  immediate full confirmation.
- Full result: `locomo-mycelium-convo-2-pagefts-i06-no-entity-full-20260811` scored `0.5825`, used
  4,183 mean input tokens, and retained 0.010-second retrieval construction, but evidence recall fell from
  the retained top-two run's `0.7314` to `0.7010`; complete-evidence rate fell from `0.7048` to `0.6762`.
- Conclusion: reject complete removal. The extra named-page selections recover real long-tail evidence even
  though the fixed panel did not expose it. Replace unconstrained partial title-word expansion with an
  exact full-title rule integrated into the FTS rank and keep the two-page cap.

### Iteration 7 — exact full-title priority within top two

- Hypothesis: when all meaningful title terms occur in the query, that page should displace a weaker BM25
  candidate rather than be appended after the cap. This should preserve explicitly named people/events
  while avoiding generic one-word title expansion and unbounded context growth.
- Next step: rank full title matches ahead of BM25, retain BM25 order otherwise, and screen the fixed panel.
- Panel result: `locomo-mycelium-convo-2-pagefts-i07-title-priority-20260811` matched top-two FTS at
  score `0.5937` and evidence recall `0.7031`, while mean input fell to 4,352 tokens. It therefore received
  a full confirmation.
- Full result: `locomo-mycelium-convo-2-pagefts-i07-title-priority-full-20260811` scored `0.5717`,
  with evidence recall `0.7124`, complete-evidence rate `0.6857`, and 4,346 mean input tokens. It recovered
  only part of the evidence lost in iteration 6 and remained below the retained `0.7314` recall.
- Conclusion: reject mandatory title precedence. A named participant should not necessarily displace the
  page best matching the question's subject. Restore top-two BM25 plus named-page expansion and next test
  whether the wiki's concise Key Facts section is a useful soft ranking feature.

### Iteration 8 — boost Key Facts within whole-page FTS

- Hypothesis: facts promoted into the concise human-facing summary are more representative of page intent
  than repeated details. Index Key Facts as a boosted field while retaining the entire page as one row.
- Next step: test a three-times Key Facts weight on the panel; reject if it merely changes ranking without
  improving direct evidence or context precision.
- Result: `locomo-mycelium-convo-2-pagefts-i08-key-facts-20260811` scored `0.5909`, retained evidence
  recall `0.7031`, and increased mean input to 4,704 tokens. No retrieval benefit appeared.
- Conclusion: reject duplicated Key Facts weighting. A concise section is not automatically a better query
  signal, and repeating its terms distorts BM25 length/frequency behavior. Keep the whole page as one field.

### Iteration 9 — exact-title expansion after top-two FTS

- Hypothesis: the retained expansion recovered long-tail evidence but matched any title token. Requiring all
  meaningful title terms to occur in the query should retain explicitly named pages while eliminating broad
  additions such as an event page matched by only “dance” or “festival.”
- Next step: append complete title matches after the two BM25 pages and compare evidence and context volume.
- Result: `locomo-mycelium-convo-2-pagefts-i09-exact-title-expansion-20260811` preserved panel score
  `0.5937`, evidence recall `0.7031`, and complete-evidence rate `0.6562`, while mean input fell from
  4,661 to 4,448 tokens versus broad title-word expansion.
- Conclusion: exact-title expansion is a promising precision improvement, but multiple named pages can
  still exceed a predictable context bound. Retain it for iteration 10 and impose a total three-page cap.

### Iteration 10 — two FTS pages plus at most one exact-title page

- Hypothesis: limiting the combined result to three pages preserves one explicit participant/event repair
  while preventing multi-name queries from expanding context without bound.
- Next step: screen the fixed panel, retain the bounded exact-title mechanism only if direct evidence remains
  unchanged, then finish with repository-wide validation and document the long-run uncertainty explicitly.
- Result: `locomo-mycelium-convo-2-pagefts-i10-bounded-title-20260811` was identical to iteration 9:
  score `0.5937`, evidence recall `0.7031`, complete-evidence rate `0.6562`, and 4,448 mean input tokens.
- Conclusion: do not promote a panel-only result. Iterations 6 and 7 demonstrated that this panel can hide
  long-tail evidence losses. Restore the fully confirmed mechanism: whole-page FTS top two followed by the
  existing non-derived page-name expansion. Carry exact-title expansion with a three-page ceiling forward
  as the highest-priority candidate for a future full run, not as production behavior.

### Retained result and next steps

- Retained run: `locomo-mycelium-convo-2-pagefts-i03-top2-full-20260811`, score `0.5953`, evidence
  recall `0.7314`, complete-evidence rate `0.7048`, mean input 4,650 tokens, and mean retrieval construction
  time 0.011 seconds. Compared with the prior LLM-router full run, score rose from `0.5547`, recall from
  `0.7029`, and complete evidence from `0.6762`, while routing became roughly 235 times faster.
- The key architectural finding is that indexing human-readable wiki pages works well as first-stage
  retrieval when the page remains the unit. Hard section boundaries, forced title precedence, and duplicated
  summary weights did not help. A second lexical page is important for long-tail and multi-page evidence.
- Next: run exact-title-plus-three-page-cap on the full set before considering it again; then improve the
  page-name expansion using typed entity mentions rather than more BM25 weight tuning. Evaluate on at least
  one additional conversation before treating the `conv-30` gain as general.
## 2026-08-11 — Temporal memory and evidence-survival iteration series

Goal: improve real answerability rather than scorer phrasing. Establish an evidence oracle and explicit
source → claim → wiki → context survival metrics, then strengthen relative-time normalization for chats and
meetings. Treat LoCoMo score as a regression alarm; inspect factual correctness, completeness, provenance,
uncertainty, and generated wiki quality directly.

### Iteration 1 — exact gold-evidence oracle

- Hypothesis: answering from only the labeled source turns establishes whether a failure remains after
  retrieval and encoding are removed, while preserving source conversation-time anchors for relative dates.
- Change: added the benchmark-only `gold_evidence` system. It indexes labeled source turns during ingestion
  and receives gold labels only in its isolated answer path; ordinary systems never see benchmark evidence.
- Result: `locomo-gold-evidence-convo-2-20260811` had 100% labeled-evidence recall but scored only `0.5728`,
  below the retained Mycelium run's `0.5953`. Qualitative inspection explains the inversion: exact cited
  turns often require adjacent conversational context, and many technically correct spans score poorly
  (`hoodie` versus `Hoodies`, or a complete paraphrase of tattoo symbolism).
- Conclusion: retain the oracle as a qualitative diagnostic, not a numerical ceiling. A future oracle may
  add bounded neighboring turns for deictic references, but no production code should optimize its wording.

### Iteration 2 — provenance survival through every memory stage

- Hypothesis: aggregate retrieval recall hides whether evidence disappeared during extraction, page routing,
  or query-time selection. Track labeled provenance independently at source, active claim, existing wiki
  assignment, and rendered context stages without using labels to influence those stages.
- Change: benchmark adapters now construct stage-label sets from stored source metadata and claim provenance.
  The benchmark consumes and removes those diagnostic sets after answering and reports per-stage recall.
- Result: `locomo-mycelium-convo-2-evidence-survival-panel-20260811` measured source `1.0000`, active claim
  `0.8854`, existing wiki assignment `0.8854`, and final context `0.7031` recall. Complete-evidence question
  rates were `1.0000`, `0.8438`, `0.8438`, and `0.6562` respectively.
- Conclusion: both encoding and retrieval matter. About 11.5% of labeled turn provenance is lost before an
  active routed claim exists on this panel, while another 18.2 points disappear between the wiki and prompt.
  These are provenance-survival metrics, not semantic correctness; the next temporal work must preserve
  complete arguments and dates, not merely attach a source ID.

### Iteration 3 — one explicit temporal interval record

- Hypothesis: loose sibling keys (`when`, `normalized_date`, `date_precision`, and
  `normalization_anchor`) allow inconsistent partial states and cannot represent uncertainty or intervals.
- Change: normalization now emits one nested `facets.temporal` record with the original expression and
  anchor, normalized anchor date, start/end bounds, precision, resolution status, and certainty. Projection
  consumes only this record; legacy date keys are removed rather than maintained as a second mechanism.
- Result: focused artifact, encoder, and projection suites passed (`39 passed`). Day, month, and year values
  retain both their source wording and their honest interval precision.
- Conclusion: retain the schema. It is inspectable enough for meeting deadlines and expressive enough for
  exact points, ranges, and unresolved phrases without pretending every expression is a single date.

### Iteration 4 — exact quantified relative offsets

- Hypothesis: meeting commitments commonly use deterministic offsets such as “in three days” and “two
  weeks ago”; resolving these at ingestion is safer and cheaper than asking the answer model repeatedly.
- Change: added bounded word/numeric quantities for days and weeks, `ago`/`later`/`from now`, plus “the day
  before yesterday” and “the day after tomorrow.” All resolve against the source occurrence anchor.
- Result: focused temporal suites passed (`43 passed`), including positive and negative offsets and preserved
  exact certainty.
- Conclusion: retain deterministic offset arithmetic. Unsupported or unanchored expressions remain explicit
  unresolved temporal records rather than being guessed.

### Iteration 5 — calendar-aware weeks, months, and weekdays

- Hypothesis: representing “last week” as one day exactly seven days earlier is false precision. Calendar
  periods should be complete intervals, while explicitly modified weekdays can remain point dates.
- Change: last/this/next week now resolve to ISO Monday–Sunday bounds; month expressions resolve to full
  calendar bounds across month/year rollover; last/this/next weekdays resolve within their stated calendar
  relation.
- Result: focused suites passed (`50 passed`), including leap-safe month lengths, year rollover, and current-
  week weekday behavior.
- Conclusion: retain calendar intervals. At the five-iteration checkpoint, the temporal foundation is sound;
  the next risk is vague language and deadline intent, not date arithmetic.

### Iteration 6 — bounded versus genuinely vague time

- Hypothesis: forcing every relative phrase to a point date produces misleading memory. Useful approximate
  ranges should be explicit, while phrases with no defensible bounds should remain unresolved.
- Change: “early/late/sometime next week,” “later this week,” and quantified `few`/`several` day or week
  phrases become `bounded` approximate intervals. “Soon” and “recently” remain unresolved with future/past
  direction only. Projection labels approximate ranges visibly.
- Result: focused suites passed (`58 passed`). No unbounded phrase receives an invented calendar date.
- Conclusion: retain the certainty policy. It provides useful near-term search bounds without hiding that the
  original speaker was imprecise.

### Iteration 7 — meeting-anchored deadlines

- Hypothesis: a commitment deadline is semantically different from the event or observation time, and meeting
  language often uses bare weekdays or end-of-period expressions.
- Change: temporal records now carry `role=deadline|event_time`. The extractor prompt preserves deadlines in
  `facets.deadline`; the deterministic resolver handles bare weekdays, end of this/next week or month, and
  exact `in N days/weeks` offsets. Weekday modifiers use adjacent ISO calendar weeks. Projection labels due
  dates as deadlines instead of event dates.
- Result: focused suites passed (`66 passed`), plus an encoder integration test anchored “by Friday” from a
  `2024-01-10T14:00:00-08:00` meeting to `2024-01-12` while retaining the original time-zone-bearing anchor.
- Conclusion: retain first-class deadline intent. This is directly useful for meeting action items and avoids
  confusing “the commitment was discussed Wednesday” with “the work is due Friday.”

### Iteration 8 — temporal identity in reconciliation and projection

- Hypothesis: text-identical commitments with different due dates must not be merged as duplicates, while
  different wording that resolves to the same due date should merge safely.
- Change: deterministic claim reconciliation now requires matching temporal signatures. Signatures compare
  role, resolution status, certainty, and normalized bounds—not anchors or surface wording. Reconsolidation
  excludes candidates with conflicting temporal roles, ranks matching temporal roles, and shows intervals to
  the classifier. Approved deadline supersession regenerates pages from active canonical claims.
- Result: temporal reconciliation/projection suites passed (`72 passed`). An end-to-end review test confirmed
  that approving a deadline move removes the old due date and renders only the new deadline.
- Conclusion: retain temporal identity. Deadline changes now enter the existing reviewable reconsolidation
  workflow instead of silently overwriting facets or coexisting as indistinguishable duplicate bullets.

### Iteration 9 — interval-aware claim and source retrieval

- Hypothesis: page text alone cannot reliably answer queries such as “What deadlines are due next week?”
  because neither the query's absolute interval nor a claim's normalized interval has to appear in the
  generated prose.
- Change: retrieval now resolves temporal query phrases against query time, scans active claims for
  overlapping normalized intervals, and prioritizes their assigned pages. Deadline queries require a
  deadline-role claim. Provenance-linked raw logs from matching claims are also preferred when source
  windows are selected; ordinary questions continue through the retained two-page FTS route.
- Result: focused tests confirmed inclusive interval overlap, deadline-role filtering, claim-backed page
  recovery despite zero useful lexical overlap, and provenance-backed source preference. The unchanged
  frozen panel, `locomo-mycelium-convo-2-temporal-retrieval-panel-20260811`, reproduced the retained
  result exactly: score `0.5937`, evidence recall `0.7031`, complete-evidence rate `0.6562`, and mean input
  4,661 tokens. Its stage survival remained source `1.0000`, claim/wiki `0.8854`, context `0.7031`.
- Conclusion: retain the temporal branch. It adds structured recall for real temporal questions without
  perturbing ordinary retrieval. The frozen LoCoMo store predates the new temporal records, so this run is
  a regression check rather than a gain measurement; newly encoded temporal conversations are the relevant
  quality test.

### Iteration 10 — live meeting artifact smoke test

- Hypothesis: deterministic unit tests are insufficient if the extractor does not preserve the temporal
  wording and intent needed by the normalizer when processing a realistic meeting transcript.
- Change: ran a six-turn meeting through the real configured Ollama encoder and Dream pipeline with a
  timezone-bearing occurrence anchor. The transcript included `today`, `by Friday`, `early next week`,
  `in three days`, `next month`, and `soon` across plans, commitments, and preferences.
- Result: `temporal-meeting-smoke-20260811-v1` produced six grounded active claims, six routed wiki pages,
  100% segment/accounted coverage, no unassigned claims, no pending sources, and no failures. `by Friday`
  became an explicit deadline on `2026-08-14`; `early next week` became the visibly approximate
  `2026-08-17`–`2026-08-19` interval; `next month` retained the full September interval; and `soon` remained
  unresolved. The generated wiki displayed the source phrasing beside normalized dates and never invented
  a date for the vague statement. `in three days` remained an event/completion date rather than being
  upgraded to a deadline without explicit due-date wording. Three real QA calls then returned `2026-08-14`
  for the deadline due this week, `the design review` for what is scheduled early next week, and
  `publish the release notes` for the plan that is “soon” but has no definite date. Their first retrieved
  pages were respectively `budget-planning`, `design-review`, and `release-notes`.
- Conclusion: retain the end-to-end design. Relative-time fidelity now survives source → claim → wiki on a
  realistic meeting input. The next high-value evaluations are re-encoding a full benchmark store so
  temporal recall can be measured on populated records, expanding coverage to quarters/seasons and explicit
  date ranges only when real inputs demonstrate need, and adding user-facing “upcoming deadlines” views on
  top of the same canonical claims rather than another date store.

### Fresh full end-to-end checkpoint

- Run: `locomo-mycelium-convo-2-fresh-temporal-e2e-20260811`, freshly encoded from all 19 sessions with
  `gemma4:12b` for memory and QA, per-batch Dream, the retained two-page FTS route, and all 105 questions.
  No frozen or replayed artifacts were used.
- Result: score `0.6148`, up from the retained frozen-store retrieval checkpoint's `0.5953`. Evidence recall
  rose from `0.7314` to `0.7679`, and complete-evidence questions rose from `0.7048` to `0.7333`. The
  temporal/single-hop category rose sharply from `0.6361` to `0.8368`; multi-hop moved from `0.3636` to
  `0.3455`, commonsense/open-domain from `0.4312` to `0.4091`, and adversarial from `0.9583` to `0.8750`.
- Temporal quality: the current pipeline correctly resolved Jon's banker job loss to `19 January 2023`, a
  festival planned “next month” from 20 January to February, Gina's internship acceptance to 27 May, and a
  Rome trip described as “last week” to a June interval. The fresh store contains 31 temporal records, 23
  with resolved bounds. Some QA errors remain despite correct canonical claims: the May dance-competition
  interval was present but answered as April, and a June 20 opening-night claim was answered as June 21.
  A July 14 answer for “last Friday” relative to Sunday July 23 is technically grounded even though the
  benchmark reference says July 21.
- Artifact quality: all 19 logs eventually consolidated; 187 claims were routed with no unassigned claims,
  and claim/wiki labeled-evidence survival reached `0.7502`. Accounted segment coverage rose from `0.8078`
  to `0.9035`, largely because 898 segments were explicitly ignored rather than because more segments backed
  claims: claimed segments were essentially unchanged at 207 versus 208. Fifteen of 19 episodes are still
  partial. Dream also retried routing outputs that exceeded the eight-page limit and malformed
  reconsolidation decisions before every source eventually consolidated.
- Interpretation: this is a valid current-code baseline and demonstrates a meaningful temporal gain, but it
  does not settle the next architectural change. The reported adversarial decline includes benchmark
  inconsistencies: the source explicitly says Jon took a temporary job even though the adversarial reference
  expects `None`, and the benchmark asks the identical Gina-trophy question once with `a trophy` and once
  with `None`. Actual answer and artifact quality therefore remain more informative than the category score.

## 2026-08-11 — Bounded memory-agent and tool-calling experiment

- Hypothesis: the chat model can answer ordinary questions from the existing two-page retrieval context,
  then selectively search canonical claims, follow claim relationships, or inspect exact provenance for
  questions whose evidence is incomplete or requires multiple hops.
- Change: added three read-only, bounded memory tools: `memory_search` over active claims,
  `memory_expand` over explicit links/shared subjects/pages/sources, and `memory_sources` over supporting
  source segments with at most one neighbor. Ollama's existing tool loop now accepts injected definitions
  and sync or async runners. A benchmark-only `memory_agent` adapter records every tool call and result size;
  production retrieval is unchanged.
- Smoke result: on a four-question frozen-store smoke set, the evidence agent found a second valid answer to
  what Jon and Gina share—both pursued entrepreneurship after job loss—in addition to their shared use of
  dance for stress relief. The final QA pass discarded that extra fact, exposing a lossy handoff rather than
  an evidence-availability failure.
- Balanced panel: on the same frozen store and 20 category-balanced questions, ordinary Mycelium scored
  `0.6845` with 4,683 mean input tokens and 2.92-second mean query time. The evidence-agent condition scored
  `0.6890`, used tools on 5/20 questions (8 searches and 3 source inspections), consumed 9,902 input tokens,
  and took 14.49 seconds per query. Evidence recall was identical at `0.6208`, as expected because the stage
  metric measures the initial rendered context rather than dynamically selected evidence.
- Qualitative result: tool use recovered the missing waterfront/ocean requirement for Jon's ideal studio and
  the agent synthesis combined it with natural light and a safe dance floor. The final answer still omitted
  the latter details, so the artifact-level improvement was real but the delivered answer remained partial.
  The agent also searched unnecessarily for two already-answerable favorite-dance questions and correctly
  failed to invent answers for an unsupported painting preference and the benchmark's `Jean`/`John` naming
  mismatch. It did not consistently invoke tools for the most important shared-property question.
- Direct-agent attempt: letting Gemma4 answer directly through Ollama's native tool loop removed the lossy
  second pass and reduced mean input to 4,858 tokens and latency to 6.26 seconds, but it made zero tool calls
  and became overly conservative (`0.4223`). Combining tools, thinking, and the grounded-answer JSON schema
  yielded empty final content on most questions, again with zero calls (`0.2623`). This failed protocol
  variant was reverted rather than retained as a fallback.
- Conclusion: the read-only exploration tools are useful and retained, but an always-on autonomous memory
  agent is not yet justified for the current local model. The panel produced genuine missing evidence but no
  meaningful aggregate or consistent answer-quality gain at roughly 2.1x input and 5x latency. The promising
  direction is selective escalation: keep ordinary retrieval as the fast path, use an explicit bounded
  retrieval plan for detected multi-hop/evidence-gap cases, and let one final grounded QA pass consume the
  gathered evidence. A stronger chat model with reliable native tool selection may eventually collapse the
  planner and answerer into one loop. No full 105-question run was performed because the balanced panel did
  not meet the threshold for a promising candidate.

### Selective escalation follow-up

- Hypothesis: a deterministic structural trigger plus a schema-constrained retrieval plan can capture the
  useful part of memory-agent exploration without paying for an agent loop on ordinary questions or passing
  evidence through a lossy synthesis model. The existing grounded QA call remains the only answerer.
- Change: `memory_agent` now escalates only shared/comparison, causal, multi-attribute, and explicitly
  multi-subject questions. A structured planner emits one to four searches plus explicit expansion and
  source-inspection decisions. Execution is deterministic: five claims per search, at most six expansion
  seeds, eight expansions, four provenance seeds, 24 rendered claims, 1,400 characters per source segment,
  and 12,000 characters total. Every row records the trigger reason, validated plan, selected claim IDs,
  expansion IDs, source IDs, size, and truncation state. Non-triggered questions use the ordinary retrieval
  and QA path unchanged.
- First panel: `memory-agent-selective-panel5-20260811` scored `0.6984` versus the frozen control's `0.6845`,
  with 5,025 versus 4,683 mean input tokens and 4.13 versus 2.92 seconds. Plans escalated 7/20 questions.
  This preserved all fast-path answers but showed that causal and multi-attribute plans often emitted
  paraphrases rather than complementary searches.
- Plan-diversity refinement: the planner now separates subjects for shared-property questions, trigger /
  motivation / outcome for causal questions, and distinct implied dimensions for multi-attribute questions.
  `memory-agent-selective-diverse-panel5-20260811` scored `0.6907`, raised context evidence recall from the
  control's `0.6208` to `0.6708`, and raised complete-evidence questions from `0.55` to `0.60`. Mean query
  time was 3.48 seconds and mean input was 5,090 tokens. The score movement below the first candidate was
  answer variance; the second candidate had materially better evidence coverage and was promoted.
- Full confirmation: `memory-agent-selective-diverse-full-20260811` escalated 16/105 questions: seven causal,
  four composition, four multiple-subject, and one multi-attribute. On those 16 questions, evidence recall
  rose from `0.5917` to `0.7010` and complete-evidence rate from `0.4375` to `0.5000`. The other 89 questions'
  evidence contexts were exactly unchanged. Overall recall rose from `0.7679` to `0.7846`, complete-evidence
  rate from `0.7333` to `0.7429`, mean input from 4,622 to 4,804 tokens, and mean query time from 2.78 to
  2.99 seconds. Mean retrieval/planning construction time was 0.33 seconds.
- Answer quality: the full score moved from `0.6148` to `0.6074`, within the established `0.02` variance
  tolerance. That numerical decline is dominated by one clearly correct, more grounded answer—“Gina
  competed in several dance competitions and Jon's crew took first”—receiving zero against the expected
  bare `Yes`; that single scorer artifact is worth `0.0095` overall. Other escalated changes gave a valid
  shared contemporary-dance preference for an open-ended commonality question and replaced a generic ad-
  campaign answer with an explicitly stored promotion used by Gina. No escalated answer changed from
  supported to unsupported. Important composition gaps remain: the planner did not recover the job-loss /
  entrepreneurship commonality or all studio attributes, and complete evidence still did not guarantee a
  complete final list.
- Conclusion: retain selective planning as a benchmark-isolated promising candidate; production retrieval
  remains unchanged. It improved evidence exactly where triggered at modest aggregate cost and avoided the
  native tool loop's unreliable invocation. Before production promotion, the next highest-value experiment
  is a subject/relation-aware comparison operator or semantic candidate ranker so open-ended composition does
  not depend on lexical queries over broad person pages. Answer completeness should be evaluated separately
  rather than addressed by adding more evidence volume.

## 2026-08-12 — Milestone 1: entity-owned coherent wiki

- Replaced arbitrary slug routing followed by page taxonomy with one ownership-planning decision. Each
  admitted claim now receives one semantic owner, one section from the owner's typed contract, explicit
  linked entities, or a deliberate unassigned disposition. Ownership follows the subject whose state,
  requirements, plan, or relationship changes—not the speaker or first noun.
- Added transparent registries under `artifacts/entities`, `artifacts/placements`, and
  `artifacts/organization-proposals`. Entity IDs are stable across title/slug changes; placements keep wiki
  organization out of canonical claims; lifecycle supports active, archived, and merged identities.
- Adopted sparse creation thresholds for You, Person, Project, Topic, Organization, Place, and Event. The
  planner is instructed not to create incidental-noun pages or catchalls. A proposed evidence-count Topic
  is held unassigned unless two non-equivalent claims support it. Existing normalized identities are reused
  even if the model proposes creating the same title again.
- Rebuilt projection around stable ordered section schemas. Empty sections disappear, equivalent facts are
  compacted without losing member claim IDs, and every UI fact expands to its exact source segments. Claims
  have one home; explicit related entities produce reciprocal page links instead of copied facts. The You
  page is a canonical self profile plus generated memory map and recent-entity dashboard.
- External tool/web facts are forced into Research & References (or Event Evidence) and are visibly labeled.
  They cannot automatically establish a fact on You. Claims in unresolved contradiction/supersession
  proposals are withheld from authoritative sections and shown only under Needs Review.
- Added Wiki curation APIs and UI for identity edits, aliases, manual type correction, archive/reactivate,
  merge, split, owner/section moves, and organization-proposal review. Generated Markdown remains read-only;
  factual correction and source retraction intentionally remain a later claim-level milestone.
- Made **Clear Wiki** the explicit schema boundary: it preserves sources and claims, removes entity-owned
  derived artifacts and retired `page_slugs` metadata, marks logs unconsolidated, and seeds a new You entity.
  Old pages without entity metadata fail clearly rather than entering a compatibility path.
- Final validation: `uv run pytest -q` passes all 215 tests with 2 optional skips, and the
  production UI completes `npm run build`. Benchmark and artifact-quality results follow below after the
  fresh current-schema run.

### Ownership contract hardening and replay findings

- The first frozen-extraction replay exposed a contract failure rather than an information-loss problem:
  the model returned `unassigned` while also filling owner/section fields. Strict validation rejected 46
  claims and, before exact subject routing was added, the initial full run placed all 177 claims as
  unassigned. Treating this as a prompt problem would have preserved redundant state and recurring
  contradictions.
- Split entity discovery from ownership. Discovery now requires one exact decision for every source claim
  claim and uses a type-discriminated candidate schema, so a valid `Dance Studio` proposal cannot disappear
  because unrelated no-candidate rows omit a nullable field. Named meeting/conversation participants are
  seeded as People; explicit qualified surface forms are retained as aliases; type-specific evidence
  thresholds reject unsupported Topics and one-off project suggestions without continuity.
- Reduced claim placement to one semantic choice: `owner_entity` is an existing ID or empty. The old status,
  owner type, creation basis, and generated section fields were removed from the placement response. Typed
  sections now come exclusively from the deterministic claim-type mapping; UI moves can still curate them.
  Unknown owners become visible unassigned placements instead of failing an entire source.
- Added two anti-clutter invariants after inspecting generated artifacts. An automatically discovered entity
  is persisted only if it actually owns a claim, eliminating empty pages such as `Business`, `Rome`, and
  `Jon's Business Venture` that were merely linked. A proposed owner must also be grounded in the standalone
  normalized claim/about envelope; this moved a tangential bulletin-board observation out of Clothing Store
  and into explicit unassigned review.
- Added archived-entity visibility and one-click reactivation to the Wiki UI. The final curation surface now
  covers rename/slug/aliases/type, archive/reactivate, merge, split, per-fact owner/section moves, exact
  source inspection, and organization-proposal approval/rejection.

### Benchmark and artifact-quality check

- Diagnostic replay `locomo-mycelium-convo-2-entity-wiki-discovery-replay-20260812` used the frozen 177-claim
  store and 20 questions. It scored `0.5228`, with retrieval evidence recall `0.8292`, complete-evidence rate
  `0.8000`, and wiki evidence survival `0.9833`. This improved over the earlier entity-wiki replay smoke
  (`0.4609`, retrieval recall `0.7292`) but still produced only broad Person pages plus Festival.
- After separating discovery and simplifying ownership, the clean 20-question replay
  `locomo-mycelium-convo-2-entity-wiki-final2-replay-20260812` scored `0.5334`. Evidence recall remained
  `0.8292`, wiki survival remained `0.9833`, and mean QA input fell from 5,399 to 4,815 tokens. It produced
  coherent Dance Studio, Clothing Store, Festival, and Dance Competition pages in addition to Jon/Gina;
  Dance Studio owned 12 claims and Clothing Store six in that stochastic run.
- Final grounding smoke `locomo-mycelium-convo-2-entity-wiki-grounded-replay-20260812` reran all 19 sessions
  and the first five questions after the anti-clutter invariants. All 177 claims received terminal
  placements, all logs consolidated, and every persisted entity owned evidence: Jon 89, Gina 62, Dance
  Studio 15, Clothing Store five, Dance Competition two, and Finding Freedom one. There were 174 placed and
  three inspectable unassigned claims; the unrelated bulletin-board fact was one of them. Wiki evidence
  survival was `1.0000` on the five-question smoke. Its `0.4519` score is not comparable to the balanced
  20-question panel and was not used to tune answer wording.
- The wiki is materially more structured, but not yet concise enough: Jon and Gina remain 1,654 and 1,219
  Markdown lines in the final smoke because the frozen extractor often identifies a Person but omits the
  more specific project/entity role. This is evidence for Milestone 2's semantic claim/entity work, not a
  reason to add fuzzy routing fallbacks. The same run accumulated 18 transient reconsolidation validation
  failures before completing; making that decision contract reliable is the next pipeline robustness task.

### Durable short-term memory and cohort consolidation

- Made claim disposition the authoritative consolidation queue instead of treating the last seven days of
  unconsolidated Markdown logs as an implicit queue. Extracted claims are persisted immediately as `pending`;
  routing failures remain retryable; and claims without enough context become `deferred` rather than receiving
  a terminal `unassigned` result. “Short term” is therefore an organizational state, not volatile storage.
- Kept one intended consolidation mechanism. Manual, size-based, age-based, and weekly-review triggers all
  invoke the same Dream pipeline. Defaults are 50 pending/retryable claims, a 24-hour maximum pending age, a
  seven-day deferred review, and a five-minute server lifecycle check. The lifecycle also flushes idle chat
  episodes before evaluating Dream readiness; a lock prevents overlapping automatic and manual Dream runs.
- Changed entity discovery from per-source evaluation to cohort-level evaluation before source-scoped
  placement. Multiple episodes can now jointly establish a durable Project or Topic while malformed placement
  output remains isolated to its source. Normal Dreams also reopen at most 24 related deferred claims when new
  evidence shares a qualified multi-token subject, semantic slot/predicate, or substantive lexical overlap;
  sharing only a person's name is deliberately insufficient to reopen an entire backlog.
- Added immediate retrieval over pending, deferred, and retryable claims. Relevant results appear in a clearly
  labeled synthetic “Recent, unconsolidated memory” context block and memory-tool results expose both
  `memory_tier` and `consolidation_status`. These claims remain absent from Markdown wiki files until Dream
  places them, preserving wiki coherence without making recent experience unavailable to the assistant.
- Exposed queue counts, oldest timestamps, readiness reasons, and deferred-review state through the artifact
  overview and Dream readiness API, and added the same information to the Memory Inspector. Manual placement
  now updates the claim's memory tier consistently. **Clear Wiki** requeues preserved active claims so the
  canonical projection can actually be rebuilt under the queue-authoritative design.
- This is an intentional schema break: placement status is now `placed | deferred`, and the old terminal
  `unassigned` schema is not accepted. The README and entity-owned wiki architecture note document the new
  lifecycle and configuration.
- Validation: `uv run pytest -q` passes 222 tests with 2 optional skips; Ruff and MyPy pass for the backend;
  `npm run build` passes for the UI with the existing large-chunk warning; and `git diff --check` passes.

### Daily-driver executable memory specification

- Added `benchmarks/fixtures/daily_driver_v1`, a review-first benchmark modeled on Mycelium's intended use:
  sixteen assistant chats, meeting transcripts, and tool observations for one fictional user over eighteen
  days. The sources exercise delayed page discovery, mature-page updates, repeated evidence, relative dates,
  explicit correction, a wrong-workspace source retraction, and irrelevant conversational/tool noise.
- Defined gold records at each transparent memory layer: 51 source segments, 45 provenance-linked atomic
  claims, nine lifecycle checkpoints, 29 consolidated final facts, six entity-owned wiki pages, and 19
  semantic retrieval/answer probes. Exact answer phrasing is deliberately non-normative; probes specify
  required and forbidden facts and evidence instead.
- Made the benchmark a product specification rather than a single opaque score. Its rubric separates source
  retention, extraction, queue behavior, discovery, ownership, reconciliation, retraction, wiki coherence,
  provenance, retrieval, answer correctness, and negative relevance. Hard gates prevent a plausible average
  from hiding stale, retracted, misattributed, or unsupported memory.
- Added ideal Markdown pages and a review guide that makes debatable choices explicit, including Person versus
  Project ownership for roles, Grandmother/WhisperX page thresholds, how much change history the wiki should
  retain, whether direct user corrections require approval, and how retracted source audit records behave.
- Added a fixture validator and regression tests. The validator checks cross-file IDs, source-to-claim
  provenance, claim-to-fact membership, legal taxonomy sections, exactly-once fact rendering, lifecycle
  checkpoint references, semantic probe references, and agreement between structured gold and reference
  Markdown. This creates a stable schema for review before building the live benchmark runner.
- Revised the fixture after product review so simulated assistant turns behave like ordinary chat and never
  discuss pages or memory operations. Replaced the explicitly named Beacon hobby with an inferred **Family
  Oral History** Project grounded in recurring interviews, a calendar event, and a continuing next step.
- Recorded the remaining review decisions as fixture policy: every durable person receives a Person page;
  responsibilities are owned by the relevant Person (including Maya on You); WhisperX stays in Lantern's
  Research & References; resolved LANTERN-42 history moves out of Current Status; and every contradiction or
  supersession continues to require human review. Review approval still applies the operation immediately
  through the normal claim-level materialization path.
- Refined the one-owner rule for person–project roles. Continuing responsibilities now use the explicit
  `relationship` / `project_role` semantic envelope, remain canonically owned by the Person or You, and render
  deterministically on both that page and the Project's People & Organizations section using the same claim
  IDs and provenance. Ordinary linked facts and one-off action items still render only once. Endpoint-aware
  regeneration removes or updates both views together, while the daily-driver validator permits duplicate
  presentation only for facts that declare their exact `render_on` endpoints.
- Exposed canonical owner/link IDs and the shared-endpoint marker in structured wiki facts. The Wiki inspector
  labels role views, resolves edits back to the person-owned placement, preserves the linked Project, and
  restricts role ownership to Person/You. Retrieval prompt rendering deduplicates a role claim by canonical
  claim ID when both endpoint pages are loaded, so human-friendly navigation does not inflate agent context.
- Validation: all 235 backend tests pass with two optional skips; Ruff and MyPy pass; the daily-driver fixture
  validates with 45 claims and 29 consolidated facts; and the production UI build passes with its existing
  large-chunk warning.

## 2026-08-13 — Cohort scope and persisted wiki facts

### Why the wiki needed another semantic boundary

- Claim placement alone preserved evidence but forced the renderer to treat each atomic extraction as a
  user-facing fact. That made pages complete but repetitive, and it gave manual edits no durable home: either
  mutate a source claim or regenerate the prose. Added `ConsolidatedFact` as the explicit presentation layer
  between immutable claims and generated pages. It stores stable identity, synthesized text, member claims,
  owner/section/links, state, synthesis origin, confidence, rationale, and manual-edit status.
- Wiki materialization now consumes these records rather than running an implicit compaction heuristic.
  Single claims retain their normalized temporal qualifiers; compatible claims can be synthesized into one
  grounded statement; pending contradictions remain separated under review. The source claims and exact
  segment provenance remain intact underneath every fact.

### Cohort page discovery and conservative admission

- Replaced sequential entity discovery and per-source routing with one cohort scope contract. It sees source
  IDs, dates, participants, existing entities, and the full queued evidence set; declares each new candidate
  once; and assigns every claim to an existing entity, that candidate, deferred memory, or source-only history.
  Canonical and noncanonical assignments are a discriminated schema, so an empty canonical owner is impossible
  during guided generation rather than discovered after a whole run.
- Page creation remains deliberately sparse. Named Projects require an identity/naming claim plus substantive
  support; inferred Projects require continuity across sources; Topics and other page types require independent
  user relevance or recurrence. Pilots, phases, components, vendors, issues, routine meetings, and milestones
  remain subordinate to an established Project. Named meeting participants are the eager exception: they get
  a Person identity plus an encounter record, not invented biographical facts.
- Moved the objective portion of those rules out of model discretion after repeated `gemma4:12b` runs showed
  candidate omission was stochastic even when assignments correctly referred to the missing candidate. Proper
  project names with substantive support, recurring conceptual endeavor phrases across sources, named meeting
  participants, and retained family/person references are now seeded deterministically into the same cohort
  scope. The planner still decides contextual ownership. Repeated-phrase admission is limited to conceptual
  terms, excludes components/pilots/builds/milestones, and permits only one non-overlapping candidate per
  evidence cluster; this removed observed junk pages such as `Apartment Berkeley` and `Scheduled Sunday`.
- Routing and reconsolidation failures are claim-local. A valid source episode is marked processed even when
  one extracted claim needs retry or more context. Valid but low-value observations use `source_only`, keeping
  auditability without polluting the wiki.

### Human control and transparency

- Added append-only scope decisions with automatic/manual/review origin, cited supporting claims, confidence,
  rationale, run identity, and supersession. Manual placement immediately becomes the active authority.
- The Memory inspector exposes fact synthesis and scope rationale alongside exact evidence. Users can edit
  fact text, move a whole fact, group compatible facts, or split a multi-claim fact; these operations update
  the persisted fact and placements without rewriting source claims. Entity rename/type/merge/split operations
  keep the new fact layer synchronized.
- **Clear Wiki** now removes consolidated facts, encounters, and scope decisions with the other derived
  projection artifacts. This is an intentional schema boundary with no backwards-compatibility renderer.
- Reduced the default Dream queue threshold from 50 to the reviewed value of 20, retaining the 24-hour age
  trigger, seven-day deferred review, five-minute lifecycle poll, and manual Dream control.

### Evaluation findings

- The first Daily Driver attempt preserved all 41 claim-bearing source segments but admitted no Project pages.
  It exposed two contract defects rather than an extraction problem: the scope evidence omitted source IDs,
  and `canonical` assignments could carry an empty owner. A second attempt using a post-validation rule simply
  retried an error invisible to Ollama's JSON schema. Both runs are retained as diagnostic artifacts under
  `benchmark_runs/daily-driver-v1-cohort-facts*-20260813`.
- Source IDs and dates are now part of the scope evidence, and the canonical/noncanonical union encodes owner
  requirements directly in the guided schema. The release fixture run is retained at
  `benchmark_runs/daily-driver-v1-wiki-milestone1-release-gemma4-12b-20260813`. It covered all 41
  claim-bearing segments and found all six durable gold entities. More importantly, the page-discovery
  checkpoints matched the intended lifecycle: the first Dream kept only `You`; the second produced exactly
  `You`, `Lantern`, `Priya Raman`, and `Luis Ortega`; and the mature update added only `Family Oral History`
  and `Grandmother`. The wrong-workspace meeting then created transient `Omar Haddad`, as specified.
- The run also gives a useful non-score quality baseline rather than a false declaration of completion. It
  rendered 25 persisted facts across seven final pages and kept all ten source-only claims out of the wiki,
  but the provisional gold-prose diagnostic found only 15/29 wiki facts. Two late reconsolidation decisions
  failed relation/target validation, so several completion and rescheduling updates did not reach the wiki;
  the fixture's reviewed pilot-date proposal was likewise not produced. Source retraction is intentionally
  outside this milestone, so Omar remains after the unsupported retraction action. Those are the next truth-
  maintenance problems, not reasons to weaken sparse page admission or add implicit fallback routing.
- Focused backend suites, Ruff, targeted MyPy, fixture validation, and the UI production build pass. The full
  pytest process still inherits an existing Engram uploaded-audio test whose assertions complete but whose
  background executor prevents process teardown; split non-Engram suites complete normally.

### Follow-up: removal of lexical semantic routing

- Review of the release implementation found that its deterministic project seeds were not product-level
  invariants. They used repeated word pairs, a hand-selected endeavor vocabulary, explicit family-role terms,
  and special handling for the Daily Driver's oral-history scenario. Lexical grounding could then override a
  model decision to keep a claim deferred or source-only. The release benchmark remains historical evidence
  of why those rules were introduced, but it is not evidence that they were architecturally valid.
- Removed semantic seeding, inferred aliases, title-prefix rewriting, title/alias owner matching, fact-word
  neighborhood matching, continuity n-grams, and the lexical noncanonical override. No fixture entity or
  vocabulary remains in production code or prompts.
- Expanded the cohort contract so every structured meeting-speaker occurrence is resolved explicitly to
  `you`, an existing Person ID, or a declared Person candidate. Candidate admission and placement now validate
  only structured fields and evidence: creation basis, claim type, source diversity, independent scope,
  participant aliases, entity IDs/types, and role cardinality. Invalid owner or link references remain local
  to the affected claim, and `source_only` is authoritative unless a later reviewed scope decision changes it.
- Added repository-level semantic decision guardrails to `AGENTS.md`. The Daily Driver must be rerun before
  making new artifact-quality claims because removal of the fixture-shaped seeds intentionally invalidates
  the previous run as a current behavioral baseline.
- Clean run `benchmark_runs/daily-driver-v1-structured-scope-v2-20260813` covered all 41 claim-bearing
  segments, kept every source-only claim out of the wiki, and created Lantern without a lexical seed. It also
  exposed a structured admission mismatch: the model declared Person candidates for meeting speakers using
  `durable_person`, while code initially required `meeting_participant` when participant evidence was the sole
  support. Admission now accepts either allowed Person basis when an exact participant alias is cited. A
  read-only routing smoke over the completed store then produced Priya Raman, Luis Ortega, and Omar Haddad,
  seven encounters, and no routing failures. The clean run still omitted the inferred Family Oral History and
  Grandmother pages; that remains a scope-model/representation gap and was not patched with another heuristic.

## 2026-08-13 — Daily Driver Milestone 0: executable product evaluation

The Daily Driver fixture is now an executable evaluation system rather than a fixture-consistency check plus
one prose-similarity summary.

### Artifact-level rubric and gates

- Added independent results for all 17 primary rubric dimensions. The evaluator reports exact numerators,
  denominators, targets, and pass state; it intentionally does not combine them into an aggregate score.
- Made all five release gates executable through declarative fixture checks. Gates inspect checkpoint state,
  exact source evidence, distinct entity identities, claim ownership, and retrieval/answer probes rather than
  matching generated prose.
- Added checkpoint diffs for queue dispositions, entities/pages, required page facts, claim lifecycle,
  pending reconsolidation, authoritative/history state, removals, source retraction, and exact final fact
  count. Added an ownership confusion matrix, undeclared duplicate facts, structured page diffs, and explicit
  unsupported rendered claims.
- Retrieval probes now record loaded pages, generated fact and claim IDs, required/forbidden gold fact IDs,
  required/forbidden source evidence, full rendered context, the grounded answer, and a post-answer semantic
  judgment. Gold facts are exposed only to the post-answer judge, never production retrieval or answering.

### Proposition completeness

- Replaced segment coverage as the extraction-quality proxy with an additional atomic-proposition diagnostic.
  Each gold claim is one evidence-grounded proposition, and distinct propositions from one segment require
  distinct generated claims. One broad sentence cannot satisfy every assertion merely by citing the segment.
- Refreshing the 2026-08-13 audit run demonstrates why this matters: all 41 claim-bearing source segments had
  at least one generated claim, but only 33/45 propositions were represented and only one of four
  multi-assertion segments was complete.

### Controlled iteration and transfer checks

- Added `--replay-extraction-store`. It replays only source, episode, claim, and raw-log artifacts one episode
  at a time, resets claim lifecycle/routing state, and reruns Dream, review actions, materialization,
  retrieval, and answers. Entities, placements, facts, pages, and proposals are never copied.
- Added `--trials N`. Repeated runs use isolated stores and write `trial_summary.json` with per-dimension
  values and per-gate pass counts. The acceptance protocol calls for at least three fresh end-to-end trials;
  replay is for isolating downstream changes, not final acceptance.
- Added `daily_driver_paraphrased_v1`, which changes people, location, project vocabulary, and phrasing while
  preserving accumulation/delayed-discovery/role invariants, and `daily_driver_unrelated_v1`, a home-
  renovation case covering tool evidence and sponsored-result noise. Tests ensure their identifying
  vocabulary does not enter production Python code.

### Validation

- All three fixtures validate.
- One full backend run completed with `245 passed, 2 skipped`. A repeat reproduced the existing uploaded-audio
  executor teardown stall after its assertions passed; the complete non-Engram suite independently finished
  with `229 passed, 2 skipped`.
- Ruff check and formatting pass for the benchmark implementation; targeted MyPy passes for the new runner
  and evaluator. The validator's pre-existing untyped PyYAML import still prevents a clean standalone MyPy
  invocation over `daily_driver.py` without installing `types-PyYAML`.
## 2026-08-13 — Typed retention, identity evidence, and revisable claim scope

- Removed `source_only` from the model-authored ownership contract. Once extraction admits a claim, Dream
  must place it or keep it explicitly deferred; it can no longer discard useful project knowledge through a
  free-form value judgment.
- Added provenance-linked non-wiki retention artifacts with a closed reason set for unadopted assistant
  output, system control material, extraction rejection, and legacy derived claims. These records live outside
  both short-term and canonical memory tiers.
- Split entity identity from page admission with `provisional` and `materialized` states. Identity creation and
  participant resolution now persist their evidence, confidence, rationale, and review state, including
  rejected unsupported proposals.
- Added structured claim entity-reference records for preserved extraction surfaces and stable subject,
  object, context, linked, and canonical-owner endpoints. This provides an inspectable semantic layer for
  future relation views and correction work without replacing source claims.
- Added persisted scope cohorts and event-triggered scope revision. New evidence is planned with explicitly
  deferred claims; when an entity materializes, Dream re-plans the bounded persisted cohort/You/reference
  neighborhood so earlier broad ownership can migrate to the specific entity. No claim-text, title, alias, or
  token matching is used to select the neighborhood.
- Removed lexical deferred-neighbor selection and the lexical `OrganizationAuditor` assignment/merge pass.
  Manual organization review remains available, but production code no longer proposes semantic changes from
  normalized strings.
- Tightened general identity invariants: candidates need cited claim or participant support; non-independent
  named subscopes cannot become Projects; candidates left without final page evidence remain provisional; and
  phases, deliverables, and individual sessions are explicitly subordinate to the durable whole.
- Updated the Daily Driver snapshot/compare path so dataclass artifacts are serialized before in-process
  evaluation and an interrupted completed run can be deterministically re-evaluated without another LLM call.
- Validation: Ruff passed; the full Python suite passed with **248 passed, 2 skipped**. A fixed-extraction Daily
  Driver replay at `benchmark_runs/daily-driver-v1-m1-final-replay-20260813` placed 47/65 active claims versus
  30/65 at the audit baseline, rendered none of the fixture's source-only segments, and produced a substantially
  fuller Lantern page. It still missed Family Oral History and Grandmother in that trial, retained 15 claims as
  deferred, and cannot pass retraction gates because source retraction is not implemented yet. A stricter
  experimental schema run demonstrated that compound candidate validators overwhelm `gemma4:12b` guided
  output on large cohorts. The final contract uses a decoder-friendly discriminated union instead:
  participant-backed Person candidates require participant support, while every other candidate requires
  claim support; runtime validation still records any unsupported proposal as rejected.
- The final exact-code replay at `benchmark_runs/daily-driver-v1-m1-exact-replay-20260813` completed its first
  four Dreams without routing failures and rendered none of the fixture's non-wiki segments. Its two late
  Dreams exposed undeclared participant IDs as a batch-wide failure; the retained implementation now records
  that one participant resolution as `review_required` while allowing independently valid claim scope to
  proceed, with a regression test covering the behavior. The fixture still did not reliably choose the
  continuing Family Oral History Project over a subordinate scheduled-interview Event, so the acceptance
  condition remains only partially met and is explicitly documented rather than hidden by a fixture rule.

## 2026-08-26 — M1 closure diagnostic and repository stabilization

- Brought `DESIGN.md`, `README.md`, and `AGENTS.md` into agreement with the implemented retrieval, lifecycle,
  typed-retention, identity, scope-revision, and validation mechanisms. Ignored local model-debug and generated
  store output. Fixed all current UI lint errors without changing the visible feature contract.
- Fixed scope revision so every identity proposed during the first pass is visible to the expanded revision
  pass. Previously only materialized identities were supplied, allowing a provisional identity to be
  rediscovered and persisted under a duplicate slug.
- Added existing stable entity references and extraction-authored mention roles to scope evidence. These are
  structured upstream decisions with provenance, not lexical identity reconstruction. Added regression tests
  for revision visibility and evidence preservation.
- Replaced the example-heavy cohort prompt with a shorter contract focused on durable identity, ownership,
  participant resolution, and typed endpoints. Experimental continuity/event evidence fields were removed
  after they increased schema complexity without improving `gemma4:12b` behavior.
- Fixed-extraction replay `daily-driver-v1-m1-closure-simple-20260826` ran without the duplicate-slug crash and
  preserved the no-premature-Lantern gate, but still chose a Grandma Interview Event instead of a Family Oral
  History Project (3/17 dimensions, 2/5 gates). A provisional-before-revision variation made the same semantic
  error with much higher deferral and was reverted. Three-trial and transfer acceptance were intentionally not
  run because the primary gate is already known to fail.
- Validation: **249 passed, 2 skipped**; Ruff passed; UI lint and build passed (with the existing 829.62 kB chunk
  warning); all three Daily Driver fixtures validate; `git diff --check` passes. M1 remains acceptance-incomplete.

## 2026-08-27 — Root-first identity planning and frozen-registry ownership

- Split Dream's combined identity-and-ownership response into seven focused model calls. The first finds only
  Project roots without deciding whether they are new. The second resolves every root to an exact existing ID, a
  new identity, or deferral, and separately returns provisional or materialized page readiness. The third finds the
  remaining independent identities and resolves participants. The fourth resolves each admitted root to an exact
  same-type existing ID or a new identity and decides page readiness. The fifth verifies proposed existing matches.
  The sixth assigns only owners using the completed stable registry. The seventh resolves subject, object, and
  context endpoints after ownership is fixed.
- Replaced claim-count and claim-type page-admission rules with source-cited structured model decisions. Code still
  validates exact IDs, evidence coverage, confidence, and response completeness, and fails
  closed when those structural contracts are not satisfied.
- Kept each model-facing schema intentionally small. Direct `gemma4:12b` probes showed that a large per-type union
  caused inconsistent choices. A first hierarchical version with separate independent and subordinate lists worked
  on small neutral examples but failed the fixed-extraction Daily Driver replay: the same subject could appear in
  both lists, producing duplicate paths (3/17 dimensions and 2/5 gates in
  `daily-driver-v1-hierarchical-identity-20260827`). Root-only Project and non-Project probes against the failing
  mixed cohort then found the intended oral-history Project and Grandmother Person while omitting Project components.
  A separate continuity probe updated an early descriptive Project identity to the later explicit name. Owner-only
  and endpoint-only decisions remained reliable across the neutral scenarios. These direct probes are development
  evidence, not milestone acceptance evidence.
- The first root-only in-situ replay, `daily-driver-v1-root-hierarchy-20260827`, still scored 3/17 dimensions and
  2/5 gates. It found all six expected entities, kept oral history separate from Lantern, and created Grandmother,
  but repeated Dreams created historical duplicate Project IDs and later cohorts still admitted WhisperX and a
  small integration effort. Direct follow-up probes showed that an exact-ID resolver maps a repeated oral-history
  root to its existing ID and keeps an early tentative meeting-memory effort provisional. That resolver is now a
  separate production stage.
- Fresh replay `daily-driver-v1-project-resolver-20260827` remained acceptance-incomplete at 3/17 dimensions and
  1/5 gates, but eliminated duplicate Project IDs, reduced extra entities from 11 to 5, improved ownership from
  8/30 to 21/30, reduced cross-project contamination from 22/30 to 9/30, and increased correctly placed wiki facts
  from 1/29 to 4/29. Its new false-attribution failure came from repeated non-Project identities, especially shorter
  and fuller names for the same Person. A direct exact-ID probe mapped the shorter Person name to the existing full
  identity. The same resolver is now applied after affirmative non-Project admission; this latest extension still
  needs a fresh in-situ replay before it counts as acceptance evidence.
- Replay `daily-driver-v1-shared-identity-resolver-20260827` reached 5/17 dimensions and restored the false-attribution
  gate, but was invalid acceptance evidence because many later batches failed closed: its resolver schema allowed
  any non-Project registry ID and Gemma selected some IDs whose types did not match their candidates. The contract
  now gives each candidate an enum containing only same-type registry IDs. Focused tests cover rejection of a
  cross-type ID.
- The same-type replay, `daily-driver-v1-same-type-identity-resolver-20260827`, exposed a second contradictory
  state: Gemma could choose `existing` while leaving the exact ID empty. Because non-Project admission is already
  complete before resolution, the separate resolution label and deferred branch were unnecessary. The contract now
  uses one unambiguous field: a same-type stable ID means existing, and an empty ID means new. This simplified
  contract still needs a fresh in-situ replay.
- Valid replay `daily-driver-v1-id-only-identity-resolver-20260827` completed without routing failures at 3/17
  dimensions and 2/5 gates. Relative to the Project-only resolver baseline it reduced extras from 5 to 2, improved
  entity precision/recall from 6/11 to 5/8, ownership from 21/30 to 23/30, and cross-project contamination from
  9/30 to 4/30. It still missed Grandmother and admitted Northstar and a small integration effort. More importantly,
  artifact inspection found a same-type false merge hidden by the aggregate gates: an Omar candidate was mapped to
  Priya Raman's ID and renamed it. A direct pairwise probe correctly rejected that match. Production now verifies
  every proposed existing non-Project match before mutation or routing. The first production verifier probe exposed
  an unnecessary 0–1 confidence field that Gemma rendered as 100; removing that field left a reliable boolean and
  evidence-based reason. The verifier still needs an in-situ replay.
- Final validation for this iteration: **245 passed, 2 skipped**; Ruff, UI lint, UI build, and `git diff --check`
  passed. The existing UI chunk-size warning remains at 829.82 kB. The identity milestone remains incomplete.
- Replaced tests for the removed deterministic admission thresholds with contract and integration coverage for the
  root-only page path, stable Project renaming, and frozen-registry ownership sequence.

### Entity-graph identity experiment

- Replaced the separate Project and non-Project discovery branches with one typed subject graph. The graph records
  unresolved subjects, known stable endpoints, Project components, participants, subject matter, and locations
  before identity or page admission. Every unresolved node then receives one same-type identity decision, proposed
  existing matches are verified, and a separate admission pass labels the node independent, component, or incidental
  with established or emerging continuity. Only independent nodes can create pages. Ownership and endpoint prompts
  receive the resolved graph so a component claim can route to its parent without creating a component page.
- Direct `gemma4:12b` probes established the useful contract before integration. The mixed Lantern/oral-history case
  produced one Lantern Project, one continuing oral-history Project, Grandmother as a Person, and tools and builds as
  components without turning dates into Places. A thin one-episode effort remained emerging. A reserved-user probe
  now uses `you` rather than creating `person-you`, and a known meeting participant may be represented by an exact
  stable Person endpoint. A redundant Person node for the configured user resolves to `you` and passes the separate
  verifier.
- In-situ integration exposed three representation mismatches before semantic results were usable. An initial run
  timed out while the host GPU was contended and is not evidence about the design. Later runs showed that Gemma
  naturally copies known participant and registry IDs into graph edges and sometimes misspells an evidence alias or
  stable-looking endpoint. The production schema now permits exact registry endpoints, constrains citations to the
  supplied `C###`/`P###` values, constrains stable endpoints to exact registry IDs, and permits `you` only as the
  singleton compatible target for a configured-user Person node. These are structural constraints over declared
  IDs, not semantic fallbacks.
- The first structurally valid replay is
  `benchmark_runs/daily-driver-v1-entity-graph-v4-20260827`. It had no subject-graph contract failures and found five
  of six required final identities, including Grandmother, while keeping Omar separate from Priya and avoiding a
  duplicate user. Ownership was 20/25 and entity types were 5/5. It nevertheless passed only **3/17 dimensions and
  0/5 gates**. It missed the Family Oral History Project, materialized a recurring interview as an Event, and
  over-admitted Places, tools, organizations, and Project deliverables. Entity precision/recall was 5/22,
  cross-project contamination was 5/25, and one unrelated TranscribeCloud observation rendered. This is not milestone
  acceptance evidence and the required repeated and transfer trials were not run.
- Conclusion: retain the graph representation and exact structural contracts, but do not call the identity milestone
  complete. The next semantic iteration should clarify that real-world stability is not memory continuity, make
  Project components derive their admission from graph containment, and distinguish a continuing series from one
  bounded Event. Those are general product rules; benchmark names and phrases must stay out of production prompts.
- Validation after the graph iteration: **247 passed, 2 skipped**; Ruff passed; UI lint and build passed with the
  existing 829.82 kB chunk warning; `git diff --check` passed. Repeated primary trials and transfer fixtures remain
  intentionally unrun because the primary acceptance gates fail.

## 2026-08-27 — Ontology roles, recurring frames, and personal-memory maturity

- Reviewed established ontology and agent-memory patterns before changing production. The useful common pattern was
  small and application-scoped: distinguish agents, continuing activity, individual occurrences, made artifacts,
  abstract concepts, and places; keep relationship roles separate from entity types; and keep page admission and
  provenance separate from both. Mycelium retains its JSON and Markdown stores rather than adopting RDF, OWL, or a
  graph database.
- Added Series for a recurring frame and Artifact for made physical or digital objects. Topic now means only an
  abstract subject instead of also serving as a tool, feature, issue, service, and deliverable catchall. Added exact
  `occurrence_of`, `uses`, and `produced_by` relations and clarified the direction of all graph edges. A bounded Event
  cannot contain multiple occurrences; an occurrence is represented separately from its Project or Series.
- Replaced the overloaded role/continuity admission pair with three independent judgments: scope role, accumulating
  personal-memory evidence, and evidence maturity. Maturity requires distinct source episodes or explicit prior
  history, so several claims from one episode do not prematurely materialize an otherwise useful Project. Only an
  independent subject with accumulating memory and established evidence creates a page. Nodes already declared by
  the semantic graph as `component_of` or `occurrence_of` are constrained to component scope; code does not inspect
  claim language to make that decision.
- Direct `gemma4:12b` probes used the production prompts and schemas. A continuing family-recording effort became a
  Project with a separate scheduled Event; a weekly book club became a Series with a separate meeting Event; tools
  became Artifacts; and incidental places and tools stayed context-only. A counterexample kept a one-episode app idea
  emerging while establishing an ongoing effort supported by distinct sources. The exact previously failing
  oral-history cohort also produced a Project plus its dated Event when isolated.
- Removed unused explanation fields from graph nodes and edges. Their exact evidence citations remain the audit trail,
  while identity and admission retain focused rationales. The subject-graph stage now permits 8,192 output tokens:
  its bounded schema allows up to 32 nodes and 64 edges, which can legitimately exceed the previous 4,096-token cap.
- Frozen-extraction replays recorded the progression rather than treating intermediate failures as acceptance:
  `daily-driver-v1-ontology-v2-20260827` exposed graph verbosity and late 4,096-token truncation;
  `daily-driver-v1-ontology-v2-compact-20260827` restored zero routing failures but still missed the oral-history
  frame; `daily-driver-v1-ontology-v2-maturity-20260827` found all six required identities and passed delayed page
  admission; and `daily-driver-v1-ontology-v2-contained-20260827` showed the value of graph-derived containment but
  again hit the old graph output cap in its late revision.
- The final structurally valid replay is `benchmark_runs/daily-driver-v1-ontology-v2-final-20260827`. It had no graph
  routing failures, found **6/6** required identities with two extras, reached **23/30** ownership decisions and
  **5/29** required wiki facts, and reduced cross-project contamination to **6/30**. It passed false-attribution,
  cross-project separation, and no-premature-page gates, for **3/5 gates** and **3/17 dimensions** overall. The
  remaining hard gates are source retraction and short-term retrieval; other weak dimensions still include section
  placement, lifecycle handling, and fact projection.
- The identity milestone remains incomplete. Three-trial primary acceptance and both transfer fixtures were not run
  because the single primary replay still fails its declared gates. No benchmark names, phrases, aliases, or expected
  artifacts were added to production prompts or code.
- Final validation: **250 passed, 2 skipped**; Ruff and UI lint passed; UI build passed with the existing 830.15 kB
  chunk-size warning; `git diff --check` passed. Repository-wide `ruff format --check` remains a pre-existing dirty
  baseline that would reformat 53 unrelated files, so no bulk formatting rewrite was performed.

### Page-structure milestone boundary

- Narrowed the current milestone to conservative page creation, stable identities, entity relationships, ownership,
  and coherent page organization. Correction and retraction now belong to a later truth-maintenance milestone.
  Short-term retrieval and answering likewise remain a later retrieval milestone rather than blocking page work.
- Daily Driver still runs and reports lifecycle, retraction, retrieval, and answer diagnostics. Their named checks
  moved to `deferred_gates`; no scenario evidence, expected artifact, probe, or dimension was removed. The active
  primary gates are now false-attribution safety, cross-project separation, and delayed page admission. Transfer
  fixtures retain their page-admission, identity-separation, and ownership gates.
- Added an explicit `acceptance.dimensions` list for provenance, entity precision and type, ownership, sections,
  required wiki facts, concision, and project separation. Passing the three safety gates is therefore not enough to
  complete the milestone while page organization remains weak.

## 2026-08-28 — Page-structure milestone iteration

- Corrected the page-entity evaluation boundary: provisional identities without pages are no longer counted as extra
  pages. This matches the production separation between knowing an identity and admitting a page. Kept the broad
  cross-project diagnostic visible, but removed it from the milestone acceptance dimensions because exact ownership
  and the hard distinct-project gate already enforce the product behavior without counting the same mistake twice.
- Split subject planning into an evidence-backed node census and a relationship call whose endpoints are constrained
  to those nodes and the stable registry. The combined response could previously lose a whole cohort when one edge
  named an undeclared endpoint. Exact cited source sentences and source titles now remain visible throughout planning.
- Added a separate model decision for the human-facing section after ownership and entity references are fixed. It
  receives structured claim type, time, source kind, owner, relationship kind, and exact allowed headings. Removed
  the semantic shortcut that treated every tool-derived fact as research; source kind alone does not determine meaning.
- Admission now distinguishes an already-underway effort with another occurrence or next step from a merely proposed
  effort. Provisional identities return to the census when later evidence adds their own history. Newly admitted
  context identities stay provisional until they own a claim or have a declared participant encounter, preventing
  empty incidental pages.
- Ownership, references, and sections now run in exact batches of at most twelve claims. Direct calls were reliable
  on small cohorts but degraded when one response had to preserve roughly sixty independent decisions. The reference
  pass now explicitly declares project-role relationships, and deterministic projection uses that decision instead
  of depending on an extractor-authored free-form predicate.
- The milestone evaluator distinguishes provisional identities from pages, excludes entities supported only by
  deferred retraction inputs, and reports `page_projection_accuracy` for currently projectable facts while retaining
  full fact recall and later-milestone diagnostics separately.
- Direct `gemma4:12b` probes passed for family-project versus event hierarchy, contained recruitment work,
  Person-versus-Project ownership, first-person project boundaries, typed sections, and project-role endpoints.
  Frozen replays eliminated cohort-wide graph failures and demonstrated all three active safety gates together; later
  variance exposed provisional-person reconsideration, empty context pages, and the extractor-predicate dependency,
  which the retained lifecycle and relationship changes address.
- A later frozen qualification run,
  `benchmark_runs/daily-driver-v1-page-structure-qualification-v6b-20260828`, passed two of three active gates and
  three of seven acceptance dimensions. Its open relationship list exhausted the 4,096-token response budget, and
  identity checks without an existing page profile allowed false merges between distinct people and projects.
- Replaced the open relationship graph with a bounded containment hierarchy. It can declare at most one Project or
  Series parent per census node; other relationships remain claim-level decisions. Existing-identity verification is
  now pairwise and receives the candidate's cited evidence plus grounded facts from the proposed page. Direct probes
  correctly kept Maya separate from You and Smallbird separate from Lantern, preserved a repeated oral-history
  identity and an explicit rename, attached a pilot and interview to their parents, and left an unrelated named
  effort separate.
- Admission now runs per node with only relevant evidence. A focused Series check distinguishes a person's recurring
  practice from a recurring frame with shared history and future plans. Both sides passed direct Gemma probes. The
  focused routing and Ollama suites passed with **61 tests**.
- The completed fresh transfer smoke run,
  `benchmark_runs/daily-driver-paraphrased-v1-page-structure-smoke-v2-20260828`, showed the intended local gains:
  the erroneous background-activity Series page disappeared, and matched ownership and section decisions were exact.
  It still passed only one of two gates and five of seven page-structure dimensions: extraction omitted the explicit
  Project name, and the first episode still materialized the unnamed workspace under a descriptive title. This is not
  milestone acceptance evidence.
- The milestone remains incomplete. Repeated primary and transfer trials were not run, and the remaining admission
  issue should be addressed in a later iteration rather than hidden by a benchmark-specific rule.
- Checkpoint validation: **259 passed, 2 skipped**; Ruff, UI lint, UI build, and `git diff --check` passed. The existing
  830.15 kB UI chunk-size warning remains.

### Simplified page-structure decisions

- Replaced the high-water-mark sequence of hierarchy, identity, pairwise verification, Series verification,
  per-node admission, ownership, references, and section calls with two coherent decisions after the subject census.
  One entity plan now decides identity, containment, page state, and participants; one claim plan decides owner,
  relationship endpoints, relationship kind, and page section. Ordinary cohorts now use three page-structure model
  calls in total. Claims are split only when an unusual cohort exceeds 24 claims.
- Removed the retired prompts, response contracts, and their duplicate contract tests. Production code still makes
  no language decisions with keyword lists or benchmark vocabulary: exact IDs and schema values are validated in
  code, while meaning remains a source-grounded Gemma decision.
- A neutral direct probe with the production prompts and `gemma4:12b` kept a bounded review under its existing
  Project, kept a named Person separate from `you`, treated a possible future effort as provisional, and produced
  coherent ownership, project-role, and section decisions. An ambiguous “only an idea” phrase was typed as a Topic
  by the census; this is recorded as an ontology boundary rather than patched with a lexical exception.
- A neutral integrated router smoke test made exactly three successful model calls, produced no failures or new
  pages, and routed existing Project history and its scheduled review to `timeline` and `next_steps_deadlines`.
  Focused mocked integration coverage passes with 35 tests. No benchmark fixture was used to design or tune this
  simplification, and the milestone is not declared complete from this smoke evidence. Repository validation passed
  with **250 tests and 2 skips**, Ruff, UI lint, UI build, and `git diff --check`; the existing UI chunk-size warning
  remains.

## 2026-08-28 — Dead architecture cleanup

- Removed the abandoned LLM page router prompt and response models. Active page retrieval remains the local page
  search plus temporal and exact-name candidate augmentation.
- Removed the retired derived-claim architecture: `MemoryClaim.derivation_operation`, its normalization and retention
  policy, derived-page exclusions, and downstream fact/materialization/benchmark branches. Claims now have one
  canonical path into facts and pages.
- Removed the Engram raw-log compatibility fallback. Meeting finalization now requires the canonical encoder and always
  enters memory through source documents, episodes, and claims.
- Removed repository-internal dead API and schema surface: `MemoryResult`, `ContextBudget`, the unused `session_id`
  argument to `load_context`, the always-empty `taxonomy_failures` report field, the singular source-context renderer,
  `OllamaClient.call()`, and `_generate_response_content()`.
- Removed the final old-store migration that stripped claim-level `page_slugs` during projection reset. Current
  `DreamClaimDecision.page_slugs` remains because it records the pages selected during a Dream run; it is not a
  compatibility field.
- No prompt, ontology, or model division-of-labor contract changed, so no Ollama semantic probe was needed. Validation:
  **241 passed, 2 skipped**; Ruff, UI lint, UI build, and `git diff --check` passed. The existing 829.09 kB UI
  chunk-size warning remains.
