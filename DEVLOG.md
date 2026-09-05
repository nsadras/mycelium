# Development Log

## 2026-08-28 — Externalize model prompts as strict Jinja templates

- Added one strict Jinja rendering boundary in `mycelium.prompting`. Undefined variables fail closed, templates are
  loaded from the packaged `mycelium/prompt_templates` tree, and Jinja is now a direct runtime dependency.
- Moved all repository-owned model-facing prompt text out of Python: memory extraction/census/identity/routing/fact
  synthesis/reconsolidation, assistant retrieval and chat context, Engram summary/reduction, and benchmark answer,
  retrieval-plan, and judgment prompts. Python call sites now inject runtime evidence, structured ontology claim
  types, source-specific extraction policy, conversation context, and serialized evaluation payloads.
- Kept the six core memory prompts byte-for-byte identical for representative inputs. Added template inventory,
  strict-undefined, schema injection, multiline preservation, and package-data tests. A built wheel contained the
  renderer and every `.jinja` file.
- Direct `gemma4:12b` probes used the production Jinja prompt and structured schemas. Reconsolidation correctly chose
  `supersedes` for an explicit editor-preference replacement and `additive` for an unrelated scheduled review. A
  neutral extraction probe retained the two user claims and ignored the assistant proposal. An earlier project probe
  also invented an unsupported project-lead relationship; this is recorded as a model behavior rather than accepted
  evidence, and no lexical repair or fixture-derived prompt rule was added.
- In-situ replay:
  `benchmark_runs/daily-driver-unrelated-v1-jinja-prompts-20260828`, replaying frozen extraction from
  `daily-driver-unrelated-v1-central-ontology-refined-20260828`. Both Dream runs completed with zero failures, all ten
  active claims were routed and rendered, the expected three entities/pages were present, and both safety gates
  passed. Its evaluation exactly matched the source run at 8/12 dimensions and 5/7 acceptance dimensions; the known
  presentation-quality misses remain, so the fixture is not release-ready.
- Validation: 235 non-Engram tests passed; the focused prompt/Engram/core pipeline run passed 80 tests; Ruff and lock
  validation passed. The corpus-backed AMI path remains outside the fast suite.

## 2026-08-28 — Split architectural hotspots by responsibility

- Replaced the monolithic artifact module with a small public facade over separate persisted models,
  filesystem repository, transcript segmentation, temporal logic, and cross-store integrity modules. Existing
  artifact imports and serialized shapes remain unchanged.
- Kept Dream orchestration in `DreamProcess` while moving retention, evidence admission, revision, and audit
  mutations into `DreamPolicy`. Split consolidation support into contract models, prompt formatting, and
  participant/entity-resolution artifacts without changing the model prompts or call sequence.
- Replaced the single memory API implementation with composed artifact-inspection, wiki, lifecycle, and curation
  routers plus shared request/response contracts. HTTP paths remain unchanged; tests now import implementation
  functions from their owning router modules.
- Split Engram presentation/formatting helpers from its stateful controller. Split Memory Inspector data loading,
  selection and review state into a hook, with separate overview and shared presentation components.
- This was a structural refactor only: no prompt, ontology, structured-output contract, or division of model labor
  changed, so no direct Ollama probe was required.
- Validation: Ruff and `git diff --check` passed; 230 non-Engram tests and the focused artifact, Dream, API, and
  runtime suites passed; frontend lint and production build passed with the existing large-chunk warning. The
  corpus-backed AMI test remains excluded from the fast suite as documented in the audit.

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

## 2026-08-28 — Redundant log and claim fields removed

- Made `LogEntry.consolidated` the sole log-consolidation state. New Markdown no longer writes `status`, the parser no
  longer loads it, and benchmark replay resets only the boolean.
- Removed the unused claim `kind` and `salience` fields. `claim_type` remains the semantic classification. A follow-up
  removed `importance` from logs and wiki pages entirely because retrieval, context admission, Dream, fact synthesis,
  and rendering never consumed it. It is no longer written to log Markdown or wiki frontmatter, exposed by APIs/UI,
  included in benchmark metadata, or compared during page regeneration.
- Removed claim-wide `inferred`. Explicit-versus-inferred evidence now lives only on each `ClaimProvenance.evidence_type`.
  `evidence_modality` is restricted to observation channels (`speech`, `visual`, `tool`, `mixed`, or `unknown`) and no
  longer doubles as an inference flag. The inspector derives its inferred badge from provenance.
- Direct `gemma4:12b` probes used the production extraction prompt and proposed constrained schema. Initial probes kept
  explicit speech grounded and rejected a negated moving-plan inference, but an ordinary family example exposed an
  unmarked derived grandparent claim. Tightening the contract to distinguish observation channel from inference caused
  the final family probe to retain only directly supported relationships with explicit speech provenance; the negated
  plan counterexample also remained explicit and did not invent a moving plan. Earlier fever and logical-entailment
  probes were conservatively represented as their directly stated premises rather than inferred conclusions.
- Fresh in-situ validation is at
  `benchmark_runs/daily-driver-unrelated-v1-schema-cleanup-20260828`. It covered all 6/6 claim-bearing segments, leaked
  0/2 source-only segments, persisted ten claims with correct speech/tool modalities and explicit provenance, placed
  every claim, and recorded no Dream failures or routing failures. Both hard gates passed. It matched 6/8 expected
  claims and passed 5/7 acceptance dimensions; claim recall, section accuracy, and page projection remain meaningful
  fixture weaknesses, and answer quality was intentionally skipped to isolate memory construction.
- Added structural contract and pipeline tests preventing the removed fields and inference-as-modality from returning.
  Persistence tests also require importance-free log and wiki files. Final validation: **242 passed, 2 skipped**;
  Ruff, UI lint, UI build, and `git diff --check` passed. The existing 828.90 kB UI chunk-size warning remains.

## 2026-08-28 — Central authoritative memory ontology

- Added `mycelium/ontology.py` as the single ordered registry for claim types, entity types, user-facing labels,
  discoverability, section keys and headings, semantic descriptions, claim-type fallback sections, and project-role
  sections. Pydantic extraction/census contracts, artifact and wiki validation, curation remapping, materialization,
  index groups, benchmark validation, and production prompt catalogs now derive from that registry.
- Removed `mycelium/wiki_schema.py` and the duplicate constants in `models.py`. The React memory explorer now loads
  `/api/memory/ontology`; its groups, labels, entity-type choices, allowed sections, and role destinations no longer
  carry a separate TypeScript ontology. This also exposes every declared section consistently, including
  `needs_review`.
- Removed the old source-modality section shortcut. Tool evidence is subject to the same meaning-based model routing
  as speech and visual evidence; deterministic fallback uses only the structured claim type and the exact declared
  `project_role` predicate.
- Direct `gemma4:12b` probes used the production prompts and structured schemas. The initial entity probe separated a
  continuing effort, its checklist Artifact, and a bounded kickoff Event. Routing selected Artifact `purpose`,
  Project `current_status`, and You `profile`, including a tool-observed personal fact without treating its source
  kind as a page section. A follow-up boundary probe selected Project `requirements_constraints` for a current
  preference, Person `shared_projects` with a project-role relationship for continuing responsibility, Project
  `next_steps_deadlines` for a scheduled future event, and Project `timeline` for the completed counterexample.
- The first frozen-extraction replay,
  `benchmark_runs/daily-driver-unrelated-v1-central-ontology-20260828`, exposed overlapping section descriptions:
  a current project preference landed in Timeline and a continuing project responsibility landed in Goals & Plans.
  The registry descriptions were tightened at those general semantic boundaries rather than adding lexical rules.
  The refined replay at
  `benchmark_runs/daily-driver-unrelated-v1-central-ontology-refined-20260828` restored the expected placements,
  passed both release gates, found all 3/3 entities with no extras, placed and rendered all 10 active claims, and
  recorded no Dream or routing failures. It matched the prior fresh run's 4/6 section decisions and 3/6 projected
  page facts; the remaining claim-recall and projection weaknesses are unchanged capability gaps.
- Validation: **247 passed, 2 skipped** in the full suite before the final description refinement; the final focused
  ontology, routing, Dream, encoder, wiki, and API suite passed **59 tests**. Ruff, UI lint, UI build, and
  `git diff --check` passed. The existing 827.70 kB UI chunk-size warning remains.

## 2026-08-29 — Unified owner-scoped claim-to-fact resolution

- Replaced pairwise `ClaimReconsolidator` plus section-bucket `FactConsolidator` with one owner-scoped
  `FactResolver`. Its production schema requires one keyed assignment for every supplied claim, exact fact-key
  coverage, ontology-constrained sections, declared linked-entity aliases, and exact claim aliases on both sides of
  any contradiction or supersession proposal. The prompt receives all active claims for the owner, exact source and
  segment evidence, normalized temporal data, existing presentation facts, and prior review decisions.
- Removed the old reconsolidation and fact-synthesis prompts/contracts, free-text `about` candidate filtering, the
  date/number regex grounding rule, and the singleton-on-error fallback. A rejected owner plan now preserves the last
  valid facts/page, reports `fact_resolution` in the Dream audit, leaves its incoming source unconsolidated, and keeps
  its claims retryable. A genuinely single claim with no prior fact uses direct deterministic projection because no
  equivalence or truth decision exists.
- Truth changes are group-capable review proposals with exact incoming and target claim-ID lists. Deterministic code
  withholds proposed incoming facts, preserves accepted target facts, and moves incoming placements to
  `needs_review`. Approval mutates canonical claim links/status and reruns the same resolver; rejection likewise reruns
  it with the reviewed decision. Display facts now record derived `current` or `history` state. Manual display text is
  retained only when the resolver returns the exact same membership and scope, rather than shielding member claims
  from later resolution.
- Direct `gemma4:12b` probes used the production Jinja prompt and structured schema. The initial list-based contract
  omitted claims and confused pending sides, so it was replaced with exact keyed assignments. Subsequent neutral
  probes grouped repeated support, kept adjacent facts separate, treated equal-date repetition as support rather than
  replacement, proposed an explicit deadline replacement, and returned no new truth change for approved or rejected
  reviews. A follow-up tightened approved contradiction semantics after the model initially demoted one side; the
  final probe kept both sides current and emitted no repeated proposal.
- Persisted in-situ real-model runs are at `benchmark_runs/fact-resolution-neutral-support-20260829` and
  `benchmark_runs/fact-resolution-neutral-20260829`. The support run produced one current fact backed by both exact
  claim IDs and no proposal. The correction run produced one `supersedes` proposal from `new` to `old`, preserved only
  `fact-old`, moved `new` to `needs_review`, and recorded no failures.
- The frozen downstream transfer run at
  `benchmark_runs/daily-driver-unrelated-v1-fact-resolution-20260829` passed both release gates, placed and rendered all
  10 active claims, retained exact provenance, produced no routing or fact-resolution failures, and passed five of
  seven acceptance dimensions. Its remaining claim, section, and projection misses are unchanged broader capability
  gaps rather than resolver failures.
- The attempted primary frozen replay was invalid because the selected pre-cleanup extraction store still contained
  the intentionally removed `derivation_operation` field; no compatibility path was added. The fresh primary run at
  `benchmark_runs/daily-driver-v1-fact-resolution-fresh-20260829` was dominated by upstream identity/routing contract
  failures before the correction reached fact resolution, so it is recorded as upstream failure evidence rather than
  resolver acceptance evidence. No `fact_resolution` failures occurred in that run.
- Structural and pipeline validation: **249 passed, 2 skipped**; Ruff, UI lint, UI build, and `git diff --check`
  passed. The existing 847.49 kB UI chunk-size warning remains.

## 2026-08-29 — Fail-closed identity adjudication and upstream routing contracts

- Split page maturity out of the combined identity/scope decision. The subject census now emits explicit entity-type
  adjudication and participant evidence; a separate exact keyed maturity plan can propose only schema-allowed
  continuity bases, and an independent verifier checks any single-episode `explicit_prior_history` proposal. Project
  and Series proposals supported only by one episode cannot be silently auto-admitted: they remain provisional or
  enter the identity-review queue. Cross-episode nodes receive only `multiple_episodes`, and named source participants
  are materialized from the structured participant resolution before claim routing.
- Tightened all upstream/downstream boundaries. Entity planning uses discriminated scope variants (`materialized`,
  `provisional`, `component`, `occurrence`, `standalone_event`, and `context`), page state is derived from that scope,
  invalid parent/type combinations cannot be generated, and only materialized identities enter the owner-routing
  schema. Claims supporting provisional or review-required independent identities are deferred rather than assigned
  to an unrelated page, preserving them for later cross-episode promotion. Routing no longer chooses wiki sections;
  the owner-scoped fact plan remains the authoritative section decision.
- Added a complete identity-review workflow. Review-required decisions persist the proposed type, scope, parent,
  page state, aliases, exact supporting claims/segments, and type rationale. The API accepts approve/reject plus exact
  overrides, approval writes authoritative manual identity references and reopens affected claims, and both actions
  immediately rerun Dream. The React Memory Inspector exposes the review queue and approve/reject controls.
- Direct `gemma4:12b` probes preceded each semantic contract change. Neutral probes distinguished a one-episode
  antique-restoration effort from explicitly stated prior work plus future continuation; accepted a named meeting
  participant as a direct encounter; accepted an unambiguous renovation Project while marking a genuine
  Project-versus-Series boundary for review; and independently rejected invented prior history based on an object's
  age, assumed condition, present-progressive work, or a current-episode decision. The verifier accepted the
  counterexample with work begun last month, a plan approved last week, and continuation next week. Production-schema
  pair probes also rejected the same-episode false basis repeatedly.
- The final unrelated frozen-extraction replay is
  `benchmark_runs/daily-driver-unrelated-v1-identity-adjudication-v7-20260829`. It passed both release gates, found all
  3/3 expected entities with no extras, placed and rendered all 10 active claims, preserved the first-episode Project
  claims as deferred, then materialized the Project and Person after later evidence. Three independent final-code
  trials at `benchmark_runs/daily-driver-unrelated-v1-identity-adjudication-trials-20260829` passed
  `no_premature_project` and `correct_role_owner` in **3/3 trials each**; entity-type, ownership, and provenance
  accuracy were 1.0 in every trial.
- The primary frozen replay is at `benchmark_runs/daily-driver-v1-identity-adjudication-20260829`. It passed the
  no-premature-Lantern gate and demonstrated an inspectable review-required decision, but is not release-ready: the
  model still chose Series for the family oral-history effort, created an extra Pilot Evaluation Project, and later
  fact calls hit malformed-output limits. It also exposed grouped project-role placements receiving a fact group's
  union of links. That deterministic downstream bug was fixed after the run: facts may aggregate linked endpoints,
  while every canonical placement now retains its own exact project endpoint. A regression test covers two Person
  role claims grouped across two different Projects.
- The old paraphrased replay store was correctly rejected because it contains the removed `derivation_operation`
  field; no compatibility reader was added. Fresh runs are at
  `benchmark_runs/daily-driver-paraphrased-v1-identity-adjudication-fresh-20260829` and
  `benchmark_runs/daily-driver-paraphrased-v1-identity-adjudication-fresh-v2-20260829`. The retry achieved complete
  claim-bearing source coverage and passed the no-premature-project gate, but the model split the continuing Hearth
  effort into a provisional Project plus Artifact/component and unsupported Series nodes, so the distinct-entity gate
  remains a recorded cross-vocabulary model-quality failure rather than being patched with lexical rules.
- Final validation: **253 passed, 2 skipped**; Ruff, UI lint, UI build, and `git diff --check` passed. The existing
  853.51 kB UI chunk-size warning remains.

## 2026-08-31 — Contractual extraction coverage

- Replaced best-effort `ignored_segment_ids` extraction output with an exact per-segment disposition contract. Every
  supplied batch segment must appear exactly once as `claimed` or `source_only`; claimed dispositions and claim
  evidence have reciprocal claim-key links, unknown/duplicate/missing segments fail validation, and a source-only
  decision preserves its model-provided reason. Episodes persist these dispositions with real claim IDs, and the
  artifact API and Memory Inspector expose the same accounting.
- Extraction now validates and builds a complete batch before saving it. Removed lexical claim rejection, subject
  detection, and subject-repair code from the persistence boundary; standalone attribution is the structured model's
  responsibility, while deterministic code validates only IDs and declared schema structure. An invalid or incomplete
  batch persists no claims from that batch and leaves the episode partial and retryable.
- Two direct `gemma4:12b` probes used the production extraction prompt plus the proposed schema before integration.
  Both extracted the lease-signing assertion from the substantive segment, classified a gratitude-only segment as
  source-only, returned exact reciprocal links, and passed the complete-coverage validator.
- Validation: **249 passed, 2 skipped** under `pytest tests`; focused extraction/runtime/API/Dream tests passed
  **100/100**; Ruff, UI lint, and UI build passed. A bare repository-wide pytest invocation still discovers the
  intentionally stale `benchmark_runs/mab-loader-check/test_routing_q49.py` artifact, which imports the previously
  removed routing recall index; the maintained `tests/` suite is clean.

## 2026-08-31 — Separate identity matching and taxonomy verification

- Split identity decisions into explicit stages: the subject census now declares evidence-grounded candidates without
  typing them; identity matching partitions every candidate node into exactly one identity group and fixes each group
  as existing, new, or review-required; ontology type proposal and independent type verification then run before
  maturity and containment. Entity planning can no longer choose a different existing entity or rename/retype the
  identity decision because its entity ID is schema-fixed and its title/aliases come from matching.
- Identity grouping is the structural duplicate boundary. Candidate nodes may be merged into one identity group, all
  nodes must be covered exactly once, group keys must be unique, and an existing canonical entity may appear in only
  one group. Reviewed manual identity references are checked against the matching result before later stages run.
- Taxonomy verification returns `supported`, `ambiguous`, or `unsupported` with exact evidence and alternative types.
  Only supported proposals can be accepted automatically; ambiguous and unsupported results force the identity into
  review and defer its claims. No lexical or title-similarity identity rule was added.
- Before integration, two repeated direct `gemma4:12b` probes grouped two explicitly co-referential census nodes and,
  when canonical facts were supplied as in production, matched that group to its existing registry ID in both runs.
  Two independent taxonomy probes accepted a clearly outcome-directed relocation Project and marked a recurring
  gathering with an unresolved Project/Series boundary ambiguous in both runs.
- Validation: **251 passed, 2 skipped**; Ruff and `git diff --check` passed.

## 2026-08-31 — Persist identity maturity proposals and verifier results

- Added append-only identity maturity assessment artifacts. Every evaluated identity now records its local identity
  group and source nodes, proposed title/type, exact supporting sources/claims/segments, proposed admission and full
  structured continuity basis, proposal rationale/confidence, independent verifier verdict/rationale, effective page
  admission, Dream run, and eventual canonical entity ID when one exists.
- Dream persists these assessments alongside identity-resolution decisions, preserves both initial and revision-pass
  assessments, and removes them with the rest of the derived projection. Artifact APIs support list, filtered-by-run,
  and detail reads; Dream-run detail includes its assessments, and the Memory Inspector displays the proposal and
  verifier audit together.
- Validation: **251 passed, 2 skipped**; focused persistence/API/Dream tests passed **96/96**; Ruff, UI lint, and UI
  build passed. The existing 854.25 kB UI chunk-size warning remains.

## 2026-08-31 — Bounded fact resolution stages

- Replaced the single large owner-wide fact response with three fail-closed contracts. A compact truth stage proposes
  only new contradictions/supersessions; a compact grouping stage assigns every exact claim alias to an F001-style
  fact key while structurally separating truth-change sides; bounded rendering calls then write text, state, section,
  confidence, and rationale for at most 12 fixed groups at a time. Deterministic code assembles the complete plan and
  retains the existing review, manual-text, placement, and fact-ID behavior.
- The stages have separate Jinja prompts and exact Pydantic schemas. Truth decisions retain owner-wide context and
  reviewed relations, grouping cannot write presentation text, and rendering cannot merge, split, omit, or redefine
  groups. A 13-group pipeline test verifies two presentation calls and 13 deterministically assembled facts.
- Direct `gemma4:12b` probes preceded integration. The initial combined compact grouping/truth response detected the
  correction but repeatedly violated its own grouping constraint, so the division of labor was tightened further.
  The final three-stage probe explicitly proposed `C003 supersedes C001,C002`, grouped repeated old support together
  while separating the correction and unrelated commitment, and rendered three exact facts with the corrected value
  current and the prior value historical. This resolved the malformed combined-contract failure rather than adding a
  fallback parser.
- Validation: **252 passed, 2 skipped**; focused fact/Dream/prompt tests passed **49/49** before the batching regression
  was added; Ruff and `git diff --check` passed.

## 2026-08-31 — Bounded contractual extraction stages

- The first fresh unrelated transfer run at
  `benchmark_runs/daily-driver-unrelated-v1-contracts-fresh-20260831` exposed a structural failure in the initial
  all-in-one extraction contract: `gemma4:12b` generated all three correct meeting claims and dispositions, then
  duplicated the claim array. Three retries repeated the malformed shape, leaving the meeting episode partial. The
  same run also showed that the prior source-only policy admitted an unsolicited catalog result because it did not
  distinguish adopted external evidence from unselected suggestions.
- Replaced that monolithic output with two bounded, fail-closed contracts. The first makes one exact `claim_bearing`
  or `source_only` decision for every supplied segment and preserves its reason. The second receives only admitted
  segments and must cover all of them through exact claim evidence IDs. Temporary claim keys and reciprocal
  cross-references are gone; persisted `claimed` dispositions are assembled from validated canonical claim IDs.
- Removed the deterministic image-URL/source-furniture admission rule. Transport content, rejected or unadopted
  suggestions, and unsolicited external content are now source-only only through the structured coverage decision;
  durable selected external evidence remains claim-bearing. A coverage-stage or claim-stage failure leaves affected
  segments unaccounted and saves no claims from that batch.
- Before integration, a direct `gemma4:12b` coverage probe admitted three meeting assertions and a selected product
  observation while classifying an unsolicited result source-only. A production-derived bounded claim probe then
  extracted the three meeting claims once with exact evidence coverage and no malformed duplication.
- Validation: **252 passed, 2 skipped**; focused extraction/runtime/ontology tests passed **63/63**; Ruff and
  `git diff --check` passed.

## 2026-08-31 — Exact keyed fact truth adjudication

- The corrected fresh transfer run at
  `benchmark_runs/daily-driver-unrelated-v1-contracts-fresh-v2-20260831` achieved exact extraction accounting but
  exposed a repeated fact-truth contract failure for owner `you`. The frozen debug replay at
  `benchmark_runs/daily-driver-unrelated-v1-contracts-replay-debug-20260831` captured all three attempts: the schema
  allowed every canonical alias on both truth-change sides, while runtime required incoming aliases to oppose only
  previously accepted aliases. The model consequently proposed self-supersessions even though each explanation said
  that no truth change existed.
- The first direct schema probe separated incoming and target enums. It removed self-reference but still forced the
  model's per-claim “no change” conclusions into proposal objects. The final contract therefore adjudicates every
  incoming alias through an exact keyed discriminated decision: `no_change`, or `truth_change` with target aliases
  schema-limited to prior claims. Deterministic validation rejects competing incoming decisions for the same target;
  runtime converts only truth-change decisions into review proposals.
- Direct `gemma4:12b` probes of the final contract returned `no_change` for three compatible or independent incoming
  facts from the transfer run, and returned `supersedes` with the exact prior alias for a neutral explicit date
  correction counterexample. No lexical or benchmark-specific rule was added.
- Frozen replay validation also exposed a harness sequencing defect: it copied every future log into the destination
  before replaying the corresponding source artifacts, causing an artificial first-checkpoint preparation failure.
  Replay now appends each frozen raw log as unconsolidated alongside its source, episode, and claims, matching the
  production ingestion sequence and preventing future evidence from leaking into earlier checkpoints.
- The final frozen downstream runs are
  `benchmark_runs/daily-driver-unrelated-v1-contracts-final-replay-20260831` and
  `benchmark_runs/daily-driver-unrelated-v1-contracts-final-replay-v2-20260831`. Both final Dreams completed without
  identity, routing, maturity, or fact-resolution failures; the second run, after the replay sequencing fix, completed
  both Dream checkpoints with zero failures and no structured debug dumps. It preserved exact 6/6 claim-bearing and
  2/2 source-only accounting, passed both hard lifecycle gates, persisted 13 maturity proposal/verifier assessments,
  and rendered 7 consolidated facts. It passed four of seven acceptance dimensions.
- The transfer fixture remains not release-ready because the model did not co-resolve initial “1920s kitchen”
  references with the later “kitchen renovation” identity. The independent maturity verifier correctly rejected the
  resulting single-episode Project's invented prior-history basis, leaving it provisional. This is retained as an
  inspectable identity/review-quality miss rather than overridden with lexical matching.
- Validation: **253 passed, 2 skipped**; focused FactResolver and Dream tests passed **46/46**; Ruff and
  `git diff --check` passed.

## 2026-08-31 — Bounded, resumable identity work units

- The fresh LoCoMo conversation 48 run showed that retryable claims were repeatedly combined into a growing
  all-or-nothing identity contract. Identity work is now bounded to 16 claims in stable cohort order. A malformed
  subject, matching, type, maturity, entity-plan, or routing response fails only that unit; sibling units continue.
- Added durable identity work-unit artifacts containing exact claim/source membership, attempt history, current
  stage, failure reason, and validated subject, matching, type, maturity, and entity-plan outputs. A retry resumes
  after the last persisted successful stage instead of regenerating its subject census or other accepted decisions.
- Before integration, a direct `gemma4:12b` production-prompt probe produced a valid subject census for a six-claim
  neutral cohort. A counterexample with two different people named Rowan remained structurally separate, but the
  matcher incorrectly declared both new while its reasons associated them with existing registry histories. This
  confirms that bounded execution is structurally viable and that cross-run new-identity verification must remain a
  separate next step; no title or lexical fallback was added.
- Validation: focused Dream/artifact/store/reconsolidation tests passed **113/113**; Ruff and `git diff --check`
  passed.

## 2026-08-31 — Independent cross-run new-identity verification

- Added an independent verifier before canonical creation for every identity initially classified as new when an
  active canonical identity of the same fixed ontology type already exists. Registry comparisons are bounded to 12
  candidates per call. Exact `existing` decisions reuse the canonical ID, `review_required` preserves all plausible
  IDs for inspection, and only unanimously `distinct` partitions permit new creation. Multiple competing positive
  or ambiguous partitions fail closed to review.
- The verifier has its own strict Jinja prompt and discriminated structured-output schema. It cannot change ontology
  type, maturity, containment, or ownership, and exact registry IDs are schema-constrained. Final verdicts and
  evidence-backed reasons are persisted in the resumable identity work unit. No name, title, token, fuzzy, or
  benchmark-derived comparison was added.
- Before integration, the exact proposed contract was probed directly with `gemma4:12b`. It matched a proposed Ada
  identity to canonical Ada from specific continuing Bluebird history. In the counterexample, a generic statement by
  someone named Rowan could not distinguish the canonical baker from the canonical researcher, so it returned
  `review_required` with both exact candidate IDs.
- Validation: focused Dream/prompt/artifact/store/reconsolidation tests passed **120/120**; Ruff and
  `git diff --check` passed.

## 2026-08-31 — Incremental owner fact resolution

- Fact resolution no longer sends an owner's complete accumulated claim history through truth and grouping on every
  update. New-to-owner claims first scan existing presentation facts in bounded partitions of 12. Only selected fact
  groups and their canonical member claims enter truth adjudication and regrouping; structurally affected groups are
  always included, and every unselected fact is preserved exactly.
- Added a strict candidate-selection schema and Jinja prompt. This stage can only select exact supplied fact aliases
  and explain relevance; it cannot decide truth changes, grouping, sections, or wording. Selection remains semantic
  and model-driven, with no token, predicate, title, fuzzy, or benchmark-specific shortcut.
- Before integration, a direct `gemma4:12b` probe selected the prior tea-preference fact for an incoming coffee
  preference, selected nothing for an unrelated hiking plan, and correctly rejected a tea-colored paint statement as
  merely sharing vocabulary. This demonstrated the intended high-recall semantic boundary and counterexample.
- Validation: focused fact/Dream/prompt tests passed **56/56**; the incremental preservation test proves that an
  unselected existing fact is excluded from the grouping prompt and returned byte-for-byte unchanged. Ruff and
  `git diff --check` passed.

## 2026-08-31 — Verified self-contained presentation facts

- Every newly rendered fact batch now receives an independent structured quality verdict. Supported text must be
  understandable under its owner and section without conversational context, identify the relevant subject and
  object or activity, preserve qualifiers and constraints, and remain entailed by every fixed member claim.
- Unsupported facts receive one bounded repair call that is schema-forced to preserve the exact fact key, state, and
  section. The repaired subset is independently verified again. If it remains unsupported, owner resolution fails
  closed and preserves the prior projection. No pronoun list, keyword rule, regex, or other deterministic semantic
  fallback was added.
- Direct `gemma4:12b` probes rejected the context-dependent text “Jolene wants to try it,” repaired it to the
  source-grounded standalone fact “Jolene wants to try surfing and is looking for a lesson,” and then accepted the
  repaired text on a second independent verification call.
- Validation: focused fact/Dream/prompt tests passed **57/57**, including a complete reject-repair-reverify pipeline;
  Ruff and `git diff --check` passed.

## 2026-08-31 — Type-verifier considered alternatives

- The first integrated frozen-extraction replay at
  `benchmark_runs/daily-driver-unrelated-v1-bounded-replay-20260831` reached the second Dream with exact source
  accounting, then failed one bounded identity unit at type verification. All three raw responses coherently chose
  `supported: project` for the renovation while listing `series` as a weaker considered alternative; the schema
  rejected supported verdicts whenever the alternatives list was non-empty.
- The alternatives list is now audit information under a supported verdict as well as required evidence of the
  unresolved boundary under ambiguous/unsupported verdicts. The verdict remains authoritative downstream, and the
  prompt explicitly distinguishes a weaker considered type from a materially plausible ambiguous alternative.
- A direct `gemma4:12b` production-prompt/schema probe accepted `project` for a bounded accessibility upgrade while
  recording `artifact` as considered but weaker. No parser repair or semantic fallback was added.

## 2026-08-31 — Authoritative review boundaries and existing-match verification

- The first corrected bounded replay,
  `benchmark_runs/daily-driver-unrelated-v1-bounded-replay-v2-20260831`, completed both Dreams after the type-verifier
  schema fix but exposed an identity authority defect. Automatically accepted entity decisions were included under
  `PRIOR REVIEWED IDENTITY DECISIONS` in later work units. The matcher consequently treated its own earlier output as
  user authority, matched a thirty-inch induction range to Rosa Alvarez and oak cabinets to the renovation Project,
  and then overwrote both canonical titles with those evidence phrases.
- The reviewed-decision catalog now requires a real `reviewed_at` timestamp in addition to an accepted or rejected
  state. Automatic decisions remain inspectable but cannot recursively become authoritative. A focused persistence
  test proves that only the human-adjudicated record enters the prompt catalog.
- Every identity initially matched to an existing canonical ID now receives an independent identity-only verification
  call before it can inherit that entity's fixed type and continue to maturity or routing. The verdict is persisted in
  its bounded identity work unit for resumable execution. A rejected exact ID returns to normal type resolution and is
  excluded from the subsequent same-type new-identity scan; ambiguous matches fail closed to review. No title,
  vocabulary, fuzzy, or other deterministic semantic comparison was added.
- Before integration, direct production-prompt/schema probes against `gemma4:12b` rejected a thirty-inch induction
  range proposed against canonical Rosa Alvarez as `distinct`, while accepting Rosa Alvarez against the same
  canonical person when the supplied evidence and registry facts shared the specific renovation history.
- The post-integration frozen replay is
  `benchmark_runs/daily-driver-unrelated-v1-bounded-replay-v3-20260831`. Both Dreams completed with zero failures; it
  preserved exact 6/6 claim-bearing and 2/2 source-only accounting, routed and rendered all 10 active claims, passed
  both lifecycle gates, and retained correct canonical titles for Rosa Alvarez, the 1920s kitchen Project, and You.
  All three identity work units completed with persisted verifier results and no malformed-output debug dumps.
- The replay remains intentionally not release-ready. The model left the kitchen-renovation identity ambiguous with
  the provisional 1920s-kitchen Project, then routed three appliance/inspection claims to Rosa even though its own
  route reasons said that the Project was the intended owner. This is recorded as a separate routing-consistency and
  project-co-resolution quality miss; it was not hidden with a lexical owner override or benchmark-specific rule.
- Validation: focused identity, prompt, artifact, and reconsolidation tests passed **112/112**; the complete maintained
  suite passed **262/262 with 2 skipped** using host access for Ollama-dependent tests. Ruff and `git diff --check`
  passed.

## 2026-08-31 — Durable unresolved-identity claim blockers

- The bounded v3 replay showed that an initial identity work unit correctly deferred claims associated with a
  provisional or review-required kitchen Project, but a later overlapping revision census omitted that unresolved
  subject and replaced the deferrals with routes to Rosa. The route reasons still named the Project as the intended
  owner. The defect was loss of structured identity state across work-unit and Dream boundaries, not a need for a
  lexical Project-owner override.
- Deferred routes now carry exact identity-resolution decision IDs whenever their supporting subject is provisional
  or review-required. Revision merging cannot replace such a route with a canonical route, and placements plus scope
  decisions persist the blocker IDs across Dream runs. A persisted blocker clears only when its review decision is
  rejected, or when its accepted provisional entity is the exact entity that becomes materialized. Missing blocker
  records fail closed. Manual placement remains an explicit user override and therefore starts without automatic
  blockers.
- The Memory Inspector displays unresolved blocker IDs on the claim's latest Dream decision. The mechanism uses only
  exact artifact IDs and declared review/page states; it does not inspect claim text, model rationale, titles, or
  vocabulary. No prompt, ontology, or division of model labor changed, so no direct semantic probe was required.
- The post-integration frozen replay is
  `benchmark_runs/daily-driver-unrelated-v1-bounded-replay-v4-20260831`. Both Dreams completed with zero failures and
  passed both lifecycle gates. This trial independently materialized `Project: Kitchen Renovation`; the range price,
  electrical requirement, and permit inspection routed to that Project, while Rosa retained only her project-role
  claim. Three claims with review-required identity decisions remained deferred through the overlapping revision and
  persisted their exact blocker IDs instead of being reassigned.
- Validation: focused Dream, artifact, API, queue, and reconsolidation tests passed **116/116**; the complete maintained
  suite passed **264/264 with 2 skipped**. Ruff, `git diff --check`, UI lint, and UI production build passed. The
  existing 854.63 kB UI chunk-size warning remains.

## 2026-08-31 — First-class canonical correction and source retraction

- Explicit claim correction now creates a new canonical claim backed by its own `manual_correction` source and
  complete episode evidence, links it as the superseding claim, preserves an established placement, and rebuilds the
  affected facts and wiki page. The replaced claim remains available as inactive canonical history. Corrections are
  only accepted for active claims and require a user-authored reason.
- Sources now have a validated active/retracted lifecycle with a timestamp and reason. Retraction preserves the
  source and all provenance for audit, retracts an active claim only when none of its supporting sources remain
  active, and rebuilds every affected owner so unsupported facts disappear. A claim with independent active source
  support remains canonical.
- The Memory Inspector exposes both operations and displays source lifecycle state and retraction details. These are
  explicit user decisions over exact artifact IDs; no semantic prompt, ontology, natural-language rule, or model
  division changed, so a direct Ollama probe was not applicable.
- Validation: lifecycle/artifact/store/reconsolidation tests passed **81/81**; endpoint and lifecycle tests passed
  **12/12**; the complete maintained `tests/` suite passed **271/271 with 2 skipped**; UI lint and production build
  passed. Repository-root pytest also collected a generated `benchmark_runs/mab-loader-check/test_routing_q49.py`
  artifact that imports the intentionally removed `routing_recall_index`; the maintained suite is scoped to
  `tests/`.

## 2026-08-31 — Retrieval abstention and a total assistant prompt budget

- Page FTS, temporal matching, and short-term claim search now generate bounded candidates only. A structured
  relevance decision evaluates every candidate, can exclude all of them, and fails closed to no memory on malformed
  output. The previous title/slug word-intersection admission override was removed. No lexical score threshold,
  keyword margin, fuzzy match, or benchmark-derived semantic rule was introduced.
- Before integration, direct production-prompt/schema probes against `gemma4:12b` included a record that directly
  answered a scheduling question, rejected an unrelated project record, distinguished a jasmine-tea preference from
  a paint color containing “Tea,” and excluded every candidate for an unrelated writing request.
- Assistant chat assembly now enforces `session.context_budget_tokens` as one budget across the system prompt,
  current request, recent transcript, and admitted memory, capped by the model context window. It preserves the most
  recent transcript first, admits memory only when the complete prompt still fits, backfills older history with
  remaining space, and retains the end of an individually oversized current request. The exact pages that survive
  prompt assembly are the pages reported to the UI and session log.
- Validation: focused retrieval, prompt, context, runtime, and budgeting tests passed **25/25** before the portability
  cleanup and **23/23** afterward; the complete maintained suite passed **278/278 with 2 skipped**. Ruff and
  `git diff --check` passed. The direct probes were valid structured responses with no timeouts or malformed output.

## 2026-08-31 — Crash-idempotent ingestion and Dream lifecycle persistence

- Source ingestion now records a stable operation identity and input digest before writing its log, source, episode,
  or claims. Production chat episodes, tool observations, Engram meetings, benchmark batches, and session transcripts
  supply stable idempotency keys. Repeating the same request resumes its episode; reusing a key for different input is
  rejected. Log append is atomic and idempotent within the process, and extracted claim IDs are deterministic per
  source batch so a claim written before an episode checkpoint is overwritten rather than duplicated on retry.
- Dream now journals its complete artifact write set before applying it. Entity, placement, fact, proposal, retention,
  identity, encounter, scope, cohort, projection, log, and audit writes are replayed in dependency order. Claim
  dispositions are published only with the final Dream audit after projection and log persistence. Every non-dry run
  first recovers prepared/applying commits, and exact run/claim-derived IDs make replay idempotent.
- A simulated ingestion interruption immediately after the first claim write recovered to one log, source, episode,
  and claim. A separate restart test interrupted a Dream commit immediately before audit publication, constructed
  fresh repository/store/service instances, then recovered one fact, scope decision, cohort, Dream audit, routed
  claim state, consolidated log, and an unchanged wiki page version.
- No prompt, ontology, or semantic division changed, so no direct Ollama probe was applicable. Validation: focused
  ingestion/store/runtime/Engram tests passed **91/91**; focused Dream/recovery tests passed **130/130**; the complete
  maintained suite passed **282/282 with 2 skipped**. Ruff and `git diff --check` passed.

## 2026-08-31 — Referentially complete entity merge and manual curation

- Manual entity merge now redirects every live canonical endpoint: placements, facts, claim-entity references,
  entity-resolution decisions and proposed parents, maturity assessments, encounters, scope cohorts and decisions,
  pending organization proposals, reconsolidation affected entities, and non-complete identity work-unit payloads.
  Active claim and scope references receive explicit manual successors while their original records remain as
  superseded history. Proposal meaning, titles, and rationale are not rewritten.
- Artifact persistence rejects placed claims, consolidated facts, active references, and encounters that point to
  archived or merged entities. Identity review likewise rejects inactive selected IDs. Merge refuses to run while a
  Dream commit is prepared/applying, preventing a recovered write set from resurrecting pre-merge entity endpoints.
- Artifact integrity reporting now identifies inactive entity endpoints in placements, facts, active references,
  active scope decisions, encounters, live identity decisions, maturity assessments, and scope cohorts.
- This change only redirects exact canonical IDs under an explicit user curation action; it makes no language-level
  identity judgment and changes no prompt or ontology, so a direct Ollama probe was not applicable. Validation:
  focused curation, artifact, API, and recovery tests passed **81/81**; the complete maintained suite passed
  **285/285 with 2 skipped**. Ruff and `git diff --check` passed.

## 2026-08-31 — Production-path memory lifecycle acceptance

- A production-shaped acceptance test now enters through the real session API and session file, overlaps chat
  generation with automatic episode flushing, and verifies that the per-session lock prevents the flush from
  racing ahead of the new turn. It also checks persisted message timestamps, relative-date normalization, the
  total assistant prompt budget, short-term recall, complete retrieval abstention, canonical correction, source
  retraction, and state visibility from a newly constructed store.
- The fixture uses a deterministic schema-aware model double so storage, API, locking, and lifecycle behavior are
  isolated from semantic variance. It supplies only IDs declared by the production structured-output contracts and
  accounts for every extraction segment. It is therefore production-path structural evidence, not a fresh or judged
  real-model semantic trial. The earlier retrieval work separately records fresh direct production-prompt/schema
  probes; restart recovery of an interrupted Dream journal remains covered by its dedicated fresh-store test.
- No prompt, ontology, or semantic division changed in this task, so a new Ollama probe was not applicable.
  Validation: the focused production/runtime/recovery/lifecycle/context suite passed **18/18**; the complete
  maintained suite passed **286/286 with 2 skipped**.

## 2026-08-31 — Honest temporal and provenance-aware wiki presentation

- Removed wiki page confidence from the canonical model, Markdown frontmatter, update history, store filtering,
  retrieval context, chat metadata, APIs, benchmark snapshots, and frontend types. The deleted value was only the
  mean of claim-model confidences and did not measure page completeness, unresolved conflicts, currentness, source
  support, or scope quality. No substitute score is exposed until those dimensions have an explicit contract.
- Deterministic page compilation now formats normalized temporal start/end values from structured claim facets,
  orders Timeline facts and encounters by semantic event time, and retains the original temporal expression in
  structured evidence metadata. The Wiki evidence view shows source wording beside the normalized value. No claim
  text, vocabulary, or benchmark phrase is parsed during presentation.
- Generated Markdown now carries compact exact-source footnotes down to segment IDs. The link-only Recent Changes
  section was removed from the authoritative ontology rather than continuing to duplicate Memory Map without a true
  fact-diff lifecycle.
- Because the ontology changed, direct production-prompt/schema probes against `gemma4:12b` were run after
  integration. A neutral profile preference rendered to `preferences_working_style`; a project deadline
  counterexample rendered to `next_steps_deadlines`. Both returned valid exact fact-rendering contracts.
- The post-integration real-model trial at
  `benchmark_runs/daily-driver-unrelated-v1-presentation-replay-20260831` is a **replayed-extraction**, unjudged
  downstream run, not fresh extraction. Both Dreams completed with zero failures; it preserved exact 6/6
  claim-bearing and 2/2 source-only accounting, passed both hard lifecycle gates, and produced pages with source
  footnotes and without page confidence or Recent Changes. It passed 5/12 measured dimensions and 3/7 acceptance
  dimensions. The model again left the kitchen Project unresolved, so entity/ownership/page projection remained a
  meaningful identity-quality failure; it was not overridden in presentation.
- Validation: focused page/ontology/context/store tests passed **39/39**; the complete maintained suite passed
  **288/288 with 2 skipped**; Ruff, `git diff --check`, UI lint, and UI production build passed. The existing large
  frontend chunk warning remains.

## 2026-08-31 — Inspectable frontend memory review and lifecycle controls

- Memory Inspector now has one review inbox for pending identity, claim-reconciliation, and organization decisions.
  Provisional identities and persisted maturity/verifier evidence are visible alongside the actionable queue without
  presenting evidence-waiting states as approval tasks. Overview counts expose the same exact backend states.
- Canonical correction now lets the user replace the claim text and its declared claim type, predicate, temporal
  status, and reason. Source evidence can still be retracted with a reason. Claims link unresolved identity blockers
  to the exact identity adjudication and wiki facts link non-authoritative rendering to the exact pending truth-change
  proposal.
- Identity review now exposes the complete downstream contract: selecting or creating the canonical identity,
  correcting its ontology type and title, choosing independent/contained/event/context scope, choosing provisional
  or materialized page admission, and selecting an exact parent where containment requires one. Approve and reject
  both use the existing rerouting endpoint.
- Entity inspection distinguishes canonical provisional identities from materialized pages and includes persisted
  maturity proposals and verifier results. Entity detail API responses now attach those assessments by exact entity
  ID. No prompt, ontology, or semantic decision rule changed, so an Ollama probe was not applicable.
- Validation: UI lint and production build passed; focused artifact/wiki tests passed **26/26**; the complete
  maintained suite passed **288/288 with 2 skipped**; `git diff --check` passed. Repository-root pytest additionally
  collects an old generated benchmark test that imports the intentionally removed `routing_recall_index`; maintained
  tests remain scoped to `tests/`. The existing large frontend chunk warning remains.

## 2026-09-01 — Contract-aware Dream structured-output recovery

- The completed LoCoMo conversation-8 run reported generic JSON parsing failures, but exact replays with structured
  debug capture showed valid JSON rejected by cross-record validators: extraction omitted an admitted segment, and
  identity matching proposed two groups with the same exact canonical entity ID. An entity-plan failure separately
  crossed a schema that allowed containment under a parent the downstream contract rejected.
- Structured-output retries now include the invalid assistant response and exact validation error instead of making
  the same blind request. Final failures preserve the underlying error type and message. The extraction coverage
  validator identifies missing and unexpected exact segment IDs, so a retry can repair the incomplete contract.
- Identity groups that select the same exact existing entity ID are coalesced before validation; this implements the
  invariant that one canonical ID denotes one identity and makes no language-level identity decision. Entity-plan
  validation now enforces the existing downstream invariant that a graph parent is accepted and independently
  materialized or provisional before a child can be contained beneath it.
- Before integration, an exact production-prompt/schema correction probe against `gemma4:12b` repaired the persisted
  six-segment extraction failure on its first correction turn. After integration, the exact 16-claim identity work
  unit that had failed all three original attempts replayed to completion with 16 routes, 2 proposed entities, and no
  failures on a disposable copy of the benchmark store.
- Validation: focused Ollama/Dream tests passed **66/66**; the complete maintained suite passed **292/292 with 2
  skipped**.

## 2026-09-01 — Recovered extraction operation consistency

- Dream's pre-run extraction retry now updates the ingestion operation tied to the exact episode ID after every
  retry. A recovered episode is marked complete with its stale error cleared; an episode that remains incomplete
  keeps a failed operation and the current extraction error. This closes the observed state split where session 9's
  episode recovered but its ingestion operation remained failed.
- No prompt, ontology, or semantic decision changed, so no additional model probe was applicable. Validation:
  focused artifact/core/runtime/production-lifecycle tests passed **69/69**; the complete maintained suite passed
  **292/292 with 2 skipped**.
- Post-integration, the exact failed episode from
  `benchmark_runs/locomo-mycelium-convo-8-fresh-overnight-20260901` was replayed against `gemma4:12b` on a
  disposable store copy. Its persisted batch moved from coverage-complete/claims-failed at attempt 14 to complete
  at attempt 15; the episode and ingestion operation both became complete with no remaining error.

## 2026-09-02 — Sequential identity matching with accumulated local identities

- Replaced cohort-wide identity partitioning with one canonical-registry decision per subject node. Each call sees
  the complete current registry but only the current node and its supporting evidence, so the structured contract
  requires an exact decision for that node instead of allowing later nodes to disappear from an otherwise valid
  response.
- Canonically new nodes receive a separate comparison against previously accumulated, canonically new local
  identities. This separation matters: an initial combined canonical/local probe could explain a canonical match
  while selecting an unrelated local target. Existing canonical identities are merged only by exact entity ID;
  all language-level identity judgments remain structured model decisions.
- Canonical node decisions, local accumulation decisions, and the accumulated identity groups are checkpointed
  after each successful step. A failed work unit therefore resumes at the unfinished node or unfinished local
  comparison without repeating successful model decisions.
- Before integration, direct `gemma4:latest` production-prompt/schema probes correctly matched a neutral known
  person to the canonical registry and joined an explicit project alias to a prior local identity. A production
  node from the failed conversation-8 work unit also matched the correct canonical topic on its first call. The
  combined-decision design was rejected after a real-model replay exposed target-confusion; the split contract was
  then probed directly before integration.
- Post-integration, the exact 17-node work unit `identity-work-264b88732bba0a96` replayed on a disposable copy at
  `/tmp/mycelium-sequential-final-replay.Qoc07m`. It completed with 17/17 canonical decisions, 4 required local
  comparisons, 17 accumulated identities, 16 claim routes, and zero failures or structured-output retries. The
  existing subject census still proposed several date-like nodes; changing census quality is intentionally outside
  this task.
- Validation: focused Dream/prompt tests passed **56/56**; the complete maintained suite passed **295/295 with 2
  skipped**; Ruff and `git diff --check` passed. Repository-root pytest still collects the unrelated generated
  benchmark scratch test that imports the intentionally removed `routing_recall_index`.

## 2026-09-02 — Centralized subject representation ontology

- Moved the existing extraction `about` policy, subject-census eligibility policy, routing endpoint policy,
  entity-planning scope definitions, containment guidance, and page-state guidance out of their individual prompt
  templates and into the authoritative ontology module. Prompt entry points now inject the relevant projection of
  that shared definition.
- Subject scopes now centrally declare their model-facing key, persisted review scope, and resulting page state.
  Entity-plan schemas, consolidation, formatting, persisted-artifact validation, and identity-review validation
  consume those authoritative values instead of maintaining separate scope/page-state lists and mappings.
- This was intentionally a semantic no-op. Before and after SHA-256 hashes and character lengths were identical for
  the rendered census (`02b4b837…`, 1743), extraction (`83ba9415…`, 3138), entity-plan (`b9359e00…`, 3321), and
  claim-routing (`be54501b…`, 1493) system prompts. Because the production prompts and structured decision space did
  not change, a new Ollama semantic probe was not applicable.
- Validation: focused ontology/prompt/Dream/review tests passed **69/69**; the complete maintained suite passed
  **296/296 with 2 skipped**; Ruff and `git diff --check` passed.

## 2026-09-02 — Clear, extraction-grounded subject census prompt

- Rewrote the census policy in plain language. It now defines a census and temporary subject node before giving
  instructions, explains the `C...`, `P...`, `N...`, registry, provisional-identity, and reserved `you` concepts,
  distinguishes subjects from claim-local details and temporal metadata, and states the exact responsibilities left
  to later identity, type, relationship, and page-admission stages.
- The user prompt now labels its inputs directly and includes an `ELIGIBLE SUBJECT CANDIDATES` checklist generated
  only from extraction's structured `about` mentions and source-declared participants. This is a presentation of
  existing structured decisions, not lexical entity discovery. The model is instructed to treat those entries as
  authoritative and to use the remaining claim, source, qualifier, stable-reference, and registry content only as
  evidence and context.
- Direct first-attempt production-schema probes used `gemma4:latest`. A neutral person/project example produced both
  required nodes, while an event/place counterexample produced the event and place without promoting either the
  claim date or the source timestamp. Earlier candidate wording was rejected after it either promoted the source
  timestamp or undercounted the neutral and frozen cohorts.
- The frozen 16-claim conversation-8 work unit `identity-work-264b88732bba0a96` was first probed at the census stage,
  where the final prompt returned exactly Deborah, Jolene, a photo, Deborah's mother, and Jolene's partner—no date or
  incidental-detail nodes. A full disposable replay at `/tmp/mycelium-census-pipeline-replay.KqDzLO/store` then
  completed in one work-unit attempt with the same five persisted nodes, five canonical identity decisions, 16/16
  routes, and no failures.
- That replay still exposed downstream identity-quality issues in the previously polluted registry: identity
  matching selected the existing parents Organization for Deborah's mother despite a Person candidate, and treated
  Jolene's partner as new despite an existing Person. Those decisions were preserved and are not overridden by the
  census prompt change.
- Validation: focused prompt/ontology/Dream tests passed **64/64**; the complete maintained suite passed **298/298
  with 2 skipped**; Ruff and `git diff --check` passed.

## 2026-09-02 — Evidence-first type and identity verification

- Canonical identity types may overlap in their names and aliases: a person and an organization can both be valid
  subjects with the same label. Identity verification now follows the independently proposed and verified ontology
  type rather than inheriting the type of the initial registry match. A supported type bounds the verifier's
  registry candidates; ambiguous type evidence enters user review.
- Type proposal, type verification, and identity verification now receive a neutral subject rendering containing
  only the census title and cited evidence aliases. The initial match's resolution, entity ID, and inherited aliases
  are omitted, so those later decisions are grounded in source evidence rather than the earlier hypothesis.
- The identity-verification prompt was simplified to one affirmative contract: determine whether the evidence
  identifies exactly one canonical subject, multiple plausible subjects requiring review, or no existing subject.
  It contains no benchmark-specific language or person/organization example.
- A proposed full-registry verifier was rejected before integration. Although a two-candidate direct probe handled
  the intended ambiguity, a frozen pipeline replay produced unrelated candidates across independently evaluated
  registry chunks. The retained type-bounded design uses the existing division of model labor instead of adding
  prompt exceptions or deterministic name matching.
- Direct `gemma4:latest` calls with the production type proposal and verifier schemas classified the neutral
  “Deborah's mother” evidence as `person` and verified that proposal as supported. A final frozen-census replay at
  `/tmp/mycelium-neutral-type-verifier-replay.wInGCQ/store` completed in one attempt with no failures: the initial
  matcher proposed `organization-deborah-s-parents`, while the independent type and identity stages resolved the
  final canonical identity to `person-deborah-s-mother`.
- Validation: all Dream routing tests passed **54/54**; the complete maintained suite passed **300/300 with 2
  skipped**; Ruff and `git diff --check` passed.

## 2026-09-02 — Authoritative typed memory lifecycle

- Added one high-level `MemoryPipeline` with four explicit operations: `ingest_source(SourceInput) ->
  IngestionResult`, `retrieve_context(RetrievalRequest) -> RetrievalResult`, `consolidation_status() ->
  ShortTermMemoryStatus`, and `consolidate(ConsolidationRequest) -> ConsolidationResult`. The result contracts expose
  created artifact IDs, rendered retrieval context, extraction retries, and the consolidation report instead of
  requiring callers to infer all outcomes from store mutations.
- Extracted retrieval orchestration from the `Mycelium` composition root into `MemoryRetriever`. `core.py` now wires
  repositories and services, exposes the typed lifecycle, and retains `session()` only as an ergonomic wrapper around
  retrieval and ingestion.
- Renamed the internal `DreamProcess` to `ConsolidationProcess` and introduced typed preparation and commit inputs.
  Queue/source preparation and durable commit construction are now named boundaries around the existing routing,
  fact-resolution, and materialization mechanics.
- Migrated web episode flushes, immediate tool observations, chat retrieval, Engram meeting finalization, benchmark
  ingestion/retrieval/consolidation, and examples to the same public façade. Removed the public `load_context`,
  `dream`, `dream_if_ready`, and `short_term_memory_status` aliases; no compatibility path was added.
- Updated the README with an input/output operation table and explicit integration example. Updated `DESIGN.md` to
  describe the current lifecycle modules and the actual sequential identity/type/maturity pipeline rather than the
  superseded combined entity-plan flow.
- This was an orchestration and contract refactor with no intended semantic or prompt change, so an Ollama semantic
  probe was not applicable. Validation: the complete maintained suite passed **303/303 with 2 skipped**; Ruff passed
  across the library, server, Engram, benchmarks, examples, and tests; and the UI lint and production build passed.

## 2026-09-02 — Plain-language memory decision prompts

- Rewrote the active memory prompt family around explicit tasks and locally defined terms. Fact resolution now tells
  the model how to distinguish an independent claim, a repeated new state, and a genuine replacement; grouping keeps
  opposing truth states separate; rendering and quality require each detail to be supported by the claim group as a
  whole rather than by every individual member claim.
- Identity matching now defines subject nodes and stored identities before stating its decision contract. Type,
  page-admission, representation, routing, extraction coverage, and extraction prompts similarly define their local
  concepts and distinguish the decision made in that stage from decisions owned by later stages. The extraction
  prompt explicitly defines `about`, its allowed roles, `slot`, `facets`, evidence modality, and explicit versus
  inferred evidence.
- The entity-planning call now receives the persisted page-admission proposal and verifier verdict for every node.
  Those results are fixed inputs when the model chooses independent versus contained representation, rather than a
  hidden upstream decision that the downstream schema alone attempts to enforce.
- Before integration, direct one-attempt probes against `gemma4:latest` used the proposed prompts and exact production
  schemas with neutral examples and counterexamples. The fact contract correctly selected one replacement among two
  compatible incoming claims, left an unrelated budget-review claim independent, kept old and new truth groups
  separate, and combined complementary supported details. The first routing draft incorrectly treated a Project
  requirement as a person's continuing role; an explicit positive decision order corrected that result. The first
  extraction draft used an unsupported `object` role; defining the exact `subject`, `owner`, and `participant` roles
  and requiring every explicitly named durable identity corrected the output.
- After integration, a second direct validation rendered prompts through the production entry points and used their
  exact structured schemas with `max_retries=1`. All calls passed on the first attempt: truth replacement and the
  independent-claim counterexample, fixed materialized/provisional entity planning, Person-role versus
  Project-requirement routing, extraction coverage, Person-subject/Project-owner extraction, and complementary fact
  rendering. No benchmark names, fixture vocabulary, lexical rules, or post-hoc semantic overrides were added.
- Validation: focused prompt/ontology/Dream tests passed **69/69**; the complete maintained suite passed **309/309
  with 2 skipped**; Ruff and `git diff --check` passed.

## 2026-09-03 — Partial-run pipeline correctness fixes

- Made a placed-to-deferred routing transition authoritative throughout fact resolution. Every successful route,
  including a deferred route, now participates in affected-owner discovery and the resolver's placement snapshot, so
  a claim removed from an owner deletes its stale derived fact and disappears from regenerated page content in the
  same Dream commit.
- Replaced the global truth-change comparison with bounded sequential decisions. Prior-fact selection now evaluates
  one incoming claim against bounded fact partitions and preserves a per-claim candidate map. Truth adjudication then
  sees one incoming claim and only the older claim members selected for it; accepted target choices accumulate and are
  unavailable to later calls. This removes the cross-batch uniqueness failure rather than retrying it. An initial
  in-situ probe exposed that the incoming claim was also rendered under the older-target heading; separating those
  prompt inputs corrected the contract. The final production-prompt probe classified an explicit bicycle-color
  replacement as `supersedes`, its later supporting repetition as `no_change`, and an unrelated budget plan as
  `no_change`, all on first attempts.
- Added the persisted source-participant roster to every extraction call. The production prompt defines it as an
  unordered attendance list and combines it with speaker labels and turn context. Direct `gemma4:latest` probes
  resolved “both of us” in a two-person source to both named participants and selected an explicitly addressed person
  from a three-person roster. A three-person example without an identified addressee remained ambiguous and the model
  selected a roster member anyway; no deterministic semantic override was added because the current task was context
  delivery, not a new ambiguity representation contract.
- Added a distinct unresolved-proposal matching stage between within-batch identity accumulation and type decisions.
  It compares each noncanonical identity group with bounded persisted `review_required` creation proposals using exact
  decision IDs and source-backed proposal evidence. An exact match keeps the proposal unresolved, merges the new
  source/claim/segment support into the same decision, and blocks the new claim on that existing decision instead of
  creating a competing proposal. Ambiguous matches cite the existing proposal IDs and remain deferred. A direct prompt
  probe matched new lease evidence to the correct pending cafe and kept an unrelated bakery distinct. A disposable
  full `ClaimRouter` run with the real model completed without failures, returned only
  `identity-northwind-review`, accumulated both claims, and deferred the new claim on that same blocker.
- Centralized the durable-owner policy with the ontology. Every materialized identity can own its own durable record;
  the policy now explicitly distinguishes Organization operations and history, Project state and work, and Person
  commitments and personal history. Production probes routed weekend operating hours to the Organization while
  routing a person's volunteering commitment to the Person. Fact grouping now treats a new source event as support
  for an existing display fact when the claims express the same durable state, while distinct memories remain
  separate. A reused fact keeps its stable fact ID when it absorbs additional supporting claims. Production probes
  grouped equivalent weekend-hours claims together and kept delivery service separate.
- Validation: focused consolidation, extraction, prompt, ontology, and artifact suites passed **140/140**; the complete
  maintained suite passed **314/314 with 2 skipped**; Ruff passed across `mycelium` and `tests`.

## 2026-09-03 — LoCoMo accumulated-state correctness fixes

- Audited the twelve-session partial run at
  `benchmark_runs/locomo-mycelium-convo-2-refactored-e2e-20260903-005917`. Extraction accounted for all 799 source
  segments, but six of eleven committed consolidation runs had owner-scoped fact failures. The store also contained a
  completed fact whose text came from a different claim than its declared member, six competing review proposals for
  one studio, noisy truth-change proposals, and an integrity warning caused only by provisional entities without
  pages.
- Fact resolution now processes more than twelve unrepresented owner claims as accumulated groups of at most twelve.
  Fact rendering, quality verification, and repair each receive exactly one fact and its own fixed claim group per
  call, preventing another group's evidence from legitimizing cross-wired text and keeping presentation calls below
  the model context ceiling. A second failed
  verification now persists the initial draft, repair, both verdicts, and fixed group in the Dream failure reason.
  Recording timestamps were removed from fact-semantic evidence because an integrated real-model fixture initially
  rendered an unsupported September 3 event date from `recorded_at`; the corrected rerun at
  `/tmp/mycelium-fact-in-situ-v2-p4sxi6j4` completed with three correctly bound facts, no added dates, no failures, and
  no truth-change proposals.
- Truth-change output now has to state the shared durable field, prior value, incoming value, and transition evidence.
  The first revised wording still missed a genuine later bicycle-color state, so it was rejected. The final
  proposition-comparison contract returned `no_change` for an elaborated business priority, equivalent
  opened/started wording, and two compatible benefits, while returning `supersedes` with exact old/new values for the
  explicit repainting transition. The structured comparison is persisted on review proposals and displayed in the
  Memory Inspector.
- Unresolved entity proposals now retain immutable identity-defining claim IDs separately from their growing support
  set. Later matching sees that anchor evidence rather than every claim ever associated with the proposal, and review
  proposals created by one bounded identity unit are accumulated for subsequent units in the same Dream. Pending
  matching now runs after independent type verification and compares only proposals with the same exact verified
  ontology type. This prevents a Topic such as an activity from being compared with an Organization proposal merely
  because their broad subject matter overlaps. The integrated same-type prompt probe reused the intended studio
  proposal; the different-type boundary is deterministic and covered in the routing suite.
- Clarified the central extraction `about` contract around the record actually changed. Post-integration production
  prompt/schema probes assigned a person's operating-hours update to the named Organization as `owner`, while keeping
  the person's volunteering commitment on the Person and representing the Organization as `participant`.
- Page integrity now requires a wiki page only for active materialized entities. Re-evaluating the audited partial
  LoCoMo store reports healthy with no issues; its provisional entities remain intentionally page-less.
- Validation: the focused prompt, ontology, Dream, fact, artifact, and API suites passed **151/151** before the final
  type-ordering regression was added; the final complete suite passed **319/319 with 2 skipped**. Ruff, UI lint, UI
  production build, and `git diff --check` passed. The existing large UI chunk warning remains.

## 2026-09-03 — Five-session Dream failure follow-up

- Audited the five-session rerun at
  `benchmark_runs/locomo-mycelium-convo-2-refactored-e2e-20260903-032716`. All five ingestions and extraction
  manifests were complete, but all four attempted Dreams failed. The persisted diagnostics showed that a verifier
  call declared one member alias while still rendering every claim in its fact batch. The final Dream also exhausted
  the 32,768-token context while producing structured output. Fixed-group rendering now selects only the group's
  declared member aliases and only their linked registry entries; presentation rendering itself is singleton rather
  than a twelve-fact batch.
- The rerun also showed that source session timestamps had entered canonical claim semantics before fact rendering:
  41 of 78 claims used the source timestamp as their event-time expression and 20 embedded it in claim text. The
  extraction model no longer receives `SOURCE TIME` or per-segment timestamp metadata. It extracts temporal wording
  from the cited source words; the storage layer uses an unambiguous cited-segment timestamp to resolve a relative
  phrase. A proposed production prompt/schema probe against `gemma4:12b` kept an untimed rehearsal untimed and
  preserved “tomorrow” as a relative expression on its first attempt. Post-integration production Encoder checks at
  `/tmp/mycelium-untimed-check.yqDvec` and `/tmp/mycelium-temporal-check.KurpvY` persisted, respectively, only
  `observed_at` for an untimed durable statement and a correctly resolved 2026-09-04 event time for “tomorrow.”
- Identity creation now treats disagreement between the initial matcher and independent verifier about a same-type
  canonical candidate as `review_required`. It cannot turn that disagreement into a duplicate entity. A new entity
  remains allowed when the initial untyped match has a different verified ontology type and the correctly typed
  registry is adjudicated distinct. Entity-plan schemas receive identity-review state explicitly, and entity
  construction has a final exact-state guard requiring `identity_resolution=new`.
- A disposable real-model FactResolver run at `/tmp/mycelium-fact-singleton.iARMs2` rendered and verified two distinct
  facts on their first attempts with correct one-claim membership and no failures. Validation passed **147/147** for
  the combined Dream, fact, prompt, ontology, and artifact regression set, then **322/322 with 2 skipped** for the
  complete maintained suite. Ruff and `git diff --check` passed.

## 2026-09-03 — Two-session LoCoMo pipeline iteration

- Added a `--max-sessions` benchmark option, forwarded by `MAX_SESSIONS` in `scripts/benchmark-locomo.sh`, so a fresh
  run can exercise ingestion and Dream over a bounded session prefix without truncating the individual conversations.
- The first two-session run at
  `benchmark_runs/locomo-mycelium-convo-2-pipeline-iteration-20260903-01` extracted 22 claims but exposed one fact
  verification failure. A correctly rendered absolute date for “yesterday” was rejected because the verifier treated
  a linked conversation participant as required assertion content. Direct production-prompt probes accepted the
  evidence-supported dated fact and rejected a counterexample that falsely added the participant. The central fact
  evidence policy now defines linked registry entries as navigation context rather than evidence of involvement.
- The second run at
  `benchmark_runs/locomo-mycelium-convo-2-pipeline-iteration-20260903-02` exposed a separate interpretation error:
  the verifier treated an unresolved relative-time normalization as uncertainty about whether the source statement
  was supported. Direct production-prompt probes accepted the exact relative phrase and rejected an invented absolute
  date. The central evidence policy now distinguishes unresolved calendar normalization from epistemic uncertainty.
- The third fresh run at
  `benchmark_runs/locomo-mycelium-convo-2-pipeline-iteration-20260903-03` completed both Dreams without failures. All
  three identity work units completed on their first attempts; 22 claims yielded 18 placed facts and two coherent,
  cited person pages. Inspection found that routing's explicit object endpoints and incidental contextual identities
  were still collapsed into the same persisted link list, causing unsupported participant links on otherwise correct
  facts.
- Routing now constructs persisted relationship links only from the structured subject/object endpoint decisions.
  It still validates and retains the model's contextual identities on the transient route, but they no longer become
  relationship annotations on facts and wiki pages. The frozen-extraction replay at
  `benchmark_runs/locomo-mycelium-convo-2-pipeline-iteration-20260903-04` completed both Dreams and all three identity
  work units without retry or failure. It retained Gina as the explicit endpoint of Jon's commitment, removed Gina
  from Jon's unrelated Paris visit, and produced 17 evidence-bound facts across coherent Gina and Jon pages. One
  second-session claim was conservatively deferred rather than fabricated.
- Final replay integrity is healthy. All 148 source segments are accounted for: 22 claimed and 126 explicitly
  `source_only`, with no pending or unaccounted segments. The complete maintained suite passed **325/325 with 2
  skipped**; Ruff and `git diff --check` passed.

## 2026-09-03 — Complete LoCoMo sample-9 validation

- Monitored a fresh 25-session sample-9 build and corrected five contract failures as they appeared. An identity
  already materialized in the registry now remains materialized when matched by later evidence instead of being
  re-admitted from the current cohort alone. Direct production prompt/schema probes retained an existing entity and
  still classified a genuinely new, weakly supported identity as provisional.
- Truth-change sides now receive distinct fact keys in the grouping schema. The central temporal evidence policy also
  permits a canonical present-tense claim with unknown temporal status to remain present tense. The exact production
  grouping prompt separated both sides of a transition on its first valid real-model response.
- Added a structured fact-group quality decision before presentation rendering. It distinguishes equivalent claims,
  composable details, and groups that must be split. Direct production probes treated two names for the same mountain
  range as equivalent, split an unrelated cooking-class/routine group, and conservatively split a broad health bundle.
  Equivalent claims retain complete membership but give rendering one representative, preventing synonym lists from
  being presented as multiple objects.
- Rendering and its verifier now treat canonical claims—not raw extraction evidence—as the representation contract;
  extraction evidence has already been adjudicated upstream. A direct production probe preserved a canonical
  qualified therapy claim. Singleton facts and equivalent-group representatives are structurally constrained to the
  canonical display claim and skip synthesis verification, because they perform no semantic synthesis. Replaying the
  exact previously failing beach claim and the accumulated final store completed without failures.
- The completed run is
  `benchmark_runs/locomo-mycelium-convo-9-pipeline-validation-complete-20260903`. Its final store has 25 sources and
  episodes, 210 active claims, 159 facts, five entities, and no unconsolidated logs. Of 1,671 source segments, 196 are
  claimed and 1,475 are explicitly `source_only`; none are pending, unaccounted, or tied to failed/partial episodes.
  Two hundred claims are placed and ten are conservatively deferred for review. Historical failed Dream records from
  the monitored iterations remain in the audit trail, while the newest Dream completed with no failures or pending
  sources.
- All 196 QA queries completed without retrieval or answer errors. Mean answer score was **0.3805**; retrieval-context
  evidence recall was **0.2521**, compared with **0.7344** at claims, **0.6723** at wiki pages, and **0.9847** at raw
  sources. This identifies retrieval/context selection as the principal quality loss after a now-complete pipeline.
  The summary's 1,922-second elapsed time covers the QA continuation only, not the full memory-build runtime. Later
  Dream sessions often required 10–20+ minutes, so throughput remains a major follow-up even though correctness and
  accounting completed cleanly.
- Validation: the complete maintained suite passed **330/330 with 2 skipped**. Ruff and `git diff --check` passed.

## 2026-09-04 — Claim-first hybrid retrieval

- Replaced whole-page BM25 retrieval and lexical raw-log windows with a rebuildable LanceDB projection over active
  canonical and short-term claims. Source-policy exclusions never enter the index. EmbeddingGemma runs through the
  configured Ollama host, using its documented query/document task formats; LanceDB combines those vectors with its
  full-text index. Similarity only generates candidates—the structured assistant-context decision still explicitly
  admits or rejects every claim. The superseded page-search and lexical source-window modules were removed rather
  than retained as compatibility paths.
- A direct EmbeddingGemma probe correctly ranked Mira's cello memory over her gardening memory and Jonah's guitar
  memory for a Mira instrument question (`0.7061`, `0.5976`, `0.3263`), then ranked Jonah's guitar first for the Jonah
  counterexample (`0.7406`). On the frozen sample-9 store, hybrid claim retrieval found labeled evidence for 56.9%
  of applicable questions at 10 candidates and 62.0% at 20, versus 48.0% and 50.9% for the former lexical claim
  search. This established the candidate generator before production integration.
- Retrieval now renders selected canonical claims through their consolidated facts and renders factless or
  short-term claims directly. It attaches only the exact source segments cited by those claims, including persisted
  benchmark labels when present. Candidate rank, hybrid score, model disposition/reason, selected IDs, budgeted IDs,
  and selection failures are persisted with chat turns, returned by the API, recorded in benchmark answers, and
  inspectable from an expandable chat control.
- The production path was validated against a copy of the completed sample-9 store at
  `/tmp/mycelium-retrieval-validation-20260904`. With the real configured chat model and EmbeddingGemma, it selected
  and rendered exact cited evidence for Evan's Prius, the family's Jasper road trip, and Sam's prospective hobbies.
  Final validation passed **322/322 with 2 skipped**. Ruff, `git diff --check`, UI lint, and the UI production build
  passed; the existing large-chunk warning remains.

## 2026-09-04 — Sample-9 hybrid retrieval QA replay

- Ran all 196 sample-9 questions against the exact completed frozen store using `gemma4:latest` for QA and context
  admission plus `embeddinggemma:latest` for hybrid retrieval. The run completed without retrieval, structured-output,
  or answer-call failures at
  `benchmark_runs/locomo-mycelium-convo-9-lancedb-retrieval-20260904`.
- Retrieval evidence improved: overall context recall rose from **0.2521** to **0.3358**, and factual-question recall
  rose from **0.2975** to **0.3834**. Empty factual contexts fell from 73 to 41. Average factual QA input fell from
  3,767 to 284 tokens, retrieval time from 8.39 to 7.25 seconds, and answer time from 1.96 to 0.37 seconds.
- The final score nevertheless fell from **0.3805** to **0.3243**. Factual QA abstentions rose from 85 to 100; 25
  questions with some labeled evidence and 15 questions with all labeled evidence were still marked unanswerable.
  Replaying the exact Great Gatsby failure reproduced the abstention. Inspection showed that single cited segments
  often omit an antecedent, neighboring turn, or conversation timestamp needed to ground the question's full
  relation. The QA prompt also still names the removed `CANONICAL SOURCE LOG SNIPPETS` representation. The candidate
  stage reached 0.5957 factual evidence recall, which fell to 0.3825 after claim admission. The next retrieval change
  should therefore repair the evidence/QA contract and add bounded provenance neighborhoods before tuning the vector
  candidate generator.

## 2026-09-04 — Evidence-to-QA contract repair

- Source evidence now includes each exact cited line plus a bounded structural neighborhood: the cited source turn,
  two preceding turns, and one following turn. Turn boundaries come from extraction's persisted
  `parent_segment_index`, with segment order as the fallback; no vocabulary or benchmark labels participate in the
  decision. Cited lines are presented before optional surrounding context, and each source block states its
  conversation time. Memory records also expose persisted normalized temporal ranges from their member claims.
- Replaced the obsolete QA instruction about `CANONICAL SOURCE LOG SNIPPETS` and wiki summaries with the actual
  claim/fact/source-evidence contract. Context admission now sees the claim text, normalized timing, and consolidated
  representations that a candidate can contribute. It retains records that supply complementary pieces of a
  multi-record answer, while continuing to reject merely adjacent records.
- Direct `gemma4:latest` prompt/schema probes answered the supported Great Gatsby identity chain, rejected the same
  book for the wrong person, retained two complementary course records while excluding an unrelated preference, and
  used normalized timing for a supported period while rejecting a wrong period. Integrated frozen sample-9 checks
  then answered Great Gatsby, mid-August painting classes, and watercolor painting while healing; wrong-person and
  wrong-period queries remained unanswerable. The initially chronological evidence rendering still caused the
  temporal case to abstain; placing cited lines before surrounding context corrected it.
- Replaced the synchronous LanceDB bridge with its native async connection, table, indexing, and query APIs. The
  maintained suite passed **322/322 with 2 skipped** in an environment where LanceDB's native runtime is permitted;
  focused retrieval and admission tests, Ruff, and `git diff --check` also passed.

## 2026-09-04 — Assistant-directed memory retrieval

- Added a bounded read-only memory tool loop on top of automatic claim retrieval. Each response receives a small
  initial context, then may issue focused `memory_search` calls and inspect exact cited dialogue with
  `memory_sources`. Searches accumulate already-returned claim IDs, share one evidence-token budget, and expose their
  arguments and results in the existing chat and benchmark diagnostics.
- Probed the production assistant template and Ollama tool schema directly with `gemma4:12b`. Given evidence only
  about Evan's watercolor practice, a composed Evan-and-Sam question produced one focused search for Sam's creative
  outlets before answering. A counterexample asking only which instrument Mira practiced was answered directly from
  sufficient initial evidence without a tool call.
- The web chat retains Ollama web search/fetch alongside memory tools. Web observations continue through ingestion;
  memory reads are deliberately excluded so retrieval cannot manufacture duplicate evidence. The default Mycelium
  benchmark path now exercises this same agentic retrieval loop and records tool evidence for evidence-survival
  analysis. The obsolete keyword-based benchmark escalation planner and its templates were removed. After
  integration, the same two real-model cases reproduced the intended search/no-search behavior. Final validation
  passed **320/320 with 2 skipped**; Ruff, `git diff --check`, UI lint, and the UI production build passed.
- The first full frozen sample-9 QA replay completed all 196 questions without retrieval or tool failures and raised
  context evidence recall to **0.5964**, but 136 responses exhausted a benchmark-only 256-token generation limit while
  the model was still thinking. This caused 130 fallback refusals and made the **0.1615** score invalid. Removed that
  override from benchmark QA so Ollama uses its normal generation behavior; regression assertions now protect both
  the agentic and structured benchmark calls. The full maintained suite again passed **320/320 with 2 skipped**.
- A balanced five-per-category frozen sample-9 panel at
  `benchmark_runs/locomo-convo-9-agentic-retrieval-panel5-uncapped-20260904` completed 25/25 without system or tool
  errors. Retrieval context recall was **0.6823**, with all required evidence present for 60% of questions, but the
  score was only **0.1313**. Inspection exposed a benchmark wiring mismatch: agentic QA did not pass its configured
  32K `num_ctx` to `call_messages`, so Ollama used a 4K context. One initial prompt exhausted that context, while
  follow-up tool evidence could displace the original question and cause dialogue continuations or “I need a
  question” replies. Tool-using questions averaged **0.0061** despite successful tool execution. No full replay
  should be interpreted or started until the configured context window reaches the tool loop.
- Passed the configured 32K context window into benchmark agentic QA, matching the production chat call. On the same
  balanced panel at `benchmark_runs/locomo-convo-9-agentic-retrieval-panel5-numctx-20260904`, all 25 responses stopped
  normally, lost-question replies disappeared, runtime fell from 815 to 330 seconds, and score rose from **0.1313**
  to **0.3855**. Retrieval recall remained **0.6823**, isolating the prior collapse to context-window wiring.
- Replaced the benchmark answer-style paragraph with a clear injected Jinja contract: fact questions return the
  requested value, time questions return one natural time phrase, and synthesis questions return one sentence of at
  most 30 words. Neutral direct probes produced a value-only car answer, a one-sentence shared recommendation, a
  concise relative time, and a consistent refusal for an unsupported relation. The final identical panel at
  `benchmark_runs/locomo-convo-9-agentic-retrieval-panel5-concise-v2-20260904` completed without system, tool, length,
  or truncation failures. Mean output fell from 29.4 to **15.1 tokens** and score reached **0.4078** at the same
  **0.6400** context recall as the immediately preceding prompt run. The maintained suite passed **320/320 with 2
  skipped**; Ruff and `git diff --check` passed.

## 2026-09-04 — Exact-segment evidence survival

- Replaced turn-label presence accounting with exact source-segment coverage. LoCoMo evidence labels identify whole
  dialogue turns, which Mycelium splits into sentence segments; the previous report incorrectly credited an entire
  turn when any one segment carrying its label appeared in a claim, page, or QA context.
- Each stage now reports fully present, partially present, and missing labels, plus per-label fractional coverage.
  Context coverage is determined from persisted segment IDs rather than printed benchmark labels. On the frozen
  sample-9 fitness-watch case, claim coverage is now **0.2** and context coverage **0.0**, correctly exposing that a
  different sentence from the five-segment gold turn was encoded while the device caption was not retrieved.
- Focused benchmark tests passed **23/23**, including regression coverage proving that a printed dialogue label alone
  does not count as evidence and that one represented sentence from a multi-sentence turn is reported as partial.

## 2026-09-04 — Structured assistant evidence results

- Separated stable assistant policy from request-specific memory. The system prompt now explains the evidence and
  tool contract without embedding retrieved content; a dedicated user template carries the structured initial
  evidence followed by the current request. Production chat, benchmark QA, and the library session use the same
  layout.
- Added a typed evidence envelope for fact/claim records, explicit subject identities, member claim IDs, normalized
  timing, citations with conversation time, and structured source excerpts. Initial retrieval includes bounded source
  neighborhoods in this envelope. `memory_search` returns compact records in the same schema, while
  `memory_sources` expands previously shown claim IDs into cited and contextual segments. Fact-member claim IDs are
  all eligible for subsequent source traversal.
- Before integration, direct `gemma4:12b` probes with the proposed prompt and native Ollama tool schema answered a
  sufficient new-Prius case and rejected a wrong-person Jasper premise. An incomplete count still answered from one
  record without searching; a general completeness instruction alone did not change that behavior, so this remains
  an agent-control limitation rather than being hidden by a fixture-specific rule.
- The first integrated frozen-store smoke run at
  `benchmark_runs/retrieval-evidence-structure-smoke-20260904` showed that compact records alone removed useful source
  context. Structured bounded source excerpts were restored for automatic retrieval, and citations gained explicit
  conversation times. The final replay at
  `benchmark_runs/retrieval-evidence-structure-smoke-v2-20260904` improved three of five diagnostic cases: the May
  road-trip count changed from refusal to **2** after one search, the new-Prius case changed from refusal to **a new
  Prius**, and the false Sam/Jasper premise changed from attributing Evan's experience to Sam to a supported refusal.
  The incomplete broken-car set remained partial, and the missing fitness-device extraction remained unavailable.
- Validation passed **323 tests with 2 skipped** using host access required by LanceDB, plus Ruff and
  `git diff --check`.

## 2026-09-04 — Product-oriented memory tool language

- Removed the shared prompt rule that singled out totals, complete sets, and comparisons, along with the
  question-answer framing around required answer parts. Benchmark response shape remains isolated in the benchmark's
  injected response instructions; production chat retains its natural-response instruction.
- Reframed the shared assistant contract around fulfilling the current request and using additional remembered
  information when it would materially improve the response. Reframed context admission around usefulness to the
  request, and changed `memory_search` from finding an "unresolved evidence requirement" to finding relevant memory
  for any aspect of the request. No LoCoMo categories, labels, expected answers, or fixture vocabulary appear in these
  production components.
- Direct `gemma4:12b` probes with the proposed production prompt used supplied preference memory to draft an outing
  suggestion, searched once to recall Sam's dietary preference before recommending dinner, and ignored irrelevant
  memory while rewriting a sentence. The context selector included an Atlas launch-date record and excluded an
  unrelated notebook preference. Focused prompt, tool, context-selection, benchmark-adapter, budgeting, and production
  lifecycle tests passed **48/48**. The full suite passed **324 tests with 2 skipped**; Ruff and `git diff --check`
  passed.

## 2026-09-04 — Assistant execution-trace observability

- Added a per-round execution trace to tool-capable Ollama responses. Each step records the attempt and round, native
  `thinking` text, visible content, normalized tool calls, corresponding tool observations, round outcome, and Ollama
  response metadata. Benchmark QA persists the trace in answer metadata; production chat continues to persist only
  the clean user/assistant transcript and its existing retrieval/tool metadata.
- Contract tests prove that an assistant message containing `thinking` and a tool call is passed intact into the next
  Ollama request, and that the resulting tool observation is associated with the originating trace step. Focused
  Ollama, benchmark, runtime, and production-lifecycle validation passed **50/50**.
- Real `gemma4:latest` frozen-store probes are recorded under
  `benchmark_runs/agent-execution-trace-probe-20260904`. The supported Jasper question identified the answer directly
  in initial evidence and returned `Jasper` without searching. The previously missed May-hobby question explicitly
  noticed that its evidence did not establish a May hobby but immediately chose the benchmark refusal rather than
  trying `memory_search`; a direct focused search could retrieve May claims that Sam was considering painting, though
  those claims do not establish that the planned activity actually began. The new-Prius and fitness-device probes also
  stopped without searching: the former saw both the old breakdown and a contextual new Prius but treated them as
  unrelated, while the latter concluded that no device was present in initial evidence. These traces isolate an
  early-stopping/evidence-interpretation problem rather than loss of Ollama reasoning between tool rounds.

## 2026-09-04 — Cumulative memory-evidence prompt contract

- Clarified that initial retrieval is a starting selection rather than the complete memory store, and that evidence
  returned by tools joins it in one cumulative body of evidence. The assistant is now explicitly instructed to call
  `memory_search` before responding when a memory-dependent request is unsupported by the initial selection, then to
  reconsider the request after every tool result. Response-style instructions follow this exploration policy, and
  the benchmark refusal phrase now refers to accumulated evidence after memory exploration.
- Direct `gemma4:latest` probes established the boundary of the change. On a neutral incomplete-evidence case, the
  model searched for Mira's instrument, retained its reasoning through the tool round, and answered from the returned
  cello claim; with the cello claim initially present, it answered directly. With the frozen Prius record but no
  expanded source neighborhood, it searched for the missing replacement and reevaluated six returned records.
- The integrated frozen-store Prius replay at
  `benchmark_runs/agent-execution-trace-probe-20260904/integrated-prompt-replay.json` now performs the intended search
  and second reasoning round, but still refuses because it will not compose the old-Prius breakdown with the returned
  new-Prius evidence. The May-hobby replay answered "cooking class" without searching by incorrectly connecting a May
  check-up to a class cited in June and August. Thus the prompt improves the retrieval decision in a real failing case
  but does not solve evidence interpretation; noisy expanded context can still cause either excessive conservatism or
  an unsupported relation. Probe variants and complete traces are stored beside the integrated replay.
- Focused prompt, Ollama, benchmark, memory-tool, and prompt-budget tests passed **63/63**; Ruff and
  `git diff --check` passed.

## 2026-09-04 — On-demand source expansion A/B

- Probed a product-level tool division in which `memory_sources` expands the exact cited lines and nearby dialogue of
  an existing relevant claim, while `memory_search` discovers additional records when current records do not point to
  the missing information. With `memory_search` declared first, `gemma4:latest` repeatedly searched for another claim
  instead of expanding the claim it had. Declaring `memory_sources` first with the same semantic contract caused it to
  expand the claim, retain the returned source line, and answer the neutral source-dependent question correctly. A
  sufficient-record counterexample answered directly without any tool.
- Ran a controlled six-question frozen sample-9 A/B at
  `benchmark_runs/initial-source-expansion-ab-20260904`. Both arms received identical initially selected records. The
  baseline also received expanded sources; the proposed arm received records and citation metadata only, declared
  `memory_sources` first, and used the explicit operation-routing descriptions.
- The proposed arm reduced mean initial prompt size from **3,598 to 1,051 tokens** (70.8%). Direct car and Jasper
  answers remained correct without unnecessary tool calls. On the May-hobby case it expanded the relevant cooking
  claims instead of searching broadly and correctly found no May support. On the May-road-trip count it searched,
  expanded the two relevant claims, and reasoned over their exact dialogue. On the missing fitness-device case it
  searched rather than treating initial absence as final, though the store still lacked the required device evidence.
- Aggregate score was effectively flat on this small diagnostic panel (**0.3333** baseline versus **0.3485** proposed)
  and is not a meaningful quality estimate. The proposed arm made five tool calls (three searches, two source
  expansions) versus three baseline searches and no source expansions. Both arms still refused the new-Prius answer,
  showing that on-demand sources improve traversal and context cost but do not resolve the separate relationship-
  composition problem.

## 2026-09-04 — On-demand source expansion integration

- Removed automatic source-neighborhood expansion from initial retrieval. The initial evidence now contains compact
  claim/fact records, their supporting claim IDs, timing, and citations; exact source text is available only through
  `memory_sources` for IDs already exposed to the assistant.
- Integrated the A/B-tested operation contract and declaration order. `memory_sources` is presented first as the way
  to inspect a relevant or potentially related record, including the member claim IDs of a fact. `memory_search` is
  the discovery operation for gaps not pointed to by current records. The shared assistant prompt directs the model
  to choose between those operations from the cumulative evidence after every round.
- Focused retrieval, tool, prompt, benchmark, prompt-budget, pipeline, session, runtime, and Ollama-client tests passed
  **75/75**. Ruff and `git diff --check` passed. The heavier production lifecycle acceptance test was not included in
  that total because it did not complete promptly when run in the broader batch.
- A production-path, five-category frozen sample-9 replay completed without retrieval, tool, parsing, or generation
  errors at `benchmark_runs/locomo-convo-9-on-demand-sources-integrated-20260904`. Initial contexts had empty source
  arrays. The model answered sufficient compact records directly, used `memory_sources` for potentially relevant May
  hobby evidence, and used source expansion followed by a focused search to answer the May travel question. It used
  search for both replacement-car questions. The small panel scored **0.6000**; the two misses reflect unresolved
  evidence meaning/relationship issues rather than a failure of the new traversal contract.
- Replayed the same five-per-category sample-9 panel as the earlier expanded-source `concise-v2` run at
  `benchmark_runs/locomo-convo-9-on-demand-sources-panel5-20260904`. All **25/25** questions completed without system,
  tool, parsing, or generation errors. Mean score increased from **0.4078 to 0.5039**, with 6 questions improving, 4
  regressing, and 15 unchanged. Mean QA input fell from **2,322 to 1,194 tokens**. The assistant used memory tools on
  21 questions versus 9: 14 source inspections and 10 searches, compared with 10 searches and no source inspections.
  Runtime rose from 313 to 359 seconds as a result of the additional reasoning rounds.
- Context evidence recall fell from **0.6400 to 0.3623** and all-evidence coverage from **0.56 to 0.28**, as expected
  when source neighborhoods are loaded selectively rather than attached to every initial record. Despite that lower
  bulk recall, category 3 improved from **0.1026 to 0.3139**, the model recovered the previously missed Canada answer,
  and all five false-premise questions were handled correctly. Remaining weaknesses are selective source/search
  coverage and evidence interpretation, especially temporal attribution, counts, and connecting the old-Prius
  breakdown to the separately recorded new Prius.

## 2026-09-04 — Deliberate memory-result representation

- Replaced model-facing JSON evidence with one Markdown/pseudo-XML renderer shared by initial retrieval,
  `memory_search`, and `memory_sources`. Records now lead with their statement and subject. Source results explicitly
  map each supporting claim to its cited segment IDs and render the selected transcript in source order, marking cited
  lines in place. Free text is escaped before entering the markup.
- Removed generic character slicing from the Ollama tool loop and removed the obsolete truncation field from tool
  events, server persistence, and the UI. Search and source tools reserve their envelope cost before retrieval, admit
  only complete evidence units under their cumulative token budget, and report when more evidence remains available.
- Before integration, a direct `gemma4:latest` probe using the production prompt and tool definitions inspected a
  related claim through the proposed source format, followed the explicit claim-to-segment association, and answered
  that Jordan recommended Mira's novel. A sufficient cello counterexample answered directly without calling a tool.
- The focused representation/runtime suite passed **76/76**. The complete deterministic backend suite passed **324
  tests with 2 skipped**; Ruff, `git diff --check`, UI lint, and the UI production build passed.
- The identical frozen sample-9 five-per-category replay completed **25/25** without tool, parsing, generation, or
  result-shape errors at `benchmark_runs/locomo-convo-9-markup-evidence-panel5-20260904`. All tool-result documents
  were complete; the largest cumulative result for one question was **2,990 tokens** against the 6,000-token budget.
  Mean QA input fell from **1,194 to 929 tokens** compared with compact JSON, while context evidence recall rose from
  **0.3623 to 0.3741**.
- Mean score was **0.4865**, versus **0.5039** for compact JSON and **0.4078** for automatically expanded JSON. Four
  questions improved, six regressed, and fifteen were unchanged. The format corrected the Prius count to **Two** and
  selected the earlier May doctor visit rather than the later October warning; all five false-premise questions
  remained correct. Two measured regressions were token-overlap artifacts on semantically equivalent answers. One
  substantive regression exposed the next agent-control issue: after source inspection failed to establish the May
  24 family destination, the model stopped instead of using `memory_search` for the remaining gap.

## 2026-09-04 — Search/source result strategy comparison

- Directly probed the production assistant prompt and tool schemas with a neutral incomplete-memory example before
  running the comparison. After `memory_sources` showed that a known claim did not establish the requested travel
  detail, an explicit operation result saying that unresolved information should be discovered with a focused
  `memory_search` caused `gemma4:latest` to search, retain the intermediate reasoning, and answer from the newly
  returned record.
- Replayed the same frozen sample-9 store and the same five questions from each category through three isolated arms
  at `benchmark_runs/memory-search-source-strategies-20260904`: separate search/source tools with that transition
  guidance, search results with automatic exact cited lines, and search results with automatic chronological source
  neighborhoods. All **75/75** question runs completed without API, tool, parsing, generation, or markup-shape errors.
  No tool result exceeded its cumulative 6,000-token evidence budget; the largest per-question totals were **3,027**,
  **3,027**, and **4,717** tokens respectively.
- The separate arm scored **0.4589** with context evidence recall **0.4091**. Automatic exact citations scored
  **0.4355** with recall **0.4583**. Automatic full neighborhoods scored **0.4156** with recall **0.6083**. Thus the
  additional source text improved bulk evidence coverage monotonically but answer quality moved in the opposite
  direction. Mean initial input remained approximately **929 tokens** in all three arms because source text was added
  only after a search.
- The transition guidance produced one genuine `memory_sources` -> `memory_search` continuation in the exact-citation
  arm, on the replacement-Prius question. The returned source had already said Evan had just returned in his **new
  Prius**, and the subsequent search returned the same fact, but the model still refused because it interpreted the
  question as asking for a different car after the new Prius failed. This is an evidence-composition failure, not an
  evidence-availability failure.
- Automatic source inclusion introduced a concrete precision risk on false-premise questions. Exact citations caused
  one response to substitute Evan's Jasper trip for a nonexistent Sam trip; full neighborhoods caused another to
  answer what Evan found relaxing after correctly observing that Sam had never taken the trip. The separate arm
  correctly refused all five false-premise questions. Conversely, the exact and full arms recovered Jasper on one
  ordinary question because those runs chose `memory_search` first while the separate run chose `memory_sources`;
  that gain occurred before their result-format difference and demonstrates remaining tool-choice variance rather
  than a benefit from automatic source attachment.
- The result supports retaining the explicit two-step graph: compact records for discovery, then source expansion when
  exact wording or context is needed. Source text should not be attached automatically to every search hit. The next
  improvement should make the post-source decision more reliable and improve relationship/temporal composition,
  while preserving the distinct operations and their inspectable claim-to-source edge.

## 2026-09-04 — Production source-to-search transition

- Kept `memory_search` and `memory_sources` as distinct production operations. The production assistant system prompt
  now states the tested transition explicitly: inspect an existing relevant record with `memory_sources`, then use a
  focused `memory_search` when those sources do not establish the remaining information. Search results remain compact
  records with citation pointers; neither exact cited lines nor full source neighborhoods are attached automatically.
- Validated the actual production prompt and tool definitions against `gemma4:latest`. In a neutral case where no
  existing record pointed to the requested city, the model called `memory_search` directly and answered from the new
  record. In a compound counterexample, it called `memory_sources` to recover the title of Jordan's recommendation,
  recognized that the city was still missing, called `memory_search`, and combined both results correctly in the final
  answer while retaining the intermediate reasoning across all three rounds.
- Removed tests that pin prompt wording or inspect prompt strings. Template tests now cover external template
  discovery, strict variable handling, and package inclusion; semantic prompt behavior is established with direct
  configured-model probes and persisted pipeline runs rather than copy assertions.
- The focused retrieval/runtime suite passed **73/73**. The deterministic backend suite excluding the independently
  non-terminating LanceDB, Engram, and production-lifecycle test files passed **299 tests with 2 skipped**. Ruff,
  `git diff --check`, UI lint, and the UI production build passed. The LanceDB test hung when run alone, and the full
  suite also stalled in Engram tests; both processes were stopped without producing test failures.

## 2026-09-04 — Runtime-managed evidence workspace

- Added a typed, per-response evidence workspace owned entirely by the runtime. Initial retrieval records, later
  search records, and explicitly requested source transcripts merge by stable IDs; source segments retain conversation
  order. The workspace also records each successful or failed memory operation and the remaining search/evidence
  budgets. No workspace-writing tool or model-authored notes were added.
- Changed the Ollama tool loop so the newest memory result contains one complete current workspace. After the first
  memory operation, the initial user message becomes request-only; after later operations, the prior full workspace
  becomes a compact supersession receipt. Raw incremental tool results remain in persisted tool events, while assistant
  reasoning and tool-call history remain chronological. The same mechanism is used by web chat and benchmark QA.
- Before integration, direct `gemma4:latest` probes compared a mutable top-of-prompt workspace with a chronological
  replacement protocol. The former answered correctly but made an unnecessary source call after briefly treating the
  refreshed state as empty. The chronological protocol cleanly followed `memory_sources` then `memory_search` and
  combined the recovered novel title and city. An integrated probe using the production prompt, `MemoryToolset`,
  renderer, and Ollama client repeated that correct two-operation traversal with a revision-2 workspace.
- The final workspace is persisted on assistant transcript entries and benchmark predictions. The React chat exposes
  it in a collapsed inspector grouped by subject, with operation history, budgets, citations, and chronologically
  rendered source lines.
- Validation passed: **303 tests with 2 skipped** across the deterministic backend suite excluding the three
  independently non-terminating LanceDB, Engram, and production-lifecycle files; targeted MyPy; Ruff; UI lint; and the
  UI production build.
- A frozen sample-9 replay completed all **25/25** questions without tool, parsing, generation, budget, or result-shape
  failures at `benchmark_runs/locomo-mycelium-convo-9-evidence-workspace-panel5-20260904`. It scored **0.4252** versus
  **0.4589** for the earlier separate-tool transition run. Candidate rankings and initially selected claim IDs were
  identical across all 25 questions. Measured context recall fell from **0.4091 to 0.2841** because the assistant made
  fewer source expansions: 11 source calls covering 18 claim IDs, versus 15 calls covering 31 IDs previously. Several
  answers stopped at sufficient compact records instead of loading every benchmark-labeled source segment. The one
  category-5 scoring regression was a grounded premise correction (the stored evidence says Sam had never visited
  Jasper) rather than evidence leakage or an agent-loop error. The replay is therefore a runtime validation, not
  evidence that the workspace improves answer quality by itself.

## 2026-09-04 — Reset comparison and restored test baseline

- Compared the agreed reset with live capture, retrieval, organization, correction, storage, and UI callers.
  Recorded proposed keep/replace/remove boundaries and incremental acceptance checkpoints in
  `planning/reset_incremental_plan_2026_09_04.md`. Product refactors remain for joint review; no production
  code or live store was changed, and no server was started or stopped.
- Reproduced the previously reported test hangs with bounded sandboxed runs. Outside the sandbox, the
  LanceDB claim-index test and all 15 Engram tests completed; the production lifecycle test still hung.
  Its 260-token input budget was smaller than the current 262-token system prompt alone. Prompt assembly
  raised before the fake model signaled generation, leaving the test waiting on an event indefinitely.
- Repaired only the lifecycle test: a 1,024-token budget admits the production envelope while a new
  assertion verifies that the long transcript is still trimmed. A bounded TaskGroup surfaces chat-task
  exceptions and cleans up concurrent tasks. Existing chat/flush serialization, source timing,
  correction, retraction, and restart assertions remain in place.
- Validation: lifecycle test **1 passed**; complete backend suite outside the sandbox **320 passed,
  2 skipped in 11.45 seconds**. Ruff, UI lint, UI build, and diff whitespace checks passed. The UI retains
  its existing large-bundle warning. No live-model semantic probes or real-audio transcription runs were
  performed; this change does not modify model contracts. Interactive app validation remains user-run.

## 2026-09-04 — Reset increment 1: evidence-first retrieval and prompt budgeting

- Implemented the approved first increment without changing extraction, organization, ranking, model admission
  prompts, source retention, or ingestion behavior. No live-store migration, server operation, or commit.
- Removed synthetic retrieved WikiPage construction, duplicate fact/claim/source formatting, and page-owner-based
  chat admission. Complete typed evidence now determines retrieval and complete chat-prompt budgets through one
  fitting helper. Accounting uses the existing token estimator on actual rendered envelopes, including omission
  notices; impossible envelope budgets fail explicitly.
- RetrievalResult and Session expose page_references containing WikiPageReference metadata instead of page bodies.
  Chat JSON loaded_pages describes only real pages associated with initial evidence surviving prompt fitting.
  Actual wiki pages, source inspection, and the full-wiki benchmark renderer remain available.
- Updated library/session callers, examples, benchmark adapters, UI metadata explanation, and documentation.
  Daily Driver now reads exact claim/fact IDs from typed evidence and assigns that evidence to its answer session;
  removed its obsolete page-source-context scan. This fixes evaluation plumbing, not a demonstrated score gain.
- Added coverage for exact compact-record budgets with long transcripts, whole-record omission, duplicate hits,
  real-page metadata, impossible budgets, unowned/same-subject chat records, persisted post-fitting chat metadata,
  and typed benchmark IDs. Removed obsolete synthetic-page test setup.
- Validation: full backend suite **326 passed, 2 skipped in 9.36 seconds**, outside the sandbox due to the established
  database-test limitation. Ruff, UI lint/build, and diff whitespace checks passed. The existing ~880 KB UI bundle
  warning remains. Intermediate runs caught new-test setup errors (missing source fields and a mistyped session-file
  constant), both corrected before the final run.
- In-situ automated coverage includes the isolated production lifecycle (chat/flush, retrieval, correction,
  retraction, restart) and chat route with budgeted evidence and persisted page metadata. These use controlled
  model doubles. No prompt, ontology, or model-labor contract changed; no direct Ollama probes were performed.
  Real-model answer quality and interactive UI behavior remain unverified.
- User smoke checkpoint: ask about existing memory, inspect evidence/citations, reopen the chat, and browse the
  relevant wiki page. Agree increment 2 separately; do not advance automatically.

## 2026-09-04 — Automatic capture and explicit Build Memory

- Implemented the user-approved capture/build boundary. ingest_source now returns captured/empty and persists
  source, log, ingestion-operation, and extraction-manifest records without LLM or embedding calls. Explicit
  consolidate snapshots source IDs, processes unfinished extraction, and runs the retained organizer against
  that snapshot. Builds are serialized; later capture remains pending. ConsolidationResult exposes
  processed_episode_ids rather than describing all first-time extraction as a retry.
- Web chat saves a completed turn before capture and advances a durable captured-turn cursor only after source
  and external-tool observation writes succeed. Stable ingestion keys make interrupted cursor writes replayable.
  Capture errors do not discard the reply: the UI reports pending capture, and the next turn/build retries.
  Memory-tool results remain excluded from new evidence. Removed active-episode buffers, Flush controls/routes/
  request contracts/helpers, and age/count readiness configuration and conditional build APIs.
- POST /api/memory/build now backs Build Memory; /build/status reports pending sources and statement counts.
  Updated sidebar/avatar labels, inspector capture state, library contracts/examples, and README/DESIGN. Existing
  benchmark capture callers now inherit capture-only behavior and their explicit consolidation calls perform
  extraction. No raw-source index or independent wiki-page retrieval was added.
- Reviewed meeting sources are captured before optional summary generation. Summary failure leaves the source
  admitted and the meeting completed with an error; Retry Summary does not recapture. Transcript and speaker
  editing remain available before admission and are blocked afterward. No real audio processing was run.
- Per-turn chat capture stores references to up to four prior captured turns. Earlier context is bounded to a
  quarter of the configured model window using complete source groups. The existing two-stage extractor still
  classifies/extracts only new segments; an optional exact-ID context_segment_ids field retains additional
  citations against their original sources. This is bounded reference resolution, not a combined extractor or
  a new consolidation policy. Source-only context is not automatically promoted to accepted user knowledge.
- Direct configured-host gemma4:latest probes used production prompts and a candidate structured context-citation
  schema before integration: acceptance and refusal of a neutral workshop commitment were distinguished, with
  earlier context cited where needed. Both could emit redundant statements; that pre-existing extraction-quality
  weakness is recorded rather than repaired with lexical deduplication. Probe script:
  /tmp/mycelium_capture_context_probe.py. Host /api/tags and model calls used network escalation.
- In-situ cross-turn extraction at /tmp/mycelium-context-integration-p_8u3_a_ produced a correctly resolved workshop
  commitment with provenance to both sources; the earlier source remained unprocessed. Redundant statements
  remained. The production capture/build/retrieve run at /tmp/mycelium-capture-build-qc1ksxx3 captured zero claims
  before building, built one meeting-time preference, updated the You wiki page without failures, retrieved the
  supported fact with exact citation, and preserved capture idempotency after restart. These small probes establish
  the tested lifecycle/meaning boundaries, not general memory quality or benchmark improvement.
- Validation: **330 passed, 2 skipped in 10.40 seconds**; Ruff, UI lint/build, and diff whitespace checks passed.
  Focused regressions cover capture without model calls, restart, interrupted capture-cursor persistence, build
  snapshot concurrency, no repeated extraction on no-work builds, original-source context citations, retired
  routes, and meeting admission/retry despite summary failure. Existing extractor tests now explicitly capture
  then extract; obsolete Flush tests were replaced. UI retains its existing ~878 KB bundle warning.
- Test-isolation incident: newly added automatic capture exposed two older chat-route tests that mocked the route's
  memory provider but not runtime.get_mem. They created three test sources, three episodes, three ingestion records,
  and a daily log containing only those test entries in the default store. Verified exact stable IDs and absence
  of downstream claims, then moved only those ten files to /tmp/mycelium-test-records-An7HJ5. User chat sessions
  were preserved. Both memory providers are now mocked explicitly; final full-suite verification did not recreate
  the records. No server was started/stopped and no git commit was made.
- Remaining user smoke check: capture a new chat, inspect saved/pending status, Build Memory, then retrieve it in
  another chat and follow its citation/wiki page. Check reviewed meeting finalization separately. Do not advance
  to combined coverage/extraction until this lifecycle is reviewed.

## 2026-09-04 — Preserve configured-user identity during Build Memory

- User confirmed the capture/build/recall smoke check, then reported an empty canonical You page alongside a
  populated person-you page. Read-only inspection of identity-work-598b4fe07d618e3e showed that the matcher
  recognized the user in its explanation but returned new. Code excluded you from the allowed matching IDs
  and both verification candidate lists; with no candidates, code declared distinct without a model call.
- Fixed the identity contract, not page naming: expose active you as an identity candidate, retain its registered
  type after matching (you is not a discoverable type), and compare proposed people against both person and you
  identities. A verified existing match retains the selected registry type. Other ontology candidate filters remain.
  No lexical matching or post-hoc ownership overrides were added. Source roles now accompany cited segments;
  identity prompts explain the configured chat-speaker binding and distinguish mentioned/quoted people.
- Direct configured-host probes: /tmp/mycelium_identity_probe.py, gemma4:12b from mycelium.toml, host /api/tags
  verified with escalation. Merely exposing you failed: the original prompt returned review_required because
  no personal name/history was supplied. Adding explicit source-role guidance passed user and colleague cases
  for both matching and duplicate verification before production integration.
- In-situ probe: /tmp/mycelium_identity_in_situ.py. Initial store
  /tmp/mycelium-identity-in-situ-bz0fxfr7 routed the self statement correctly directly to you with no subject node;
  the probe's assumption that a node must exist failed, not routing. Replayed a persisted neutral census node
  to exercise the reported entry condition, using real model calls for every subsequent decision. Store
  /tmp/mycelium-identity-in-situ-wrb7eibu: self matched you and routed to you, with no second person; colleague
  remained a distinct provisional person with its claim deferred under existing page-admission policy.
  This validates identity routing, not extraction or general retrieval quality.
- Regression tests cover initial existing-user matching and recovery of an initial new-person proposal through
  duplicate verification, exact selectable IDs, source-role presentation, retained ownership, and skipped user
  rediscovery typing. Meeting participant mocks now explicitly answer the newly required user duplicate checks.
  Validation: 332 passed, 2 skipped; focused lint and git diff --check passed.
- Existing user data, including the duplicate, was not changed. No migration, server operation, or git commit.
  Empty startup-page removal and repair of already-built duplicate identities remain separate follow-ups.

## 2026-09-04 — Replayable real-chat memory regression

- Added tests/fixtures/chat_memory_replay.json with user-authorized verbatim exports of the three fried-rice
  turns and two alignment turns from live sessions 31a5add9 and 51276085. Verified all ten role/content/timestamp
  records exactly match the saved transcripts. Excluded derived claims, old retrieval results, capture cursors,
  and the third assistant answer. The original third-chat question is the recall input.
- Added opt-in tests/test_chat_memory_replay.py. Starts from default Mycelium initialization in a fresh pytest
  temporary store, persists completed turns chronologically through production chat capture, and checks stored
  source segments against the fixture before Build Memory. Runs the production build with real extraction,
  identity resolution, synthesis, and materialization; asserts no build failures, complete extraction, a single
  You page, and canonical user-owned facts supported by both input conversations.
- Opens an empty third chat through the actual chat handler with real hybrid retrieval, admission, generation,
  and memory tools. Only web tools are removed from this local test. Checks fried-rice source IDs in the final
  evidence workspace and validates citation segment IDs, rather than using answer keywords or search candidates
  as a proxy for recalled memory. Both runtime and route memory providers, metadata paths, and locks are isolated.
- Run: MYCELIUM_RUN_CHAT_REPLAY=1 .venv/bin/pytest -q -s tests/test_chat_memory_replay.py (host escalation).
  Passed in 109.62 seconds using the configured gemma4:12b and embeddinggemma:latest. Artifacts:
  /tmp/pytest-of-nitin/pytest-533/test_two_conversations_build_o0, including store/, build_report.json,
  pages.json, and recall_response.json. Default suite: 332 passed, 3 skipped; replay lint and diff checks passed.
- README documents execution, model variability, diagnostics, and the personal-text fixture sharing caveat.
  No production prompts or algorithms were changed for this fixture. No live data changed, no server operations,
  and no commit. This is a reproducible regression scenario, not a general memory-quality benchmark.

## 2026-09-04 — Repair live duplicate user page

- User explicitly requested live repair. Backed up the complete store to
  /tmp/mycelium-before-user-merge-sA05KP/store before mutation.
- Allowed the existing manual merge service to accept person -> canonical you; automatic identity decisions
  and other cross-type merge restrictions are unchanged. Extended reference-redirection/history regression
  coverage to this case: 20 entity/wiki tests passed, lint and diff checks passed.
- Ran the service to merge person-you into you. Six facts now belong to the canonical user; only wiki/you.md
  remains visible. The duplicate page was archived and its entity retained as a merged redirect so old links
  still resolve. Verified source documents, extracted claims, and session transcripts are unchanged against
  the backup. No server operations or git commit.

## 2026-09-04 — Combined extraction and coverage accounting

- Replaced separate coverage and claim-extraction model calls with extraction_output_model: one response contains
  claims plus one claimed/source_only disposition and reason per new segment. Deterministic validation requires
  exact segment accounting, exact allowed citation IDs, and equality between claimed segments and claim citations.
  Empty claim output is valid only with all segments source-only. Context citations remain on their original sources.
- Removed the coverage prompt pair/factory/schema, separate coverage/claim statuses, and claim_pending state.
  ExtractionBatchState now has one pending/failed/complete status and a temporary validated response. Persisting
  the response before claim writes lets restart replay identical output after an interrupted write; completed
  batches discard it. Insert-only publication cannot overwrite a claim superseded by a user correction.
  Existing temporal normalization, batching size, identity/page organization, and synthesis were not redesigned.
- Direct host model: gemma4:12b, verified through escalated /api/tags. Prototype /tmp/probe_combined_extraction.py
  first passed source-only and unaccepted suggestions but failed cross-turn citations: it resolved a reference
  while omitting the earlier source IDs. Required context citation fields and explicit general guidance fixed it;
  acceptance/refusal then passed both structural checks and evaluation-only meaning judgments.
- New tests/test_extraction_replays.py and tests/fixtures/extraction_replays.json run the production prompt/schema
  directly and the real capture/build/restart/session-retrieval path for six neutral cases. No source-specific
  words, expected answers, or evaluator logic enter product prompts. Exact accounting and provenance are tested
  structurally; model judgments assess paraphrased expected meaning and forbidden assertions, not independent truth.
- Important integration failure: the original chat replay initially extracted no claims, explaining self-reported
  experiences and goals within questions as non-facts. /tmp/probe_question_admission.py proved general guidance
  with a neutral roles/experience/goal question and a purely informational counterexample before integration.
  Final combined prompt preserves assertions inside questions without inferring personal facts from bare questions.
  These counterexamples were added to the permanent probes and full-system replays.
- Test-harness failures corrected: SourceInput segment dictionaries initially omitted required segment_id; the
  restart test compared mutable organization bookkeeping as though it were immutable extraction content.
  It now checks extracted fields/provenance and no processed episodes, allowing existing deferred-work bookkeeping.
  Old staged mocks/call counts were replaced, not retained as compatibility helpers. Added interrupted claim-write
  recovery and preservation of a superseded claim between partial publication and restart.
- Final validation: 334 backend tests passed, 15 skipped; Ruff and diff checks passed. With both
  MYCELIUM_RUN_EXTRACTION_REPLAYS=1 and MYCELIUM_RUN_CHAT_REPLAY=1, all 13 real-model checks passed in 231.44 seconds.
  Artifacts: /tmp/pytest-of-nitin/pytest-544, including per-case model outputs/judgments/build/retrieval artifacts
  and test_two_conversations_build_o0 with the original verbatim chat replay. That replay passed its single
  populated You page, both conversations' user-owned facts, and third-chat cooking-source citation assertions.
- User explicitly approved backing up/rebuilding the live test store instead of adding schema compatibility.
  Backup: /tmp/mycelium-before-combined-extraction-mRPuyX/store; untouched pre-swap directory also retained at
  /tmp/mycelium-before-combined-extraction-mRPuyX/original-live. First staged build reflected the omission regression
  and was NOT installed. The second build passed populated-page checks and preserved all six source IDs and every
  original segment's text/role/timestamp. After checking live session metadata was unchanged, swapped it into place.
  Live store now has one You page, four extracted claims, six sources, and zero pending sources. Historical derived
  chat retrieval/tool snapshots were reset rather than relinked to changed claim IDs; original messages and Engram
  data were preserved. No server started/stopped and no git commit. Backend restart is user-run for the new schema.
- Post-swap live retrieval smoke check passed: the original cooking query returned citations to
  source-6c522d36c58ec125 through the real hybrid index and model admission path.
