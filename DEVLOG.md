# Development Log

## 2026-09-10 — Repair structural model contracts and replay five sessions

- Prioritized extraction, synthesis, and review reliability before repeated-review scheduling. Seven neutral Gemma 4 12B probes passed before initial integration; all requests/schemas/responses are saved under `benchmark_runs/contract-reliability-20260910/`.
- Native schemas now distinguish singleton/combined synthesis, require each truth comparison, distinguish no-change/change selections (`changed_targets`), and use one identity evidence list with explicit speaker bindings. Context time anchors must cite actual evidence; unspecified anchors across different cited timestamps stay unresolved. No lexical semantic rules or silent semantic repairs were added.
- Extraction bookkeeping failures reproduced in an exploratory replay. The first replacement, a per-segment bare list/string union, was **rejected** after an in-situ batch returned useful assertions as strings interpreted as no-claim reasons. Named `claims`/`reason` variants subsequently passed acceptance/refusal and two captured 48-segment requests, including the lost child/aunt batch (22 claims). Added explicit-label, evidence, temporal ambiguity, persistence/resume, and native-schema tests. A probe setup KeyError for absent context was corrected before its replay call.
- Final truth repair passed all 16 captured verdict/target failures and two neutral counterexamples first attempt. Final production reasoning checks for synthesis/truth/extraction passed first attempt with 32,768-token budgets (48.6s/25.9s/53.9s); nonempty thinking recorded. No clear semantic advantage appeared, and extraction still omitted its time anchor. Semantic acknowledgment noise and occasional synthesis partition duplication remain under evaluation.
- The replay exposed person/non-person identity evidence domain errors and stale historical P/C aliases in model-authored explanations. Typed evidence variants plus omitting historical model reasons from identity context preserve actual evidence, canonical IDs, and human reviewer notes. Typed probes passed 5/6; the remaining captured failure passed after context repair, as did three other captured cases. One probe setup lacked an uncommitted entity; used its exact captured registry declaration before rerunning.
- Finished sample-3 first-five replay at `benchmark_runs/locomo-contract-reliability-off-final-20260910/`. Checkpoint-resumed during identity repair; preserved all 77 preexisting claims. Recorded model time 33.8 minutes versus 173.9 in the saved reasoning prefix. Extraction 0/9, synthesis 0/40, truth review 0/76 rejected attempts, versus 14/23, 24/53, 5/81. Full run had 10 identity rejections; 3 occurred after final repair and recovered (duplicate speaker/canonical identity). One initial exhausted identity call preceded the repair; final completed builds have no failures. This compares combined repairs/mode changes, not a pure reasoning ablation or a frozen-revision full replay.
- Final artifacts represent 126/129 claims versus 107/111; five extractions complete, no pending segments. Aunt/child/event details survive into the wiki, and the doll-photo association improved. Concision and organization remain mixed: 77 facts/1,196 words/eight pages versus 47/1,050/three, with repetitive sentiments and weak theme pages. Three claims deferred for identity review; some exact segment citations remain incomplete. No QA score claimed. Full methodology, rejected experiments, remaining failures, and source-grounded review: `planning/contract_reliability_replay_2026_09_10.md`.
- Validation: full host-access suite 436 passed/87 skipped; Ruff and whitespace checks passed. Sandboxed full-suite attempts stalled and were interrupted, matching the prior environment limitation. No server processes started; no commit made.

## 2026-09-10 — Static unused-code and test cleanup

- Removed confirmed dead helpers/files and obsolete test scaffolding; repaired misleading synthesis/identity rejection tests and stale model-probe reasoning, singleton projection, and nullable serialization. Simplified fixtures and extracted shared test/benchmark helpers. Maintained probe runners now use fresh outputs rather than silently reusing dated results.
- Active production prompts and decision schemas remain unchanged. Retained uncertain public API candidates and historical experiment artifacts. Details and pending validation: `planning/unused_cleanup_2026_09_10.md` and `benchmarks/README.md`.
- User explicitly requested no code execution. Reviewed text, references, and diffs only; no imports, tests, collection, lint/type checks, model calls, benchmarks, or servers run. Runtime/model validation remains pending. No commit made.
- Subsequent user authorization: verify and commit. Full host-access test directory passed (427 passed/87 skipped, 5.68s); Ruff, whitespace checks, and UI production build passed. The sandbox suite attempt stalled and was interrupted. Benchmark imports, seven-case callback collection, and unique output paths passed; two real Gemma context-selection smoke calls passed and existing output reuse was rejected before inference (`benchmark_runs/contract-simplification-20260910T073847Z-9ed453ca/`).
- Selected host Gemma validation: 6 passed/2 failed in 972.07s, under `benchmark_runs/cleanup-validation-20260910/`. Both synthesis probes, direct refusal extraction, refusal pipeline replay, and shared/incidental page probes passed. Both replay stores represent all two claims; refusal also passed restart/retrieval. Initial probe setup lacked the basetemp parent directory and failed before inference; corrected before the actual run. Logs and coverage inspection saved with `artifact-review.json`.
- Model validation is not entirely green. Accepted-reference direct extraction cited a valid earlier-context time anchor that the unchanged schema forbids; retry exhausted 32,768 tokens after 412.8s without final output. Refusal replay reproduced the anchor error but recovered. Accepted replay retained acceptance, time, and citations, but its combined tentative/accepted wording failed the wiki semantic judge; restart/retrieval for that case were not reached. Documented both follow-ups without weakening assertions or changing production semantic contracts. See the cleanup report for exact artifacts and proposed investigation boundaries.

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

## 2026-09-04 — LoCoMo wiki baseline before organization simplification

- Updated benchmark capture to preserve named speakers, participant roster, explicit roles, and
  source labels through SourceSegment inputs. Unnamed document inputs retain transcript parsing.
  Added explicit LoCoMo user-speaker mapping without rewriting dialogue or inferring identity.
- Added --wiki-baseline: fresh default user store, capture/build per session, full initial/per-build
  snapshots, selected verbatim inputs, transformed messages, effective config, hashes, and git context.
  It rejects reused outputs and derived-artifact replay; no QA/gold answers enter this path.
- Real host gemma4:12b runs used sample 1, sessions 1–2 in two isolated stores:
  benchmark_runs/locomo-wiki-baseline-20260904-external and
  benchmark_runs/locomo-wiki-baseline-20260904-user. External finished with 17 claims and three pages;
  user-mapped finished with 11 claims, three pages, and one pending source. Both kept separate
  Caroline/Melanie pages; declared user-role Caroline incorrectly remained distinct from You.
- User session 2 extraction batch 1 failed the exact claimed-segment/citation contract after three
  response attempts, leaving 48 segments pending. Normal runner exit and empty generic error lists
  must not be interpreted as full build success. Preserved the failure without a cleanup retry.
- Review, reproduction commands, limitations, and snapshot links:
  planning/locomo_wiki_baseline_2026_09_04.md. No production semantic changes or live-store writes.
- Validation: 25 focused benchmark tests passed; full backend suite 336 passed, 15 skipped;
  Ruff and git diff checks passed. Real-model findings establish current behavior, not passing
  semantic acceptance. No server processes started/stopped and no git commit.

## 2026-09-04 — Simplified identity/page planning

- Replaced the subject census, sequential/local identity matching, type proposal/verifier,
  new/existing identity verifiers, maturity proposal/verifier, and scope admission plan with
  one grounded identity/page response followed by claim routing. Stable identities, exact
  evidence references, unresolved review, manual identity authority, bounded work units, and
  failed-routing resumption remain. Cumulative fact synthesis was not redesigned.
- A page is a usefulness decision, not a continuity/maturity threshold. Known subjects can
  remain without pages. Stopped manufacturing encounter-only pages and meeting participation
  bullets; source rosters remain retained evidence, and incidental external speakers need not
  become memory identities. Historical audit readers/manual organization APIs remain intact.
- Removed 20 old prompt templates, their factories/schemas, unused formatting/encounter helpers,
  and obsolete cascade-stage tests. Added focused ID/binding, duplicate-canonical-ID, explicit
  human-decision protection, and partial-commit identity allocation tests. Completed plans are
  reconsidered against the registry; failed routing reuses its validated plan and allocated IDs.
  Contract-specific cache IDs prevent reusing the retired cascade's plans. No migration or
  live-store rebuild was performed; removed tracked code is recoverable from the prior Git revision.
- Direct-probe development exposed meaningful failures before and during integration:
  unconstrained evidence/participant keys; redundant participant cross-references; missing
  non-speaker subjects; external speakers mistaken for You; and a named user duplicated despite
  correct source roles. Neutral probes were expanded to two speakers/multiple claims rather
  than adding benchmark-specific names or lexical identity rules.
- The first in-situ comparison is preserved at benchmark_runs/locomo-wiki-post-rework-20260904-{external,user}.
  External produced person pages; user binding failed contract validation and left claims unplaced.
  A diagnostic of saved session-1 claims captured the model explicitly proposing the user as a new
  person: /tmp/mycelium-identity-diagnostic-20260904/debug/structured-failure-f369452e-attempt-1.json.
- Proven replacement: source-declared user labels are exposed as authoritative canonical-ID bindings,
  and the structured schema fixes their You identity separately from other subjects. A model still
  decides claim meaning, other identities, and page usefulness; there is no semantic name-matching
  fallback. Four final neutral host gemma4:12b probes passed in 26.95 seconds at
  /tmp/pytest-of-nitin/pytest-564 (tests/test_identity_plan_replays.py).
- Final real chat replay passed at /tmp/pytest-of-nitin/pytest-566/test_two_conversations_build_o0:
  verbatim alignment/cooking inputs, one populated You page, both conversations represented,
  and fried-rice source citations in the third chat. Runtime was 151.60 seconds while sharing Ollama
  with the two LoCoMo runs; this is not a controlled latency benchmark.
- Regression suite: 317 passed, 19 skipped; Ruff, compileall, and git diff checks passed.
  Sandboxed tests stalled inside LanceDB even with fake embeddings; host-escalated suite passed
  in 13.45 seconds. Interrupted only the two stalled test invocations, not any server process.
- Final comparison run IDs: locomo-wiki-post-rework-final-20260904-external and
  locomo-wiki-post-rework-final-20260904-user. See the separate comparison review for completed results.
- Completed comparison: external retained 17 placed claims on the same two person pages; user variant
  now has seven personal claims on You, four on Melanie, and no duplicate Caroline page/entity.
  User session 2 still has the baseline extraction-contract failure (48 segments pending, one pending
  source), not a fully successful build. All extracted-claim source/segment references passed read-only
  integrity checks. Review: planning/locomo_wiki_post_rework_2026_09_04.md.

## 2026-09-04 — Extended the existing chat replay with Chicago follow-up

- With user permission, appended the six saved messages from chat b24a9554 to the existing
  tests/fixtures/chat_memory_replay.json: cooking recall, mapo-tofu pairings, and Chicago restaurants.
  Preserved both web_search events verbatim, including arguments/results/metadata. The original
  fried-rice and alignment messages were checked unchanged against the live saved conversations.
  No derived memory/retrieval snapshots or live-store changes were included.
- The same opt-in replay now captures all three historical chats into a fresh default store,
  builds once, and asks the original cooking question in a fresh recall chat. It checks eight
  captured chat turns plus two tool sources, exact message/result text and tool arguments, one
  populated You page with the original personal evidence, tool-grounded restaurant/person pages,
  no tool-backed facts on You, and cooking-source retrieval. Representative page identities
  (Lao Sze Chuan and Tony Hu) are checked by an evaluation-only model judgment, allowing naming
  variation; their provenance and the personal/tool boundary are structural assertions.
  No historical assistant response or web search is regenerated.
- Real configured-host run: MYCELIUM_RUN_CHAT_REPLAY=1 .venv/bin/pytest -q -s --tb=short
  tests/test_chat_memory_replay.py. It FAILED in 139.31 seconds at the build-success assertion.
  Capture verification passed; all ten source episodes extracted completely. The identity planner
  invented candidate registry IDs (e.g. lao_sze_chuan) and failed validation after three attempts,
  leaving 16 routing failures. The later page-judgment and fresh-recall checks were not reached.
  This is a recorded regression, not a passing expanded replay. No product prompt/schema changes,
  assertion relaxation, or extra build retry was made to conceal it.
- Artifacts: /tmp/pytest-of-nitin/pytest-568/test_chat_history_rebuilds_use0; build_report.json
  contains the failures, and llm/structured-failure-8fde87e6-attempt-{1,2,3}.json contains the
  invalid model output. Ruff and git diff checks passed. No server started/stopped or git commit.

## 2026-09-04 — Identity contract repair and shared evidence formatting

- Clarification of the previous failure: Lao Sze Chuan was present in the frozen web results.
  The model invented a registry reference (`lao_sze_chuan`), not the restaurant. The supplied
  registry contained only You. This was a new-vs-existing identity decision error, not slug formatting.
- Implemented mutually exclusive structured variants for new, existing, and unresolved identities.
  Existing ID/type pairs and unresolved candidate IDs are constrained in the native output schema;
  new IDs remain allocated by application code. New/existing decisions require empty candidate lists;
  unresolved decisions cannot materialize pages. Preserved authoritative user bindings and cross-node
  validation. No lexical identity rules, fallback model, or extra retry mechanism was introduced.
- Staged the candidate schema separately from the router for direct configured gemma4:12b probes.
  First round: five passed, two failed by duplicating the bound user. Clarified resolution semantics
  and the separate user object; all seven then passed in 29.52 seconds before router integration.
  Added neutral tool-discovered business/founder, existing match, and genuine two-candidate ambiguity
  probes alongside user, namesakes, project, and two-speaker cases.
- Schema-only full replay FAILED its Tony Hu page assertion in 126.72 seconds, despite completing
  the build and passing the earlier capture/personal-page checks. The large unit produced structurally
  valid but semantically wrong review candidates referencing You. A later unit discovered Tony Hu
  but chose no page. Preserved output at benchmark_runs/identity-contract-20260904-schema-only-chat.
  Final cooking recall was not reached; this run is not a semantic pass.
- Investigating that failure exposed repeated verbatim source segments in every citing claim's input:
  the prior failed planner's user message was 171,318 characters. Now each exact (source_id, segment_id)
  appears once in a shared evidence appendix, with explicit references from every citing claim. No
  evidence is summarized or discarded. Reformatting the saved 16-claim unit yields 34,022 characters
  of evidence (excluding the registry/template). This is a size comparison, not proof of exact token
  counts or a claim that server-side truncation was observed.
- Probed the new evidence format before enabling it in identity planning and claim routing: all seven
  direct cases passed in 32.19 seconds. Durable probe outputs:
  benchmark_runs/identity-contract-20260904-probes. Removed the temporary candidate path/format flag
  after integration; work-unit contract keys now use identity-plan-v4.
- Added structural tests for impossible resolution states, native-schema candidate constraints,
  unknown-candidate pipeline rejection, shared evidence references, and source-local segment IDs.
  Corrected a pre-existing test's assumption that hashed work-unit filenames sort in processing order:
  it now checks exact claim-batch-to-status mappings. Full suite: 329 passed, 22 opt-in tests skipped;
  Ruff and git diff checks passed. Extraction and synthesis semantics are unchanged in this increment.
- Final expanded replay with both changes FAILED in 228.81 seconds at the tool-person-page check:
  benchmark_runs/identity-contract-20260904-chat. Build completed all ten source episodes with no
  failures or pending sources, one populated You page, five populated restaurant pages, and a Tony Hu
  person identity/page. The Tony Hu page has no grounded facts: the sole extracted founder statement
  was placed on Lao Sze Chuan. The planner correctly proposed Tony as a new person with page=true;
  this remaining failure is page population/claim placement, not invented IDs or incorrect person type.
  The evaluation model incorrectly accepted the restaurant page as the person page; the independent
  structural person-type assertion caught that false positive. Fresh cooking recall was not reached.
- Kept the failing page assertion; did not invent a new personal fact, force a fixture-specific page
  assignment, or count build completion as full replay success. The next decision is how a statement
  involving multiple subjects should populate their wiki views. General context-budget enforcement
  and extraction-accounting reliability also remain outside this increment. Live store untouched;
  no server started/stopped, no migration, and no git commit.

## 2026-09-04 — General multi-page statement placement

- Product decision: a statement can appear on multiple subject pages when it substantively describes
  each subject; mention alone is insufficient. Store the statement once and preserve the same source
  evidence across views. Discovering an identity must not by itself manufacture an empty page.
- Separated identity resolution from page usefulness. Removed the identity schema's page flag and
  replaced the old general/project-role routing contract with one explicit page-placement response:
  exact destinations, type-valid sections, per-destination reasons, and an internal primary owner
  used by the unchanged synthesis stage. All resolved active identities are eligible, including those
  without pages. Updated the reset spec and DESIGN.md; no new maturity/admission stage was added.
- Direct configured gemma4:12b placement probes passed before integration (17.41 seconds): a neutral
  founder/business statement selected both pages, incidental attribution selected only the business,
  and a person/project responsibility used the same general mechanism. No fixture vocabulary was
  added to production prompts and no lexical placement override was introduced.
- Removing page admission from identity resolution exposed neutral probe failures during development:
  a missing project, a single ambiguous referent split into separate unresolved candidates, and an
  omitted external speaker. Clarified the definition of resolved identities vs unresolved referents,
  distinguished personal ownership from identity, and required coverage of external personal claims.
  The unchanged seven semantic assertions then passed in 28.17 seconds (pytest-585). Some responses
  still cite broader contextual evidence than necessary; passing these probes is not general identity
  reliability proof. Earlier failed rounds were not counted as successes.
- Persist explicit ClaimPlacement.page_sections, validate active IDs/sections, and keep primary section
  metadata aligned when synthesis regroups it. Placement reasons retain the per-page explanations.
  General shared views replace the automatic person/project-only renderer. If only some members of
  a synthesized paragraph belong on another page, render those canonical statements rather than leak
  unselected members or manufacture a second persisted fact. Shared views preserve claim IDs/citations.
- Regenerate old as well as new destinations when placements move; retracting a statement updates its
  selected views. Empty non-You pages are removed, with identities retained as provisional. Explicit
  manual moves can supply destinations, and entity merges redirect destination IDs. Generalized
  combined-agent-context deduplication from project-role-only to exact shared claim IDs.
- Updated assignment replay to project frozen statements into facts instead of producing empty pages
  from placements alone. It preserves saved sections and does not call model synthesis. Updated old
  role fixtures to declare shared placements explicitly; retained batching and blocked-revision guards.
- Expanded deterministic coverage: shared provenance without duplicate storage, incidental omission,
  partial-group non-leakage, retraction, removed destinations, invalid persisted IDs/sections, and
  combined-context deduplication. Final backend suite: 336 passed, 25 opt-in tests skipped. Ruff,
  compileall, and git diff checks passed.
- First full frozen-chat replay PASSED in 258.34 seconds: all ten source episodes completed, populated
  You/restaurant/person pages, and cooking-source retrieval in a fresh chat. Preserved at
  benchmark_runs/multi-page-placement-20260904-chat-1. The replay now checks rendered page statements,
  not exclusive synthesis ownership, consistent with the agreed multi-page policy.
- Added an explicit shared-canonical-claim assertion for the fixture's restaurant/founder page pair.
  Second full replay PASSED in 260.76 seconds at benchmark_runs/multi-page-placement-20260904-chat-2:
  no build failures/pending sources, five populated restaurant pages, a populated Tony Hu person page,
  the same canonical statement present on founder and restaurant pages, one populated You page, and
  cooking-source retrieval. Both runs used fresh stores and the frozen original turns/tool results.
- Final repeated direct suite: 9 passed, 1 FAILED in 39.04 seconds at
  benchmark_runs/multi-page-placement-20260904-probes. All three placement probes passed again, but
  the ambiguity probe again split one uncertain referent into two unresolved proposals with separate
  candidates. No forced identity match occurred, but the intended representation is not reliably
  achieved. Kept the failure and assertion intact; did not rerun until green or introduce a semantic
  fallback. This remains an identity-contract reliability issue despite the two passing product replays.
- Final deterministic suite after all changes: 336 passed, 25 opt-in tests skipped; Ruff, compileall,
  and diff checks passed. Live data unchanged, no server started/stopped, no migration, and no git
  commit. Cumulative synthesis, extraction-accounting reliability, and the repeated ambiguity failure
  remain separate work; this increment does not establish a fully reliable memory system.

## 2026-09-07 — Extraction accounting repair and smaller cumulative synthesis

- User confirmed the multi-page UI smoke test passed and authorized these two encoding changes. Live store
  untouched; no server started/stopped, no migration, no git commit. A new user-run smoke check is still needed
  for this increment, distinct from the already-passed placement check.
- Extraction now returns claims first, followed by explicit source-only reasons for the uncited remainder.
  Claimed dispositions are derived from exact citations, not independently generated by the model. Complete,
  disjoint accounting is still required; missing IDs, duplicate remainder IDs, and overlap fail visibly. Validation
  errors include exact offending/missing IDs for the existing bounded structured-output retry. Published claim
  IDs, insert-only recovery, context citations, and full persisted episode dispositions are preserved.
- First direct partition probes: 6 passed at benchmark_runs/extraction-partition-20260907-probes. Integration
  recovery/lifecycle subset: 72 passed. Twelve direct/public capture-build-restart-retrieval checks also passed
  at benchmark_runs/extraction-partition-20260907-replays (680.86 seconds under shared host load).
- The first large run FAILED: benchmark_runs/synthesis-before-20260907-user retained two partial source episodes
  with cited/source-only overlap. Tiny probes were insufficient. The response schema initially generated the
  remainder before the claims; reordered it to claims-first, instructed the same order, and added exact-ID error
  feedback. A new neutral 48-segment probe plus the six small probes then passed (7 tests, 223.86 seconds) at
  benchmark_runs/extraction-partition-20260907-ordered-probes. No omitted segment was implicitly accepted.
- The corrected pre-synthesis LoCoMo user run at benchmark_runs/synthesis-before-20260907-ordered-user completed
  both sessions: 8 then 17 canonical claims, two populated pages, all 51 then 105 source segments accounted for,
  no pending extraction or source/provenance errors. This is accounting reliability on this input, not proof that
  all useful assertions were extracted. The original September 4 user runs had left 48 segments pending.
- Traced cumulative synthesis: prior-fact candidate selection and sequential truth-change review make decisions
  separate from presentation. Kept those, incremental work scoping, pending-review protection, existing fact-ID
  reuse/manual-text behavior, selected-page projection, and commit/recovery. Replaced grouping, group verification,
  per-fact rendering, prose verification, repair, and re-verification with one grounded presentation contract.
- Initial synthesis probes passed five cases at benchmark_runs/synthesis-20260907-probes. Removing an inherited
  fixed-group compatibility assumption exposed under-grouping: the next probe round had 4 passes and 2 failures
  at benchmark_runs/synthesis-20260907-final-probes. Both outputs preserved canonical meanings as separate bullets.
  The modality test's mandatory one-bullet count was an unjustified compression requirement; it now tests faithful
  uncertainty, while the complementary-details case still requires consolidation. That second failure motivated
  an explicit compatible-detail grouping instruction and a smaller group-first representation, not a lexical fix.
- Final direct contract: each group supplies its exact member claim aliases, section, state, text, confidence,
  and reason. No model-generated fact registry or duplicate assignment map. Every claim appears exactly once;
  pending truth-change sides cannot share a group; singleton text must copy the canonical display statement.
  Canonical statements/temporal records constrain synthesis; raw transcripts are not re-exposed as competing
  evidence. All six direct probes passed before integration (119.49 seconds) at
  benchmark_runs/synthesis-20260907-group-probes, including distinct memories, equivalent support, modality,
  complementary attributes, explicit conflict separation, and corrected statements versus stale prior wiki prose.
- Removed ten retired prompt templates, their schema factories/verdict types, the compatibility/render/repair
  helpers, obsolete call-count/repair fixtures, and internal assignment/fact-key round-tripping. Deleted files
  are recoverable from git; no user sources or memory artifacts were deleted. Added exact membership/section/
  singleton/conflict tests, corrected-canonical-input isolation, and retained cumulative support, selected-fact
  preservation, failure-closed prior facts, truth-review, shared provenance, and recovery checks.
- Full backend suite after integration: 340 passed, 32 opt-in tests skipped; Ruff, compileall, and diff checks
  passed. Four initially failing Dream tests used the retired staged-response helper; updated that helper to
  the group-first response instead of restoring old stages. Tightened the invalid-synthesis test so a valid
  truth decision actually reaches and exercises the conflict-separation guard.
- Post-change matched LoCoMo and the full frozen chat/web-search replay are recorded below when complete.
  Existing identity ambiguity, general context budgeting, semantic extraction omissions/modality, and truth-review
  reliability remain explicit follow-ups. The pre-synthesis run proposed camping versus swimming as incompatible
  plans despite separate evidence; preserving review behavior does not establish that those decisions are correct.
- First post-synthesis LoCoMo run FAILED at the second-session Melanie presentation:
  benchmark_runs/synthesis-after-20260907-user. Extraction completed (9 then 18 claims, no pending segments),
  but the model repeated the conflict's members in an additional review-summary group. This was duplicate
  membership, not a missing statement; the initial generic error did not distinguish them. The guard rejected
  all three attempts, preserving prior Melanie facts and leaving four claims unplaced. One first-session
  singleton also added a calendar date; the existing bounded retry corrected it. Do not count this run as a pass.
- Clarified the synthesis/review boundary: review UI owns disagreement summaries; synthesis emits ordinary
  nonduplicated groups, never a second conflict-summary group. Added exact repeated/missing aliases and expected
  singleton text to validation feedback. Expanded direct probes to use production-shaped canonical/temporal input,
  include the needs_review section, and cover a neutral conflict mixed with compatible details and a distinct event.
- Full frozen chat replay FAILED after 498.79 seconds at
  benchmark_runs/encoding-simplified-20260907-chat/test_chat_history_rebuilds_use0. All ten sources extracted
  completely (22 claims), but the unchanged page-placement model selected two different sections of You for one
  statement about cooking for a partner. Exact destination uniqueness rejected three attempts; three source
  entries report routing failures. The build still reports no pending sources, so pending count alone is not an
  acceptance check. The test stopped at the build-failure assertion; its full page and fresh-recall assertions
  were not reached. No assertion was removed and no section was selected by a fallback. This newly exposed
  placement-contract issue is separate from synthesis and remains a follow-up, not a passing product replay.
- Expanded final synthesis/review probes PASSED: 7 tests in 26.79 seconds at
  benchmark_runs/synthesis-20260907-review-boundary-probes. Final matched LoCoMo run PASSED both builds at
  benchmark_runs/synthesis-after-20260907-review-boundary-user: 9 then 17 canonical claims, 7 then 13 facts,
  two populated pages, all 105 cumulative segments accounted for, no build failures/pending sources/unplaced
  claims, and valid claim-to-source and fact-to-claim references. One extraction omission was corrected by the
  existing bounded retry; no synthesis failures were logged. Input hash and effective configuration match the
  pre-synthesis run (8/17 claims and 8/15 facts). The final truth reviewer did not reproduce the baseline's
  questionable conflict, so this does not establish truth-review reliability or exercise that exact in-situ path.
- Final deterministic checks after the guard refinement: 340 passed, 33 skipped in 13.51 seconds; Ruff,
  compileall, and diff checks passed. Page comparison, limitations, preserved failures, and replay command:
  planning/encoding_simplification_2026_09_07.md. Updated the incremental plan with duplicate-page placement
  as the recommended next bounded repair, before another UI smoke check. No additional organizer redesign was
  implemented to make the failed chat replay pass.

## 2026-09-07 — Unique-per-page placement repair

- User confirmed the invariant: a canonical statement may appear on multiple pages, but not more than once on
  the same page. Replaced the repeatable destination list with an exact page-ID-keyed response. The model chooses
  one type-valid section or `not_selected` per eligible page, with a reason; primary owner must be selected.
  This is an explicit structured model decision, not a deduplication fallback or application-chosen section.
- Probed before integration using the configured host gemma4:12b and production prompt/schema. Initial sparse
  maps under-selected substantive shared placements (2 passed / 2 failed); choosing destinations before the owner
  improved the project case but not the founder case (3 passed / 1 failed). Preserved runs:
  benchmark_runs/page-map-20260907-probes and page-map-20260907-destinations-first-probes.
- Explicit per-page nullable decisions selected the intended pages, but the incidental case failed revalidation:
  the shared LLM serializer removes null fields. A mixed object/string exclusion variant then returned all pages
  unselected despite reasons describing useful destinations (4 failed). Neither variant was integrated; shared
  LLM parsing was not changed to accommodate them. Runs: page-map-20260907-explicit-probes and
  page-map-20260907-final-probes. Early failed rounds lack full debug dumps; their pytest outputs record failures.
- Uniform per-page objects with a declared `not_selected` section choice PASSED all four direct cases in 13.43
  seconds at benchmark_runs/page-map-20260907-section-probes. Founder/business and person/project relationships
  selected both useful pages; incidental attribution selected only the business; a personal goal motivated by a
  relationship chose one section on You. No fixture vocabulary or lexical semantic rule entered production.
- Integrated only the proven contract. Retired the old list and temporary probe switch, updated routing's
  conversion to selected `page_sections`, and retained explanations for selected and unselected pages in routing
  reasons. No persisted claim/page schema change, live-store reset, migration, or alternative pipeline.
- Updated affected fixture registries explicitly, including unselected existing entities and identity renames.
  Contract tests reject missing/unknown destinations, wrong-type sections, lists of duplicate page entries,
  multiple sections, and an unselected owner. Added parser/serializer round-trip checks, multi-page acceptance,
  and no-eligible-page deferral. The full chat replay now checks exact canonical claim-ID uniqueness across all
  sections on every page, while retaining the shared restaurant/founder claim assertion and fresh retrieval check.
- Backend suite: 343 passed, 34 opt-in tests skipped in 17.91 seconds. Ruff, compileall, and diff checks passed.
  Full frozen chat replay is recorded below when complete. Live data untouched; no servers started/stopped and
  no git commit. Existing unrelated identity ambiguity, truth-review reliability, and context-budget issues remain.
- Full frozen chat/web-search replay PASSED in 294.09 seconds at
  benchmark_runs/page-map-20260907-chat/test_chat_history_rebuilds_use0: all ten input sources completed,
  22 extracted claims, no build failures/pending sources, one populated You page, five populated restaurant
  pages and one person page, shared restaurant/founder canonical evidence, no repeated canonical claim ID within
  any page, and fried-rice source retrieval in a fresh chat. The earlier failing replay remains intact. No
  assertion was relaxed and no additional build was used to hide incomplete work.
- Updated DESIGN.md, the incremental plan, and the prior encoding comparison with this repair's outcome. Next
  checkpoint is user-run UI smoke testing; the LoCoMo comparison from the synthesis increment was not rerun
  in this bounded placement repair. Explicit per-page decisions grow with registry size; general context/output
  budgeting remains a follow-up, not something this contract alone solves.

## 2026-09-07 — Truth-review scope repair

- User confirmed the latest UI smoke test and page quality; build latency is acceptable and not an optimization
  target. Authorized separate truth, identity, and extraction repairs with incremental successful commits.
- Narrowed the existing truth-review prompt: same subject/topic is insufficient; evidence must establish the same
  particular state/event and incompatibility or replacement. Multiple plans and uncertain alternatives may coexist.
  No additional pass, schema, lexical rule, automatic correction, or change to review authority.
- Initial seven neutral direct probes passed even before the change (`benchmark_runs/truth-20260907-before`);
  they do not reproduce the historical false positive. Final eight direct production-contract probes passed at
  `benchmark_runs/truth-20260907-after`, including same-domain independent plans and genuine cancellation.
- Three actual capture/two-build replays passed in 120.51s at `benchmark_runs/truth-20260907-replays`: compatible
  plans generate no proposal; explicit replacement and same-event contradiction generate pending proposals and
  preserve accepted canonical claims. This also exercises prior-fact selection and cumulative synthesis.
- Backend: 343 passed, 45 opt-in skipped; Ruff and diff checks passed. No live data or servers touched.
- Include the two existing, unchanged synthesis templates in this commit: they were untracked despite being
  required by the previously committed production pipeline. Other unrelated untracked files are excluded.
- These are bounded regression checks, not a claim that truth review has perfect semantic accuracy.

## 2026-09-07 — Identity ambiguity and retained review alternatives

- The original ambiguity probe passed once at `benchmark_runs/identity-20260907-before`; historical failures
  remain relevant. Added a rephrasing and a counterexample with two distinct unknown actors, plus exact
  speaker-claim citation assertions. No production lexical merging or fixture-dependent overrides.
- Retained unsuccessful direct experiments under `benchmark_runs/identity-20260907-*`: `referent-first`
  (7/9; existing match incorrectly deferred, distinct actors collapsed, and inspection found bad citations),
  `resolution-first` (8/9; duplicate user representation), `neutral-referent` (6/9; citation contamination and
  candidate splitting), `explicit-referent` (6/9; the unresolved-only field biased generation into new identities),
  and `common-referent` (6/9; speaker and ambiguous matching regressions). None of these variants was integrated.
- Final contract uses existing fields: explain the source referent before choosing identity, resolve the bound user
  before additional subjects, choose alternatives after resolution, and constrain evidence descriptions to this
  subject. Removed experimental extra fields. Nine direct probes passed in 36.20s at
  `benchmark_runs/identity-20260907-user-first` before integration.
- Persist candidate_entity_ids in EntityResolutionDecision; previously only the cached identity plan retained them.
  Exact candidate IDs are repository-validated and included with the reason in pending-review context. No inferred
  candidate reconstruction, migration, live-store edits, or automatic ambiguous matching.
- Integrated validation: 12 passed in 47.91s at `benchmark_runs/identity-20260907-integrated`: all nine direct
  probes plus three real ClaimRouter replays. Routing defers ambiguous claims without creating identities;
  one actor retains one proposal with both alternatives, two distinct actors retain two, and candidates/evidence
  survive repository reload. Added deterministic routing/roundtrip and user-first schema checks.
- Backend: 344 passed, 50 opt-in skipped; Ruff and diff checks passed. The counterexample's titles still describe
  possible roles rather than clearly distinguishing the offered actions; candidate sets and uncertainty remain
  intact, but review-description quality and broader model reliability are not solved by these small probes.

## 2026-09-07 — Extraction commitment-level fidelity

- Added five neutral fixtures: tentative outing, explicitly undecided outing, conditional intention, firm
  commitment, and an uncertain report. The old prompt passed four small examples at
  `benchmark_runs/fidelity-20260907-before`. A shorter tentative example reproduced the defect at
  `benchmark_runs/fidelity-20260907-tentative-before`: "thinking about" became unqualified "plans to".
  The old model judge incorrectly passed that output; inspection, not its score, caught the problem.
- Tightened the evaluation-only judge to distinguish tentative consideration from unqualified intention. Added
  a judge counterexample that must reject a strengthened intention. No evaluation vocabulary enters production.
- Added one extraction prompt paragraph requiring the readable assertion to preserve commitment level, conditions,
  negation, and attribution. No extra extraction stage or certainty taxonomy; categories/confidence cannot replace
  qualifiers. The matched tentative output now says "is considering" instead of "plans to".
- Thirteen direct checks passed in 139.27s at `benchmark_runs/fidelity-20260907-after-probes`: eleven extraction
  cases, the judge counterexample, and 48-segment accounting. The large batch initially omitted source-only entries;
  the existing bounded structured-call retry recovered. Its failed output remains in llm-errors, not hidden.
- Eleven actual capture/build/restart/retrieval replays passed in 193.56s at
  `benchmark_runs/fidelity-20260907-replays`. Added meaning checks over rendered wiki statements as well as stored
  claims and retrieved evidence. This covers suggestions, context-dependent acceptance/refusal, source-only input,
  and the five fidelity cases. No replay assertion was relaxed; no-work rebuilds preserve canonical claims.
- Backend: 344 passed, 61 opt-in skipped; Ruff, compileall and diff checks passed. Full frozen-chat regression
  is recorded below when complete. Source attribution can still be implicit in citations rather than readable
  prose (the reported-move example); the model judge is not a proof of every qualifier or relationship's retention.
  This increment repairs demonstrated commitment-strength drift, not all semantic omissions.
- Combined frozen-chat/web-search replay PASSED in 264.22s at `benchmark_runs/semantic-repairs-20260907-chat`:
  one populated You, expected tool-grounded restaurant/person pages, shared canonical restaurant/founder evidence,
  no repeated canonical statement ID within any page, and fried-rice source recall in a fresh chat. One extraction
  response overlapped cited/source-only accounting; the existing bounded retry recovered, with the failure retained
  in the replay's llm directory. No extra build or relaxed assertion was used.
- Final backend rerun: 344 passed, 61 opt-in skipped in 16.50s; lint/compile/diff checks clean. Updated DESIGN.md
  and the local incremental plan. The pre-existing untracked plan remains untracked, as do unrelated user files.
  The earlier LoCoMo comparison was not rerun in this increment. No live data, server processes, or model settings
  changed; speed remains out of scope. User-run UI check of these latest repairs is the remaining handoff.

## 2026-09-08 — Limit historical replanning to actual materialization

- The partial long-session run exposed repeated historical routing. The router's `new_entities` also includes
  updated existing identities; Dream incorrectly treated those updates as newly materialized subjects.
- Compare persisted materialization state before triggering scope revision. Creation and provisional-to-materialized
  transitions still replan history; routine updates do not. No semantic heuristic or prompt change was introduced.
- Added a structural regression and corrected the existing materialization fixture to exercise a real transition.
  Three real two-build truth probes also verify that updating the same subject does not invoke historical revision:
  3 passed in 198.89s at `benchmark_runs/long-memory-20260908-replan`.
- Backend: 345 passed, 61 skipped; Ruff and diff checks passed. Original benchmark and live store untouched.

## 2026-09-08 — Keep pending truth review outside presentation synthesis

- Removed post-synthesis group dropping: pending incoming IDs and all members of protected accepted facts now
  leave the presentation input before synthesis. Whole accepted facts remain unchanged. An unrelated claim cannot
  disappear just because the model grouped it with a review-held statement. An entirely held work unit needs no
  presentation call. No lexical inference or alternate extraction path was added.
- Direct production prompt/schema checks passed (distinct memories and complementary details with review sides
  excluded): 2 passed in 11.53s at `benchmark_runs/long-memory-20260908-review-contract`, before integration.
- Structural tests cover existing pending review, preservation, exact membership and rejection of incomplete output.
  Updated mock responses to reflect the smaller input rather than silently accepting extraneous aliases.
- First integrated pass: two passed, one test assertion failed because the model legitimately first-materialized
  a children identity. The original no-replan assertion was broader than the invariant; changed it to inspect every
  trigger's persisted prior state. Build itself completed successfully; retained the failed run at
  `benchmark_runs/long-memory-20260908-review-integrated`.
- Extended the public replay with an unrelated third capture/build after replacement and contradiction reviews:
  all eligible placed claims remain represented, all held incoming claims stay out of accepted facts. Three cases
  passed in 153.93s at `benchmark_runs/long-memory-20260908-review-three-builds`.
- Backend: 346 passed, 62 skipped in 13.49s with host access; Ruff and diff checks clean. Sandbox-only full suite
  stalled on local networking; host-enabled rerun is the recorded validation. No live or original benchmark edits.

## 2026-09-08 — Bounded cumulative additions and batch-local failure recovery

- Additions against existing history now use at most four new claims per work unit (initial batches remain twelve).
  Prior facts are still selected semantically; there is no lexical partition or arbitrary truncation of old evidence.
  The direct synthesis contract remains unchanged and was exercised by the preceding neutral probes.
- Previously, a late batch failure discarded all successful work for its owner. Addition-only failures now carry
  exact failed claim IDs; successful batches persist, and a subsequent Build retries the missing claims only.
  Existing placement changes still fail owner-atomically. Pending proposals are carried across batches before commit.
- Added injected first/late failure tests with and without history, an existing-placement atomicity counterexample,
  and a full Dream commit/retry regression: twelve valid facts survive a thirteenth-claim failure unchanged, then the
  retry completes the remaining claim without duplicates. Chronological input order is preserved across batching.
- Public real-model neutral replay: three captures/builds with six statements each, complementary details, repetition,
  independent facts, reloads, and bicycle retrieval. Passed in 543.66s at
  `benchmark_runs/long-memory-20260908-neutral-batching`. Every eligible placed claim is represented; no per-page
  duplicate claim IDs; strict meaning checks retain profession duration, painting preference, bicycle details, and
  language-practice schedule. Timing includes concurrent model probes and is not a latency comparison.
- Backend: 353 passed, 69 skipped in 15.88s; focused final tests 60 passed; Ruff/diff clean. The sandbox-stalled pytest
  was terminated by its verified PID after the host-enabled replacement passed; no server processes were touched.
- Fifteen-session frozen-extraction replay is running separately from commit eef5aa3, before this batching change;
  results will be attributed accordingly. The admission wording was being probed during the neutral replay; admission
  has separate direct and integrated tests and is committed separately. This replay is not an isolated A/B on extraction.

## 2026-09-08 — Admit concrete experiences without promoting conversational encouragement

- Clarified existing admission policy: ordinary experiences, actions, observations, and changing conditions can
  remain useful as dated history. Durability is not permanence or subjective importance. Generic encouragement
  does not establish recipient traits or commitments. No keyword filtering, extra admission pass, or benchmark
  vocabulary entered the production prompt.
- Three neutral tiny cases passed under the old prompt at `benchmark_runs/long-memory-20260908-admission-before`;
  these alone did not reproduce the long-run omissions. After clarification, five direct cases/counterexamples
  passed in 88.08s at `benchmark_runs/long-memory-20260908-admission-after`.
- A longer external-participant probe uses eight concrete reports interleaved with filler. The first assertion
  incorrectly indexed input turns after ingestion split them into sentences; its output had retained the reports.
  Added evaluation-only metadata to carry fixture identity through splitting (not rendered to the model).
  The corrected 48-segment probe passed in 71.64s at `benchmark_runs/long-memory-20260908-multiparty-admission-ids`:
  all eight assertion segments cited, no filler cited, and meal/health/travel details preserved by the meaning check.
- Three public capture/build/wiki/restart/retrieval cases plus the long direct probe passed in 219.80s at
  `benchmark_runs/long-memory-20260908-admission-replays`. Existing suggestions, acceptance/refusal, fidelity,
  questions and large-batch accounting probes all rechecked: 15 passed in 395.35s at
  `benchmark_runs/long-memory-20260908-admission-regression-probes`.
- Backend at this stage: 355 passed, 71 skipped; Ruff/diff clean. Frozen-extraction benchmark runs cannot measure
  extraction recall improvement; these are explicit policy and neutral regression checks, not a claimed LoCoMo
  recall gain. Earlier loss cannot be recovered by merely resynthesizing frozen claims.

## 2026-09-08 — Expose presentation gaps in existing artifact diagnostics

- Extended coverage reporting with represented active claims, active claims without facts, pending-review holdbacks,
  placed claims missing facts after excluding holdbacks, and repeated canonical fact membership. These are structural
  accounting measures, not semantic recall or compression targets; the existing benchmark stats include them.
- Integrity reporting detects repeated claim IDs within one page while allowing projection onto different pages.
  Added neutral tests distinguishing unplaced input, intentional review holdback, lost presentation, canonical
  duplication, and allowed cross-page sharing. Existing inspection API expectations include the new issue key.
- Read-only application to the original interrupted store identifies 109 represented active claims, two review-held
  claims and one unexplained placed-claim gap (`claim-c4e8ab413633657d`), without treating all three as equivalent loss.
- A direct synthesis regression for two distinct occurrences of the same activity, their dates/details, and unrelated
  preferences/plans passed at `benchmark_runs/long-memory-20260908-occurrences` in 56.64s. The current contract handled
  this neutral case; no extra grouping stage or speculative prompt change was justified by this result.
- Focused diagnostics/API tests: 31 passed; backend: 355 passed, 71 skipped; Ruff/diff clean. Initial test failures were
  incomplete page fixture identity metadata and the old exact API issue-key expectation; both fixtures were corrected.

## 2026-09-08 — Do not invent a quantity for unquantified relative years

- Removed the temporal normalizer's implicit one-year default when its parsed year quantity is absent. This removes
  an unsupported inference rather than adding a natural-language classification rule. The invariant is that absent
  quantities cannot acquire exact calendar intervals during normalization; original wording stays unresolved.
- Tests exercise both a supplied temporal facet and recovery from canonical claim text. Existing explicit-year
  precision and other relative-time tests remain. Artifact/temporal tests: 59 passed; Ruff/diff clean.
- This does not rewrite old extracted temporal artifacts. The frozen-extraction replays intentionally retain the
  original extraction, including its old temporal normalization; a fresh extraction uses the repaired mechanism.

## 2026-09-08 — Bound placement grids and keep failed routing sources pending

- The established chat replay failed at `benchmark_runs/long-memory-20260908-chat` in 713.89s. A placement response
  repeatedly selected an owner excluded from its page map (about 6,900 output tokens / 95s per returned attempt);
  other routing failures had empty exception messages. The old batch limit counted claims, not claims times pages.
- Routing now targets at most 32 claim/page decisions per response while preserving every claim and every eligible
  page. A registry larger than 32 still receives a complete single-claim row; this is a workload bound, not a full
  input/output token-budget solution. Exception types are included in routing errors. No page is selected by code.
- Five production page-contract probes passed before integration at `benchmark_runs/long-memory-20260908-page-grid-probes`
  in 50.97s, including four claims against eight identities and shared/irrelevant subject counterexamples.
- Failed routing now adds the source's raw-log ID to pending accounting. Previously the report could list failures
  while marking their logs consolidated. Corrected two tests that encoded that bad completion behavior; added a
  successful retry check and page-grid size/coverage checks across growing registries.
- The smaller-grid chat replay completed its build but failed the stronger shared-evidence assertion in 611.80s
  at `benchmark_runs/long-memory-20260908-chat-page-grid`: a restaurant identity was omitted. Inspection also caught
  the evaluation judge incorrectly matching a different restaurant; that did not pass the shared-statement gate.
  These semantic failures were retained and addressed separately below, not reported as a successful chat replay.
- Backend: 366 passed, 73 opt-in skipped; Ruff/diff checks clean. Combined public replay validation after the
  source-policy correction below passed; the grid change alone is not claimed to solve identity omissions.

## 2026-09-08 — Keep experience admission specific to conversational sources

- The broader admission wording had also applied to tool results, broadening incidental review-author extraction
  and crowding identity planning in the chat replay (30 claims versus 23 after correction). The paragraph now applies
  only outside the declared `tool_observation` source type. Tool extraction retains its existing targeted policy;
  a rendered-prompt comparison against eef5aa3 confirmed identical words apart from whitespace. No name filter was added.
- Added source-type prompt-boundary tests and a neutral real-tool probe preserving business/founder/address facts
  without promoting transport metadata. That probe and the two conversational experience probes passed in 45.99s at
  `benchmark_runs/long-memory-20260908-source-policy-probes` before the new public replay.
- Tightened the evaluation-only page matcher: shared industry or similar names do not establish identity, and aliases
  or translations cannot be invented. The shared canonical statement requirement remains unchanged.
- Full chat replay PASSED in 438.33s at `benchmark_runs/long-memory-20260908-chat-source-policy`: one populated You,
  tool-grounded restaurant/person pages, shared founding evidence, per-page claim uniqueness, and fresh cooking-source
  retrieval. Neither prior failed run was deleted, and no expected page or shared-evidence assertion was weakened.
- This is a source-policy scoping repair, not proof of perfect identity discovery. Both the benchmark and the neutral
  corpus remain guideposts; no fixture names or desired answers enter production prompts or matching logic.

## 2026-09-08 — Stop rescheduling review-held facts and shrink later initial-build batches

- A pending truth proposal already determines that its incoming statement cannot enter accepted presentation.
  Exclude those exact persisted pending IDs before fact candidate selection, not just before prose synthesis.
  Underlying claims remain active/stored/retrievable. Once review releases a statement it is eligible again.
- The smaller addition limit now applies after the first successful batch inside a long initial build, not only
  when history existed before the build started. Failure-injection tests now span 29 additions, including failed
  first/late batches and owner-atomic changes to valid existing page placements.
- Added a no-model-work pending-review regression and a release-after-review counterexample. Existing pending-review
  coverage tests now assert the reduced input rather than asking the model to reconsider the held statement.
- Three actual repeated-build review cases passed in 277.76s at
  `benchmark_runs/long-memory-20260908-review-scheduling`; focused fact tests: 23 passed. Backend: 367 passed,
  73 opt-in skipped in 19.03s; Ruff/diff checks clean.

## 2026-09-08 — Completed fifteen-session accumulation replay and quality audit

- `benchmark_runs/long-memory-20260908-replay-after-batching` completed all 15 builds in 5,088.22s with no build-level
  failures. It reuses the original sample9 extraction in a fresh organization store; no QA was requested (count 0).
  Four rejected structured synthesis responses recovered on retry. Original/live stores were not rebuilt or cleared.
- Original: 178 active claims, 109 represented by 60 canonical facts, 2 held, 66 unplaced, 1 unexplained placed gap;
  eight completed builds, six failed, and a cancelled fifteenth. Replay: the same 178 claims, 166 represented by
  107 facts, 12 held, no unplaced claims or unexplained placed gaps. Cross-store integrity is healthy and canonical
  memberships / within-page claim IDs have no duplicates. These structural measures are not semantic recall scores.
- Total audited claim decisions fell from 1,161 to 197; identity work units from 106 to 20. Session 12 deferred eight
  claims; session 13 retried and placed them all. Later knee-recovery, Tahoe, and ER/gastritis facts are now present.
- Manual page inspection still finds substantial irrelevant cross-page sharing, particularly the Canadian woman's
  31-bullet page, plus over-broad synthesized sentences, stale current context, and questionable truth-review holds.
  Coverage/reliability improved; uniformly good organization or concise faithful prose is not claimed.
- Attribution: this process started after the batching increment but before the subsequent placement-grid and
  review-scheduling changes. Those later changes passed their own real probes/replays and the latest backend suite.
  Frozen extraction cannot test the fresh admission/temporal repairs. Concurrent model tests preclude a clean latency
  comparison; the last three builds took 7.48/6.07/4.75 minutes, but selected historical context remains unbounded.
- Full comparison, commit map, neutral/public replay evidence, limitations, and reproduction command:
  `planning/long_memory_repairs_2026_09_08.md`. Next semantic priority is page relevance, followed by event/grouping
  fidelity and truth-review precision, using neutral counterexamples before another corpus-scale run.

## 2026-09-08 — Print per-session benchmark elapsed time

- LoCoMo now prints a flushed completion line with elapsed seconds around each `memorize` call. This includes that
  session's build under `per-batch`, but not separately deferred `finalize_case` work under `per-case`.
- Wiki-baseline output also shows its existing checkpoint duration (capture/build plus snapshot copy).
- Extended the bounded-session runner test with a controlled clock to verify individual rather than cumulative
  durations. Benchmark test module: 25 passed; targeted Ruff and diff checks clean. No real benchmark was launched.

## 2026-09-08 — Retry HTTP timeouts in Ollama calls

- Both chat and structured response handlers now catch HTTPX TimeoutException through their existing bounded retry
  loops, covering read/connect/write/pool timeouts. Exhaustion preserves the original exception. Timeout duration
  and benchmark checkpointing are unchanged.
- Client tests: 36 passed; targeted Ruff and diff checks passed. New failure-injection cases exercise recovery and
  exhaustion in both entry points. An initial test omitted the required structured schema; corrected before acceptance.
- No model or server process was started and no benchmark was rerun for this transport change.

## 2026-09-08 — Preserve event scope during cumulative truth comparison

- Truth input and canonical synthesis records now carry cited source occurrence times and segment timestamps,
  excluding ingestion timestamps. Each proposed truth target requires a structured, evidence-backed referent
  comparison; only a model-declared same scope can support a change. Scope explanations remain in review proposals.
- Direct baseline with dates alone still falsely contradicted separate injuries. The refined per-target contract
  passed separate occurrences, different objects, an explicit correction, and an exclusive-state transition.
  Probe artifacts: `benchmark_runs/cumulative-contracts-20260908/temporal-before-integration`,
  `temporal-per-target-scope`, and `temporal-integrated` (4 model checks plus structural multi-target rejection).
- Existing truth probes and actual repeated-build review replays: 11 passed in 142.40s at
  `benchmark_runs/cumulative-contracts-20260908/truth-regression`. Backend: 384 passed, 77 deselected;
  targeted Ruff passed. Fixed an intermediate canonical-record indentation error and updated mock contracts
  before acceptance. These are bounded behavioral checks, not a new LoCoMo score.

## 2026-09-08 — Explicit temporal extraction and complete contextual assertions

- Extraction must deliberately classify temporal status, with citations and temporal context generated before
  readable claim text. Prompts distinguish intended/completed actions, preserve travel direction and ordinary
  experience details, and reconstruct the scope and decision in contextual acceptance/refusal replies.
- Neutral six-assertion prototype retained every assertion with correct checked temporal states, intention, and
  direction. Final integrated fidelity check: 2 passed at
  `benchmark_runs/cumulative-contracts-20260908/extraction-final-fidelity`.
- The initial full extraction suite produced 30 passes and two real failures: contextual replies omitted the
  proposal's timing. Context wording alone repaired acceptance but not refusal. Evidence-first ordering retained
  the timing; the refusal still lost the act of declining. A neutral decision-preservation probe passed before
  the final prompt integration. Final refusal direct/build checks: 2 passed in 37.83s at
  `benchmark_runs/cumulative-contracts-20260908/extraction-decision-integrated`; acceptance direct/build checks
  passed in the preceding `extraction-evidence-first-integrated` run. All intermediate failures remain inspectable.
- Structural mocks now declare temporal status rather than relying on an implicit unknown default. The combined
  backend suite passed 389 tests (79 opt-in deselected); final six-assertion fidelity tests passed. No lexical
  correction or source-only override was added. Original benchmark stores were not modified.
- Final prompt regression sweep: 17 direct extraction/admission cases passed in 193.97s at
  `benchmark_runs/cumulative-contracts-20260908/extraction-final-regression`, including large and multi-party
  batches, contextual replies, uncertainty, questions, and tool observations.

## 2026-09-08 — Ground cumulative organization in subject and memory scope

- Placement now emits a complete page grid, including on deferred decisions. Each destination has source-backed
  subject evidence and model-declared relevance before section selection. Exact schema invariants reject selected
  incidental/unrelated pages and invalid owners. The relevance evidence is preserved in placement explanations.
  Initial union-based prototypes escaped into deferral even with positive reasons; a complete grid removed that
  short branch. An attribution probe was clarified because explicitly asserting a reading interaction can itself
  describe its participants. The final neutral probe and all 5 existing placement regressions passed.
- Identity catalogs retain accepted founding and recent resolution evidence, including canonical claim text and
  exact source/segment citations. Staged decisions survive source work units and scope revision; unresolved proposals
  remain distinct from accepted grounding. Additional identity prompt wording regressed distinct ambiguous actors
  and was removed. The smaller grounding-only repair passed both ambiguity probes/replays and the staged unnamed
  identity router case (3 tests in 26.62s). Its existing ID and page placement were preserved.
- Candidate selection now sees canonical fact members and their source times, rather than only the old summary.
  Synthesis declares concrete memory scope before membership/prose and may split old over-broad groups. Scope is
  retained in fact reasons. Required membership, singleton fidelity, manual corrections, and review isolation remain.
  Initial generic scope labels plus unknown temporal input still produced incorrect current state; concrete scope
  and explicit temporal input passed before integration. Nine existing synthesis probes passed in 58.63s; the
  explicit over-broad-group repartition regression passed in 12.49s. Structural fixtures were updated before acceptance.
- Truth comparisons now have an 8192-token generation ceiling for per-target scope explanations. A real 16-target
  probe returned all comparisons and no false conflict (1715 generated tokens), documenting why the former 2048
  ceiling leaves little room for growth. Historical context size itself is still not fully bounded.
- Final full backend: 389 passed, 79 deselected in 16.07s. Subsequent focused checks and targeted Ruff/diff checks
  passed after the budget/formatting cleanup. No server or benchmark job was started.
- Public capture/build/restart/retrieval replay: all 3 builds completed without failures, 18 claims retained as
  13 facts, membership/coverage checks and semantic retention/retrieval judgments passed in 296.70s at
  `benchmark_runs/cumulative-contracts-20260908/final-cumulative-replay`. This run preceded only the final narrow
  extraction refusal wording and truth output-budget increase, which have their own direct/build validations.
- New handoff: `planning/cumulative_quality_repairs_2026_09_08.md`. It records limitations, including a still-imperfect
  temporal classification of ongoing tenure and the absence of a separate briefing/detail layer. LoCoMo QA and
  corpus-scale semantic coverage remain for the user's next fresh benchmark run; old stores were not rebuilt.

## 2026-09-09 — Audit prompt clarity and remove presentation bias from synthesis

- Audited all six memory-construction calls, assistant context selection, chat/benchmark QA, and Engram summary
  inputs. Findings and remaining limitations: `planning/prompt_context_audit_2026_09_09.md`. The active memory
  templates have no few-shot demonstrations; repetition and evidence/presentation boundaries were the larger issues.
- Staged candidate templates and input formatters outside production and probed configured host `gemma4:12b` before
  integration. `benchmark_runs/prompt-clarity-20260909/candidate-contracts`: 34 passed, four semantic failures
  (synthesis over-splitting, duplicate bound-user identity, two ambiguous identity cases), and one transport timeout.
  The first harness invocation failed before model calls because its pytest temp parent did not exist; it was fixed.
  Concurrent candidate suites increased request queueing; final verification ran serially. Timeouts are not counted
  as semantic evidence against a prompt or the model.
- The shorter identity prompt was withheld. With the original identity instructions and new JSON evidence,
  `input-regressions` passed all ten identity probes/replays and four temporal cases. That run totaled 29 passes
  and two extraction regressions: strengthened consideration and admission of a question without personal facts.
  The shorter extraction template was also withheld. No lexical fallback or post-hoc source-only override was added.
- Accepted concise affirmative placement/truth/synthesis templates: 443/539/565 words became 253/260/311.
  Placement's registry exposes exact page subjects and only their active types' section definitions. On the latest
  four-person registry, its catalog changed from 919 to 328 estimated project-tokenizer tokens. Identity/placement
  evidence now uses JSON with canonical claims, participant aliases, and shared source records. Cross-source cited
  context, source titles when present, and missing-source citation references are retained. No recording timestamps
  are promoted to occurrence evidence.
- Pydantic inheritance had placed truth verdicts before dynamically added scope comparisons, contrary to the
  prompt's requested order. Both output branches now declare scope first while preserving exact alias and shared-
  scope validation. `refined-contracts`: 22 passed; its one failed mixed-history synthesis probe remained useful
  evidence of broad grouping. Four truth probes cover repeated habits, relative dates across different months,
  compatible activities, and an exclusive-state replacement amid unrelated historical claims.
- Controlled synthesis experiment: a neutral 14-claim set produced eight groups with old over-broad display prose,
  incorrectly merging independent plans and routines. The identical original system prompt produced the correct
  ten groups when that prose was removed. The shorter final prompt also produced ten groups with canonical-only
  evidence. Requests/responses are in `synthesis-controls`; the two original-system hashes match. Wording-only
  refinement (`synthesis-refinement`) still merged plans, so it was not treated as sufficient.
- Synthesis now receives canonical members and explicit manual presentation constraints, excluding previous
  automatically generated display groups. Their evidence remains in canonical members; ordinary fact-ID reuse,
  manual presentation preservation, and pending-review isolation remain. Truth/selection claim inputs and existing-
  fact records are JSON; cited text is deduplicated by exact source/segment IDs, with each claim retaining citations.
- Final direct/in-situ validation at `benchmark_runs/prompt-clarity-20260909/final-input-replay`: all six checks passed
  in 264.43s. The four mixed-history truth checks used the actual candidate production input formatter, followed by
  the 14-claim synthesis check and a public capture/build/restart/retrieval replay. All three builds completed with
  no failures or truth-review proposals; 18 claims remained represented as 12 facts, with semantic retention and
  bicycle-detail retrieval checks passing. Candidate fact-input methods were integrated after their direct probes;
  the replay used those same methods and the accepted production prompts.
- Backend regression: 395 passed, 85 opt-in checks deselected. An old display-string assertion was updated to verify
  the JSON evidence contract. Targeted Ruff and diff checks passed. Original LoCoMo artifacts were not rebuilt,
  and no server or benchmark job was started. Changes are uncommitted.
- Follow-up: aggregate historical input/schema budgets and full-cohort identity decisions in placement batches
  remain open. Focused passes do not establish corpus-scale coverage/correctness; the user's next fresh LoCoMo run
  should reassess wiki quality and complete QA.

## 2026-09-09 — Consolidation efficiency with coverage checks

- Investigated safe batching and bounded semantic retrieval before integration. Configured host `gemma4:12b`
  selected all expected matches in a neutral 4-incoming/84-prior paired probe: 28 calls / 52.75 s previously,
  7 calls / 34.54 s batched. Production selection schema and prompt were used. Evidence lives under
  `benchmark_runs/consolidation-efficiency-20260909/batch-contract/`.
- Bounded embedding shortlist was deliberately withheld: three narrow queries retrieved their expected match
  first, but a broad correction needed 28 historical records and top-24 retained only 24. Top-12 retained 12;
  top-48 happened to retain all 28. The production structured selector independently confirmed the 28-record
  scope and excluded the unrelated measured property. Increasing the cutoff to fit this example would not
  establish completeness. See `shortlist-recall/embedding-recall.json`; no lexical fallback or lossy cutoff shipped.
- Integrated four-incoming/twelve-prior comparisons, caching canonical records within each selection operation.
  Input budgeting includes prompt and schema plus output/safety reserves. Exact input sets split recursively;
  every pair is covered once. An irreducibly oversized pair fails explicitly without truncating evidence.
- Removed truth calls with no eligible target aliases. Product invariant: a truth change requires an existing
  target; the empty domain admits no change. Canonical synthesis still handles incoming claims, and nonempty
  target domains retain model truth review and pending-proposal isolation.
- Added durable per-store `diagnostics/llm-calls.jsonl`: stage, model, attempt/call ID, success, latency, character
  counts, and native token/duration metadata. No raw prompts or responses are written there. Trace persistence
  survives restarts and the in-memory deque limit; diagnostic I/O failure does not discard a completed response.
- Initial integrated selection probes: narrow case passed; broad correction retained all 28 needed records but
  over-selected twelve unrelated records. Preserved the strict specificity check. A concise affirmative prompt
  explicitly matching subject/property and temporal/event scope passed both direct production-schema probes
  before integration (2 passed in 37.40 s, `refined-selection-contract/`). No benchmark vocabulary entered product
  code or prompts. Success dumps in subsequent probes preserve actual requests, responses, and reasoning fields.
- Paired public capture/build/restart/retrieval replay, serial baseline then optimized: both passed. Baseline
  restores the two pre-change methods and both use the original selection wording to isolate batching and
  empty-target skipping. Total 193.11 -> 174.80 s (9.5%); summed Dream-model time 147.24 -> 130.32 s (11.5%).
  Selection 12 calls / 28.96 s -> 4 / 15.57 s; truth 18 / 43.55 s -> 8 / 30.69 s; total attempts 49 -> 31.
  All 18 claims remained represented across three successful builds with no proposals. Final facts 12 -> 13:
  Spanish learning/practice remained separately displayed in the optimized run, so improved concision is not
  established. Retention and bicycle retrieval semantic checks passed. Two optimized synthesis attempts failed
  exact-singleton-text validation and recovered; failure dumps retained. See `paired-replay/comparison.json`.
- Added structural tests for complete pair coverage, schema-inclusive budgets, oversize failure, empty truth
  domains, and persistent retry traces; adjusted mocks to the actual context-window interface and removed obsolete
  empty-target responses. First broad backend run exposed four outdated fixtures; fixing them yielded 401 passes,
  87 opt-in tests deselected. Temporary out-of-tree harness runs emitted unregistered integration-marker warnings;
  these were harness configuration warnings, not production/model failures.
- Detailed assessment and next-run interpretation: `planning/consolidation_efficiency_2026_09_09.md`. Exhaustive
  selection still grows with history; this is a measured reduction of avoidable work, not proof that long-session
  cost is optimal. No full LoCoMo benchmark or server process was started; no commit was made.
- Final integrated native validation: 6 passed in 323.91 s at
  `benchmark_runs/consolidation-efficiency-20260909/final-native/`: both selection probes (exact narrow matches and
  all 28 broad targets with no extras), compatible-plan/replacement/contradiction multi-build checks, and the final
  three-build replay. Compatible plans created no proposal; actual changes retained pending supersedes/contradicts
  proposals. The cumulative replay retained all 18 claims as 12 facts, no proposals, passing retention and retrieval
  judgments. Two exact-singleton-text synthesis failures recovered; this remaining retry cost is documented rather
  than hidden. Final backend: 401 passed, 87 deselected in 4.77 s; targeted Ruff and `git diff --check` passed.

### 2026-09-09 — Static-audit remediation, validation in progress

User authorized implementing the audit fixes, configured-model probes, small fresh benchmarks, artifact inspection, and committing after validation. The preexisting working-tree patch was saved at `/tmp/mycelium-audit-fixes/preexisting.patch`; unrelated user notes/assets remain untouched.

- **Proved contracts before integration:** configured host `gemma4:12b`, production prompts/schema. Singleton synthesis first failed three times with only a nullable text field; explicit singleton/combined schema branches passed, including two independent future plans. The application now renders singleton canonical text. Evidence: `benchmark_runs/audit-fixes-20260909/direct-contracts/`, including failure dumps.
- **Sparse placement:** the first candidate passed small cases but omitted relationship endpoints in a larger registry. It was not integrated. The revised positive instruction establishes all described subjects before choosing an owner. All five probes passed (shared, incidental, project, personal plan, eight-entry registry), then the sparse schema/prompt was integrated. Full request budgets split complete claim batches rather than shrinking according to an unrelated-page matrix. Evidence: `benchmark_runs/audit-fixes-20260909/placement-contracts/`; first failed response also saved under `/tmp/mycelium-audit-fixes/sparse-placement-first-failure.json`.
- **Extraction:** the production prompt/schema resolved a new reply through a cited neighboring proposal, retaining cedar boards and next Saturday without treating the proposal as a new assertion. Evidence: `benchmark_runs/audit-fixes-20260909/adjacent-context/response.json`. Integrated complete-segment token batching, two adjacent context-only segments, and resume from persisted segment boundaries.
- **Retrieval:** pending proposal IDs/status/relations/incoming and target claim IDs accompany evidence. Matched canonical assertions accompany display summaries. Limits count distinct records while retaining multiple matched members. Exact-ID source retrieval and request-local fact/review snapshots avoid repeated artifact deserialization.
- **Index/storage:** incremental LanceDB merge/delete, bounded embedding batches, metadata-only vector reuse, unchanged-index revision checks; no unconditional table/FTS recreation. First native test caught the installed AsyncConnection's synchronous context-manager API; fixed and retested. Bounded JSON decoding cache returns deep copies, invalidates by file metadata, and excludes large payloads. Exact-ID/state lookup indexes reduce repeated deserialization; metadata scans remain. Pending commit recovery filters explicit prepared/applying states.
- **Budgets/diagnostics:** complete request envelopes, schema/tool definitions, and output reserve checked at the Ollama boundary, including retries/tool rounds. Durable inference traces record individual chat rounds without counting the aggregate again; response usage sums successful rounds. Embedding and meeting-summary timing paths added. These are conservative cl100k estimates, not a Gemma tokenizer proof; oversized truth/identity/synthesis scopes still need explicit bounded decision contracts.
- **Chat/Engram:** history fitting preserves complete contiguous turns; oversized current requests raise instead of silently truncating. Session GETs avoid metadata writes. Regression tests caught an accidentally removed create-session save and a conflation of input-budget vs model-window reserves; both fixed. Engram reuses original ASR text for timed speaker assignment, constructs transcribers off the event loop, and serializes meeting processing. Speech dependencies are absent in this Python environment, so no live ASR/diarization quality claim is made.
- **LoCoMo durability:** each completed question has an atomic fsynced checkpoint. Resume reuses exact question indices and validates dataset/settings/model/config fingerprints; run manifest marks completion. Interruption test verifies one saved answer survives a second-question failure and only the two remaining questions rerun.
- **Structural validation so far:** focused retrieval/synthesis/Engram/runtime: 64 passed; index/checkpoint/client: 68 passed; complete `pytest -q tests`: 407 passed, 87 opt-in skipped. Broad unscoped pytest discovery was stopped (only our test process) and replaced with explicit `tests/` discovery. No server was started or stopped.
- **Fresh benchmark underway:** `benchmark_runs/audit-fixes-20260909-locomo-small/`, sample 9 (`conv-49`), first two sessions, three QA questions, configured model, real source extraction and per-session consolidation. Session times: 146.7s and 166.2s. These short-prefix times are not evidence about session-25 scaling; final quality inspection and native cumulative replay follow before commit.

Validation follow-up:
- Fresh sample 9 completed two builds and all three QA questions. 114/114 segments have dispositions; all 24 active claims are represented in 14 facts, with no pending extraction, held review, unresolved provenance, or repeated fact memberships. All six synthesis attempts succeeded. Source-level coverage is not complete: for example, Sam's never having visited Jasper was marked source-only. The earlier overnight prefix had 27 extracted claims (12+15), versus 24 (13+11) here; this is not a paired extraction experiment and does not establish a coverage improvement. Wiki prose retains some vague/redundant hobby-update statements. These limits must accompany any speed claim.
- The neutral public three-build/restart/retrieval replay passed in 152.89s at `benchmark_runs/audit-fixes-20260909/cumulative-replay/`. Both retained-detail and bicycle retrieval semantic judgments passed. Prior integrated replay was 174.80s; one replay per version is insufficient to isolate timing variance.
- Native retrieval plus the production assistant prompt kept the Lisbon move unresolved rather than treating it as accepted. Evidence and answer: `benchmark_runs/audit-fixes-20260909/native-review/`.
- A bounded search-query contract was probed before integration: reference resolution retained choir rehearsal, while the counterexample switched to bicycle location. The first 2000-character schema was rejected by the host's grammar compiler; the compact 500-character schema passed. Preserved outputs: `benchmark_runs/audit-fixes-20260909/query-contract/`. Long queries now receive a model-formulated embedding query while original requests remain available to evidence admission. Deterministic HTTP 4xx errors (except timeout/rate limiting) are no longer retried.
- Admission now budgets whole candidate records instead of prefix-truncating each at 1200 tokens. Over-budget sets split losslessly; all decisions retain exact candidate IDs. Chat retrieval gets bounded coherent history from preflight; oversized requests fail explicitly before retrieval, and initial prompts render the current request once.
- Expanded same-source extraction context from two neighboring sentences to a bounded contiguous prefix, prioritizing recent source context over older sources. The quarter-window bound and whole-segment rule remain. This addresses referents farther back than two sentence segments without unbounded accumulation.
- A second fresh LoCoMo sample (sample 1, one session/one QA) is in progress at `benchmark_runs/audit-fixes-20260909-locomo-second/` to check the final integration on different source material.

Final checks before commit:
- Second sample completed in 134.5s, with 13 claims and eight facts across Caroline/Melanie pages; all 51 segments accounted for, and the support-group date answer matched May 7, 2023. Inspected the source and both page bodies.
- Final native long-query retrieval formulated “Mira's residence location and status of her move” and retained pending-review evidence. Real meeting summary preserved the room-twelve decision, Mira's Friday notes action, and unresolved projector availability. Evidence: `benchmark_runs/audit-fixes-20260909/final-native/`.
- Final backend suite: **414 passed, 87 skipped in 5.22s**. Ruff passed; `git diff --check` passed. Opt-in skipped tests are not claimed as executed; configured-model runs are listed separately above.
- Detailed quality findings, timing limitations, and larger unresolved audit items are documented in `planning/audit_fixes_2026_09_09.md`. In particular, broad identity/history review, multi-call truth/synthesis budgets, projection duplication, and session/UI storage redesign remain open.
- Final staged review found the single-member synthesis schema still advertised an impossible combined-group array bound (min=2, max=1). A staged singleton-only schema passed a configured-model probe before integration; scope/membership were correct, though its explanatory reason was uninformative. Evidence: `benchmark_runs/audit-fixes-20260909/single-member/`. Added general feasible-array-bound checks for one, two, and five claims. Candidate selection now uses the same complete-request estimator as the LLM boundary. Final rerun: **417 passed, 87 skipped in 5.13s**, Ruff and whitespace checks passed.


## 2026-09-09 — Reasoning on/off experiment

- User authorized real-model reasoning controls, sufficient output budgets, and longer computation when it improves quality. Experiment-only harness: `benchmarks/reasoning_comparison.py`; no production defaults changed.
- Confirmed Ollama Python SDK 0.6.2 uses `AsyncClient.chat`, serializing `think` at the top level of `/api/chat`. Host 0.32.15 advertises thinking support for configured `gemma4:12b`. Captured SDK serialization and actual host responses under `benchmark_runs/reasoning-comparison-20260909/`.
- Production extraction prompt/schema, contextual acceptance: temperature 0/off returned correct JSON in 10.9s; on exhausted 16384 tokens on all three production retries (617.1s total) with empty final content. Enlarging context to 49152 and output to 32768 still exhausted output (416.0s). Temperature 0.2 also looped on both acceptance and refusal. Failures preserved, not treated as evidence about recommended sampling.
- Google recommends temperature 1.0, top-p 0.95, top-k 64. Our structured client overrides temperature to 0; top-p/top-k match model defaults. With all recommended settings explicit and otherwise identical payloads, reasoning-on succeeded on acceptance/refusal in 30.4s/34.0s, with approximately 2112/2293 cl100k thinking tokens and no length stops. Refusal output coherently retained the decision, later possibility, and both evidence citations. Off split the assertion, omitted contextual provenance on the refusal, and labeled the future possibility atemporal/preference. This isolates a real sampling sensitivity at one seed, not general model quality.
- Native successful thinking-plus-schema usage counters appear to describe the final generation phase rather than all returned reasoning. Preserve raw counters but use wall time and separate estimated thinking/content lengths; do not claim native eval_count is total compute.
- Exact schema currently travels in `format`, absent from message text. Ollama recommends both. This remains an untested potential improvement; the temperature-1 controls already succeeded without modifying prompts.
- Paired fresh-store neutral cumulative and short LoCoMo builds launched at recommended sampling, 32768 context/16384 output, 900-second request timeout, same inputs and fixed seed. Results pending. Detailed report: `planning/reasoning_comparison_2026_09_09.md`.


Reasoning experiment follow-up:
- Completed neutral cumulative pair at recommended settings: off 149.3s/25 attempts/14 facts; on 897.7s/27 attempts/11 facts. Both retained all supplied details and represented 18 active claims. On consolidated related facts and repeated preferences more cleanly; it added unsupported “just” to tenure and had mixed section placement. Two contract corrections recovered omitted segments/group members. No output-limit stops. This establishes a limited consolidation benefit at roughly six times the runtime.
- Natural-dialogue first-batch extraction on returned one claim and relegated other durable assertions to source-only despite recognizing them during reasoning. The later batch added three generic social assertions. Interrupted only our comparison client deliberately, preserving the incomplete store; host Ollama was not stopped. Remaining LoCoMo arms were not run. Explicit interruption record is in the pipeline artifact root.
- Exact schema-in-prompt grounding was proved structurally on neutral probes, but was not uniformly better: acceptance 18.2s, refusal 104.1s with weaker grouping and incorrect semantic `about.role=user`. No integration. Exact natural-dialogue grounded replay still returned only one claim. Off controls returned 10/9 claims but each missed a required segment and incorrectly upgraded a repair/sale decision to completed action.
- Final diagnostic removed only native `format` from the grounded reasoning-on SDK request, retaining the same prompt/schema, seed, recommended sampling and Pydantic validation. Request-key comparison confirmed that single change. It returned nine claims and passed validation in 192.6s, with 14858 native generated tokens under the 16384 allowance and 8806 native prompt tokens. Coverage recovered substantially, but the repair/sale temporal error remained. This implicates the constrained-output path in this reproduction without proving a specific server bug or establishing a production workaround.
- Full findings and paths: `planning/reasoning_comparison_2026_09_09.md`; `benchmark_runs/reasoning-comparison-20260909/`. Production code/config unchanged, no commit. Ruff and whitespace checks passed. Further integration requires fixing configurable sampling/thinking/output reserves and investigating constrained generation, then revalidating real artifact quality.


## 2026-09-09 — Selective Gemma 4 reasoning and validated output contracts

- Researched official Google Gemma 4 sampling/thinking guidance, Ollama structured-output and thinking docs, and matching public Ollama 0.32.15 routes/renderer source. SDK `AsyncClient.chat` is the production transport; `think` is top-level. Our Pydantic list syntax matches the documented API. The rendered server route restarts generation at the reasoning/final boundary when format is supplied; the Gemma turn rendering makes this a plausible explanation for prior context-dependent coverage loss, not a confirmed host bug. Links and full analysis: `planning/gemma_reasoning_policy_2026_09_09.md`.
- Proved neutral list, extraction, truth-change/distinct-object and synthesis contracts with real configured host model before enabling reasoning in production decision calls. Harness: `benchmarks/reasoning_contract_probes.py`; preserved raw requests/responses and separate production-parser validations: `benchmark_runs/reasoning-policy-20260909/probes/`. Six-item arrays and six-claim extraction succeeded in both format modes. Truth change needed one nesting correction; distinct-object and synthesis passed directly and had the intended meaning. Initial probe-only fence failures disappeared when using the actual production parser; raw evidence was retained. Extraction's permissive about.role still permits semantically questionable values.
- Enabled reasoning for fact truth review and cumulative synthesis; QA/tool chat also honors the configured policy. Other structured steps remain native-format without reasoning. Selected reasoning calls use schema-in-prompt, one generation without native format, required Pydantic validation and bounded corrections. Native format is an explicit configuration alternative, not an automatic failure path. No lexical semantic rules added.
- Applied temperature 1.0/top-p .95/top-k 64 consistently, removed structured/benchmark hardcoded temperature zero, configured 64K context/32K generation/900-second request timeout, and updated retrieval preflight reserves. Token-limit responses fail closed instead of accepting partial JSON or spending three unchanged retries. Trace/debug artifacts expose effective reasoning, output mode and allowances.
- Validation: focused contracts/config/client checks 71 passed; full suite 427 passed, 87 opt-in skipped; final runtime check 8 passed. Initial sandboxed suite stalled in index tests; stopped only the owned test client and reran with host filesystem access. One stale runtime stub then failed for missing new config fields and was updated; production gained no compatibility fallback. Ruff and git diff whitespace checks passed.
- Fresh integrated LoCoMo run completed at `benchmark_runs/reasoning-policy-20260909-locomo/`: one session of sample index 1, two questions, 346.2s, 13 claims/8 facts/two person pages. Manual source/wiki review found sensible grouping and retained core details. QA 1/2: support-group date correct, painting date remained relative (last year instead of 2022). One recovered correction each in extraction, synthesis and retrieval selection; no token-limit stops. This does not prove broad improvement.
- Diagnostic caveat: a raw HTTP debug-render request accidentally used `debug_render_only` instead of the source-defined `_debug_render_only`, then timed out after 30 seconds during LoCoMo. It is not evidence of server failure or a verified rendered prompt, and it may have affected runtime. Raw HTTP was diagnostic only; production and semantic probes use the SDK. No server was started/stopped.
- Cumulative real-model regression is being run separately, serially after LoCoMo, at `benchmark_runs/reasoning-policy-20260909/cumulative/`. No commit made.

Cumulative reasoning validation completed: real-model test passed in 730.78s, artifacts at `benchmark_runs/reasoning-policy-20260909/cumulative/test_cumulative_memory_keeps_i0/`. Eighteen claims retained in twelve facts; bicycle retrieval and semantic checks passed. Twenty-nine attempts, one recovered singleton-text contract error, zero token-limit stops, max native generation 7,466. Truth review 266.1s and synthesis 369.4s dominate. Recurring volunteering remains under plans. No commit.


## 2026-09-09 — Prompt/schema audit and Gemma 12B versus Qwen 9B

- Audited production prompt families, schema generators and field consumers. Measured actual dereferenced output container depth and schema size: extraction 14 fields/5 levels, one-incoming truth 5 levels, small identity registry 9,162 schema characters from five repeated 11-field branches. Findings/priorities: `planning/prompt_schema_model_audit_2026_09_09.md`; measurements: `benchmark_runs/model-contract-comparison-20260909/schema-audit.json`. Recommended flatter single-decision truth output, clearer schema-versus-instance boundary, explicit temporal/identity-role contracts and fewer duplicated explanations. No production prompt/schema rewrite during this audit.
- Verified installed host models using escalated read-only tags: gemma4:12b and qwen3.5:9b both Q4_K_M. Researched publisher recommendations and used each model's general-task sampling in an isolated benchmark transport. Kept the same production contracts, selective reasoning mode, 64K context, 32K reasoning generation and seed 17. Host Ollama/SDK unchanged, no downloads/server starts/stops.
- New harness `benchmarks/model_contract_comparison.py`; all requests/responses, corrections, timings and stores preserved under `benchmark_runs/model-contract-comparison-20260909/`. Four direct contracts per model followed by three nine-statement cumulative builds/restarts/retrieval. Gemma direct timings 9.5/32.1/25.6/19.6s, Qwen 6.7/39.7/39.1/35.3s. Both had correct final truth/synthesis decisions; Qwen's extraction metadata was weaker. Gemma truth-change needed a target-nesting correction (initial commentary incorrectly said all were first-attempt successes; corrected after raw attempt inspection).
- Cumulative: Gemma270.7s versus Qwen275.2s, both nine claims/five facts, exact nine-member coverage and correct bicycle retrieval. Manual coverage/correctness/concision/organization review found equivalent substantive outcomes. Gemma one recovered singleton-text failure; Qwen two recovered failures on one truth decision (schema echo, then missing scope). No output-limit stops. Qwen decoded about115tok/s versus82, but generated30,346 versus20,488 tokens, eliminating the throughput advantage.
- Additional direct real-dialogue extraction: same first48segments of conv-26/session1, production renderer/schema, no reasoning/native format. Gemma82.8s/11claims; Qwen84.4s/21claims, each two attempts. Both recovered missing-segment accounting. Qwen included more descriptive/research details but omitted workload, strengthened assertions, miscited a painting assertion and emitted redundant photo-association facts. Gemma also misses some details and has an overextended relaxation citation; both leave temporal facets empty. More claims did not establish better quality.
- Recommendation: retain Gemma default while proving prompt/contract simplifications; Qwen is competitive on the tiny neutral workload but has no demonstrated pipeline speed benefit and weaker natural-dialogue correctness here. Single-seed evidence is not a general model ranking. Ruff and whitespace checks passed; all requested comparison arms completed. No commit or production-model switch.

## 2026-09-09 — Compact Gemma contracts

- Retained Gemma and simplified extraction, identity, routing, truth, synthesis and retrieval-admission outputs. Removed unused generated confidence and duplicated known metadata; kept evidence IDs, explicit decisions, review blockers and exact accounting. Existing-identity renames retain one nullable title field after a structural test exposed that removing it would lose a supported feature. See `planning/contract_simplification_2026_09_09.md` for field counts and scope.
- Proved contracts before integration using host Gemma and saved actual requests/responses under `benchmark_runs/contract-simplification-20260909/`. Truth/synthesis, namesakes/ambiguous identities, project/coordinator separation, user binding, personal versus joint page placement, deferral, rename/retain and retrieval include/exclude counterexamples were inspected. Early extraction revisions were rejected for missing acceptance/refusal context, misclassified entity roles or conflating schedules with deadlines. Final v5 uses typed details and reasoning when prior context is supplied; independent extraction remains native-format without reasoning. Natural-dialogue extraction retains the main information but still omits minor details and groups several independently useful assertions.
- Grounded every structured request with its JSON Schema and an explicit schema-versus-result instruction. Preflight and actual request budgeting now count the same grounded schema once. Kept native constraints on non-reasoning calls and the previously proven prompt-structured reasoning mode. Batching now reserves the configured reasoning output allowance for context-dependent extraction.
- Fixed required-null preservation in the structured parser and persisted extraction results. Added/updated structural checks for serializer/retry validity, cited time anchors, exact identity and page IDs, renaming, truth scope, canonical singleton text, complete synthesis membership, context-triggered reasoning and matching preflight budgets. Model confidence is no longer regenerated; existing artifact metadata remains source/member-derived or the extraction default.
- Final test directory: 429 passed, 87 opt-in integration tests skipped (`/tmp/compact-tests-final3.log`). Direct host probes are separate from skipped integration tests. A broad root-discovery run and a duplicate sandboxed test run stalled; ended only those agent-started duplicate validations and reran the explicit test directory with host access. No server was started/stopped. Ruff and whitespace checks are recorded with the final artifact review below.
- The integrated cumulative test exposed one long truth response (188.6s, 14,983 generated tokens) with an empty required comparison list on compatible evidence. Validation rejected it and the correction succeeded in 32.6s. Preserved both attempts in `cumulative/requests/0009.json` and `0010.json`; reduced schema size does not guarantee bounded reasoning time or first-attempt compliance.
- Full cumulative artifact inspection found a semantic regression beyond the recovered schema error: the initial compact truth prompt treated a more detailed compatible job statement as `supersedes`. The incoming claim remained safely in pending review, but only eight of nine claims appeared in the wiki. Preserved the initial 532.7s run and separate `coverage-audit.json`; added represented/missing member counts to the neutral cumulative harness.
- Proved a concise truth-prompt revision against both actual problematic request bodies and an explicit repainting counterexample (`truth-clarity-v7/probes/`). It explicitly separates the complete comparisons list from review targets and defines supersession as an ended/replaced condition or decision. Compatible detail and the more specific preference returned `no_change`; repainting returned `supersedes`. Integrated only after those direct calls passed. No extra output fields or semantic overrides were needed. A fresh cumulative rerun follows, rather than changing the initial run's pending review artifacts.
- Corrected cumulative rerun: `benchmark_runs/contract-simplification-20260909/cumulative-final/`, 327.8s, nine claims/five facts, all nine claim members represented, no pending truth proposals, correct bicycle retrieval, no output-limit stops. Compatible tenure is retained and the undecided plan remains qualified. A possession detail was deferred in build two and admitted in build three; this was visible in the intermediate artifact audit even though the final coverage check passed.
- Proved and integrated one ordinary-language routing clarification for explicitly owned objects (`routing-clarity-v8/`): the actual prior request routes its owned attribute to You; a listener receives no other person's possession, and an unrelated object is deferred. A production `ClaimRouter` replay in a fresh isolated store retained all three statements but proposed an artifact identity/destination for the owned object. Its stricter all-owners-must-be-You assertion failed. `routing-in-situ/artifact-audit.json` records the manual review and context difference (no prior profile facts); this is allowed by the artifact ontology but shows remaining organization variability. Did not override the model or add a benchmark-specific rule.
- LoCoMo: `benchmark_runs/contract-simplification-20260909-locomo/`, conv-26, one session/two QA questions. Completed in273.0s; encoding/consolidation251.1s. Eleven claims all represented across eight facts on two correct person pages; one recovered synthesis validation failure and no output-limit stops. QA1/2: support-group date correct, painting answer retained “last year” instead of resolving to2022. Calendar-year normalization/QA specificity and minor extraction omissions remain. Raw predictions, stage timings, wiki and `artifact-audit.json` preserved. This small sample does not establish long-span recall or a general speed improvement.
- Final code validation after the last prompt integration:429passed/87skipped (`/tmp/compact-tests-complete.log`), Ruff and `git diff --check` clean. Final ownership wording received direct and in-situ router validation; the complete cumulative run was not repeated for that final one-sentence clarification. No commits, model switches, server changes or semantic fallback paths.

## 2026-09-10 — Selective wiki and recoverable memory lifecycle

- Implemented the user's evidence/briefing split and publish-with-uncertainty policy. Placement/synthesis now declare briefing/detail prominence; UI and Markdown expand supporting detail while retrieval retains it. Uncertain identities receive separate tentative identities, pending truth accounts remain visible, and placement/identity/retraction qualifications survive materialization and retrieval. Partial extraction no longer marks a source complete just because some claims publish. Identity-plan reuse now validates the actual request digest against registry/evidence/prompt/schema/model changes.
- Unified visible corrections around canonical statements, reassessed correction metadata/subjects/ownership, removed independent fact-text editing and stale metadata defaults in the inspector. Corrections, retractions and truth review use staged snapshots plus durable idempotent publication journals. API curation and builds share a reentrant lock; capture remains independent. Corrections/retractions invalidate obsolete pending proposals and reconsider surviving incoming evidence. Restart recovery runs before store use; full clear also removes operation journals. Replaced destructive Clear Wiki with Rebuild Wiki Views, retaining evidence and curation.
- Preserved dates in displayed claim text, removed prose-based temporal inference, and normalized fully specified calendar dates from declared metadata. Historical claims and revision links remain retrievable; source inspection carries interpretation state within its token budget. Retraction keeps mixed-supported evidence visibly uncertain instead of assuming each source independently sufficient.
- Direct host Gemma probes preceded semantic integration. Rejected early placement/synthesis contracts that omitted project-role endpoints or combined conflicting accounts (`lifecycle-design-contracts-20260911T000946Z-a44fd98a`); v2 passed the same neutral cases (`...001032Z-27767a0d`). Initial correction relative-time anchoring failed (`...001513Z-9cf42a0a`); revised contract passed date/subject/timeless/relative cases (`...001700Z-a0073947`). v3 prominence probes retained commitments/preferences but still rated an incidental cup briefing. Extraction v1 mixed dates across claims (`...003238Z-268d2622`); revised facet-locality instructions separated them (`...003805Z-111349e1`). Some about/predicate omissions remain; no lexical overrides added.
- First integrated three-session replay: `benchmark_runs/lifecycle-design-replay-20260911T002712Z-60bc888b`, 152.5 seconds, no pipeline failures. Manual review found a hidden draft commitment, prominent generic sentiments, technical wording and unsupported pronouns. Final fresh replay: `benchmark_runs/lifecycle-design-replay-20260911T003925Z-68f0545b`, 180.5 seconds across three sessions, 18 claims/15 facts, all 18 represented on four pages, no reported build failures. Commitments and written-feedback preference remain prominent; general sentiments expand as detail. Two native retrieval calls preserved alternative deadlines and the draft prerequisite. Saved artifact-audit.json records remaining awkward deadline synthesis and variable page admission/secondary placement. This small neutral replay is not a full LoCoMo run or long-span quality/speed proof. Reasoning was disabled only in isolated probe configs; production configuration unchanged.
- Initial in-situ date correction (`benchmark_runs/lifecycle-correction-replay-20260911T004255Z-a7895ce9`) exposed an inappropriate project_role predicate and unresolved explicit date. Predicate clarification passed direct date/subject/relative counterexamples (`benchmark_runs/lifecycle-design-contracts-20260911T004408Z-4116447b`); calendar parsing gained a focused structural test. Final date correction (`benchmark_runs/lifecycle-correction-replay-20260911T004534Z-07075a95`) completed in15.3s, predicate null, deadline2026-10-16, correct project page, retrievable superseded account and identical retry receipt. Final subject correction (`benchmark_runs/lifecycle-correction-replay-20260911T004608Z-d102a7cd`) completed in18.1s, moved ownership from Nora to Lee, updated both people and project pages, preserved current/historical retrieval and idempotent retry. Subject metadata still omitted the project in about, although identity/page planning correctly recovered it from the supplied statement.
- Validation: full tests440passed/87skipped (`/tmp/lifecycle-design/final-host-tests-v3.log`), Ruff and whitespace checks clean, UI production build passes with its existing bundle-size warning. Tests cover stage isolation, interrupted publication recovery, capture preservation, revision conflicts, retry idempotence, stale review invalidation, uncertain supporting detail, historical source inspection, complete-date metadata, partial completion and changed identity context. Early staged-service mocks were too high-level and accidentally reached an unavailable test-default model; fixed fixtures to mock the shared LLM stage interface. Sandbox-only test runs stalled on local networking; stopped only those agent-started duplicate test commands and completed the explicit test directory with host access. No model/server fallback or server lifecycle changes.
- Remaining scope is explicit in `planning/memory_lifecycle_implementation_2026_09_10.md`: automatic supported truth transitions, within-batch/cross-owner comparisons, broad registry/context scaling, cross-subject identity uniqueness, all entity/group mutation crash guarantees, multi-process writer coordination and vague/multiple temporal intervals. Lifecycle snapshots scan the store; this is a correctness repair, not a scaling optimization. No commit.

## 2026-09-10 — Session snapshots in ordinary LoCoMo mode

- Added `--snapshot-sessions` and wrapper `SNAPSHOT_SESSIONS=1`. Ordinary progress reporting and QA continue; each completed memorize step copies the store to `snapshots/<sample-id>/session_N/`. Snapshots reflect the configured build policy. Mycelium-backed systems are required; frozen-store QA replay is rejected for this option.
- Copies publish through a temporary sibling directory and rename. Resume preserves earlier snapshots rather than overwriting them with later store state. Snapshot-enabled runs record the option in their settings; ordinary runs retain their existing manifest settings shape. Enabling snapshots on an existing ordinary run requires a fresh run ID.
- Validation:29 benchmark tests passed, including cumulative source counts, QA continuation/resume, immutable earlier snapshots, unsupported systems and interrupted-copy recovery. CLI help, shell syntax, Ruff and whitespace checks passed. No semantic contracts or model settings changed, no model calls needed, and the user's ongoing benchmark was not modified. No commit.

## 2026-09-10 — Reduce repetitive extraction accounting and consolidation calls

- Kept semantic judgment with Gemma while removing per-segment no-claim explanations: extraction returns an explicit null for those segments and the application creates the audit disposition. Every input segment still requires an explicit output decision; missing output is never interpreted as no useful information. Claims, citations, timing, ownership and qualifications remain model-selected.
- Increased owner addition groups from4 to12. Candidate selection shares history across those groups, and truth comparison now decides several incoming claims in one request with explicit candidate targets per claim. Preserved complete scope comparisons, evidence-based explanations, exact target validation and the existing one-review-per-older-target invariant. Request-budget overflow splits complete decisions without discarding evidence; empty target sets still skip inference.
- Direct native Gemma4:12b probes before integration: `benchmark_runs/encoding-efficiency-contracts-20260911T014344Z-1e308af2` and `...014433Z-05bca6c0` tested explicit no-claim accounting and batched compatible/different-subject/explicit-replacement decisions. Truth passed; extraction preserved acceptance/conditions but still missed a supporting citation/time anchor. An extra attempted citation clarification did not fix that and was not integrated. `...014635Z-34e4c72a` tested12-member production synthesis with exact membership and prominent commitments/prerequisites/preferences; pronoun and prominence variability remain. No fixture vocabulary or lexical semantic rules entered product code.
- Fresh source replay: `benchmark_runs/encoding-efficiency-session2-v1`, sample3 sessions1–2 with snapshots, QA disabled. Session2 took421.1s versus the user's roughly463s; calls61→25, extraction claims39→46. Across both sessions all60 extracted claims are represented in32 facts, with no build failures or failed inference attempts. Concrete original details survived, but added sentiments and varying groupings mean this is not a controlled claim-count quality comparison. The end-to-end improvement is modest because generation still dominates.
- Fixed-data replay reconstructed the original first-session facts and the exact original39 incoming claims/placements from saved build payloads. Initial run `benchmark_runs/encoding-efficiency-matched-facts-20260911T015739Z-44926820`:158.3s,17 attempts, one recovered synthesis validation error, all51 claims represented. It incorrectly proposed taekwondo superseding kickboxing. Debug dumping was disabled for that run, so the exact recovered synthesis error is unavailable. The first harness setup failed before inference because it saved placements before claims; fixed the probe loading order, not production code.
- Proved a general coexistence clarification against a neutral activity pair, explicit stopped/replaced activity, and the observed false-positive pair (`benchmark_runs/encoding-efficiency-contracts-20260911T020342Z-a31f5299`). Results: no_change / supersedes / no_change. Integrated only after these passed.
- Final fixed-data run `benchmark_runs/encoding-efficiency-matched-facts-20260911T020420Z-32016093`:143.1s resolver time,16 calls, no failed attempts or pending truth proposals; all51 claims represented in24 facts (original28). Original fact stages used53 calls and249.2s model time. Final stages: selection6calls/36.7s, truth5/61.7s, synthesis5/41.4s; total139.8s inference plus resolver overhead. Approximately43% lower consolidation time, with the original evidence held fixed. Three real retrieval checks preserved movies/hiking, old-car donation/shelter, and taekwondo, with no erroneous replacement annotation. Inputs, outputs, coverage, timing and artifact-audit.json are retained.
- Validation:444passed/87skipped (`/tmp/encoding-efficiency/tests-final.log`), Ruff and whitespace clean. Updated tests cover null accounting, exact citations, complete claim/fact pair coverage under budget, every batched truth decision and rejection of competing or distinct-scope changes. Final source encoding was not repeated after the coexistence clarification; that final prompt received direct and fixed-data in-situ validation. No full LoCoMo QA score or general latency guarantee. See `planning/encoding_efficiency_2026_09_10.md` for the comparison and remaining semantic limitations.
- Preserved the user's reasoning-off configuration and earlier uncommitted snapshot option. No server changes or commit.

## 2026-09-10 — Use the Python CLI for selected LoCoMo runs

- Removed `scripts/benchmark-locomo.sh`; updated active benchmark instructions to use module arguments for sample selection, snapshots, replay and diagnostic limits. The module already generates timestamped run IDs; documented that default in argparse help and retained `--run-id` for explicit names. Examples explicitly select the configuration and Gemma model and explain that omitting the sample index selects all samples.
- Validation: module `locomo --help` succeeds, Ruff and `git diff --check` pass, and no references to the removed wrapper remain outside historical DEVLOG entries. No inference behavior changed or model calls needed. Other full-suite runners remain in place. No commit.

## 2026-09-11 — Consolidate benchmark packages and commands

- Replaced the old benchmark package entrypoints with `python -m benchmarks` (`locomo`, `mab`, and `daily-driver validate|run|compare`). Moved suite implementations into `benchmarks/suites`, adapters/scoring into `shared`, and all three custom scenarios beneath the daily-driver suite. Separated fixture loading from command dispatch. Daily-driver new runs now accept output-root/run-id with timestamp defaults; comparisons retain explicit output-dir. Preserved evaluator behavior, snapshot/replay options, fresh-directory checks, and existing results.
- Organized model probes under `experiments` and the dated reasoning investigation under `experiments/historical`; updated imports without changing model contracts. Removed remaining full-run shell wrappers, retaining their curated MAB configuration list in documentation. No compatibility entrypoints or batch orchestration added.
- Replaced the benchmark README with the central setup/run/artifact guide and updated active repository, design, iteration, and scenario commands. Historical logs and generated run paths remain unchanged.
- Validation:59 focused CLI/benchmark/scoring/fixture tests passed; all three scenarios validated through the new CLI. All experiment modules imported without inference. Relocated scenario/gold/wiki files were checked byte-for-byte against HEAD. Ruff, whitespace, and active obsolete-reference checks passed. An initial new comparison-dispatch test supplied the wrong mock return nesting; corrected the test to match the existing evaluator contract, with no production workaround. No model calls or server changes were needed for this structural refactor. Existing uncommitted encoding/snapshot changes and user configuration preserved; no commit.

## 2026-09-11 — Repair audit recovery changes before commit

- Removed the uncommitted terminal Dream `failed` state. Interrupted application/recovery remains `applying` with its recorded error, so later builds must finish that journal before proceeding. Entity merges retain their consistency guard and become available after successful recovery.
- Validate saved record constructors, audit/cohort structure, and ID lists before applying artifact writes. Invalid journals remain visible and block progress until explicitly repaired; no automatic discard or semantic fallback. Tests verify that an invalid later placement cannot publish an earlier entity change, repeated recovery continues to expose the problem, and correcting the journal permits recovery and an entity merge.
- Extended the interrupted-commit test with another transient failure during recovery, followed by successful idempotent completion with stable page versions and one fact/audit. Repaired the benchmark guide link after the user's protocol move and removed trailing blank lines in the audit tests. Preserved the other audit fixes for model defaults, multi-turn session capture, newlines, and index cleanup.
- Validation:15 focused core/recovery/runtime tests plus75 Dream/entity/lifecycle tests passed with host access; Ruff and `git diff HEAD --check` passed. No model calls, server changes, or commit.

## 2026-09-11 — Canonical SQLite storage and confirmed audit fixes

- Implemented fresh-store-only canonical `memory.sqlite3` with validated artifact records, indexed exact-field lookups, database-enforced entity-slug uniqueness, WAL, transactional revisions/change IDs, and OS-backed process ownership. Domain repository methods remain; artifact directory scans and JSON-file mutation APIs are removed. The shared library handle supports explicit close/context management; server lifespan releases it. `MYCELIUM_STORE` selects a fresh server store. Legacy JSON stores are rejected without converting their contents; historical benchmark runs remain untouched.
- Raw logs and chat records now live in SQLite. Session summaries are separate from individual message payloads, so listing/renaming does not read or rewrite all transcripts. Capture cursors, message metadata, and append operations persist transactionally. Preserved original within-day raw-log order with an explicit log sequence. Ingestion errors roll back source/log/operation writes rather than leaving incomplete canonical evidence.
- Replaced whole-directory lifecycle staging with a consistent SQLite read snapshot and isolated write set; publication checks consulted record/collection revisions and commits receipts atomically. Unrelated capture remains preserved. Synchronous entity/fact/identity curation is transactional. Dream application atomically commits records, log completion, audits, and projection intent. Failed plans are safely marked failed only after canonical rollback; actual process interruptions retain a replayable plan. Entity merges block only genuinely pending canonical application, not failed rolled-back plans.
- Markdown wiki/log content remains inspectable and is published through a durable ordered queue with atomic file replacement. Failed publication keeps canonical state intact and can retry without inference or duplicate page versions. Build status includes publication state; the inspector exposes errors and retry. Rebuild and clear use canonical transactions. Database/index synchronization is still intentionally separate and derived; this does not claim a cross-database/filesystem atomic transaction.
- Claim-index synchronization now uses collection revisions plus changed IDs and owner-affected claims; unchanged searches do not scan artifacts. Incremental lookups and deletion filters are bounded to500 IDs, and successful synchronization alone advances the checkpoint. No retrieval ranking, semantic admission, prompt, or reasoning-setting changes.
- Removed the retired maturity-assessment model, storage methods, commit fields, API routes, inspector requests/displays, and obsolete work-unit fields. Retained navigation edges with the supported informs relation. Removed the unused JSON persistence helper.
- Benchmarks use SQLite backup for ordinary snapshots, wiki-baseline snapshots, frozen stores, and new complete daily-driver checkpoint stores. Snapshots reconstruct Markdown from backed-up canonical state, excluding ownership locks and rebuildable indexes. Extraction replay reads repositories. Added explicit read-only JSONL export (`python -m mycelium.snapshots STORE EXPORT_DIR`). Updated active storage/run documentation; historical experiments remain explicitly historical.
- Structural validation:466passed/87skipped (`/tmp/sqlite-acceptance-tests.log`), Ruff and whitespace checks pass; UI production build passes with the existing bundle-size warning (`/tmp/sqlite-ui-final.log`). Tests cover competing writer processes and crash release, rollback/uniqueness, consulted-collection conflicts, concurrent capture, publication interruption/retry, WAL snapshots, independent session listing, exact indexed entity uniqueness, and50,000-record unchanged-search/no-filesystem-scan plus500-ID batching. Intermediate failures were stale file-path/session test assumptions and an accidentally removed public export during code cleanup; repaired exports and updated tests to assert the new storage/atomicity contracts. No compatibility backend added.
- Real host Gemma4:12b validation, reasoning off: `benchmark_runs/sqlite-matched-facts-20260911T104831Z-a6dbfc63` reused the same archived first-two-session extraction/placement inputs as the earlier controlled comparison, loaded explicitly as evaluation data into a fresh SQLite store (not a runtime migration). Resolver162.5s,16calls/153.8s model time, no failed attempts, all51 claims represented in28 facts, zero missing cited segment references, zero truth proposals. Compared with the previous143.1s fixed-data run, this is continuity evidence, not an end-to-end latency improvement. Three native retrieval checks preserved friends' movies/hiking/game nights, old-car donation/shelter, and planned taekwondo. Synthesis still varies and the family-creativity grouping remains awkward; no full QA score or general quality improvement is claimed. Result, coverage, retrievals, snapshot, and artifact-audit.json retained in the run.
- Fresh raw-input smoke benchmark `benchmark_runs/sqlite-tiny-encoding-v1`: one tiny LoCoMo fixture session, QA disabled,11.3s; one source/claim/fact, completed Dream, session snapshot, and zero pending publication. This exercises actual extraction through atomic publication, separately from the fixed-extraction replay. Explicit JSONL export of the snapshot also succeeded. Temporary harnesses/logs are under `/tmp/sqlite-validation/`; no server lifecycle changes or commit. Unrelated untracked user files preserved.

## 2026-09-15 — Audit remediation, structural and retrieval tranche

- Implemented explicit configuration precedence and strict budget/sampling validation; requested missing TOML files fail. Snapshot admission validates consulted canonical state after inference, reselects once on concurrent mutation, and reports typed retrieval failures. Rendering drops retracted claims and uses current membership/tier; indexed lookups replace full fact/source scans. Workspace merges canonical evidence by revision, refreshes state between tools and fits whole records against the rendered workspace budget.
- Benchmark execution, encoding and QA status are separate; incomplete encoding blocks QA unless explicitly marked diagnostic. Durable invocation start/end records preserve failed/resumed elapsed work, with interrupted durations explicitly unknown. Manifests retain effective config and Git patch, typed context coverage replaces label matching, and traced structured failures retain diagnostic dumps. Model digests, logical operation linkage, semantic scoring and full wiki coverage remain unfinished.
- Same-origin UI API/audio and Vite proxy, explicit host allowlist, origin checks, loopback backend default and optional built UI serving. Private Wi-Fi/Tailscale setup documented without adding login. Chat reply generations and wiki fetch cancellation reject obsolete responses; failed chat input is retained. Engram uploads copy bounded chunks and remove partial artifacts on rejection; diarization failure remains visible and speaker detection can retry without transcription.
- Before integration, direct configured host Gemma4:12b probes tested complementary evidence selection and absent-answer counterexamples, three trials each. Initial prompt failed all three counterexamples (`benchmark_runs/remediation-selection-probes-20260915T152626`); revised prompt passed (`...152753`), then exact production schema passed 6/6 (`...152926`). Integrated only the proved selector contract. Production selection returns ordered exact IDs and explicit supported aspects/gaps, with a 1024-token output allowance. No lexical semantic fallback or benchmark terms entered production prompts.
- In-situ retrieval validation: `benchmark_runs/remediation-retrieval-replay-20260915T154449` uses a read-only backup/copy of `overnight-sample3-v1/stores/conv-41`. Question28's education/infrastructure evidence appears in all three trials, 2.80/2.46/1.92s. Baseline retrieval construction was11.87s, but this is one warm case, not a controlled full QA/cost comparison. No updated QA score or encoding-quality improvement claimed. Initial replay preserved one successful result before a harness print-field error; fixed harness and reran fresh. Baseline artifacts untouched.
- Scope and unfulfilled gates are explicit in `planning/audit_implementation_2026_09_15.md`. Temporal schema, identity/page admission, truth scope, incremental consolidation, ANN, full daily-driver/sample3/sample9 validation and component tests remain outstanding. No server lifecycle operation, firewall change, migration or commit.
- Final structural validation:484passed/87deselected (`/tmp/mycelium-remediation/acceptance-final.log`); focused Engram18passed, config/workspace/benchmark60passed. Ruff and `git diff --check` pass. Final UI lint/build pass, with the existing large-bundle warning. Tests exercise invalid config rejection, snapshot conflicts/reselection, retracted rendering, revision merges, allowed hosts/origins, incomplete-encoding QA blocking, resume journals, speaker retry and partial-upload cleanup. Earlier test failures were obsolete selector mocks; an unscoped pytest command also collected experiments and was interrupted, then rerun explicitly against `tests/`. No full model integration or browser component suite was run.

## 2026-09-15 — Commit validated repairs and continue audit acceptance

- Committed the earlier validated tranche as `8139075`, excluding unrelated audit-prompt changes and untracked user files. The implementation checklist is now tracked; remaining work remains explicit.
- Added task-local diagnostic scopes: LoCoMo invocation, reset, memorize session, finalize and answer operations carry stable IDs through every LLM/embedding timing row and structured failure dump, without putting telemetry in prompts. Each invocation records its code environment. Cumulative elapsed accounting includes current invocation setup; QA-disabled runs report not_run. New benchmark protocol3 deliberately rejects older settings.
- Model provenance queries the configured host's read-only tags endpoint and records QA/memory/embedding names and digests. Changed provenance rejects resume before journal mutation. Missing digests remain explicit errors in the inventory rather than fabricated versions. Host validation found Gemma4:12b digest `4eb23ef187e2c5462566d6a1d3bbbc2f1346d0b4327cbb66d58fffbcc9b2b05c` and embeddinggemma digest `85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1`.
- Wiki citation coverage now comes from fact items actually present in typed page sections. The deterministic renderer must reproduce stored Markdown exactly; mismatched pages are reported and excluded, preventing placements or an unrelated fact from counting as published evidence. This measures provenance coverage, not semantic entailment.
- Engram configuration rejects missing requested files, invalid model strings and nonpositive/fractional/boolean budgets, and nonfinite sampling values. Audio-body middleware bounds bytes before multipart spooling, including chunked requests, while the file-level bound remains enforced. Oversized known lengths reject before reading; streamed overflow closes partial multipart files. A64KiB allowance covers multipart metadata above the audio limit.
- Structural validation:495passed/87deselected (`/tmp/mycelium-remediation/followthrough-full.log`); focused suite114passed, final timing/benchmark follow-up40passed. Tests cover task isolation, model-tag changes, question-to-call linkage, stale wiki projections, unknown-length uploads and spool cleanup. No UI changes in this tranche.
- Native in-situ run `benchmark_runs/audit-provenance-tiny-v1`: one fresh source session and one QA, snapshot enabled,15.50s total,11.43s encoding. Execution/encoding/QA complete; model provenance complete; no encoding/publication backlog. Five LLM calls and two embedding calls, no failed attempts, every timing row linked to its invocation/operation. The single tiny question scored1.0 with complete citation coverage. This validates reporting plumbing, not general memory quality or the performance targets.
- Added reproducible opt-in neutral extraction probes. Baseline `benchmark_runs/audit-extraction-contract-20260915T231554Z-b857c72d`:12calls,17claims;9 time-bearing claims lacked anchors, two standalone visitor claims omitted necessary earlier-context citations, one unsupported gendered pronoun, variable subjects. Proposed generic citation/attribution clarification `...231811Z-26be8995`:12calls,14claims;12 time-bearing claims still lacked anchors, inconsistent subjects and some omitted requests for help. Neither a semantic pass nor a reason to integrate the prompt. The clarification remains evaluation-only; production extraction prompt is unchanged. A separate required-field probe is testing whether optional schema fields explain anchor omission.
- Required-anchor schema experiment `benchmark_runs/audit-extraction-contract-20260915T232115Z-3eaf466a` completed12 calls with the original prompt: all9 time-bearing claims selected a cited anchor. This isolates optional-field omission, but does not pass temporal meaning/attribution gates: a delivery condition still becomes the event date, unsupported pronouns remain, and requests for help disappear. The schema variant also remains evaluation-only pending the multi-entry temporal/subject contract. No extraction production change was made.
- Provenance additionally hashes tracked and untracked source/configuration files, so newly added modules are represented even before commit. Final focused provenance/benchmark tests:41passed (`/tmp/mycelium-remediation/provenance-final-tests.log`). Full structural suite previously495passed; the added source-hash test increases coverage without changing inference. Ruff and whitespace checks pass. The failed semantic variants are retained by the opt-in harness, not installed as runtime prompts or schemas.

## 2026-09-15 — Typed temporal evidence, reviewed corrections, bounded workspaces

- Replaced lexical relative-date inference with model-declared time entries: verbatim expression, constrained action/state, event/deadline/condition role, exact cited segment, and absolute interval / signed day offset / calendar period / unresolved meaning. Deterministic code performs only declared calendar arithmetic. It validates interval precision and provenance, preserves message-local dates, rejects forged intervals, and reports missing/invalid anchors or calendar overflow without inventing dates. Undated messages in an otherwise timestamped source stay undated. Independent temporal entries reach facts, wiki qualifiers, retrieval and the inspector.
- Schema 2 deliberately requires fresh stores. Schema 1 rejection is checked before journal-mode changes; the rejection test verifies original database bytes are unchanged. Retired identity work-unit fields and unused assistant-context contracts were removed; experiment imports now target the production complementary selector. No store migration or compatibility parser was added.
- Direct host Gemma4:12b probes used the configured sampling/context with reasoning off and exact prompt/schema capture. Initial symbolic extraction (`benchmark_runs/temporal-contract-20260915T234850Z-df218140`) lacked a month reference; message timestamps resolved that ambiguity. Text-first schema ordering (`...235433Z-65ee62c6`,18 calls) dropped an independent deadline and was rejected. Original field ordering with explicit unresolved instructions (`...235533Z-39fb2f41`) and the exact production dynamic schema (`benchmark_runs/temporal-contract-20260916T000221Z-b65d5453`,18 calls) retained the primary event/condition times across three trials each, including calendar month and vague/missing-year counterexamples. “Recently” still sometimes stays only in text; payment may be classified as deadline or condition_time with the same target/date. This is limited contract evidence, not complete temporal coverage.
- Automatic correction-reference inference did not meet acceptance. Simple reference probes (`benchmark_runs/temporal-correction-anchors-20260916T001529Z-f08d27df`,15 calls) passed, but native `temporal-pipeline-20260916T002059Z-aa25bc6a` failed after47.36s: a second correction chose the earlier correction's timestamp rather than the preserved source reference. A concise reason-before-decision history contract (`temporal-correction-history-20260916T002714Z-af0f1d15`,12 calls) and reference replay (`temporal-correction-anchors-20260916T002901Z-36cf1cef`,15 calls) passed their direct cases, yet native `temporal-pipeline-20260916T003239Z-99b3326d` failed after45.42s by retaining an old date for an explicit new plan. A separate narrow reference-decision experiment still reset one edited duration to submission in12 calls. These automatic reference mechanisms were rejected; their artifacts and a diagnostic-only reproduction harness remain.
- Asked the user an optional preference about reviewing relative correction dates; no response arrived during continued independent work. Proceeded with the stated assumption of explicit date review. Production now extracts correction metadata only; `benchmark_runs/correction-metadata-20260916T004042Z-a6e3eb6b` completed18 direct calls with paired times, new-plan, no-time, vague-duration and absolute-date cases. Main constraints were correct in three trials each; a separate “Starting today” annotation was inconsistent, leaving coverage open. The UI presents exact offered references and resulting dates before applying each relative correction. No automatic reference-selector call remains.
- Correction drafts freeze model metadata and submission time durably. Preparing a draft leaves the original active. Applying requires exact choices for all relative times, binds to replacement inputs, checks claim/source fingerprints, and atomically publishes the replacement plus reviewed provenance. Retries reuse the prepared metadata and completed result; a source change requires a new preview. Reviewed submission dates survive a save after midnight. UI edits invalidate previews, obsolete loads are ignored,409 responses discard stale previews, and retryable failures retain text/choices. A cache-replay test caught option ordering changing after sorted JSON persistence; explicit reference order fixed it.
- Three fresh-store native temporal lifecycles completed: `benchmark_runs/temporal-pipeline-20260916T010435Z-f3b4a257`48.263s (15 LLM calls/45.471s,4 embedding calls/2.262s); `...011255Z-eb8c05a2`45.625s (15/43.306s,4/2.008s); `...011341Z-f35f98cf`45.960s (16/45.350s,4/0.294s). Zero failed attempts or retries. Each retains exact requests/responses, timing traces, effective config, encoded/corrected/final snapshots, retrieval evidence and JSONL export. The first run spent14.650s on extraction,3.404/2.801s on correction metadata, and1.195/1.157s on the two retrieval selections; remaining model time was identity/routing/synthesis. Scripted explicit choices are evaluation inputs only.
- Snapshot inspection confirms message-date arithmetic, distinct action targets, reviewed provenance and no extraction/publication backlog. Quality is not fully accepted: sections drift between Goals & Plans and Shared Projects without a named shared project; the third run extracted a separate payment condition which remains active after correction of the delivery claim. That is an H/K/L scope/coherence problem, not grounds to delete another claim deterministically. The harness completes temporal assertions only. No QA generation, daily-driver matrix or matched full benchmark was run. Failed automatic workflows are incomplete; the earlier15.50s reporting smoke used a different workload. These timings establish neither a quality improvement nor justified compute cost against a comparable baseline.
- Workspace revisions are monotonic independently of retained history. Only eight operations remain in the workspace, with a fixed latest status; diagnostics and the full rendered envelope are bounded on success and failure. Tests repeat100 invalid tools at1/500-token budgets, retaining canonical initial evidence while keeping output within budget. Full operation details remain in per-tool results.
- Added Vitest/jsdom/Testing Library for UI component acceptance. Compatible dependency updates removed the nine advisories reported during installation; `npm audit` now reports zero. No forced major upgrades. Final checks:516passed/87deselected (`/tmp/mycelium-remediation/temporal-reviewed-final-tests.log`), five component tests, UI build/lint, Ruff and whitespace checks pass. The existing >500KiB UI bundle warning remains. Python HTTP-fixture tests needed host loopback access; sandboxed attempts stalled. Only the exact agent-owned pytest processes were cleaned up; one automatic approval review timed out before the verified cleanup retry succeeded. No application server or firewall changes.

## 2026-09-15 — Canonical retrieval and source refresh acceptance

- Committed typed temporal evidence and reviewed corrections as `b320631`, excluding unrelated user files. Continued C/D acceptance without changing model prompts or semantic decision contracts.
- Admission now reads ownership, entity title, tier and claim text from the canonical snapshot; search hits supply identity/rank. Snapshot validation includes sources, cited segment IDs and supporting fact members. A concurrent owner move, source retraction or consolidation triggers one fresh selection. A repeated conflict returns `RetrievalError(concurrent_update)`; missing source/segment/owner provenance is `evidence_integrity`, distinct from an empty search. Additional tool search filters obsolete hits before applying its record limit.
- Source evidence carries a revision. Equal revisions union exact citations and promote a previously contextual segment to cited; newer revisions replace old excerpts, and older replies cannot restore removed text. Workspace refresh reconstructs shown excerpts from current source text, speaker, order, timestamp, status and current claim citations without expanding into uninspected dialogue. Retracted claims lose their excerpts. Refresh also runs after tool failure; invalid provenance clears the stale workspace with an explicit failure rather than retaining unavailable evidence.
- Extracted the chat evidence inspector into a component. It exposes exact claim-to-segment citations, source retraction reasons, interpretation status and latest operation failure even when detailed history was elided. Component rerender tests confirm old text disappears and the new status/citations remain visible.
- Final validation:527passed/87deselected (`/tmp/mycelium-remediation/source-consistency-full.log`), seven UI component tests, build/lint, Ruff and whitespace checks pass. Eleven new Python cases exercise owner moves and repeated conflicts, consolidation during admission, source retraction/deletion, missing segments, edited excerpts, citation promotion, failed-tool refresh and broken-provenance errors. A pre-existing page-reference fixture had ownership only in its synthetic index hit; it now declares a canonical placement. Initial new test failures were invalid person-section/retraction fixture data, corrected to declared schema values. Existing UI bundle warning remains; no new model benchmark or quality/cost claim.

## 2026-09-15 — Engram cancellation, admission boundaries and UI ordering

- Committed canonical retrieval/source refresh as `c87ee56`. Continued E/G acceptance with per-meeting operation ownership and the existing shared speech-device lock. A cancelled native worker finishes before the lock is released or its file is removed; repeated cancellation cannot release the device early. Deletion cancels queued jobs, waits for active work, and stops subsequent pipeline stages. Partial-upload cleanup runs only after the copying thread exits. Audio deletion failures retain a retryable meeting record instead of silently orphaning the file.
- Finalization durably freezes transcript, speaker names and source metadata before its first await. Concurrent edits/finalizations are rejected. Source admission is shielded until durable bookkeeping completes; cancellation then skips optional summary generation. Frozen inputs survive restart and retry with the same ingestion key. Engram deletion removes recording/transcript storage, not already admitted memory; the UI makes that distinction explicit when applicable. Foreign keys are now enabled, connections close deterministically, and transcript index allocation occurs in the same write transaction as insertion.
- Added typed, durable diarization/summary warning records with timestamps and resolution history. Successful retries resolve the relevant stage without erasing past failures. Both first-pass and retried diarization must preserve exact transcript text, order and timing. Restart recovery returns an already transcribed meeting to review and preserves frozen finalization inputs. API responses expose warnings and admission state; speaker/deletion conflicts return409. No model prompt, speech-model choice or semantic inference changed.
- Engram UI request scopes track both selected-meeting generation and request order. Delayed loads, speaker saves, process results, finalize continuations and deletion responses cannot overwrite another selection, including an A→B→A switch. Old transcript content disappears while the next meeting loads. Read requests abort on replacement/unmount; failed speaker/transcript edits remain available. Frozen inputs are read-only and summary/admission retries skip editing speakers. Warning history remains inspectable. Documentation now correctly puts durable transcript capture before optional summary generation.
- Validation:537passed/87deselected (`/tmp/mycelium-remediation/engram-full-tests.log`),14 UI component tests, build/lint, Ruff and whitespace checks pass. Ten new Python tests use controlled real worker threads and paused source admission to cover cancellation/deletion/restart interleavings; no speech model or application server was started. Seven new UI cases exercise deferred responses and warning/frozen-input rendering. Initial failures were a test import, an unsupported Testing Library selector option, and React's mutable-closure lint rule; the request scope now stores mutable counters in a ref. A sandboxed worker-thread test stalled; the exact agent-owned process193538 was verified and stopped, and host-access tests passed. Existing bundle-size warning remains. These are structural acceptance results, not a new encoding/QA quality benchmark.
- Final recovery follow-through:34 focused Engram/capture tests passed (`/tmp/mycelium-remediation/engram-recovery-final.log`), including a crash after a summary was saved but before status publication. Recovery marks that summary complete and resolves its warning without another model call. DESIGN now also reflects the previously committed temporal review, complementary admission and revision-aware workspace contracts.

## 2026-09-15 — Chat and wiki request-order acceptance

- Committed Engram cancellation/admission repairs as `2c9c9ca`. Chat drafts and pending requests are now scoped by session, independently of history loading. A failed history request preserves the selected session's draft, hides the previous transcript, and offers a retry before sending. An older chat completion cannot clear another session's pending state or alter its status. Failed optimistic messages are removed by object identity, preserving existing messages even with identical timestamps. Returning to an in-flight session reloads canonical history after completion; unmounted views ignore delayed replies and clear status timers.
- Promoted the Engram selection/request scope to a shared UI helper and used it for wiki navigation. Page loads and exact-source/scope reads cancel obsolete requests. Old page content is hidden while loading. Re-selecting the same page retries a failed read. Post-edit catalog refreshes cannot navigate away from a newer selection or close its editor, including A→B→A navigation. Selection changes reset page-specific claim/fact choices.
- Added six chat and four wiki component tests. Final UI suite24passed (`/tmp/mycelium-remediation/ui-wiki-tests.log`); lint and build pass (`ui-wiki-final-lint.log`, `ui-wiki-build-v3.log`). Initial checks found an unstable empty-array dependency, effect scheduling syntax flagged by lint, and a missing ontology fixture field; those were corrected. No Python or model semantics changed; the previously validated537-test Python suite remains applicable. Existing bundle-size warning remains. Private Wi-Fi/Tailscale and real-browser device checks remain unperformed.

## 2026-09-15 — Effective configuration through command paths

- Committed UI ordering fixes as `0a57c65`. Finished B's command-specific configuration gate. Library constructors copy and validate the complete effective configuration before creating a store; fractional/boolean budgets and invalid model/URL types no longer bypass validation. Callers can supply an explicit `Config` object or file path. QA overrides are validated by the same contract.
- Benchmark factories now resolve settings once. Later cases and daily-driver trials retain those settings even if the input file changes or disappears. LoCoMo protocol4 records effective memory and QA configuration and rejects changed-setting resumes before appending invocation records. Model inventory uses the captured embedding settings. MAB and daily-driver retain `configuration.json`, including before inference in daily-driver; daily-driver also records configuration in `run.json`. Daily-driver run/comparison stores close on success and failure. Updated stale model defaults, storage ownership and config examples in the guides.
- Added34 tests covering LoCoMo/MAB public command dispatch through real clients, file/default/override precedence, repeated reset, server and Engram summary settings, environment token precedence, daily-driver trial configuration capture and artifact contents, invalid inputs and changed-setting resume rejection. Focused suite98passed; maintained structural suite571passed/87deselected (`/tmp/mycelium-remediation/config-maintained-tests.log`); Ruff and whitespace checks pass. No production prompt or semantic contract changed.
- Validation mistake retained explicitly: invoking pytest at the repository root also discovered four archived benchmark harness cases under `benchmark_runs/consolidation-efficiency-20260909/harness`. The baseline failed and the optimized replay ran until the180-second process timeout. Its temporary output is `/tmp/pytest-of-nitin/pytest-166/test_replay_optimized_0`;17 completed model timing rows total153.01seconds, with interrupted work not fully accounted. This was not a planned probe or a quality/compute comparison, and no historical benchmark artifacts were overwritten. The process had exited by the verified cleanup check. Added pytest `testpaths = ["tests"]` to keep default discovery inside the maintained suite. The successful structural run explicitly targeted `tests/`.

## 2026-09-15 — Global admission after budget splitting

- Committed effective configuration fixes as `1a06053`. Continued N with the invariant that separately selected chunks do not define a global usefulness order. The selector now compares complete surviving records in one final structured model call, preserving its order, supported aspects and gaps. If those records cannot fit a joint comparison, admission returns an explicit budget error. A failed chunk aborts the selection before further calls; empty chunks preserve their gap diagnostics without a merge call. Single-batch behavior and production prompts/schema remain unchanged.
- Before integration, the exact production prompt/schema passed9/9 neutral trials (complementary support, duplicate support across batches, no-support counterexample),24 calls/30.006seconds: `benchmark_runs/selection-merge-20260916T023818Z-415dae88`. Exact requests, responses, schema, configured model settings and host model inventory are retained.
- After integration, the same three cases passed9/9 trials through production budget splitting: `benchmark_runs/selection-merge-pipeline-20260916T024111Z-c6fce75a`. The probe constrains only the selector's planning envelope to trigger splitting with small neutral records; actual model context remains the configured65536 tokens. All24 calls succeeded without retries,32.483seconds total. Six final comparison calls cost1.389–1.779seconds each (median1.676seconds);18 local calls cost22.617seconds. These are warm contract probes, not full-store retrieval/QA or a matched compute comparison. Locally discarded records can still contain jointly useful evidence; broader recall and QA gates remain open.
- Structural validation:23 focused retrieval tests, then574passed/87deselected across the maintained suite (`/tmp/mycelium-remediation/selection-merge-full-tests.log`); Ruff and whitespace pass. Tests cover final order overriding chunk order, exact complete-record preservation, rejected non-fitting survivors, no partial results after failures and gap preservation without redundant calls. The initial oversized test expected later chunks to run after an earlier failure; its input was reduced to exercise the intended final-merge boundary. No semantic fallback was added.

## 2026-09-15 — Optional reference semantic scoring with independent recovery

- Committed global selection as `32235be`. Added LoCoMo `--semantic-scoring`, using the captured QA model configuration after answers have been durably saved. The scoped structured verdict is correct/partial/incorrect/ungradable with a bounded explanation. The original legacy score remains. Reports expose strict accuracy among gradable answers, grading coverage, partial/ungradable counts and scorer failures; they do not silently score failed or ungradable calls as wrong. An empty scoring workload is `not_run`.
- The proposed exact prompt/schema passed21/21 neutral direct trials before integration: paraphrases, negation, partial lists, wrong times, abstention, refusal followed by an invented answer, and missing references. Artifact root: `benchmark_runs/reference-judgment-20260916T024708Z-fc939df4`;21 successful calls/19.770seconds, no retries. Retained exact input payloads, prompt/schema, settings, model inventory and timing rows.
- LoCoMo protocol5 persists a scorer specification/digest in run settings and captures scoring model provenance separately. QA/execution/scoring status remain distinct. Completed judgments are reused; failed or interrupted judgments retry without regenerating answers. Question checkpoints and JSONL retain the verdict/reason, errors, elapsed time and operation linkage. Full attempt history is preserved in `diagnostics/scoring-calls.jsonl`; scoring is outside the QA latency metric but inside invocation elapsed time. This evaluates agreement with supplied references, not source grounding; scorer/reference errors and same-model judge bias remain limitations.
- Native reporting/resume smoke: `benchmark_runs/audit-semantic-score-tiny-20260916-v1`, full-context baseline, one source session/question. First invocation1.773seconds, one QA call0.908seconds and one scorer call0.600seconds; both successful with matching configured model digests and separate linked operation IDs. The judgment was correct; all reported phases completed. A matching resume took0.038seconds and left both call counts unchanged at1. No memory encoding/retrieval quality or matched cost improvement is established by this baseline smoke.
- Validation:81 initial focused tests,19 additional scorer/recovery/provenance tests, then581passed/87deselected (`/tmp/mycelium-remediation/semantic-scoring-full-tests.log`); Ruff and whitespace checks pass. Tests cover invalid verdicts/extra fields, missing grades, actual CLI settings, scorer failure, cancellation after one completed judgment, unchanged-answer reuse, scorer-spec mismatch rejection and model/operation provenance. Full daily-driver/sample3/sample9 quality and longitudinal artifact gates remain outstanding.

## 2026-09-15 — User confirms date review before correction saves

- The user explicitly selected “Show dates for review before saving,” confirming the preference previously implemented as an assumption. Retained the existing correction preview: each detected relative expression shows reference choices and the resulting date/interval, and every expression requires an explicit choice before “Save reviewed dates” is enabled. Editing the correction invalidates its prior preview; the backend validates the draft and choices before applying the correction.
- Verified the existing UI and backend review guards and recorded the confirmed preference in the implementation plan. No runtime change or additional model call was needed; existing correction-review coverage remains applicable. Documentation-only change; whitespace validation passed.


## 2026-09-15 — Truth review across owners and incoming cohorts

- Moved truth comparison ahead of owner-scoped presentation. The pipeline considers active canonical claims across pages, including unplaced claims and other claims from the same incoming cohort. Candidate discovery and pair decisions have exact alias accounting; a claim cannot be its own target. Pair decisions explicitly distinguish coexistence, contradiction, and either replacement direction. Organizational ownership does not establish subject identity or chronology. Full cited evidence and identity bindings remain in the decision input. Missing provenance fails explicitly, preserves prior facts, and leaves additions retryable.
- Pending reviews preserve whole existing facts and separately publish new sides. Human approval remains the only truth mutation. Successful replacement atomically invalidates overlapping pending reviews whose evidence became inactive; stale proposals cannot be approved or rejected. Correction rebuilds include all newly affected pages. Removed the previous owner-local truth path and its same-cohort-target prohibition. Presentation-focused tests explicitly isolate the separately tested truth service; new full-path tests cover cross-owner and same-batch comparison, reverse replacement, exact schemas, unplaced claims, failure preservation and review invalidation.
- Before integration, comparison prompt/schema passed18/18 trials in `benchmark_runs/truth-scope-20260916T041416Z-f58af33d` (30.997s). The first candidate-list contract failed18/18 because self IDs remained selectable (`truth-candidates-20260916T041910Z-c1e873ff`,24.306s). Exact per-incoming legal targets removed self selections, but the list contract still failed5/18 with unrelated selections contradicting its explanations (`truth-candidates-20260916T042514Z-3174b6f3`,34.818s). Requiring an explicit compare/unrelated/uncertain decision for every eligible candidate passed18/18 (`truth-candidates-20260916T042620Z-28404b55`,31.599s). No lexical semantic repair or post-hoc override was added.
- Native production resolver plus page publication passed18/18 neutral trials in `benchmark_runs/truth-pipeline-20260916T043327Z-c74d4647`. All49 model calls succeeded with no retries,84.214s total:18 truth-candidate calls34.947s,13 truth comparisons22.740s,9 presentation-candidate calls11.776s,9 synthesis calls14.751s. Exact requests, configured settings, model inventory, sources, claims, proposals, coverage and rendered pages are retained. Inspected facts preserve both statements, exact provenance and review qualifiers; no repeated fact memberships. Unrelated hobbies/people/events coexist. Section drift remains visible (including one later lecture routed to Timeline), so this is a truth gate, not an organization or broad quality gate. All probe timings are warm and unmatched to prior encoding runs.
- Validation: initial integration test failed as intended because a new owner's singleton bypassed truth review; initial helper fixtures also had invalid entity-constructor arguments. Fixed fixtures, not production fallbacks. Updated90 focused tests passed; final maintained suite590passed/87deselected (`/tmp/mycelium-remediation/truth-scope-full-tests.log`), Ruff and whitespace checks pass. Candidate requests reserve4096 output tokens for complete decisions; comparison requests split whole pairs on budget overflow. Discovery still scans active history and successful no-change comparisons are not yet durably cached; J/M/O must address this before full compute acceptance. Device/network rollout and H/K/N/full benchmark gates remain open.


## 2026-09-15 — Durable schema-validated decision reuse

- Committed global truth review as `8692f40`. Added derived `model-decisions` records keyed by the complete prompt/output contract, JSON schema, endpoint, stage, effective sampling/reasoning/context/output settings and live configured model digest. Inventory is checked on every lookup and again after generation; changing weights during generation prevents caching. Cached results are revalidated against the current response model. Invalid/cancelled calls are not stored; concurrent identical requests share one successful result.
- Identity, page routing, truth discovery/comparison and fact selection/synthesis opt into reuse. Identity work-unit plans no longer bypass current model/config validation, and changed plans invalidate staged ID allocations. Cache successes are durable independently of an aborted canonical UnitOfWork; cache writes do not alter its authoritative read set. Cache-hit timing rows explicitly carry cache_hit, request_digest and model_digest. Retrieval/QA calls remain independent evaluations.
- Native fresh-store replay: `benchmark_runs/truth-pipeline-20260916T044433Z-7b066ed5`,18/18 neutral cases passed and each build was repeated. Initial builds made49 actual generations/80.213s; the repeats made22 cache lookups/0.033s reported lookup latency and zero further generations. All calls succeeded without retries. Requests, outputs, configured settings, digest inventory, source/fact/wiki artifacts and repeated resolution results are retained. This proves unchanged-work recovery on these cases, not general quality, bounded growth or a matched first-build cost improvement.
- Validation:18 cache tests cover process restart, discarded canonical mutations, concurrent requests, corruption, cancellation, changing inputs/prompts/schema/settings/model/digest, and weights changing during generation. The initial cache test used dictionaries where the SDK supplies response objects and failed parsing; corrected the fixture shape. Maintained suite608passed/87deselected (`/tmp/mycelium-remediation/decision-cache-full.log`), Ruff and whitespace pass. Exact response reuse still requires identical request partitions and does not replace bounded semantic candidate discovery or persisted incremental group design. J/M/O and full benchmark acceptance remain open.


## 2026-09-15 — Reviewed identity occurrences within shared claims

- Committed durable decision reuse as `61fdd47`. Found and removed a whole-claim identity constraint: a human-confirmed person previously forced every proposed subject citing that claim to resolve to that person, rejecting a separately described project or colleague. The new contract supplies exact reviewed occurrence aliases (R IDs), requires each once on its confirmed canonical entity, and independently permits other source-backed subjects. It maps review aliases back to their cited claim IDs after validation; original model output and durable reference IDs remain inspectable. Extracted surfaces now remain visible in identity-reference context.
- Human identity references now carry identity_decision_id. Approving or repeating one review supersedes references from that exact decision, preserving independent reviews of other subjects in the same claim. This is an exact review-ID invariant, not name matching. SQLite schema advances to3 with the existing fresh-store policy; schema1/2 stores are rejected without migration or modification. README and plan updated. Existing stores and earlier benchmark artifacts remain untouched.
- Direct contract:12/12 neutral trials in `benchmark_runs/reviewed-identity-20260916T045143Z-3f6867c0`,12 calls/44.492s, no retries. Cases cover a reviewed person plus a new project/colleague, two reviewed subjects sharing one claim, and a person/project with the same surface name. Native identity and page routing:12/12 trials in `benchmark_runs/reviewed-identity-pipeline-20260916T045534Z-28b27e18`,24 calls/78.892s, no failures/retries. Inspected plans preserve the reviewed entities and identify the separately described subjects with their own claim support. These are fresh-store routing probes, not full wiki/source coverage or retrieval/QA acceptance.
- Validation:617passed/87deselected in the maintained suite (`/tmp/mycelium-remediation/reviewed-identity-full.log`), Ruff and whitespace pass. Added omission/reassignment/duplication checks, confirmed You plus another subject, independent review persistence and old-schema rejection without modification. One existing evidence-shape test initially failed because surfaces and review IDs are now retained; its expectation was updated. Bounded registry candidates, incremental groups, broader extraction/organization/retrieval quality and matched benchmark compute gates remain open.

## 2026-09-15 — Confirming a person occurrence as the user

- Fixed an exact-type inconsistency in identity review: the model contract can offer canonical You for a person occurrence, but the review API rejected that selection because You has a dedicated schema type. Explicit human selection now binds the occurrence to You and preserves every field of the canonical profile, including its title and aliases. This does not infer identity from a name.
- Validation:10 focused identity-review tests passed (`/tmp/mycelium-remediation/you-identity-review-tests.log`), including canonical profile immutability and the persisted review reference. Source-first identity/index changes are still in progress and are not part of this commit.

## 2026-09-15 — Source-first identity decisions and bounded semantic candidates

- The joint discovery/matching contract failed with a bounded registry. Retained direct runs: `identity-candidates-20260916T050919Z-a58a21ab`11/12, `...051252Z-a6f50db0`11/12, `...051631Z-f84b1eaa`9/12. Failures included a person assigned to a same-named project and unsupported review alternatives. The first two fixtures also used underspecified registry titles; the third uses distinct neutral full names. None of these is accepted evidence of success. Tightening review choices to their declared entity type prevented invalid review-API choices but did not repair the joint semantic decision.
- Source-only discovery passed15/15 neutral trials in `subject-discovery-20260916T052056Z-43afeaa8` (15calls/37.160s). Source-first discovery plus typed candidate matching passed12/12 in `source-first-identity-20260916T052601Z-96fe4659` (29calls/68.310s). Candidates come from learned cosine similarity over source-backed identity records, bounded to24 per discovered subject. Exact declared types scope candidate IDs; no lexical identity rule, forced semantic repair, or ownership-derived fact summary establishes identity.
- Human-review scope needed another separation. Direct discovery with review occurrences passed15/15 (`source-subject-bindings-20260916T052808Z-4053fb01`), but the richer native representation omitted co-mentioned people in4/12 trials (`reviewed-identity-pipeline-20260916T053137Z-b203d5d0`). Removing duplicated whole-claim identity metadata alone passed11/12 (`source-identity-evidence-20260916T053431Z-64be8659`). The accepted contract discovers subjects from source evidence first, then assigns exact human-review occurrences to discovered subject IDs. Missing/ambiguous assignments fail explicitly; conflicting human bindings cannot merge. The model never sees a human review as ownership of an entire claim.
- Revised review sequence:12/12 direct trials in `source-then-reviewed-bindings-20260916T053734Z-f9c8f45a` (24calls/51.851s);12/12 integrated routing trials in `reviewed-identity-pipeline-20260916T053955Z-40f0c0d2` (46calls/98.345s). Bound IDs bypass model identity matching; other subjects receive independent typed decisions. Original discovery, review assignment and candidate traces persist with the work unit. This additional review step has a compute cost; these small runs do not establish a matched overall quality/cost improvement.
- Larger-registry native routing:12/12 trials in `source-first-identity-pipeline-20260916T054220Z-85aa154f` (39calls/93.764s), covering aliases, projects, new people sharing a project name, and unresolved alternative people. No failed LLM attempts or retries occurred in the listed successful runs. Occasional extra Event subjects remain an organization finding for K; correct identity choices alone do not establish useful pages.
- The rebuildable candidate index embeds only changed documents, reuses query vectors across reopen, checks live embedding weights, and splits long inputs without discarding characters. Exact cosine search ranks distinct parent IDs across chunks; ANN remains disabled pending the10k recall gate. Required IDs cannot exceed the bound or reference another snapshot. Page routing sees the discovered/resolved identities and canonical You, rather than the full registry. A matched provisional identity retains its outstanding human-review blockers on later placements. Pending identity listing now uses the existing SQLite status/entity indexes.
- Structural validation:637passed/87deselected (`/tmp/mycelium-remediation/source-first-final-full.log`); contract tests cover occurrence separation, forged IDs, typed candidate domains, invalid vectors, updated/deleted documents, changing weights/dimensions, long evidence/query chunks, bounded unique candidates, and indexed pending-review reads. The initial structural run exposed23 stale response/fixture assumptions; updated them for source discovery and matching, then corrected two expected call counts and a Person section fixture. No server or UI changes were made.
- Identity continuity/rebuild validation: `identity-continuity-pipeline-20260916T054534Z-2871b015`, six neutral scenarios (three trials each of a known unnamed person and an unresolved sender),18/18 builds passed. Identity IDs remained stable, pending review status and blockers survived follow-ups, and all six third unchanged builds made zero new model generations. Each successful model-cache record retains the verified weights digest. No claim of bounded first-build history cost or general benchmark improvement follows from this result.

## 2026-09-15 — Independent page admission and source-scoped destinations

- Committed source-first bounded identity work as `0badb4f`. Added a separate, cached page-admission decision for provisional identities. Each admitted page requires an entity-specific basis and exact supporting claim IDs. A known subject can remain provisional when its evidence is best presented on another subject's page. Existing materialized pages do not repeat admission. The work unit retains admission reasons and citations.
- The initial combined admission/placement contract failed8/12 in `page-admission-20260916T055121Z-af420010` (one structural retry). It repeatedly admitted a routine activity despite describing it as routine. The independent contract passed12/12 in `separate-page-admission-20260916T055509Z-82e30bda` (24calls/62.531s), then15/15 including Artifact controls in `...060143Z-1fc9ea55` (30calls/81.072s). The first native attempt `page-admission-pipeline-20260916T055818Z-b031f121` aborted on an omitted Artifact admission basis after one case; a maintained test now checks every ontology type.
- Native runs exposed two upstream issues: source discovery lacked the ontology's actual definitions, sometimes treating a bounded event with follow-ups as an ongoing project, and canonical You was eligible even when discovery found no user subject. Added the directly proved ontology descriptions and constrained page eligibility to resolved source subjects. The source-type probe passed15/15 in `source-subject-types-20260916T061022Z-cb5526fe` (15calls/44.489s). Page sections are now constrained for each actual entity ID in the native JSON schema, with the existing runtime validation preserved.
- Native admission: `page-admission-pipeline-20260916T060534Z-7988ce51`13/15, then `...061212Z-8da24286`14/15 after type/domain repairs. The remaining failure was a sound refusal to resolve a name-only seed person uniquely: that fixture claimed a pre-established materialized identity but supplied no identifying source evidence. Corrected the fixture's precondition with cited identity evidence; did not force a name match. `...061600Z-0e904657` passed15/15,74calls/182.898s without failed attempts. Incidental possessions/routine activities stayed on the person page; the continuing effort, useful reference artifact and substantial bounded event received the expected destinations. Some runs also admitted a facilities-team page; broader usefulness/concision still needs longitudinal wiki review.
- Validation:642passed/87deselected (`/tmp/mycelium-remediation/page-admission-source-final.log`), Ruff and whitespace checks pass. A prior suite run exposed two fixture assumptions about implicit You placement; those now supply explicit source discovery/matching. That failed run also emitted one SQLite cross-thread finalizer warning, retained in `page-admission-source-domain-full.log` for P/data-correctness follow-through; the final suite did not repeat it. No general QA/recall or net compute improvement is claimed from these isolated probes.
- The identity-review UI/API also offers context/component/occurrence decisions with no_page, while EntityRecord intentionally has only provisional/materialized states. Clarification of the intended scope of that human choice is pending; no unsupported EntityRecord state was added. Human review scope, successive-build event coherence, full daily-driver and matched corpus gates remain open.

## 2026-09-15 — Bounded fact membership and independently reusable prose

- Replaced combined grouping/prose generation with a strict exact partition (at most12 canonical members per automatic fact), followed by separate rendering of each multi-member group. Singletons retain canonical text. Rendering requests use stable local aliases and just the group's source-backed canonical evidence and owner, so unrelated cohort changes do not invalidate their durable cache entries. Membership remains explicit in ConsolidatedFact. Human-edited presentations retain their exact membership and text; new evidence is independently represented. Retractions/ownership changes invalidate that protection. Singleton projection now preserves the section already selected by routing.
- Direct contract proof before integration: `benchmark_runs/bounded-fact-groups-20260916T062801Z-17a5052e`,9/9 trials,15calls/36.698s. All13 inventory details survived the12+1 grouping, independent dated events stayed separate, and conditions/dates remained in displayed text. Some scope explanations abbreviated inventory members, but prose rendering receives complete canonical members rather than those explanations.
- Native successive builds: `benchmark_runs/bounded-fact-pipeline-20260916T064116Z-d90db213`,9/9 scenarios across27 builds,48generation calls/184.711s, zero failed attempts. All third builds after reopening the store made zero new generations. Separate restart checks in `render-reuse.json` reused all three multi-member renderings with reversed input member order, identical text and cache hits. First harness `...064041Z-d2fe2c6d` aborted after its first production result because timing collection sliced a deque; fixed the harness and retained the failed run.
- These are evidence/size/reuse gates, not a general organization or net compute win. Native trials sometimes kept complementary class details in two singleton facts and varied workshop/event sections across trials. Full history truth/candidate scans remain, and broader consolidation cost and longitudinal source/wiki gates are still open.
- Validation:649passed/87deselected in `/tmp/mycelium-remediation/bounded-facts-full.log`; Ruff and whitespace checks. New regressions cover exact partitions, member limits, unknown sections, manual membership protection, retracted manual evidence, stable per-group requests and preservation of routed singleton sections. Four initial failures were stale response/section assertions; updated fixtures to the actual independent contract and routed section.

## 2026-09-15 — Measured flat vector indexing and weight integrity

- Measured10,000 unique complete claim texts collected read-only from existing benchmark artifacts. Preserved corpus, configured embedding digest/settings, vectors,200 sampled query vectors and every query's neighbors/latency. Query texts are sampled claims with the production query prefix; this measures index fidelity, not QA or semantic retrieval quality.
- Cosine run `benchmark_runs/ann-recall-10k-20260916T062133Z-2fb51e8b`: exhaustive search median13.52ms/p95=15.14ms; IVF_FLAT with all100 partitions median3.85ms/p95=4.40ms, recall@20=1.0 for every query. Smaller probe counts missed neighbors, including poor individual queries despite strong average recall.
- Production uses L2, so repeated the experiment with the same vectors and that metric before integration: `...063901Z-f0a01f75`. Exhaustive median12.03ms/p95=13.29ms; all100 partitions median3.01ms/p95=3.45ms, all200 queries recall@20=1.0. Index construction0.411s. Production now creates a flat L2 index at10k records and exhausts all partitions; it includes unindexed appends and rebuilds when unindexed rows reach indexed rows. Below the threshold it continues exhaustive search. No retrieval metric or model was changed.
- Claim vectors now identify actual model weights as well as the tag. Same-tag weight replacements rebuild the derived table, including changed dimensions; a digest change during embedding/query fails explicitly before returning evidence. Nonfinite, empty and incomplete vector responses are rejected. Instances sharing a derived index share an async lock. Typed dates were already included in search documents; added a correctly cited date-change embedding regression, without claiming a missing feature.
- Validation:22focused tests passed, then658passed/87deselected in `/tmp/mycelium-remediation/index-weights-full.log`. Native LanceDB checks cover indexed appends/deletes, exhaustive partition results, restarts, changed weights/dimensions and malformed embeddings. Initial date fixture failure correctly rejected an uncited anchor; corrected the fixture citation. These results establish no end-to-end QA or warm retrieval latency improvement.

## 2026-09-15 — Database lifetime on garbage-collector threads

- Reproduced the earlier unraisable SQLite finalizer exception using a cyclic database reference collected by a worker thread. MemoryDatabase now enforces owning-thread access explicitly, holds a resource lock across transaction scopes, and allows only private final resource release to close the connection on a collector thread. It closes SQLite before releasing the writer lease; initialization failures release acquired resources too. Ordinary cross-thread reads, writes and explicit close still fail, preserving the single-thread transaction model.
- Validation:12focused tests, then661passed/87deselected in `/tmp/mycelium-remediation/database-lifetime-full.log`. The regression checks no unraisable exception, rollback of an open uncommitted transaction, preservation of committed evidence, reopening with a new writer, and rejection of foreign-thread operations. No servers were started or stopped.

## 2026-09-16 — Strict memory-tool arguments; autonomous lookup gate remains open

- Memory tools now share strict argument models with their native tool schemas. Reject unknown fields, non-string queries/IDs, empty queries, duplicate IDs, non-integer/boolean limits and out-of-range requests. A mixed set of seen/unseen source IDs fails as a whole instead of silently executing a subset. Invalid arguments preserve evidence, consume no lookup/evidence budget, and produce the normal bounded failure workspace. Removed the coercion/truncation helpers.
- Native explicit tool requests passed15/15 cases in `benchmark_runs/memory-tool-contracts-20260916T071305Z-3a4962de`,27rounds/13.511s. Source dates, source locations and discovered transport details were answered correctly; unsupported memory stayed unknown; already-sufficient evidence needed no tool. This proves native argument/execution contracts when lookup is requested, not autonomous tool selection.24focused tests and673passed/87deselected in `/tmp/mycelium-remediation/strict-memory-tools-full.log` validate structural behavior.
- Autonomous native probes failed: `...065413Z-1ada8b84`0/9 with proposed strict schemas, and `...065605Z-f75bf3b0`0/3 with then-current schemas. The model prematurely said information was unavailable. An explicit capability control `native-tool-capability-20260916T065732Z-cd296ad5` successfully called both tools. The configured model advertises tool capability; model/settings were unchanged.
- Revised prompt trials `...065840Z-f406363d` restored search but failed source inspection (9/12). That source fixture omitted normal citation metadata; supplying it in `...065942Z-a74881c8` produced10/12, including two unsupported event dates copied from the conversation timestamp. An explicit date distinction and a location counterexample in `...070059Z-cc4ef8a4` still failed source inspection (9/15). These prompt revisions are not integrated.
- A single structured answer-or-tool step was also rejected: `memory-step-contract-20260916T070458Z-cda9c3dc` and `...070754Z-dfc25da5` each3/15. It recognized missing evidence in its rationale but mislabeled abstention as a general/non-recall answer. No structured-step production execution or semantic override was added. Later experiments preserve exact unchanged SDK requests/responses through RecordingClient; earliest native probe retains outputs/timings/definitions but lacks per-round raw request dumps. Autonomous source inspection, source grounding, claims/raw-source controls and paired QA remain N acceptance work.

## 2026-09-16 — Daily-driver completion and inference provenance

- Daily-driver runs now journal invocations with configuration/code provenance, preserve the model inventory and incremental action results, and report execution, encoding and QA completion independently. Backlog checks include all unconsolidated logs rather than a seven-day window. The report identifies its one-call grounded-answer mode. Each probe retains typed evidence, selection traces and separate retrieval/answer timings; QA and judge calls have checkpoint/probe trace IDs.
- Moved unchanged SDK request recording into shared benchmark support. Every request gets a unique filename across wrappers/checkpoints/restarts, running/complete/failed status, full request/response and timing. Native call/attempt/round trace IDs join these files to timing rows; telemetry does not enter model prompts. Retry and checkpoint tests verify exact request preservation and no overwrites.
- The daily answer judge previously accepted arbitrary IDs and silently intersected them with the allowed sets. Its schema now scopes required and forbidden IDs separately, including empty domains; invalid IDs fail validation. The production judge prompt is unchanged. `benchmark_runs/daily-judgment-contract-20260916T071813Z-27db3d41` passed9/9 direct native cases,9calls/16.428s, including forbidden-answer and unknown-answer controls.
- Validation:50initial focused tests,104request-recording/config/judge/client tests, then676passed/87deselected in `/tmp/mycelium-remediation/daily-recording-final.log`; Ruff and whitespace checks pass. This validates instrumentation and narrow judge behavior; full daily-driver quality and longitudinal benchmark gates remain to be run.

## 2026-09-16 — Architecture documentation follows the implemented contracts

- Updated DESIGN to describe source-first discovery, separate reviewed-occurrence assignment, bounded typed identity candidates, independent page admission, global truth comparison, bounded fact grouping and independent prose reuse. Removed obsolete claims about a single identity response, four-claim incremental batches, combined grouping/prose generation and automatic support classification. Documented thread-affine database access, safe final resource release, embedding weight invalidation and exhaustive flat indexing.
- README now distinguishes durable capture from extracted statements that remain searchable without a wiki page. Capture-only ingestion still requires Build Memory before its text becomes searchable. Reviewed documentation against the implementation and checked whitespace; no runtime change or additional model calls. Longitudinal daily-driver acceptance is running separately with unchanged production code and prompts.

## 2026-09-16 — Execute daily-driver lifecycle actions through current services

- First native acceptance scenario (`benchmark_runs/audit-daily-acceptance-20260916T072623Z-0466e118/daily_driver_v1/trial-01`) exposed stale benchmark adapters: approval referenced removed singular claim fields, omitted the resolver and did not await the review; retraction was labeled unsupported despite the production ClaimLifecycleService. Updated both to invoke the current transactional services. Approval requires one existing proposal with the declared relation and matching evidence on every incoming/target member; ambiguous or unmatched proposals fail without mutation.
- The pre-retraction QA checkpoint also raised KeyError because its judge catalog contained only final-wiki facts. Snapshot matching and answer judging now share a catalog that includes transient/retracted facts from all their declared gold claim propositions. No final-wiki content or product prompt was changed.
- Validation:27 focused fixture/action tests passed. Combined structural validation with the independent retention fix:690passed,1skipped,87deselected (`/tmp/mycelium-remediation/retention-and-actions-full.log`); the isolated checkout has no local AMI dataset for its presence check. Ruff and whitespace passed. New tests execute real approval/retraction transactions, including multiple target claims, stale-review invalidation, unmatched members/relations and ambiguous fixture bindings. Native acceptance reruns remain necessary; the first run's execution/QA failures are retained rather than rescored as successes.

## 2026-09-16 — Keep source-policy exclusions outside global truth review

- Product invariant: only admitted memory claims participate in canonical truth comparison. The first native daily-driver scenario produced a review against an assistant-only echo already excluded by source policy. TruthReviewer had selected all active rows, including source history, and current-build exclusions were not committed until after comparison.
- Dream now passes its exact current-build exclusion IDs through FactResolver to TruthReviewer. Both truth candidates and presentation exclude those IDs and persisted excluded_source_policy rows. This follows the existing typed retention decision; it adds no language matching or model override and retains ordinary unplaced/deferred memories as comparison candidates.
- Added regressions for persisted and not-yet-committed exclusions, excluded incoming claims, broken provenance confined to source history, FactResolver propagation, and a complete Dream containing admitted user evidence plus an assistant-only statement. The latter reaches no truth-generation call and publishes only the admitted fact. Two initial test-fixture mistakes used an unsupported ClaimRoute field and disposition; corrected to the actual route contract.
- Validation: combined suite690passed,1AMI-dataset-presence check skipped,87integration tests deselected (`/tmp/mycelium-remediation/retention-and-actions-full.log`); Ruff/whitespace pass. This repairs the retention boundary. It does not establish that the model correctly finds the intended older state or classifies every replacement.

## 2026-09-16 — Remove the unused maturity ontology

- Removed the unused SubjectScopeDefinition registry and its obsolete continuity thresholds. Kept the existing persisted human-review scope/page-state values directly. No production prompt or admission decision used these descriptions; full repository reference inspection found only a test for the retired registry. Removed that test and changed the ontology-to-model check to exercise current source discovery instead of the retired joint identity planner.
- Validation:20 ontology/identity tests passed. Combined suite with benchmark progress changes:695passed,1local AMI-data presence check skipped,87integration tests deselected (`/tmp/mycelium-remediation/probe-progress-full.log`); Ruff and whitespace passed. The first targeted command named a nonexistent identity-test file and ran no tests; corrected its paths before validation.

## 2026-09-16 — Preserve checkpoint probe progress and score actual QA

- Daily-driver checkpoints now atomically persist each probe before retrieval, before answering, before judgment, and on success/failure. A failed probe retains its completed retrieval/context and answer, records the failed stage and elapsed timings, and permits later probes to run. Cancellation is recorded and propagated. QA and execution completion distinguish expected actual QA from artifact-only observations.
- Artifact probes record the actual snapshot counts and page identities; they no longer pass a fixture's expected answer to the model judge as though the application produced it. Artifact observations do not inflate QA scores. Failed or missing retrieval cannot pass absence-of-retracted-evidence checks or establish a completed retrieval metric.
- The first retained daily scenario exposed both defects: later probe failures erased earlier results, while a page-presence artifact was judged from the expected answer despite the actual page existing. Original run artifacts remain unchanged. Older rows without explicit retrieval completion are not evidence of a completed retrieval under the revised evaluator.
- Validation: six focused progress/scoring tests cover retrieval, answer and judgment failures, continued execution, cancellation, artifact exclusion and actual run-manifest completion. Full structural suite: 695 passed, 1 skipped (AMI dataset absent in isolated checkout), 87 integration tests deselected (`/tmp/mycelium-remediation/probe-progress-full.log`); Ruff and whitespace checks passed. The active baseline remains on its captured implementation; new native runs are still required to validate the corrected adapter end to end.

## 2026-09-16 — Separate source identity names from evidence IDs

- The retained daily run put participant IDs in name aliases and omitted mandatory participant evidence. A prompt-only draft passed 14/15 checks (`subject-occurrence-contract-20260916T080258Z-165f74b1`) but still mixed the two fields. The accepted schema asks for exact supporting evidence first and names the human-language field `alternate_names`; canonical identity matching still uses its existing aliases field.
- Direct configured-model proof: 15/15 final checks across neutral small/dense participant cohorts, distinct people sharing a name, and two retained failing production requests (`subject-occurrence-contract-20260916T080751Z-b78f3df6`). There were 18 attempts and three structural failures/retries, so this is not a zero-retry result. Production now uses the proven field order, descriptions and instruction without repairing model output lexically.
- In-situ validation: `subject-occurrence-pipeline-20260916T083104Z-37636d7e`, nine fresh native routing runs passed; all 54 generation attempts succeeded. Every declared participant is represented once, separate neutral people stay separate, and complete routing returns without failures. These checks do not establish correct discovery of every co-mentioned subject, page usefulness or long-term identity continuity. Overlapping correction probes make wall timings unsuitable for cost comparisons.
- Structural suite: 695 passed, one AMI dataset skip, 87 integration tests deselected (`/tmp/mycelium-remediation/source-fields-full.log`). A preceding command named a nonexistent lifecycle test file and ran no tests; the complete suite corrected that validation invocation. Ruff and whitespace checks passed.
- User authorized stopping the remaining baseline repeats after its first completed scenario. The exact benchmark wrapper received SIGINT; the first result, second partial trial, `STOP_REASON.json`, cancellation manifest and original traces remain in `audit-daily-acceptance-20260916T072623Z-0466e118`. Earlier automatic approval had rejected stopping without this explicit instruction; no signal was sent until it arrived.

## 2026-09-16 — Named weekdays, recurring schedules and reviewed date arithmetic

- Product invariant: calendar arithmetic operates only on the model's declared relationship and an evidenced or user-reviewed reference date. It never interprets the natural-language expression. Named weekdays now declare a direction or a particular calendar week; recurring schedules preserve their pattern without becoming a single occurrence. Both weekday-relative forms require the existing durable correction preview before saving. Retrieval and wiki inspection distinguish recurring from unresolved times.
- Rejected drafts are retained. The first calendar-week-only draft passed20/27 (`weekday-declaration-contract-20260916T081450Z-3fa5a2a9`), missing Sunday-to-Monday and recurrence distinctions. A later extraction draft passed30/30, but its correction counterpart passed24/30 (`weekday-correction-contract-20260916T083234Z-71d0a290`): missing timestamps caused unresolved weekdays and invented weekday substitutions for a day-relative expression. These drafts were not integrated.
- The accepted shared calendar contract passed30/30 direct correction probes (`weekday-correction-contract-20260916T083704Z-dd5a6f95`) and30/30 extraction probes (`weekday-declaration-contract-20260916T123820Z-07b44856`), with no failed generation attempts in either. The earlier extraction run was paused at16/16 completed cases at the user's request (`...083856Z-5633a58c`); it is not counted as a complete run. Production prompt text was compared with the successful retained prompts and matches exactly. Overlapping probes make their wall timings unsuitable for compute comparisons.
- Native lifecycle: `weekday-pipeline-20260916T124510Z-ac16bef5`, three fresh stores passed encoding from distinct message dates, recurring-time preservation, review before mutation, exact reference selection, idempotent correction, retrieval of both relevant dates without the superseded date, and a final rebuild. Encoded/corrected/final snapshots, exact native requests, model/config and coverage reports are retained. One claim-routing attempt failed structural validation and retried successfully; no final scenario failed. This establishes the tested date mechanism, not general longitudinal memory quality.
- Validation:65 focused tests;708 passed, one AMI dataset skip,87 integration tests deselected in the complete structural suite (`/tmp/mycelium-remediation/weekday-full.log`). Tests cover all weekday directions, calendar/year boundaries, missing/invalid anchors, overflow, forged canonical dates, invalid schema values, recurring schedules and reviewed-correction persistence. UI build and lint passed; existing bundle-size warning remains. No server was started.

## 2026-09-16 — Replay the retained older-state truth failure

- Added a read-only snapshot replay that uses the production TruthReviewer, configured model and unchanged production prompts. Each independent trial copies the SQLite snapshot, removes cached model decisions and prior proposals only from the copy, and retains exact candidate records, comparisons, native requests, model/config and timings. The source snapshot SHA-256 is checked again after all trials.
- `benchmark_runs/truth-replay-20260916T130154Z-834ea90d` passed3/3 fresh trials against the first retained daily-driver scenario's `cp5_pending_change` snapshot. The September28 pilot statement now proposes superseding the September22 statement in every trial, with12 generation attempts and no failed attempts. This confirms the particular older-state comparison after the source-policy boundary fix; the excluded assistant echo stays outside canonical truth review.
- The archived source was unchanged. Ruff and whitespace checks pass. This narrow replay does not establish overall truth recall, a matched end-to-end quality improvement, or growing-history cost acceptance.

## 2026-09-16 — Evidence-scoped page reviews and declared chat users

- Implemented the user's choice that no-page reviews apply only to the reviewed evidence. Accepted reviews retain a canonical identity and exact manual claim/entity references. Page admission cannot cite the excluded pairs; placement schemas cannot select them. Other evidence remains eligible to support an existing or new page. Partial projection of an older combined fact now removes members that no longer belong on that page. The review UI explains this scope.
- Direct page-review proof: `page-review-contract-20260916T123941Z-76fda323` passed12/12 review-scope checks and10/12 broader page-usefulness checks. An earlier draft passed8/9 broader checks. The model sometimes declines an artifact page from maintenance details; the evidence-scoped policy permits useful independent support without forcing a page from every such detail.
- Native `page-review-pipeline-20260916T132218Z-3b6f2d29` passed9/9 across an incidental subject, an existing page with an older combined fact, and independent project support. All58 generation attempts succeeded. Before/after snapshots, exact requests and model/config are retained. This validates identity retention, the excluded claim's removal, preservation of other subjects and useful independent support. It does not validate every page or actor assignment: one incidental shelf page and a separate project-role placement remain broader quality findings.
- Earlier native runs are retained: `...125541Z-e761198c` used the wrong memory profile for a You assertion; `...125900Z-83f08b60` passed3/9 and exposed missing agent-chat participant metadata. Adding that metadata alone passed6/9 actor checks (`agent-user-role-contract-20260916T130601Z-079304da`) but sometimes bound a reported person to the author. A prompt-only clarification passed9/9 small checks (`...131046Z-0b69acb3`) yet the integrated two-profile run passed14/18 (`...131513Z-4384c484`), including omitted/incorrect author bindings and declined provisional person pages. An intermediate harness run (`...131304Z-c0d4e4ce`) stopped on a new-identity lookup error; fixed the harness, retained the partial run.
- Product invariant: source role=user identifies the configured canonical user, independently of which person a statement describes. Discovery now has a required separate declared_user field when that profile exists; other subjects cannot absorb those participant IDs. The model declares supporting claims, including none when the user only reports someone else's facts. Stores without a canonical user retain ordinary person resolution. This uses declared metadata, no language matching or post-hoc entity reconstruction.
- The required-user contract passed9/9 direct probes with9 successful attempts (`declared-user-contract-20260916T131837Z-bc4432a2`); the accepted and production system prompts match. Native `agent-user-role-contract-20260916T132028Z-3248e5c2` preserved the separate identities in all nine cases, with30 successful attempts, but passed8/9 final page checks: declining the other person's page caused incorrect placement on You. That independent routing issue remains open. A proposed routing prompt passed only9/18 (`routing-scope-contract-20260916T132533Z-6db0632d`) and was not integrated.
- Structural validation:728 passed, one local AMI-data presence skip,87 integration tests deselected (`/tmp/mycelium-remediation/declared-user-review-full.log`). Updated older mocked discovery fixtures to the declared-user schema. New tests cover evidence-scoped review exclusions, retained identity, partial fact projection, role/source filtering, source scoping, both memory profiles and required/unique/exact user evidence. Ruff, whitespace, UI build and lint passed; the existing bundle-size warning remains. No server was started.

## 2026-09-16 — Select each unreviewed truth pair once

- Product invariant: relevance for truth comparison is symmetric. The candidate selector now considers each exact unordered pair of incoming statements once and omits pairs already covered by an active human-review proposal. It still considers every unreviewed candidate across the admitted active history, irrespective of page ownership, placement or cohort boundaries. Unused candidate records are removed from each request after applying these exact-ID exclusions. No semantic similarity cutoff or top-K cap was added.
- Structural coverage tests span multiple incoming/history batches and forced context-budget splits. They prove complete coverage exactly once, exclusion of only the specified reviewed pairs, and no generation when only reviewed/self pairs remain. Existing lifecycle tests now require zero candidate or comparison calls for an unchanged pending review. Updated the immutable replay wrapper to forward the exact exclusions.
- Native `benchmark_runs/truth-pipeline-20260916T134002Z-854c6098` passed18/18 owner-independent lifecycle cases: cross-owner replacement, same-batch contradiction, reversed chronology, independent plans, different people and different events. All48 generations succeeded;12 additional trace rows are cache hits. Pending-review repeats made no truth selection/comparison generations. Native SDK recording and a completion manifest are now retained by the experiment.
- Validation:15 focused tests;731 passed, one local AMI-data presence skip,87 integration tests deselected in the full suite (`/tmp/mycelium-remediation/truth-coverage-full.log`); Ruff/whitespace pass. The optimization removes provably redundant pair decisions. First-time scans still grow with admitted history; no matched whole-benchmark speed or quality claim is established.

## 2026-09-16 — Clarified acceptance expectations

- The user confirmed that extraction and search should remain behind Build Memory. Capture-before-Build should be assessed for durable source retention, not successful claim retrieval.
- The user confirmed that useful independent context may justify a page from one conversation. Cross-conversation continuity is not a mandatory page-creation threshold.
- The daily-driver fixtures will be versioned around these decisions; the original fixtures and baseline results remain historical evidence. The remaining attribution, organization, retrieval/QA and full matched-run gates are unchanged.

## 2026-09-16 — Score grouped truth proposals using current artifact fields

- The daily checkpoint evaluator still read singular incoming/target claim fields even though snapshots serialize the production plural lists. It now checks exact membership in the incoming and target sides, including grouped reviews, and requires the declared relation/status and exactly one matching proposal. Pending-review coverage includes every member on both sides. No legacy field fallback was added.
- Validation:41 focused checkpoint, action, fixture and probe-progress tests passed (`/tmp/mycelium-remediation/daily-review-evaluator.log`). Regressions cover grouped members, unrelated claims, wrong sides/relation/status, missing claim matches and ambiguous duplicate reviews. An initial test attempted to construct an invalid empty production proposal; the dataclass correctly rejected it, and the test now uses valid proposals and absent reviews. Ruff and whitespace checks pass.
- Read-only re-evaluation of the retained first daily trial's `cp5_pending_change/snapshot.json` now correctly recognizes the new-date claim's pending review. The older-date member and expected old/new pair still fail: this is the original product failure, not a scorer success. Source SHA-256 was unchanged; the sidecar is `/tmp/mycelium-remediation/daily-review-checkpoint-replay.json`. Original archived reports remain unchanged, and this correction establishes no new model-quality gain.

## 2026-09-16 — Version daily-driver acceptance around Build Memory

- Added v2 copies of all three daily-driver scenarios using the user's two explicit decisions. Before Build, checkpoints require durable source capture, zero extracted claims and pending extraction; the query must remain unanswered. After the first Build, checkpoints require complete extraction and searchable supported claims. They permit independent pages without requiring multiple conversations or forcing every claim onto a page. Added a real post-Build question in place of the obsolete page-count observation. Later gold claims, checkpoints, wiki facts and reference pages are unchanged.
- Capture evaluation checks exact segment text, labels, order, speaker/role, unique native IDs, source type, participants, fixture identity and declared timestamp. It survives a close/reopen test and requires no model call. Changed/omitted/duplicated evidence and premature extraction are explicit failures. First-build evidence can be routed or deferred, but cannot be failed, excluded or still pending.
- Discovered a separate malformed v1 paraphrased source: an unquoted comma in a YAML flow mapping turned the rest of a sentence into an unexpected key. The app received only “It must stay on my computer”. V2 restores the full literal sentence; schema version2 rejects unexpected segment fields and empty/non-string text. The original v1 files are unchanged. This source repair makes that transfer case an unmatched input comparison; changed v2 aggregate acceptance rules also cannot be reported as model improvement.
- Validation:47 focused tests passed (`/tmp/mycelium-remediation/daily-v2-acceptance.log`); all three v2 fixture validators, Ruff and whitespace checks pass. Frozen baseline checkpoint re-evaluation leaves source hashes unchanged: pre-Build capture passes all six checks; the first-Build checkpoint still misses two semantic claim matches. The sidecar is `/tmp/mycelium-remediation/daily-v2-baseline-sidecar.json`. No old report was overwritten and no new end-to-end benchmark quality result is claimed.

## 2026-09-16 — Recover after host shutdown; replace attribution references atomically

- The shutdown cleared `/tmp/mycelium-remediation/followthrough`, including uncommitted experiments and local test logs. Both committed branches survived at `65d03a1`, as did the benchmark requests/results in the main checkout. Continuing in the persistent `.worktrees/audit-followthrough` worktree; validation logs now live under `test_outputs/audit-followthrough`. Unrelated user edits are preserved. Read-only escalated `/api/tags` confirmed the configured host model is reachable; no server was started or reconfigured.
- The interrupted thinking experiment `attribution-placement-contract-20260916T145808Z-61862216` saved 39 result rows, but later rows are host connection failures after disconnection. Its 18/39 count is not a completed model-quality assessment. The earlier no-page integration `page-review-pipeline-20260916T141258Z-32821c8c` records 5/9 passing in the retained completion file; use this saved result, not the earlier provisional 8/9 interpretation. Original artifacts remain unchanged.
- Product invariant: automatic attribution replaces the complete reference set for the exact successfully processed claims; display names never identify references. Exact-ID saves now preserve distinct people sharing a name. Transactional replacement retires old automatic references (including disappeared roles or an empty new decision), retains the replacing build ID, and preserves manual decisions and unprocessed claims. A failed write rolls back both retirements and new references. Human merge/review paths already supersede exact references explicitly.
- Dream commits replace references only for successful scope decisions; corrections use the same atomic mechanism. A failed revision keeps the successful initial attribution; a successful empty revision removes it. This addresses stale attribution and same-name overwrites without interpreting natural language or adding compatibility paths.
- Validation: 73 focused persistence, commit, identity and lifecycle tests passed; full structural suite 764 passed, one AMI-data presence skip, 87 integration tests deselected (`test_outputs/audit-followthrough/reference-full.log`). Regression coverage includes same-name identities, manual retention, empty replacement, exact claim/run scope, duplicate IDs, idempotence, failed revision and injected disk-write rollback. Ruff and whitespace checks pass. New model-contract experiments remain separate from this persistence commit.

### Benchmark assessment follow-up

Manual inspection of the frozen daily `cp2_first_dream` snapshot found both propositions previously marked missing: `claim-fc2b607ecf841921` says the user wants a desktop app to protect sensitive client information, and `claim-0aa48d3ed84788ea` cites meetings containing sensitive client information. The lexical/envelope matcher selected the browser-extension refusal for both gold claims and rejected the matches. These are scorer false negatives. Source-grounded semantic alignment remains necessary before relying on aggregate benchmark metrics; production extraction must not be changed to satisfy the lexical matcher.

## 2026-09-16 — Attribute source statements before selecting page presentation

- Product invariant: who a statement describes is independent of page availability. The new required claim/entity matrix distinguishes described subjects, source participants who only report information, and unrelated entities. A separate presentation contract assigns a typed section to every admitted, described, nonexcluded page and selects a primary page only from that set. Empty page sets skip presentation generation while preserving attribution. Exact human no-page decisions exclude only their claim/entity pairs. No lexical attribution or model-output repair was introduced.
- The attribution input contains resolved identities/participant bindings, claim text and cited source evidence. It excludes prior extracted mentions, automatic projection metadata and human identity-review records; the identity stage has already applied those reviews. An identity review identifies an occurrence, not every semantic participant in a statement. Attribution is retained in the work-unit record and stable subject/context references, including unplaced subjects. Requests are bounded by claim/entity pairs and split further to fit context; failures remain local and explicit. Removed the old routing adapter and its obsolete typed-schema overlay.
- Recovered direct proof: `attribution-contract-20260916T224610Z-8d84df10`, 39/39 attribution and eligible-page sets, 38/39 primary-page choices, 66 successful generations totaling 199.21s (includes cold loading). The remaining primary-page mismatch chose the project instead of the person for an action involving both; both supported pages were retained. System prompts match all 66 retained requests exactly. No reasoning override was adopted. Earlier combined attribution/placement and primary-role drafts had semantic failures; their retained results are not acceptance evidence.
- Frozen earlier three-claim failure: `attribution-frozen-replay-20260916T225048Z-7aaa6ba2`, 3/3 passed, six generations/35.32s. First integration: `agent-user-role-contract-20260916T225621Z-0f201c0c`, 18/18 across both memory profiles, including both endpoints of user relationships; 87 generations/193.23s, no failed attempts. This separates attribution from page admission, permitting deferred but correctly attributed evidence when no profile page is admitted.
- The first page-review integration `page-review-pipeline-20260916T230113Z-fb7dd8fa` passed 7/9. Two failures omitted the user from a spelling-check action when old identity-review metadata was present in attribution input. The proposed minimal input passed 3/3 replays of that exact failing request (`minimal-attribution-replay-20260916T230512Z-cd8d9347`, six generations/32.05s) before integration. Original request hashes were unchanged. Final fresh integration `page-review-pipeline-20260916T230651Z-408dabc6` passed 9/9, 67 generations/202.90s, no failed attempts. Review exclusions, independent supporting evidence, user attribution and combined-fact projections all pass.
- Limits: the page-review experiment still occasionally admits an incidental shelf page; it does not prove general page usefulness. Primary-page preference is not perfect, and no matched full-benchmark quality/cost gain is established. Broad identity continuity, stale prose, source inspection in QA and daily/LoCoMo acceptance remain open.
- Validation: 772 structural tests passed, one AMI-data presence skip, 87 integration tests deselected (`test_outputs/audit-followthrough/attribution-final-structural.log`); focused native-schema, identity/review and routing checks also passed. Tests cover exact pair coverage, allowed reporting roles, immutable page sets, actual per-type section domains, empty domains, preserved deferred attribution, bounded cohorts and local failures. Ruff/whitespace pass. Updated current probe callers and daily-driver guide to version2. No UI code changed.

## 2026-09-16 — Retire unused identity decision contracts

- Removed the unused combined identity-plan schema, its reviewed-identity overlay, and four obsolete prompt templates. The current source discovery, subject-by-subject matching and explicit review-assignment contracts remain the production path. Exact registry metadata attachment and reviewed-occurrence expansion remain, with current router/review tests retained.
- Removed obsolete schema tests and the old direct-schema replay. The real staged-identity revisit test remains. Current neutral review cases now live in `benchmarks/experiments/identity_review_cases.py`; three current probes import them without importing a retired executable. Removed obsolete identity/rename modes from the older compact-contract probe. Historical benchmark artifacts remain untouched.
- Validation: 22 focused current identity/review tests passed; all four affected experiment modules import; Ruff and whitespace checks passed. Full structural result is retained in `test_outputs/audit-followthrough/identity-cleanup-full.log`. That run also includes the uncommitted experimental claim-assessment tests; their semantics are not accepted or integrated into the benchmark runner.

## 2026-09-16 — Reuse identity evidence reads within one preparation

- Identity record preparation now loads each exact claim/source ID once per synchronous call and reuses each source's segment-ID set for citation validation. The cache ends with that call, so the next build observes edits, supersession, retractions and missing evidence. No candidate ranking, evidence selection, prompt or semantic decision changed.
- A 100-entity shared-evidence comparison against `498ff2a` produced identical complete identity records. Claim reads fell from800 to2 and source reads from800 to1 (`test_outputs/audit-followthrough/identity-read-comparison.json`). This measures repeated-read removal, not a full ingestion or model-time speedup; history scans remain.
- Validation:23focused identity preparation/router tests passed (`identity-reads-focused.log`), including fresh-call invalidation and provenance failures. Ruff/whitespace passed. The preceding cleanup full suite finished779passed/1AMI-data skip/75integration deselected; the drop in deselected tests is the removal of12 obsolete direct-schema replays, not a new integration pass.

## 2026-09-17 — Close interrupted benchmark stage statuses

- The authorized diagnostic `audit-daily-v2-followthrough-498ff2a` was stopped after saving its second-build snapshot. It reproduced a split between an unnamed Project and its later Artifact name, plus accepted content under Needs Review. The run lasted650.47s and is incomplete; `STOP_REASON.json`, requests, snapshots, partial QA and the cancellation remain retained. Its raw manifest exposed another reporting bug: execution ended, but encoding/QA still said running.
- The shared invocation wrapper now changes only running encoding/QA/scoring/assessment stages to incomplete on a terminal exception or cancellation. Completed, disabled and blocked stages, progress counters, original errors and elapsed accounting remain intact. Historical manifests were not rewritten.
- Validation:26focused benchmark/progress tests passed (`stage-completion-focused.log`), including RuntimeError and cancellation after partial progress with both running and completed encoding. Full structural suite789passed/1AMI-data skip/75integration deselected (`section-stage-full.log`); this includes pending content-section and experimental grader work and is not a semantic acceptance pass.

## 2026-09-17 — Keep automatic content out of workflow-owned sections

- Product invariant: model-chosen content sections must not control review state or navigation. The ontology now marks Needs Review and Memory Map as managed sections. Both page routing and fact grouping exclude them from their prompts and native schema domains; their renderers and explicit uncertainty/review state remain available. In the diagnostic daily run an ordinary pending naming choice was labeled nonauthoritative solely because it landed in Needs Review. Memory Map would also discard any facts routed to that navigation-only section.
- Direct page contract: `content-section-contract-20260916T235548Z-092c1ebf`,21/21,21calls/40.14s. The first probe stopped after3successful calls because its You fixture used a nonsingleton ID (`...235437Z-446bfbb5`); retained, then corrected before a fresh run.
- First native integration `content-section-pipeline-20260916T235910Z-dce5f705` passed1/3,30calls/134.25s. Routing chose appropriate content sections, but downstream fact grouping still exposed managed sections and changed placements back to Needs Review. This was a separate real path, not an attribution failure.
- Before integrating the grouping restriction, replayed the exact failing neutral grouping request three times with the restricted domain (`content-group-section-contract-20260917T000333Z-51960da6`,3calls/7.65s, original request hash unchanged). All three retained both independent claims in suitable content sections. Its overly narrow assertion required Priorities & Plans for both statements and reported0/3; inspection showed Current Context was a valid choice for the unnamed-project state. Those original results remain unchanged; the evidence supports the section boundary, not one preferred editorial heading.
- Final native integration `content-section-pipeline-20260917T000455Z-282ec4b3` passed3/3,31calls/136.79s. All placed claims were published, no false review/navigation assignments remained, and every build finished without backlog. Incidental team/greenhouse pages still varied; page usefulness and broader organization are not accepted by this test.
- Validation:37focused grouping/routing/ontology tests passed;789structural tests passed/1AMI-data skip/75integration deselected (`content-section-final-structural.log`). Regressions reject both managed sections in the downstream grouping schema as well as every typed page-routing domain. The structural total still includes uncommitted experimental grader tests. Ruff/whitespace passed.

## 2026-09-17 — Preserve identities across discovery categories and establish final names

- Product invariant: an inferred discovery category is not an identity boundary. Ordinary source subjects now consider the bounded semantic registry across types; exact declared speaker occurrences retain the people-only domain. Candidate count remains24 and canonical You remains required when present. Existing matches retain their canonical type. Final new/review names and aliases come from the source-backed identity decision rather than being overwritten by discovery proposals.
- Identity matching now returns the preferred title for an existing identity. The old nullable rename instruction confused first naming and spelling correction with retaining the registry title. An exact returned/stored title equality is only a no-op update; it does not decide identity or natural-language equivalence. Human bindings retain their authoritative stored title, and competing actual name changes still fail explicitly.
- Initial direct boundary proof: `identity-boundary-contract-20260917T000203Z-20ebf842`,24/24,43.63s. First native boundary run `identity-boundary-pipeline-20260917T001539Z-68fe8c9a`,63calls/142.57s, raw9/12: its harness expected a nonexistent entity_match record type. Source/work-unit review showed11/12 intended outcomes, with one real first-name failure: Aurora remained an alias of Inventory Helper Project. Original results are retained.
- The nullable clarification `initial-name-contract-20260917T002053Z-77ad6879` passed9/12,19.60s; all three spelling-correction outputs still wrongly returned null. Required preferred titles passed12/12 in `preferred-name-contract-20260917T002530Z-3fb1b334`,21.76s, including the frozen first-name request, unchanged name, nickname and correction. The broader first integrated replay then exposed an unidentified visitor incorrectly marked new despite an unresolved-identity explanation. A clearer identity-established versus unidentified decision contract was proven before adoption: `identity-resolution-boundary-contract-20260917T003129Z-fbcdaa62`,24/24,44.38s. A preceding harness launch failed before any model call because its output directory was not created; its log is retained.
- Final fresh native run `identity-boundary-pipeline-20260917T003245Z-364e690c`:64calls/144.80s, zero failed attempts. Raw11/12; all12 identity boundaries pass source review. The remaining raw failure required exact title Nora, while the model correctly created the distinct person Nora (Colleague), retained the project e1, and cited the source distinction. `source_review.json` records the limitation without modifying raw results. The maintained namesake check now tests distinct person identity; source-spelling and first-name checks remain exact. This does not establish general extraction, page usefulness or growing-registry quality.
- Validation:793 structural tests passed/1AMI-data skip/75integration deselected (`test_outputs/audit-followthrough/identity-source-full.log`). This includes pending retrieval changes and32 unintegrated experimental grading tests. Focused tests cover cross-type candidates, speaker domains, final source names, immutable canonical type, explicit mock registry titles and invalid native name outputs. Ruff/whitespace pass. No lexical semantic recovery or compatibility schema was added.

### Unaccepted benchmark assessment experiments

- Frozen daily cp2 inspection showed lexical claim-matching false negatives; these must not become extraction requirements. New source-grounding and reference-containment drafts remain outside the runner. Their structural tests do not establish model accuracy.
- Retained direct runs `claim-alignment-contract-20260916T231221Z-1ef77acb`22/27, `...231502Z-b00e71b7`22/27, `...231831Z-f84b1eaa`23/27. The split-call `...232122Z-385eab22` reported27/27, but its assertion checked only the first matching candidate and missed an extra false positive; that claimed perfect result is invalid. Frozen cp2 replay `claim-assessment-frozen-replay-20260916T233514Z-4100721b` found the actual desktop/privacy information but falsely counted a browser-extension refusal as desktop choice in2/3 trials. Isolated-pair follow-up `claim-pair-contract-20260916T233833Z-b7e10ca4` passed23/27. None is adopted as a trusted scorer. Original artifacts are unchanged; full source/wiki review and comparable complete benchmark runs remain required.

## 2026-09-17 — Ground selection and initial answers in exact cited source lines

- Product invariant: retained source wording and the canonical interpretation travel together under one evidence budget. Retrieval now attaches only exact cited segments for retained records, including consolidated members. Whole records have priority; whole source segments follow, omissions are explicit, shared excerpts retain every claim link, and supersession/review/retraction metadata remains visible. Neighboring dialogue is still an explicit inspection and requires a retained cited anchor. Workspace refresh unions current automatic excerpts with refreshed inspected context using exact IDs/revisions.
- Direct QA controls `source-grounding-controls-20260917T001053Z-8b528b66`:81 answers, all zero tool calls. Source review found9/27 claims-only answers correct,24/27 with cited lines,27/27 with oracle lines. The cited arm still missed the intentionally absent initial record; the oracle supplied it. QA times per27 were10.49/10.13/10.45s. These controlled tools isolate answer behavior, not real search recall.
- First real retrieval run `source-grounding-pipeline-20260917T003554Z-60800871` completed27 cases/54 paired answers. Supplying sources only after selection was insufficient: admission discarded date/place claims before seeing their source-only details. Source review found15/27 claims-only and18/27 cited answers correct.24 selection calls/27.87s;54 answer calls/22.99s; no failed attempts. This is a retained failed integration hypothesis, not an accepted quality gate.
- Proposed source-backed candidate input then passed27/27 direct production selector checks in `source-backed-selection-contract-20260917T004110Z-e2af3c97`,28.60s. It admitted source-supported dates, places, conditions and negation while rejecting an unrelated person's record and not inventing an unstated event date. The prompt/schema did not change. A preceding harness launch used an incorrect wiki attribute and failed before selection; its log remains. Integrated the shared evidence rendering into admission and removed the separate duplicate admission/timing formatter.
- Final fresh native retrieval/QA `source-grounding-pipeline-20260917T004240Z-f809c580`:27cases/54answers complete. Every answer was reviewed against its retained question/source:19/27 claims-only,27/27 cited-source. Claims-only made4 successful inspection calls; cited answers needed none. QA totals19.514s versus10.393s; shared selection24calls/29.448s. Fresh tiny-store retrieval median1.234s/p952.006s. `source_review.json` preserves per-case assessments and limits. These are deliberately seeded neutral claims; neither extraction quality nor large-corpus recall/latency targets are established. Absent search candidates and budget omissions remain visible limitations.
- Validation:44focused source/record/workspace tests passed. Full suite802passed/1AMI-data skip/75integration deselected (`test_outputs/audit-followthrough/source-grounding-final-structural.log`), including the separately pending truth-read tests and32 experimental grading tests. New coverage checks exact-budget retention, oversized whole segments, no neighboring-source leak, no orphan source for omitted records, superseded state, shared citations, and refreshed replacement provenance. Ruff/whitespace passed.

## 2026-09-17 — Reuse source reads during truth-record preparation

- Truth preparation now shares exact source reads and segment-ID indexes within one synchronous call. The next review creates a fresh cache, so source edits, retractions and missing provenance are observed. Candidate sets, pair coverage, prompts, schemas and decisions are unchanged.
- A parity comparison against5ae98bc produced identical complete records for100/1000/5000 claims sharing one source (`test_outputs/audit-followthrough/truth-read-comparison.json`). Source reads fell100/1000/5000→1; at5000 claims preparation fell428.30ms→6.77ms. This synthetic in-memory measurement excludes database and model work; it does not reduce the remaining all-history model comparisons or establish total build speed.
- Validation:35focused truth/retrieval checks passed, including5new preparation/invalidation cases (`truth-read-and-retrieval-focused.log`). The full suite including this change passed802tests/1skip/75integration deselected (`source-grounding-final-structural.log`). Native semantics were unchanged; no redundant host rerun was used for this exact-read optimization. Ruff/whitespace passed.

## 2026-09-17 — Source review packs and honest benchmark assessment status

- Daily-driver wording-based associations are now explicitly lexical diagnostics. Reports require source review and no longer infer release readiness from those associations. Every source-linked claim candidate is exposed; proposition coverage is counted separately from generated claim granularity. A shared evidence label establishes neither entailment nor page usefulness.
- Added `daily-driver review` to export complete source/wiki snapshots, exact input digests, all evidence-linked candidates and successive artifact changes. Missing checkpoints and unavailable future reference evidence remain explicit. The exporter invokes no model, never changes original artifacts and refuses to overwrite reviews. Native source/segment pairs remain distinct even when the encoder splits one fixture turn into several segments.
- Unaccepted semantic-grader drafts and their tests are preserved under `test_outputs/audit-followthrough/unaccepted_claim_assessment/`, outside active code. Earlier apparent passes were invalidated by false positives and insufficient assertions; no automatic semantic grader was accepted.
- Export validation first exposed YAML date serialization and then a real split-turn fixture-label assumption. Both were fixed, with failed logs retained. Actual CLI export completed at `test_outputs/audit-followthrough/daily-source-review-first` for cp1–cp3, explicitly listing six missing checkpoints. Focused tests passed83 before the split-turn regression; final full structural suite passed787/1skip/75integration deselected (`source-review-reporting-full.log`). The count excludes20 archived experimental grader tests. Ruff and whitespace checks passed.
- Frozen production run `audit-daily-v2-source-grounded-20260917` at0088894 was deliberately stopped after810.12seconds with three saved checkpoints. Its manifest correctly marks execution failed, encoding/QA incomplete. The authorized stop reason and raw requests remain. This is not a full acceptance result or a matched end-to-end improvement claim.
- Source inspection found the first build's five claims accurate and the desktop answer correct with initial source evidence. The second build exposed failures beyond the narrow identity probes: the unnamed project split from its later named artifact, a service's preferred spelling changed without support, requirement details became separate pages, the old unnamed-state claim remained current, and local claim aliases leaked into fact prose. First-attempt discovery also omitted required participant aliases and retried. These findings reopen broad J/K/L/M acceptance; small neutral passes do not supersede them.

## 2026-09-17 — Explicit assignments for every declared source speaker

- The stopped daily run recorded107 generation attempts/794.963seconds, including5 failed discovery attempts/53.299seconds. All five failures omitted a required speaker ID from a subject's mixed evidence array. These were validated failures and retries, not silent data loss.
- Discovery now returns a required `participant_subjects` field keyed by every declared external speaker occurrence, pointing to a returned person subject's exact local ID. Canonical user occurrences retain their separately required field. Supporting claims remain separate from speaker assignments: reporting-only speakers can have no claims, repeated occurrences may bind the same person, and only the model decides that binding. The planner attaches those explicit decisions; it never reconstructs a missing speaker from names.
- Direct configured-model proof `participant-subject-contract-20260917T011803Z-2e05ce64` completed21/21 with21calls/164.928seconds and zero retries. All assignments were reviewed against five neutral cases and two retained failed requests over three trials. Integrated prompt and schema were checked identical to the proposed contract. The new field is native-schema required; references to absent/nonperson subjects, duplicate subject IDs, ungrounded subjects and mixed participant/claim IDs fail validation.
- Native routing `participant-subject-pipeline-20260917T012652Z-cb05dc89` completed9/9,51calls/138.857seconds, zero retries. Required bindings were correct in all nine; reporter ownership and repeated-speaker identity passed all six corresponding cases. The three same-name cases kept teacher and architect distinct but also exposed an unresolved canonical-user duplication: the teacher was separately discovered alongside declared_user, and the identity matcher lacked that participant-role context in its scoped input. Source reviews preserve this limitation; this is not a passed complete identity gate.
- Validation:67focused pipeline checks/1skip and13schema checks passed. An initial full run exposed an ontology test assuming every schema definition is an entity; updated it to inspect entity definitions. Final structural suite788passed/1skip/75integration deselected (`participant-bindings-full-final.log`); Ruff/whitespace passed. Explicit fixture builders were updated, not product compatibility paths.
- Naming/continuity experiments remain outside production: initial quoted-name contracts still miss first names or choose a description despite a given name; later variants can exhaust retries on copied spelling. The source-fidelity validator correctly rejects unsupported quotations, but the proposal has not met semantic acceptance. Retained runs start `identity-quoted-name-contract-20260917T011034Z`, `...011321Z`, `...011554Z`, and `...012107Z`. A separate same-model reasoning experiment is measuring the quality/cost tradeoff without changing production settings.

## 2026-09-17 — Carry current identity context and scope prose inputs

- Identity matching now receives every participant binding from its cited sources, even when the discovered mention itself lacks a participant assignment. A declared user role carries canonical_entity_id=you only when that profile exists. This supplies authoritative source context without choosing identity by names or leaking unrelated sources.
- Direct configured-model `identity-role-context-contract-20260917T014228Z-183fc587` passed12/12,12calls/22.699seconds, zero retries. Native rerun `participant-subject-pipeline-20260917T014735Z-5fd057f9` completed9/9,51calls/133.937seconds. All three former duplicate-teacher identities now resolve to You; other-person and repeated-speaker boundaries hold. However, downstream attribution still calls the user reporting_only on the compound teacher/architect statement in all three trials, omitting its pottery-club information from You. The retained source review distinguishes the fixed identity boundary from this still-open attribution failure.
- Truth comparison now sees the current build's exact successful reference replacements before commit, alongside new entity/placement context. Empty replacements clear old automatic references; manual reviews and unprocessed scopes survive. Invalid/duplicate/out-of-scope references and references from another build fail closed. Preparation leaves persisted records untouched. A Dream integration assertion verifies that comparison receives the same reference IDs later committed.
- Paired direct truth checks `truth-staged-identity-contract-20260917T014252Z-cf4b8b8a` passed12/12 in both persisted and staged arms,42calls/21.640seconds; they establish no causal quality gain. Native `truth-staged-identity-pipeline-20260917T015548Z-42b18a61` passed12/12,21calls/35.560seconds, zero retries. Naming/venue transitions produce correctly directed pending proposals; compatible detail and separate applications do not. Both claims remain active pending human review, as designed. Complete source/wiki snapshots are retained; broader candidate recall and growth cost remain open.
- Prose rendering now receives the same canonical records as an ordered list. Membership has already been decided, so temporary claim aliases serve no purpose in that call. Canonical statements and temporal fields remain intact, and stable ordering preserves durable text reuse. No string stripping or semantic fallback was added.
- Paired prose probe `fact-prose-input-contract-20260917T014314Z-d9b2841c` completed24outputs/15.879seconds, zero retries. All outputs were inspected: both arms preserve conditions, dates, quantities and an actual identifier inside statement text. The original retained request leaked aliases, but neither arm did in these repeats; this is not a measured leak-rate improvement. Some responsibility prose remains repetitive.
- Native `bounded-fact-pipeline-20260917T015221Z-c90d9e76` passed9cases across27builds,50new generations/150.214seconds plus3 cache hits, zero failures. All13 inventory items and the conditional commitment survive. Every third build makes zero generations; five persisted render requests reuse identical text. Ceramics facts remain separate in one trial, so broad concision/organization is not established.
- Validation:68focused checks and795full structural tests passed/1skip/75integration deselected (`current-context-focused.log`, `current-context-full.log`). New checks cover source-scoped participant context, exact staged replacements, empty scopes, retained manual reviews, rejected malformed/current-build mismatches, no preparation writes, and complete temporal prose inputs. Ruff/whitespace passed.
- Rejected reasoning experiment `identity-quoted-name-contract-20260917T013007Z-49f2e09f` was stopped after its first six-case trial. Five cases eventually returned usable decisions; the retained service-name case exhausted retries. The13 completed attempts cost674.811seconds, including8failed attempts/365.869seconds; a started repeat was cancelled. This small unmatched-completion comparison does not justify changing production inference. Configured settings remain unchanged. Unaccepted naming drafts are archived under `test_outputs/audit-followthrough/unaccepted_identity_naming/`; no quoted-name mechanism was integrated.

## 2026-09-17 — Preserve asserted subjects and separate identity from page categories

- Recovery confirmed the committed tree and saved experiments survived; read-only escalated host access succeeded. No server was started or stopped. Continued within the existing authorization for finite tests, cancellation and validated commits.
- Attribution now states the assertions involving each resolved entity before assigning described/reporting_only/unrelated. All relations allow an explanation; only described permits nonempty assertions. Native domains still require every exact claim/entity pair and restrict reporting_only to declared participants. Assertions are bounded, retained in the work unit, and never promoted into additional canonical claims. The model decides meaning; validators enforce structural consistency rather than interpreting words.
- Direct accepted proof `attribution-assertion-contract-20260917T021905Z-66124805`:42/42,42calls/117.909seconds, zero failed attempts. Reviewed all described sets and assertions against retained sources, including ownership, explicit relationships, self-reports, unrelated entities, reporting-only speakers and the compound named-user failure. Production prompt/schema were checked identical before native validation. The earlier current-contract arm scored39/42 in95.911seconds under the same configured settings. This narrow improvement costs about23% more generation time with no extra calls; it is not a full benchmark quality/cost result.
- Retained failed hypotheses: inline participant context `attribution-binding-context-contract-20260917T020133Z-3523ae19` left both arms39/42 (84calls/188.469seconds). Reason-first union `...assertion-contract-20260917T020529Z-198a15ff` scored26/42: choosing a string explanation could preclude its null-only unrelated branch. Flat explanations alone `...021004Z-f8ab0557` scored41/42 and still missed one named-user statement. The first explicit-assertion draft `...021250Z-7a9cfebf` scored42/42; some excerpts used source wording rather than canonical wording. The accepted contract treats assertions as bounded explanations, not literal quotations. Drafts are archived under `test_outputs/audit-followthrough/attribution_contract_development/`; original requests/results remain intact.
- Native attribution controls `participant-subject-pipeline-20260917T022139Z-16c53480`:6/6,32calls/78.465seconds. Named-user cases `...022345Z-bd236cc5`:3/3,18calls/54.907seconds. No failed attempts. The user's pottery-club claim reaches You in all three repeats; the architect stays distinct; reporter ownership and repeated-speaker identity remain correct. One Omar control still gets no page, and You section choices vary. These are open admission/organization findings, not attribution failures. The first invocation misspelled a case selector and omitted the named-user cases; the separate run supplies them. Unknown selectors now fail explicitly.
- Identity matching now omits inferred entity types and page publication state while preserving names, identity evidence, source-role context and human reviews. Product invariant: classification and page state do not establish whether two mentions identify the same subject; canonical type remains unchanged downstream.
- Paired direct `identity-input-scope-contract-20260917T021511Z-6924fe04`:60calls/117.142seconds, zero failures. Identity decisions improved from28/30 to30/30. Full identity-and-name checks were25/30 versus26/30: both arms still corrupted the retained long-context service spelling in all three repeats, and the scoped arm once kept a descriptive title despite recognizing the newly named project. Naming fidelity is separately open. Native `identity-boundary-pipeline-20260917T022537Z-c8bbac95` passed12/12,64calls/164.675seconds, zero failed attempts, with source/store snapshots. It preserves project continuity/type, distinct products/people, and new-service spelling in those neutral cases; it does not cover the failing long-context service rename.
- Validation:84 focused checks and799 structural tests passed/1AMI-data skip/75integration deselected (`asserted-attribution-focused.log`, `asserted-attribution-full.log`). Tests cover bounded asserted content, relation consistency, complete domains, source-context preservation, and removal of presentation metadata without input mutation. Source-review sidecars record the native limitations. Ruff and whitespace checks pass. Full daily-driver/LoCoMo and longitudinal quality/cost gates remain outstanding.

## 2026-09-16 — E1: resumed audit plan and truthful timing labels

Resumed the consolidated plan with the user's existing authorization for finite tests and commits. Kept the benchmark-as-guidepost and complexity gates in the plan; no production inference changes in this tranche. Renamed per-answer `memory_construction_time` to `retrieval_seconds` throughout current adapters/reports. Initial retrieval and answering (including later tool use) now have distinct labels; offline build cost remains in operation traces. LoCoMo protocol 6 rejects old checkpoints instead of silently mixing schemas. The MAB adapter removes the upstream scorer's injected zero construction metric and retains second units in averages. Historical results remain untouched.

Validation: 29 benchmark tests passed (`test_outputs/audit-followthrough/e1-timing.log`), plus the MAB reporting test; changed-file Ruff and whitespace checks passed. E1 remains open for current-contract probe cleanup, question-scoped rubrics, and the frozen comparison inventory. No added model calls, schemas, retries, or persisted production artifacts.

## 2026-09-16 — E1: retire obsolete production contracts

Removed unused monolithic truth/synthesis APIs and four templates, with redundant structural tests of those obsolete shapes. Current `truth_contract` and bounded `fact_groups` tests retain exact-ID, complete-accounting, scope, membership, and rendering invariants. Useful opt-in probes now invoke the current pair-comparison path and grouping/rendering builders. Synthesis checks preserve meaning, modality and distinct occurrences without demanding one exact group count or layout. Retired three experimental runners that depended on the removed contracts; their source is recoverable at `3a48d39`, saved outputs remain intact, and the experiment guide points to current runners. No live production inference changed; approximately 880 lines of obsolete code/tests removed net, no additional production calls or response fields.

Validation: host-access structural suite 782 passed, one AMI-data skip, 75 integration deselected in 30.08s (`test_outputs/audit-followthrough/e1-current-contracts-structural-host.log`). The initial sandboxed run stalled inside claim-index tests and was cancelled; the host rerun completed. Migrated configured-model probes: 27 passed, one failed, four deselected in 133.27s (`e1-native-contracts.log`, per-case artifacts in `e1-native-contracts/`). The remaining failure is the mixed-history relative-date case: two identical "last week" event statements cited March versus October were classified as same scope. Both remained `no_change`, so no evidence was discarded, but event distinction is wrong. This is retained as an open C1 semantic failure, not hidden or weakened. Changed-file Ruff and whitespace checks passed. Full native acceptance is not claimed.

## 2026-09-16 — E1: question-scoped evaluation, fixed inputs and complexity inventory

Product need: a useful concise answer should pass the question it actually answers, while an unrelated answer, guess, missed part or invented extra assertion should fail. The old daily-driver verdict checked required IDs and answerability but could accept irrelevant answers when no fact IDs were required. The first-build application-form probe also required unrelated purpose/privacy content; it now requires form only, with privacy/purpose covered by their separate questions. No production prompt contains fixture vocabulary.

Direct configured-model proof before integration: `question-judgment-contract-20260917T033736Z-cb1bcb19` compared the old evaluator (21/36 controls correct) with a question-level verdict (34/36). A wording-only clarification (`...20260917T034120Z-79ff9278`) still missed two unsupported-extra cases. The model described the unsupported addition in its rationale while accepting the requested fact. The accepted contract therefore separates question correctness from one flat `unsupported_assertions_present` boolean in the same call; no critic/retry stage. `question-judgment-contract-20260917T034344Z-b24c2fd6` passed 45/45, including new supported-extra and unsupported location/attribute counterexamples. Raw proposals/requests/results are preserved there. The temporary proposal runner was retired; maintained `daily_judgment_probes.py` now calls the actual evaluator. Native `daily-judgment-contract-20260917T034647Z-88c460bd` passed 15/15. These are development controls, not held-out performance or proof that model judgment replaces source review.

Complexity: zero added production calls, branches, schema nesting or persisted production artifacts. The evaluation-only response adds one flat boolean. On the shared 36 controls, old/new attempts were 36/36, input tokens 13,143/18,471, output tokens 3,086/3,148, latency 48.163/54.819s, zero failed requests or retries. About 0.185s extra per judge call in these sequential local measurements; larger wording clarifications alone had no extra benefit. No claim about end-to-end memory quality/cost follows from the evaluator change.

Runs now save their loaded fixture (including source timestamps and ordered review actions), its content digest, and evaluator version/prompt/schema digests alongside existing code/config/model/request recording. `planning/audit_comparison_protocol_2026_09_16.md` inventories current production calls and bounded/nested contracts, defines matched E2 inputs and reserves LoCoMo sample 10 (`conv-50`) for V1. Selection inspected only IDs/run metadata; the existing store inventory included every other sample, with no sample10 reference found in run manifests, DEVLOG or planning. Outside-repository use/pretraining contamination cannot be ruled out.

Validation: 27 focused fixture/judgment/progress tests passed (`e1-evaluator-structural.log`), including unknown/missing judgment fields, unsupported-assertion gating, interrupted probes and frozen manifest inputs. Ruff/whitespace checks passed. E1 is implemented; the known relative-date native failure and C1–C3/E2 onward remain open.

## 2026-09-16 — C1: distinguish calendar occurrence from deadline bound

Product invariant: a model-declared weekday occurrence locates the named day relative to its cited reference; a deadline constrains the action relative to that occurrence. Kept the existing call, schema fields, calendar operations, stored representation and correction-date review. Added a description to the existing `WeekdayOccurrence.direction` field explaining this distinction. No lexical date interpretation, semantic overrides, additional stages or compatibility paths.

Proof and rejected approach: the existing prompt and a prose-only clarification each passed 14 isolated controls, but mixed-context `calendar-context-contract-20260917T035347Z-82700c3a` reproduced the wrong Friday and the prose change also regressed a neutral upcoming deadline. Rejected that prompt change. One past-deadline control used the ambiguous phrase "last Monday"; replaced it in subsequent development controls with "Monday two days ago" instead of treating one convention as universal correctness. Those changed-case totals are not matched quality comparisons.

Before integration, the field-description proposal (`calendar-context-contract-20260917T035821Z-e0900c6a`) passed 4/4 mixed-source cases, including the saved failing source. Its unchanged arm also passed 4/4 on that invocation: this demonstrates valid behavior, not a measured broad accuracy gain. After integration, 14/14 isolated controls passed, including missing timestamps, undated reported speech and separate event/condition dates. Maintained current-path `calendar-context-contract-20260917T040549Z-43967932` passed 4/4, with the saved September deadline resolved to September 11. `weekday-pipeline-20260917T040236Z-af9bcc81` passed native build → reviewed correction → retrieval → no-op rebuild; 21 recorded calls/79.723s, zero failed requests. Source/store/review snapshots are retained. The earlier mixed-history truth-scope probe still has a diagnostic failure (same scope for differently dated repeated event wording); it emitted no truth change, and was not weakened or tuned away here. E2/V1 source review still gates claims of longitudinal correctness.

Complexity delta: zero calls, response fields, branches, nesting or persisted artifacts; 86 additional schema tokens for a single-segment extraction request. The discarded proposal is archived with the direct run. Maintained probes call current builders rather than carrying proposal contracts. Combined C1/citation structural validation: 792 passed, one AMI skip, 75 integration deselected in 27.26s (`c1-c3-full-validated.log`); focused checks and Ruff/whitespace passed.

## 2026-09-16 — C3, first tranche: complete exact citation resolution

Added one shared exact citation resolver, retaining the existing preparation-scoped source cache. Truth input, routing input and fact source/time input now reject missing sources, missing or wrongly scoped segment IDs, empty segment citations and empty provenance instead of silently omitting broken evidence. Singleton truth review validates citations before deciding no comparison is needed; direct singleton fact projection validates them even on a rebuild with no incoming claim. Failures remain explicit/retryable and leave canonical claims intact. Retracted-source status is preserved for callers; no semantic model decisions or source-lifecycle rules changed in this tranche.

Nine corruption/history tests cover missing secondary sources, cross-source segment confusion, empty citations, singleton paths without model calls, and retaining retracted status for explicit historical inspection. Updated one positive grouping fixture to actually store its cited source, and three old assertions that expected silent missing-citation tolerance or uncontextualized low-level exceptions. Validation: 98 focused lifecycle/truth/date checks and 25 citation/routing/cache regressions passed; final structural suite 792 passed, one AMI skip, 75 integration deselected (`c1-c3-full-validated.log`). No model prompt/schema/call changes; native date/correction workflow also passed in this worktree.

C3 remains open for projected page/link consistency and partially retracted evidence in multi-claim truth comparisons. The existing truth comparison rejects a claim if any cited source is retracted, even when other support remains; singleton display correctly retains and qualifies such evidence. That broader behavior must be reconciled without silently reusing withdrawn support. The coverage report also currently counts segment IDs globally rather than resolving source/segment pairs; tighten that diagnostic alongside the remaining integrity work.

## 2026-09-16 — C3: projected links and source-scoped coverage

Page availability is now determined before rendering references. Links, related edges and the memory map use the complete projected page set, independent of entity render order. Exact reference dependencies refresh when a destination appears, disappears or changes title; each affected entity is prepared at most once. Canonical claim/fact identity references remain available even when the identity has no independent page. A repeated unchanged rebuild does not increment page versions. This is deterministic view maintenance, with no model call or schema additions.

Coverage accounting now uses exact `(source_id, segment_id)` pairs. A real segment under the wrong source no longer counts as covered; repeated local segment IDs in separate sources count separately. Reports expose unresolved pairs, and the integrity report also flags empty segment citations. Validation: 67 focused projection/coverage checks and 796 structural tests passed, one AMI-data skip, 75 integration deselected in 27.03s (`c3-projection-coverage.log`, `c3-projection-coverage-full.log`). New tests cover destination creation, withdrawal, rename, simultaneous page creation, canonical reference preservation, stable no-op rebuilds and source-ID collisions. Ruff/whitespace passed. Partially retracted support in multi-claim truth review remains open; no source-status inference policy changed here.

## 2026-09-16 — C2: identity matches carry an explicit preferred-name update

Product need: matching an existing identity must not rewrite its name by copying a noisy discovery proposal, and a supported first name, correction or rename must preserve the canonical ID. Replaced the existing variant's required `title` with nullable `preferred_name_update` in the same call. The structured model decides identity and whether a name changes; validation checks only that a non-null update copies an exact occurrence from cited source text. The internal plan retains its existing nullable title field and source-backed identity decisions, so no new production stage, response nesting, persisted artifact or compatibility branch was added. New/descriptive titles and aliases remain semantic model decisions; this does not claim to validate all name semantics deterministically.

Direct proof: the first nullable-title proposal passed 13/14 versus 11/14 current decisions in `identity-name-update-contract-20260917T042502Z-22681141`. Its miss was a conservative review of a new name, not a wrong adopted spelling. Aligning null-retention wording regressed real updates (11/14, `...20260917T043148Z-fcc68602`); rejected. Separating the field's meaning passed 14/14 in `...20260917T043314Z-ebca04fc`, including two preserved long-context source failures, first naming, correction, rename, nickname retention, unnamed follow-up, namesakes and ambiguity. 14 calls/25.180s, 22,595 input and 1,233 output tokens, zero failed attempts. One long-context rationale still paraphrases the service name incorrectly while the canonical ID and null update are correct; no additional critic/retry layer was added to polish that rationale. These small development probes establish the decision contract, not reliability or a broad matched quality gain.

After integration, maintained current-builder probes passed 12/12 (`identity-boundary-contract-20260917T043957Z-1ec061d4`, 12 calls/21.781s) and native routing passed 8/8 (`identity-boundary-pipeline-20260917T044020Z-c936be83`, 37 calls/92.447s, zero failures). Native cases preserve IDs/types through naming transitions and keep distinct people/products separate. Request/schema/config/model records and snapshots remain with each run. The prototype was removed after archiving; maintained probes call the production builder. Structural tests reject unsupported, uncited and differently spelled updates and retain the existing lifecycle/manual-review contracts. Together with the pending C3 patch, the full suite passed 799 tests, one AMI skip, 75 integration deselected in 27.58s (`test_outputs/audit-followthrough/c2-c3-full-validated.log`); Ruff/whitespace passed. Longitudinal old/new truth-state and page quality still require E2/V1 review.

## 2026-09-16 — C3: partial retraction compares only remaining support

Invariant: withdrawing one source removes that source's support, while independent active corroboration can still participate in review. Exact historical citations must remain valid and inspectable. Truth preparation now separates active citations from withdrawn anchors and explicitly rejects active claims with no active source support, including singleton claims. For partially supported claims it withholds the potentially stale synthesis, extracted temporal/about metadata and automatic identity bindings from inference; it retains active raw assertions and authoritative manual identity bindings. Canonical text, references and historical evidence are unchanged. This avoids blocking unrelated work or asking the model to treat withdrawn details as current support.

The first active-citation-only input still produced a false conflict from stale canonical text (2/3 direct cases, `partial-support-contract-20260917T043510Z-51b87c48`). Additional instructions also failed that counterexample (`...20260917T043825Z-53cb839f`); rejected. Removing the stale synthesis from that input passed 3/3 (`...20260917T043915Z-37afc43f`, 3 calls/4.644s), preserving a supported replacement and rejecting a withdrawn-only conflict and independent activity. Production integration passed the same 3/3 (`...20260917T044301Z-16fe4208`, 3 calls/4.154s; 2,593 input/191 output tokens, no failed attempts). The maintained probe uses current production preparation/comparison. Earlier probe-only setup errors (missing output directory, incomplete retraction metadata, closure shadowing) preceded valid model runs and are retained in logs; none demonstrates product behavior.

Complexity: no extra model call or output field; one input list of withdrawn citation IDs/statuses, with reduced semantic input for partial support. No additional prompt or fallback remains. New regressions cover multi-claim progress, preservation of canonical history/manual review, and explicit singleton failure. Full structural validation with C2: 799 passed, one AMI skip, 75 integration deselected (27.58s); Ruff/whitespace passed. Together with exact citation validation and projected-link changes, C3 implementation is complete; full workload source review remains E2/V1 work.

## 2026-09-16 — E2 comparison runner and frozen longitudinal invocation

Started `audit-daily-e2-fdcc767-20260917` with production `fdcc767`, the configured host models and the full nine-checkpoint development sequence. No semantic edits will be made to this running production path. Prepared a benchmark-only ranked-claims arm that reuses exact checkpoint evidence, policy, identity metadata and review state, and retains the production source-backed renderer, ranker, budgets, QA and judge. It omits generated fact prose and generative admission. This isolates their contribution; it cannot claim standalone ingestion savings or performance of Mem0 itself. Each cloned input database is hashed; settings/model/evaluator mismatches reject comparison. Requests/timings and terminal outcomes are recorded. Rebuilt snapshot indexes make first-query latency cold; shared work and document embeddings must be reported separately.

Two focused structural tests passed for source-policy/retraction exclusion, superseded-state preservation, exact canonical text/citations, absence of generated fact prose, no admission calls, and result/context bounds. Ruff/whitespace passed. The native arm runs after the production invocation is terminal, to avoid overlapping model work. No production changes or additional production LLM calls.

E2 control clarification before running the native arm: a generated fact may bundle multiple canonical claims. Applying the same five-record cap to raw claims would restrict their evidence by construction. The control now fills the same token budget from the same bounded candidate pool, without the five-fact cap. This is a stronger simple baseline; the change preceded observing any native control result. Both focused tests still pass; no production retrieval behavior changed.


## 2026-09-16 — E2 complete diagnostic and ranked-claims comparison

Production `fdcc767` reached all nine daily-driver checkpoints; 19/19 answers,
zero final extraction backlog, execution complete with one failed approval
action (no pilot-date proposal). Ranked control `cccbe23` completed 19/19 on
immutable snapshots with matched digests/configuration/evaluator. Raw judge
10/19 vs 13/19; source review exposes overstrict family-purpose and tool-fact
abstention expectations, retained as evaluation disagreements. Retrieval
96.85s vs 4.07s and QA32.16s vs55.62s; control emits8.23× context characters,
with cold-index/shared-ingestion limitations. No broad speed/accuracy claim.

Runs: `benchmark_runs/audit-daily-e2-fdcc767-20260917`,
`benchmark_runs/audit-daily-e2-ranked-cccbe23-20260917`; source-review packs in
`benchmark_runs/audit-daily-e2-fdcc767-20260917-source-review`. Full analysis in
`planning/audit_e2_observations_2026_09_16.md`. Production memory trace321attempts,
2732.122s,11failed structured attempts; attribution897.700s dominates. Calendar
source succeeds only on seventh attempt across builds. New names, explicit date
interpretation, missed current-state change, duplicate user from tool evidence,
and broad history rerouting need general fixes. The completed diagnostic is not
product acceptance. No model/setting was changed and no app server was started.


## 2026-09-16 — Declare calendar-date syntax before decoding (C1 follow-up)

Product invariant: absolute time bounds are calendar dates; stated month/day/year
must not silently become a relative weekday operation. Added the existing
YYYY-MM-DD syntax to JSON schema and clarified the existing absolute-kind
description. The regular expression validates a declared date field, never
interprets source language. No new kind, call, nesting, or stored artifact.

Direct paired probe `calendar-date-syntax-contract-20260917T053805Z-c9b17c9c`:
current4/7, syntax-only6/7, syntax+kind7/7. Current11attempts/83.486s/6failures,
59,455input/5,457output tokens; selected7attempts/55.083s/0failures,
24,098input/3,761output. Calendar/clock and explicit-date transition failures
were tested alongside range, relative-clock and undated counterexamples.
These are narrow contract checks, not a broad reliability estimate.

Integrated maintained probe `calendar-date-contract-20260917T054402Z-541a1e5d`:
7/7direct,49.385s,24,098input/3,280output; native capture→Build→retrieval
9calls/35.852s/0failures retains the scheduled day and exhibition range with
exact citations. The larger longitudinal gate remains open.

Structural date/correction suite50passed (0.92s), Ruff and whitespace clean.
Use `.venv/bin/python -m pytest` in the worktree: the shared standalone pytest
entrypoint imported the primary checkout and caused a misleading missing-schema
assertion; the module invocation tested this worktree. An initial invocation
also named a nonexistent legacy test file and collected nothing; neither was
counted as validation.


## 2026-09-16 — Rebuild only exact page-promotion dependencies (S2)

Product invariant: caller-selected evidence remains scoped by its source/deferred
filters. A newly materialized page can revisit earlier statements linked to that
entity by active recorded references; page ownership and the previous batch do
not establish relevance. Removed the redundant initial scope expansion and the
all-You/all-deferred/last-cohort expansion. Promotion uses existing entity-reference
indexes and exact claim reads rather than enumerating all claims/placements.
No new model call, semantic heuristic, schema, or persisted production record.

Native prototype `revision-scope-contract-20260917T054843Z-c4c7b44b`: same seed,
unrelated named-project addition. Current15calls/66.208s,49,743input/3,880output;
exact dependencies12calls/52.930s,42,143input/3,152output. Zero failed model calls.
Current re-attributed both old claims; proposed re-attributed neither, retaining
old canonical claim and fact records exactly. A report parser initially expected
a claim_id stripped from attribution inputs; preserved the completed control
and resumed only the untouched proposal arm using exact text+citation record
accounting. Failed harness log and all model requests remain available.

Counterexample `page-promotion-scope-contract-20260917T055415Z-7eb03ec7`: a
source-backed provisional person gains a useful page; its earlier ink-preference
claim is reconsidered through the recorded entity reference and appears on the
new page. No broad history replay or lexical matching. This is a native prototype
with a seeded provisional identity, not a claim of end-to-end identity discovery.

Structural67passed/3.64s, including explicit include_deferred and source-limited
requests, retired/retracted/policy-excluded references, exact promotion, manual
page reviews and reference replacement. Two obsolete mocks assumed implicit
deferred inclusion or automatic replay of every You claim; updated them to
request deferred evidence or provide the explicit subject reference. The new
regressions failed on the old policy (4failed/1passed) and now pass. Ruff and
whitespace checks pass. Integrated/native and full longitudinal follow-through
continue with attribution simplification; scale/cache measurements remain S1.


## 2026-09-16 — Remove redundant attribution explanations (W1/S2 cost)

A source assertion already explains why a claim describes an entity. Removed the
separate reason string from every claim/entity attribution cell; retained asserted
content, the described/reporting-only/unrelated decision, exact pair accounting
and consistency checks. Routing audit text now uses those supplied assertions
and the declared relation. The next presentation call receives less repeated
text. No new call, schema branch, fallback, or production artifact; one field
removed per cell. Migrated maintained mocks/page probes; native assertion runner
now defaults to one trial instead of three familiar repeats.

Paired direct `compact-attribution-contract-20260917T054640Z-940494a4`:14/14both
arms, including a named-user compound statement and other-person counterexample.
Current37.275s/14,197input/2,475output; compact29.213s/13,254input/1,645output;
14calls each,0failed attempts. This establishes a narrow output/cost improvement,
not a full-workload speedup.

Integrated direct `asserted-attribution-contract-20260917T060115Z-2f48fb82`:13/13,
24.663s,0failures. Native `page-review-pipeline-20260917T060241Z-a8affa21`:3/3
evidence-scoped no-page/reusable-page cases,23calls/70.702s/0failures. Existing
reviewed evidence remains excluded while independent support keeps useful pages.

Full structural807passed,1AMI skip,75integration deselected,27.39s; Ruff and
whitespace clean. A sandboxed suite stalled at the private-network TestClient
check; cancelled that finite test process under standing authorization and ran
the full suite with host access. The stalled invocation is not validation.
Logs: `test_outputs/audit-followthrough/compact-attribution-full-tests-host.log`.


## 2026-09-16 — Ground newly adopted identity titles (C2 follow-up)

The existing name-update guard did not cover new/provisional identity titles.
Added one flat title_basis declaration (source_name or description) before title
in those existing variants. The model decides whether the source supplies a
name; a declared name must copy cited spelling exactly. Unnamed descriptive
labels may vary. No lexical identity rule, new call, nested output, or production
artifact. Aliases remain structured model decisions; this exact guard applies
to the adopted title. Raw decisions and cited evidence remain inspectable.

First proposal with the basis after title: `name-origin-contract-20260917T054159Z-b0732a16`,
12/13 vs13/13control; rejected after an existing-name case failed three attempts.
Field-order proposal `name-origin-order-contract-20260917T055833Z-b6b90c14`:
13/13 vs12/13control (the preserved long-context service typo recurs in control).
No failed attempts in either arm;26.213s/20,783input/1,350output vs
24.204s/18,298input/1,202output. The flat declaration has a small measured cost
for an enforceable spelling boundary. No critic/repair stage was added.

Integrated direct `identity-boundary-contract-20260917T060852Z-6ba5b62b`:12/12,
33.605s,0failures. Native `identity-boundary-pipeline-20260917T061228Z-df8e368b`:
8/8,37calls/91.082s/0failures, retaining namesake separation, first naming,
correction, rename and unnamed follow-up identity IDs. Some free-text rationale
still confuses proposed/source spelling; correct IDs and guarded titles are the
authoritative result, not the explanation prose.

Structural69passed/4.02s; exact source-copy tests include uncited spelling,
case changes, new/review variants and legitimate descriptions. Mechanical mocks
now explicitly declare arbitrary descriptive labels; source-name tests supply
the real cited name. Longitudinal replay and tool-observation identity continuity
remain separate gates.

### 2026-09-16 — Declared speaker names are exact source evidence

- The full structural run after the bounded-truth integration exposed a missed
  `title_basis` mock in the no-profile participant test. Reviewing that path also
  found a product defect: a source speaker need not say their own name aloud,
  but the new-name validator accepted only transcript body text. Product
  invariant: declared, source-scoped speaker metadata is also valid evidence
  for copying a model-declared name; it does not prove an identity match.
- The existing contract now accepts names from cited segment speakers and
  declared participants from a supplied source. A participant's own turn need
  not be among the selected claim excerpts; the original source establishes the
  declaration. Uncited/undeclared speakers, unknown source IDs and misspelled copies remain
  invalid. No prompt change, new output field, nesting, or model stage.
- Direct configured-model proof: `speaker-name-contract-20260917T064134Z-20766777`,
  3/3: participant-only evidence, a cited speaker, and a mentioned-person
  counterexample. Native discovery → identity → routing with no canonical-user
  profile: `speaker-name-pipeline-20260917T064506Z-2283a08b`, passed without
  failures. A descriptive museum identity also appeared; this is not evidence
  of perfect page admission or editorial quality.
- Focused structural validation: 85 passed in 4.02s, including Dream and source-role context regressions. The declared-speaker domain
  mock was corrected to actually supply its claimed speaker in source metadata.
  An initial command named a nonexistent test module; no tests ran in that
  attempt and it is not counted as validation.
- Broader validation exposed that a valid participant can have no cited claim:
  requiring their turn in the selected excerpts incorrectly rejected that case.
  Validation now uses the supplied source's participant declaration; the existing
  no-empty-page and same-source role-context regressions cover this boundary.
- User explicitly assigned real browser/microphone/Wi-Fi/Tailscale checks to
  themselves after implementation is ready; no app services were started.

### 2026-09-16 — S1 bounded truth discovery and stable semantic inputs

- Product need: fixed-size incoming evidence must not trigger model comparisons
  against every historical claim. Page ownership is not an identity boundary.
  Freeze K=48 before held-out testing: 32 global semantic neighbors plus at most
  16 additional neighbors through exact established entity references. Small
  eligible histories (≤48) remain exhaustive. Both routes include same-batch
  claims; the global route includes unresolved and unplaced claims.
- Reused the existing semantic index and configured embedding model. Exact
  eligible-ID domains share one index and query-vector cache. No lexical
  decisions, new model stage, nested output, or canonical record type. Search
  only proposes pairs; the existing structured decisions and human approval
  boundary still establish changes. Previously reviewed pairs remain excluded.
  Each unordered pair receives at most one decision, including asymmetric
  same-batch hits found only from the later side's search.
- Direct paired proof: `bounded-truth-contract-20260917T062156Z-40711e82`, 104
  source-backed records / eight incoming claims. All four annotated critical
  pairs and all three counterexample pairs survived search. Exhaustive candidate
  screening covered 796 pairs, chose 223 comparisons, made 28 model calls / 368.446s,
  175,345 input / 25,155 output tokens. Bounded screening covered 249 pairs, chose 86,
  made 16 calls / 153.073s, 85,655 input / 10,294 output tokens. Both had zero failed
  requests; shared embedding preparation cost 3.749s separately. These are narrow
  single-run costs, not an end-to-end speed or reliability claim.
- Source adjudication: bounded comparisons matched all four annotated changes;
  exhaustive misclassified the same-time cost conflict as a replacement. Both
  falsely proposed a change for an ambiguous Alex and independent museum visits
  in different years. Exhaustive inference is not ground truth. We retained these
  failures rather than expanding prompts or the candidate cap to chase a score.
- Production integration: `truth-candidate-pipeline-20260917T063546Z-ac0eeb60`.
  Native source/claim/reference preparation → search → comparisons → pending
  proposals completed with no execution failures; 14 model calls / 144.929s plus 13
  embedding requests. Canonical claims were unchanged. All four critical pairs
  were proposed, but this run again called the same-time cost conflict a
  replacement; the two false-positive counterexamples also remain. Review
  burden and generalization are open workload measurements. The first harness
  attempt failed before any model call because its output directory was absent;
  its log is retained, and the corrected fresh run is the recorded evidence.
- Compact truth inputs retain cited assertions, time, semantic reference fields,
  and explicit identity-review IDs. They omit view ownership, recreated reference
  UUIDs, build IDs, timestamps, and retirement bookkeeping; full references remain
  in the canonical audit store. Exact duplicate semantic references are deduped
  and sorted. Source, role, identity, time and human-review changes invalidate
  inference reuse. Configured embedding settings now flow explicitly through
  FactResolver/TruthReviewer and their unit-of-work lifecycle callers.
- Prior direct compact-input proof:
  `compact-truth-contract-20260917T053706Z-4c3118a3`: current and compact 5/7 each,
  input 7,161→4,401 tokens, 8.149→6.710s. Its historical case misleadingly declared
  `temporal_status=current`; it cannot establish historical-event quality.
  The current-state wording variant and follow-up event wording did not resolve
  the event failure and were not integrated. No additional truth prompt rule.
- Native actual rerouting: `truth-rerouting-cache-pipeline-20260917T064657Z-45fab1ad`
  produced disjoint reference UUIDs with identical semantic records. The second
  truth-candidate decision reused the durable result; the independent statements
  needed no comparison call. Focused cache tests separately exercise comparison
  reuse and invalidation for changed source/role/identity/time/human review.
- Scale: `truth-candidate-scale-20260917T064245Z-ef9268da`, fixed B=4 at
  N=100/1000/10000. Eligible pairs 122/156/191 stay below 192. Cold/growing-index
  elapsed 3.139/8.825/84.830s; warm 0.070/0.223/3.486s. The 1000/10000 arms grow an
  existing index, not independent cold full rebuilds. This uses short synthetic
  archive records and measures search/index work, not source preparation, a full
  ingestion pipeline, model comparisons or realistic retrieval quality. No
  exhaustive model control was run at 10k. Full-history record preparation and
  index synchronization still perform linear work.
- Structural validation: focused 106 passed in 4.71s; full 820 passed, 1 AMI skip,
  75 integration deselected in 28.13s. The full run also caught the separately fixed
  declared-speaker/excerpt boundary; earlier failing runs remain in logs.

### 2026-09-16 — Reject unproven external-user identity changes

- The first direct replay accidentally selected a later request where a duplicate
  person already existed: `external-user-identity-contract-20260917T061649Z-5b2d9d46`.
  Its claimed expected identity was not a valid creation-control test. The
  original creation request is `da926f8ec467465886175047e1588d84.json` in the E2
  diagnostics. Corrected replay: `external-user-identity-contract-20260917T063200Z-aed1483c`.
- Both current wording and source-independent-user wording passed the three
  neutral known-user/namesake/ambiguity controls and repeated the original new
  identity decision. Replacing historical claim paraphrases with exact raw source
  excerpts also produced no improvement (`identity-source-basis-contract-20260917T063851Z-c9933201`).
  Neither proposal was integrated; no extra source-input layer or critic call.
- Source inspection corrects the diagnosis: canonical You has the fixture's
  configured name as an alias, but the cited history has no direct spoken
  self-identification. The matching assignment/responsibility makes it plausible
  that the task refers to the user; it does not justify a deterministic merge.
  Ignoring that plausible alternative and creating a new identity without review
  is still a model limitation. The fixture's expected exact merge is not a rule
  to encode in product code. Preserve this for longitudinal/source review.

### 2026-09-16 — S2 production follow-through

- `revision-scope-pipeline-20260917T064837Z-17f2a9b7`: native capture and Build of
  an unrelated restoration project left both prior preference claims and their
  consolidated facts byte-equivalent and made no attribution calls for them.
  No build failures. This is production code, without the earlier prototype's
  policy override.
- `page-promotion-scope-pipeline-20260917T065142Z-b4ddd6d9`: a source-backed
  provisional printmaker was promoted after a new workshop source. Production
  exact-reference scope included the earlier ink-preference claim, which appeared
  on the admitted page. No build failures. The initial provisional identity and
  prior placement were seeded, so this isolates promotion rather than proving
  all upstream discovery behavior. Full longitudinal review remains separate.

- Native correction rerouting additionally passed:
  `truth-rerouting-change-cache-pipeline-20260917T065417Z-0ad07970`. Both the
  candidate decision and comparison reused durable results after actual routing
  generated disjoint reference UUIDs. The explicit correction remained a pending
  supersession proposal; the cache did not apply it to canonical evidence.

### 2026-09-17 — Full longitudinal comparison and existing answer paths

- Completed `audit-daily-followthrough-e4cfc9d-20260917` against E2's frozen
  `fdcc767` run with matching fixture, config, model digests and evaluator.
  Nine checkpoints and 19/19 probes finish. Both runs miss the explicit
  pilot-date approval; the new run additionally ends with five routing failures.
  No extraction backlog or unresolved exact citations; all 48 final item links
  resolve. Main model work falls 321→198 attempts, 2,732.122→1,404.580 seconds,
  2,326,261→1,090,182 input and 165,251→86,317 output tokens. Failed attempts
  11→3. Both raw answer panels pass the same 10/19. This is an observed cost
  reduction with incomplete organization, not quality equivalence or release
  acceptance. Detailed source review, stages, transitions and limits:
  `planning/audit_followthrough_observations_2026_09_17.md`.
- R1 diagnostic: `daily-runtime-qa-control-20260917T072149Z-09655d90` compares
  static QA and the existing tool-enabled benchmark prompt on seven identical
  saved evidence sets. `daily-app-qa-control-20260917T072637Z-d8775dfa` uses the
  actual app prompt/budget builder and memory loop, without web tools or prior
  chat. Model digests/config are checked. No memory tool calls occur. App-style
  responses recover deadline, privacy and pilot history from existing evidence;
  all paths still incorrectly use an earlier date for the next interview despite
  explicit uncertainty in retrieved sources. No source index, retrieval branch
  or reranker dependency adopted. This isolates answering-contract limitations,
  not a full app or device test. Archived scripts, requests and results retained.

### 2026-09-17 — Carry resolved source descriptions into attribution

- Product invariant: renaming an entity must not erase the interpretation of
  its earlier source descriptions between identity matching and attribution.
  The prior implementation discarded that context and supplied only canonical
  titles, requiring attribution to infer the identity again.
- Preserve each already resolved source title/description with its exact local
  supporting claim IDs, merge occurrences by accepted entity ID, and scope them
  to the current attribution batch. They are not canonical aliases or assertions.
  Page admission retains its prior inputs. The existing attribution call still
  determines assertions from cited evidence, within the canonical statement's
  scope. No new model calls, output fields, semantic rules or canonical record
  types. The existing identity work-unit audit contains the carried context.
- Initial direct paired proof:
  `attribution-identity-context-contract-20260917T072247Z-21804b7b`. Both arms
  19/20. Carrying context fixes the retained project-constraint omission but
  incorrectly attributes an adjacent, separate statement in a neutral control.
  This first proposal was not accepted. Clarifying the existing assertion scope
  passes 20/20, zero failed requests, 41.577s:
  `attribution-identity-canonical-scope-20260917T072453Z-bf43aa82`.
  Controls include distinct projects using the same description, a namesake
  person, reporting-only sources, ownership, relationships and unrelated facts.
  Against the recorded 20-case current arm, accepted input tokens rise
  19,312→21,054 (+9.0%), output falls 2,568→2,360, and time is 43.989→41.577s.
  These single trials support a small input-cost tradeoff for recovered coverage,
  not a latency or general accuracy guarantee.
- Native initial sequence:
  `identity-context-pipeline-20260917T073018Z-9d69fd75`, 17 calls / 56.677s, no
  execution failures. Discovery selects the scans rather than the archive app,
  so attribution cannot add the requirement to the app page. This upstream
  omission remains a limitation; the run is not a passed end-to-end quality case.
- Second neutral sequence isolates the app requirement explicitly:
  `identity-context-app-pipeline-20260917T073237Z-711cce12`, 19 calls / 58.286s,
  zero failed requests. Native discovery→matching→attribution→page publication
  preserves Cedar's identity, puts the source-described app's local-storage
  requirement on that page, and keeps Dalia's unrelated journey off it. Prior
  purpose and workstation evidence survive both builds. Source/claim/work-unit
  records and both snapshots are retained. This proves the in-situ mechanism,
  not every possible upstream discovery or longitudinal transition.
- Attribution validation now identifies every inconsistent claim/entity cell
  and describes the existing empty/nonempty constraint in retry diagnostics.
  It does not alter, accept or semantically repair an invalid decision. Structural
  tests check the unchanged rejection boundary and precise locations; no model
  reliability gain is claimed for the diagnostic change.
- Validation: focused 41 passed; full 822 passed, one AMI skip, 75 integration
  tests deselected in 30.34s. Exact batch scoping, merged identity occurrences,
  unchanged canonical aliases, source provenance and invalid-output rejection
  are covered. The earlier failed proposal and native discovery miss remain
  available alongside successful results.

### 2026-09-17 — Frozen V1 evidence and user-owned rollout checks

- Started `audit-v1-heldout-2c5c4fe-20260917` at production revision `2c5c4fe`,
  using the predeclared first four sessions of unused LoCoMo sample 10, zero QA,
  normal configured models/settings, and a snapshot per session. Production is
  frozen while it runs. The first two snapshots are complete (308.5s / 1,901.2s);
  sessions 3–4 remain in progress. This entry is not a terminal result.
- First snapshot retains six routing failures after a copied-name check rejects
  Japan absent from the selected claim citations. The normalized source claim
  cites only a pronoun reply, omitting the antecedent. The country is real in the
  source conversation. A neutral proposal clarifies existing new/context citation
  fields; it remains unintegrated and untested against the model at this point.
- Second snapshot recovers all six failures; 77 claims are routed with 34 facts.
  Source review still finds incomplete antecedent citations, unsupported exact
  dates for week/weekend expressions, a potentially misresolved performer, and
  excessive routine conversation in claims and prominent page sections. Valid
  IDs, complete execution and searchable claims do not establish semantic quality.
  Details: `planning/audit_v1_observations_2026_09_17.md`.
- Code inspection finds whole-batch rerouting after page promotion, even when
  only a small subset has changed eligibility. An isolated exact-ID prototype and
  paired native test are prepared under `/tmp`, pending the frozen run's end.
  Already valid routes, outstanding failures, old dependencies and within-build
  promotions must be preserved. No extra semantic stage is proposed.
- Full sample-3 comparison is prepared, not launched. Verified old artifacts
  include 32 snapshots, 193 questions and 440 failed attempts among 2,004 recorded
  calls. Model context is 65,536 while session budget is 32,768; older model/config
  provenance is incomplete. See `planning/audit_sample3_comparison_2026_09_17.md`.
- User-owned browser/audio/private-network acceptance is written in
  `planning/audit_device_acceptance_2026_09_17.md`, explicitly unverified. It uses
  the actual upload-based Engram flow. No application service was started/stopped.

- Accounting correction after separating trace cache hits: the longitudinal
  follow-through log has 198 main-model events, comprising **196 inference
  attempts / 1,404.578s plus two cached returns / 0.002s**. The baseline has 321
  attempts / 2,732.122s and no hits. Prior 198/1,404.580 figures included cached
  returns. Token counts, failures and qualitative conclusions are unchanged; the
  comparison report and active plan now use explicit inference/cache labels.

### 2026-09-17 — Completed held-out review and stopped citation experiments

- `audit-v1-heldout-2c5c4fe-20260917` finishes all four predeclared sample-10
  sessions/snapshots in 3,807.956s, zero QA. Execution completes, encoding remains
  incomplete: the final 41-segment extraction batch truncates at 8,192 tokens.
  126 retained claims are routed; one identity review is pending. No truth
  proposals. Source review of all four conversations and successive pages finds
  unsupported exact dates, incomplete antecedent citations, useful content
  incorrectly left source-only, routine-chat over-extraction, and cross-owned
  car content. These fail broad semantic acceptance. Exact references/links
  resolve but do not prove semantic support. The held-out measurement is retained;
  subsequent experiments on its failures are regression evidence.
- Main-model work is 314 actual inference attempts (308 unique requests and six
  retries), eight failed attempts, 3,634.789s, 2,527,628 input / 234,640 output
  tokens. Six cache returns / 0.007s are separate. Truth screening/comparison
  consumes 45.3% of inference time. Separate embeddings: 117 operations / 18.841s.
  Detailed source review, per-stage/per-call statistics, coverage and recording
  limits: `planning/audit_v1_observations_2026_09_17.md`; read-only inspection
  results and script are archived under the run's `source-review/inspection.json`.
- Citation-domain wording proposal:
  `reference-citation-contract-20260917T084001Z-1f6ff9df`. Current/proposed both
  pass 4/9 small/dense neutral controls, with zero malformed outputs. The proposed
  arm omits almost all dense-case content; lower output/time is not an efficiency
  gain. Current/proposed: 115.488/37.480s, 35,153/35,855 input, 8,260/1,999 output.
  Its synthetic dense IDs sort lexically rather than production's padded order;
  both arms receive the same ordering. Rejected, no production prompt change.
- Flat unified `supporting_segment_ids` proposal:
  `unified-reference-contract-20260917T085010Z-f5532aec`. One existing support
  domain replaces two, without more calls/nesting. The predeclared early-stop
  rule fires: 1/4 small cases passes, with resolved-place, acceptance and refusal
  antecedents missing. Four calls / 14.990s / 13,905 input / 723 output, no malformed
  outputs. Remaining five cases not run. Rejected. Stop this contract experiment
  round; keep the limitation visible rather than adding a verifier or lexical fix.

### 2026-09-17 — Scope page-promotion maintenance and retain failed updates

- Product invariant: new page eligibility changes only its recorded old
  dependencies and earlier descriptions missing that page. Keep already valid
  incoming routes. Failed maintenance stays visible/retryable without deleting
  the earlier published evidence. This uses exact IDs and existing model
  descriptions/page decisions, not semantic string rules.
- `scope_revision_evidence` selects that delta, including earlier cohorts within
  the same build even if no extra historical claim is found. Partial result
  merging retains unrelated failures and identity blockers. Routing/fact failures
  on older dependencies now enter the existing retry queue, even with a placed
  old view. Benchmark encoding status includes pending claims and retryable
  maintenance failures. No new LLM stage, output field or persisted record type.
- Initial paired native experiment:
  `promotion-delta-contract-20260917T084540Z-979a693a`. Current arm passes with
  routing sizes 3/4, 14 attempts / 46.892s. Proposed arm fails upstream in identity
  matching before reaching the changed second pass: a descriptive workshop title
  is wrongly declared a copied source name and rejected three times. Its seven
  attempts / 20.947s are **not** an efficiency gain. Preserve that semantic miss.
- Isolated comparison sharing the actual successful first-pass routing result:
  `promotion-delta-shared-first-pass-20260917T085140Z-cd79f3d8`. Both fresh
  downstream arms preserve old ink preference and new workshop/commute/childcare
  evidence without failures. Second pass 4→1 claims; downstream inference
  11→9 attempts, 40.192→21.609s, input 28,697→17,461, output 2,335→1,160.
  Different page counts are permitted. This isolates maintenance scope, not two
  independent fresh builds. Both inherit an unsupported pronoun from the shared
  seed extraction; it does not establish fully grounded upstream encoding.
- Fresh integrated production run:
  `promotion-delta-integrated-20260917T085844Z-0b16bff1`. Actual capture/extraction
  produces four new claims; production routing sizes 4/1, only old dependency
  revisited. All checks pass, prior and incoming evidence retained, no failures.
  Build: 15 inference attempts / 46.984s. Separate seed extraction: one / 11.505s.
  The fresh canonical workshop statement has no invented gender pronoun. Source,
  claims, work units, requests, results and snapshots remain inspectable.
- Structural red run: four failures before implementation. Focused promotion,
  policy and benchmark checks: 100 passed in 5.87s. Tests exercise within-build
  promotion, unaffected failures, old routing/fact failures with intact views,
  honest completion, and successful later retry.

### 2026-09-17 — Increase bounded extraction output headroom

- Product need: a structurally valid per-segment response can exceed the prior
  fixed allowance, losing a whole batch's useful extracted evidence. Increase
  the existing output ceiling to 16,384, bounded to one quarter of model context.
  Batch planning and the actual request use the same reserve. Prompt/schema and
  call sequence are unchanged. Smaller contexts retain room for complete source
  units/schema; tighter requests may require more batches. Reasoning still uses
  its independently configured allowance. No salvage path, verifier or retry loop.
- Neutral paired capacity control:
  `extraction-output-reserve-20260917T085401Z-2932b6c2`. Both 8,192/16,384 limits
  retain all 32 equipment statements, output 6,028/6,060 tokens, input 8,407 each,
  77.944/76.772s. Larger allowance does not force larger output. The same script's
  retained-request replay duplicated the schema instructions. Its zero-claim
  result is an invalid comparison, preserved as a harness failure.
- Corrected exact request replay:
  `extraction-reserve-exact-replay-20260917T090129Z-e3234344`. Assertions verify
  original messages/schema/model/options, changing only `num_predict`. One call
  completes: 17,068 input, 8,770 output, 116.774s versus original truncated
  8,192 output / 107.886s. Useful shop-service and gift content returns. All 41
  segments become claims, including routine chat/URLs; salience and antecedent
  omissions remain. This is capacity recovery, not a general semantic gain.
- Integrated retry on a **copy** of the frozen final snapshot:
  `extraction-reserve-integrated-20260917T091010Z-39ca977b`. One call / 117.068s /
  17,068 input / 8,342 output completes only the failed batch, adds 41 claims and
  clears extraction backlog. Existing sources, claims and completed batches stay
  unchanged as serialized records. New claims include the useful service
  and gift evidence but also routine chat; they are pending organization because
  this check runs extraction only. Original held-out store is unchanged.
- A first fixed 16k-reserve test exposed loss of input room at a 24k context;
  bounding the reserve to a quarter fixes that general resource issue. The new
  structural test checks actual emitted request budgets and lossless segment
  coverage across batches at the smaller context. Focused combined suite:
  87 passed in 6.09s. Full structural suite: **827 passed, one AMI skip, 75
  integration deselected in 33.03s**. Ruff on changed files and diff check pass.
  No UI changes; existing UI checks were not rerun. Native tests/probes above
  establish model observations separately from this structural suite.

### 2026-09-17 — Use monotonic attempt durations

- The frozen sample-3 run exposed a negative structured-call latency: fact text
  request `bf34f654` reports -169ms while Ollama reports 1.117s server duration.
  `call_messages` operation summaries and `_call_structured` attempt traces used
  `time.time()` differences, which can move backward on clock adjustment. Actual
  chat-round traces, cache timings, embeddings and benchmark session/retrieval
  measurements already use monotonic timers.
- Replace only those elapsed-time measurements with `perf_counter`; wall-clock
  timestamps remain timestamps. No prompt, schema, model, retry, or output change.
  Validation simulates a one-hour backward clock jump during a successful call,
  transport failure and malformed structured output, checking both durable
  attempt traces and in-memory operation summaries. Before the fix, three
  structured cases fail; chat-round traces already pass. Afterward all five
  scenarios and the full **57-client-test suite pass in 0.40s**. Ruff and diff
  checks pass. No configured-model call is needed for a clock-source change.
- This fix is made in the primary checkout while the benchmark continues from
  frozen `0f9f7ee` in `audit-followthrough`; it does not alter that process. The
  full run retains the timing limitation. Use separately labelled Ollama server
  durations where present and monotonic session/overall totals; never clamp
  negative values to zero or treat server time as client elapsed time.
- Historical inspection: prior full sample3 has four negative entries among
  2,004 attempts, 36,923.269 recorded client-wall seconds versus 39,460.313
  server-total seconds (all 2,004 have server durations, including failed output).
  Held-out: 314 attempts, 3,634.789 client-wall versus 3,770.842 server seconds;
  no negative entry does not prove absence of clock skew. Earlier quoted client
  trace latencies remain historical measurements with this limitation. Counts,
  tokens, source findings and semantic acceptance are unaffected. The current
  sample-3 review retains a separate `source-review/timing-comparison.json` and
  its read-only inspection script for corrected cost interpretation.

### 2026-09-17 — Full structural validation and frozen comparison review

- The monotonic-clock change passes the complete structural suite: **833 passed,
  75 integration deselected in 33.92s**. Log:
  `test_outputs/audit-followthrough/monotonic-timing-full.log`. This validates
  structural behavior, not the configured model's semantic decisions.
- Full sample 3 continues from unchanged production revision `0f9f7ee`; neither
  the clock fix nor these documentation changes are loaded into its checkout.
  Four snapshots currently exist. Session 4 has 12 retryable fact-addition
  failures: three attempts omit the same one of 44 claim IDs, while the generic
  validation error never identifies it. Older published facts remain intact.
  Exact missing/duplicate-ID feedback is a bounded structural hypothesis for
  later proof, not a change integrated during this workload.
- Read all 32 source conversations, all 193 prior predictions, prior
  early/middle/final principal pages, and all current pages through session 4.
  The comparison report separates canonical citation/date errors, identity
  fragmentation, failed publication, retrieval loss and QA mistakes. It also
  preserves reference defects: two questions have the wrong year and an exact
  adoption interval is unsupported. No reference edits or benchmark-specific
  product changes. The current workload has not reached QA and is not a pass.
- Corrected daily/held-out cost interpretation now uses separately labelled
  independent Ollama server durations where available. Original client-wall
  measurements remain visible with their clock-skew limitation. No historical
  traces were rewritten. The report and read-only inspection artifacts retain
  measurement coverage and distinguish server work from elapsed runtime.

### 2026-09-17 — Give fact-group retries exact partition feedback

- Product invariant: each supplied canonical claim ID must appear in exactly one
  bounded group. A validation failure should identify missing/repeated IDs;
  neither validation nor retry feedback chooses a semantic group for them.
  The running workload exposed three replies omitting the same ID from a
  44-claim request, followed by 12 retryable additions. The generic error did
  not identify the omission.
- Direct configured-model proof before integration:
  `fact-partition-feedback-20260917T101523Z-19ba5273`. Three neutral invalid-prefix
  controls cover omission, repetition and both; a fourth uses the retained real
  malformed response. Both arms use identical original production prompts,
  native schemas and settings; only the existing retry error differs. Eight
  actual model requests, no extra retries or wording variants. Control passes
  3/4 (retained case fails), proposal 4/4. All neutral repairs keep distinct
  museum/garden events separate and related class/bicycle details together.
  The retained proposal accounts for all 44 IDs with no group over 12 members.
- Integrate only exact missing/repeated-ID reporting in the existing validator.
  Initial prompts, schemas, model stages and retry limit are unchanged; valid
  cached decisions remain usable. No fallback grouping or semantic repair.
  Structural test first fails because the actual retry prompt lacks the IDs,
  then passes; fact-group, client and promotion-maintenance suites: **70 passed
  in 0.86s**. Ruff and diff check pass. The previous full structural suite remains
  833 passed; no unrelated suite or UI rerun for this localized change.
- Integrated production caller proof:
  `fact-partition-feedback-integrated-20260917T102057Z-b0114fb7`. Supplies the
  retained malformed response as an explicitly labelled synthetic first prefix,
  then performs **one actual configured-model request** through the unchanged
  structured-call retry path. It returns all 44 IDs correctly. This validates
  the caller/validator boundary, not a fresh complete Build. Actual request:
  10,358 input / 803 output tokens, 17.320 monotonic client seconds. Original
  request/schema/options equality is asserted. Existing awkward page sections
  and source/identity defects remain outside this fix.
- These nine real calls share the host model with frozen sample3. Direct window
  10:15:23–10:18:22 UTC; integrated window 10:20:57–10:21:14 UTC, during session 5.
  Record contention as a timing limitation. Direct control/proposal use
  14,557/14,618 input and 1,491/1,497 output tokens; client times 101.179/86.381s
  are observations, not an isolated speed comparison. No code/configuration
  changed in the running benchmark checkout, and its results do not validate
  this later fix. Full benchmark/source review continues separately.

### 2026-09-17 — Publish both sides of ownership transfers atomically

- Frozen sample3 session 7 exposes a publication defect. Claim
  `claim-2b3349eda8df63fd` moves from `person-john` to
  `topic-resource-inequality`; the old owner's grouping fails, but the new
  owner's fact and placement override still commit. The claim then belongs to
  both `fact-53cd1c38258a` and `fact-4945c545dd8b`. Exact references resolve,
  yet the destination page repeats the claim. The inverse failure can remove
  its only published view while preserving the canonical claim.
- Product invariant: moving published evidence requires both affected owners'
  views to commit together. Resolve failure scope over exact prior/proposed
  owner IDs, including transfer chains. Restore prior facts and suppress fact
  deletions/placement overrides throughout that scope; independent additions
  can still publish. Existing retry handling records the dependent failures.
  A global truth-review failure also holds staged maintenance because its
  proposed placements have not passed fact resolution.
- No new model call, prompt/schema change, semantic rule, persisted artifact,
  or fallback synthesis. This is publication atomicity; configured-model proof
  is not needed to change an exact transaction boundary. The frozen benchmark
  is not modified and does not validate this separately integrated fix.
- Three model-boundary failure-injection controls first reproduce duplicate or
  missing published membership; a fourth reproduces unheld older maintenance
  after truth-review failure. The tests run the actual owner resolver, Build
  commit, database and page materializer around supplied decisions. They cover
  failure at either end or the middle of a transfer chain, an independent
  successful addition, unchanged prior facts/pages, successful transfer and
  successful retry. Early test-harness fixes corrected a mismatched page owner,
  queued existing maintenance explicitly, and supplied the required queue option.
- Focused resolver/Build/commit/review suites: **76 passed in 5.46s**. Full
  structural suite: **839 passed, 75 integration deselected in 35.32s**; log
  `test_outputs/audit-followthrough/ownership-atomicity-full.log`. Ruff and diff
  check pass. This verifies storage/publication behavior, not model meaning.
- The read-only snapshot inspection now also records duplicate fact membership
  and fact/placement owner disagreement. These complement citation/link checks;
  none establishes semantic support, useful coverage, or release readiness.

### 2026-09-17 — Reuse protected facts after page ownership changes

- All six duplicated claims in the prior sample3 final snapshot are covered by
  pending truth proposals. Current production reproduces another duplication
  path without a failed model request: it preserves an old fact for review,
  then creates a second direct fact when a member moves to a different owner.
- Product invariant: review protects the original fact's exact membership;
  moving a page destination does not require another canonical fact for that
  same evidence. Check protected membership across all owners when deciding
  whether a held claim needs direct projection. Existing placement-based
  rendering can show the preserved fact on its new page. Canonical claims and
  pending review remain unchanged. No new call, prompt, schema, or semantic rule.
- The regression first fails with two facts for the old claim. It then passes
  through the real resolver and page materializer: each side appears once,
  the old fact is unchanged, both sides stay active and display their pending
  review. Focused truth, partial-support, ownership, promotion, Build and commit
  suites: **70 passed in 5.49s**. An initial command named a nonexistent test file
  and ran no tests; the corrected command above completed. Ruff and diff pass.
  The most recent full structural run remains 839 passed before this extra test.
- A fact's retained grouping owner can legitimately differ from a current page
  placement while review protects that fact. The read-only inspection reports
  that difference for investigation; it is not by itself corruption. Duplicate
  stored fact membership is separate from showing one fact on several pages.
  Neither historical snapshots nor the running frozen workload are modified.

### 2026-09-17 — Reject the unproven flat truth-shortlist integration

- Product need: truth discovery consumes over half the first-five-conversation
  model cost. Test whether the existing candidate-screening call can return a
  flat list of candidate IDs per incoming claim, removing the full relevance
  matrix and repeated reason. Candidate search/cap, later semantic comparison,
  and human approval remain unchanged; no new stage or persisted record.
- Direct paired proof:
  `benchmark_runs/truth-shortlist-contract-20260917T113104Z-0d4b6dbe`.
  Five neutral cases cover an explicit reschedule, ambiguous identity, separate
  historical occurrences, unrelated properties, and 12 independent equipment
  updates. Ten calls, no retries, completed in 149.901s. The predeclared exact
  shortlist criterion fails: control 3/5, proposal 2/5. Both preserve all 14
  required candidate inclusions; proposal admits one additional unrelated pair.
  Control/proposal input tokens 18,109/10,616, output 2,632/209, server seconds
  88.732/61.033. Conveniently aligned aliases in the dense direct case and
  shared-model timing limit generalization. This initial failure stays recorded.
- A separate downstream criterion was explicitly recorded before further calls:
  a conservative prefilter may admit extras if the existing comparison rejects
  them, preserves all 13 explicit changes, adds no false change versus control,
  and reduces combined output by at least 20% without increasing input. This
  changes the evaluation question; it does not retroactively pass the first test.
  `truth-shortlist-downstream-20260917T113818Z-44f0774e` reuses the saved selections
  with the actual comparison caller and separate fresh caches. Ten calls finish
  in 128.983s. Both arms find 13/13 changes and both falsely equate two ambiguous
  namesakes. Historical occurrences and unrelated properties remain distinct;
  the additional unrelated-person candidate is rejected downstream. Combined
  selection/comparison input 27,071/19,915, output 3,586/1,156 (67.8% less), server
  seconds 150.633/127.526. These are narrow paired observations, not reliability
  estimates or complete Build results.
- The provisional production integration uses exactly the directly tested
  prompt/schema. Structural validation passes 86 focused tests and 840 tests
  with 75 integration deselected (37.65s), logged in
  `test_outputs/audit-followthrough/truth-shortlist-full.log`. Passing structural
  tests is insufficient to adopt the semantic change.
- Fresh production-caller gate:
  `truth-shortlist-integrated-20260917T114836Z-3032d4cf`, using actual candidate
  pooling/chunking and comparison on neutral canonical records. Four cases
  finish with the same known ambiguous-identity error. The dense fifth case
  includes same-batch candidates absent from the direct control and selects
  **89/210 eligible pairs, including all 66 same-batch pairs**. The six-minute
  gate exhausts its budget: 16 requests start, 15 complete and one is cancelled.
  Completed calls consume 48,021 input / 4,709 output tokens and 342.715 server
  seconds. The final dense-case result is incomplete. No matched old-contract
  native arm exists for this expanded pool, so this is not a causal regression
  estimate; it is insufficient adoption evidence.
- Stop this proposal. Preserve `proposed-production.patch`, the experiment
  scripts/plans, exact requests and `native-candidate-inspection.json` in the
  run roots; restore all nine provisional production/probe/test files to
  committed `1883fb6`. No semantic patch is committed, no additional variant
  or enlarged experiment budget is selected. The restored truth candidate,
  truth scope and ownership-atomicity suites pass **25 tests in 2.68s**. The
  most recent full test of the adopted code remains 839 before the later
  protected-fact regression; the 840-test result above includes the rejected
  prototype and must not be relabelled as a full validation of restored HEAD.
- Shared-model windows during frozen sample3: direct 11:31:04–11:33:27 UTC
  (10 calls), downstream 11:38:18–11:40:21 (10), integrated 11:48:36–11:54:19
  (16 started / 15 completed / one cancelled), overlapping sessions 8–9. Queue
  and cache effects limit latency comparisons; counts/tokens remain in their
  own experiment traces. The frozen benchmark code and settings are unchanged.

### 2026-09-17 — Close structural validation of the retained tranche

- After removing the shortlist prototype, run the full structural suite once
  on the adopted production revision, including the protected-fact regression:
  **840 passed, 75 integration deselected in 34.57s**. Log:
  `test_outputs/audit-followthrough/retained-production-full.log`. This supersedes
  the earlier 839-test adopted-code result and is distinct from the full run
  that included the rejected prototype. No model-dependent or UI suite is
  repeated for this validation.
- All **340** recorded source-file hashes in the running sample3 manifest still
  match its worktree. Only audit documents differ there; later main-branch fixes
  cannot be credited to that run. Eight snapshots have source/view review;
  session 9 is still executing and no QA result is available.
- The plan now separates implemented mechanisms from reopened semantic quality,
  compute, full-workload and user-owned device gates. Asked for direction on
  simplification versus additional targeted semantic work after the cumulative
  cost/quality evidence; this does not block already authorized validation.

### 2026-09-17 — Reorient toward practical memory and bounded simplification

- User selected simpler encoding and asked to use Mem0, Graphiti and Hindsight
  as cost references while keeping configured Gemma. Further clarification:
  coherent, useful memory for humans and agents at practical local cost matters
  more than exhaustive fact coverage, perfect identities or benchmark scores.
  Isolated misses must not trigger repeated tuning or extra semantic stages.
- Read pinned upstream source: Mem0 `f135cb9` ordinary inferred addition has one
  generative extraction call; Hindsight `bcca388` extracts facts per chunk, with
  separate consolidation/view work; Graphiti `de8eb5b` extracts nodes/edges and
  conditionally adds resolution, timestamps and summaries. These are static
  path estimates, not matched performance/quality measurements. Do not copy
  their lexical identity heuristics. Links and differences are recorded in
  `planning/encoding_simplification_2026_09_17.md`.
- Intentionally stopped frozen `audit-sample3-0f9f7ee-20260917` during session 16
  after preserving 15 snapshots, using the existing permission to cancel tests.
  Verified the process command and worktree before SIGINT; no service changed.
  Terminal invocation: 49,118.062 monotonic seconds, failed / CancelledError;
  encoding incomplete, QA/scoring never started. The manifest's still-pending
  stage fields are retained as recorded, with their limitation explained.
- Terminal completed memory traces: 3,865 attempts, 63 failures, 47 retries,
  29 separate cache returns, 40,428,031 input / 2,836,950 output tokens and
  48,760.912 server seconds. Embeddings: 993 calls / 100.934 server seconds.
  In-flight cancelled work may not have a completed trace. Session 15 has 153
  routing-failed claims of 462; recent sessions exceed two hours. Truth work is
  about 74% of pre-stop model time. This justifies examining the whole encoding
  boundary rather than another isolated prompt variant.
- The forward plan now prioritizes a small number of source-led retention/view
  passes, a fixed comparison, and end-to-end product use. The proposed direct
  and paired experiments have not run; no new production semantic mechanism is
  integrated or validated. The configured host `/api/tags` confirms Gemma's
  recorded digest, with no model/configuration change.
- At the user's request, draft concrete policy edits in
  `planning/agent_guardrails_proposal_2026_09_17.md`: practical acceptance,
  separation of mechanical guarantees from model quality, explicit cost/value
  for added complexity, bounded experiments, and no more than three immediate
  audit priorities with explicit removal/deferral. Revise the direct-model
  workflow's proof language without removing configured-model validation.
  This is a proposal, not an applied policy. `AGENTS.md` and the user's local
  `AGENT_PROMPTS/AUDIT.md` edits are untouched. Documentation-only validation;
  the latest retained-code structural result remains 840 passed / 75 deselected.

### 2026-09-17 — Implement the bounded source-led experiment

- User approved an end-to-end simplification plan and selected **up to five
  minutes** as a directional Build target for a roughly 1,000-word conversation
  added to a modest store. Mechanical durability/review guarantees stay strict;
  semantic omissions and imperfect organization are assessed in the whole result.
- Implement two flat experimental contracts: retain useful statements, subjects
  and pending changes; then produce cited view items with source-derived headings.
  No exhaustive source partition, attribution matrix, pair-screening stage, model
  judge, alternative model or lexical identity resolution. Existing entity types
  remain lightweight metadata for current consumers, not page-admission rules.
- First direct configured-model check:
  `benchmark_runs/compact-contract-20260917T224324Z-351af0c5`.
  Three source steps complete in six requests, 6,914 input / 1,689 output tokens,
  34.427 server seconds, no retries. Outputs preserve useful conditions and avoid
  adopting the assistant suggestion, but omit the initial inspection date and
  other context. A proposed reschedule incorrectly targets a broader delivery
  statement. Separate local/existing ID fields disagree and fragment identities;
  the input also repeats obsolete local-selection fields on existing subjects.
  This is usable preliminary output with material limitations, not a perfect pass.
- Use the one planned feasibility revision to remove redundant identity selection:
  each subject chooses one exact existing or allocated new ID. No name matching.
  `compact-contract-20260917T224500Z-f8d3d605`: nine attempts, 13,547 input / 3,696
  output tokens, 53.130 server seconds. Recurring identities now reuse IDs and
  the namesake stays distinct. Three retention calls and two view calls succeed;
  one retention attempt and all three final-case view attempts fail validation.
  The final view repeatedly cites a broad memory in two separate items. Preserve
  this incomplete result; do not tune the missed facts or add more prompt variants.
- Implement an opt-in native candidate using existing capture, canonical artifact
  records, SQLite transactions, publication, search and QA on copied stores.
  Open headings and its two-call Build orchestrator remain benchmark-local;
  the application pipeline is unchanged pending comparison and lifecycle proof.
  Model output is validated against exact citations, IDs and human exclusions.
- Mechanical failure injection covers first publication and a later update:
  prior views and a manually edited fact survive rollback; retained claims stay
  available; retry does not re-extract or duplicate them. Separate contract checks
  enforce protected evidence, no-page exclusions, legal citations and declared
  identity IDs. **3 tests pass in 0.13s**; Ruff and whitespace checks pass. These
  tests do not establish semantic quality or full correction/retraction support.
- Freeze `compact-comparison-20260917T225514Z-6b46ab03`: identical 143-claim seed
  copied read-only from sample3 session 5; three new conversations of 1,008,
  1,002 and 993 words; three practical agent questions; no review actions in
  either comparison arm; independent 931-word conversation reserved before
  native results. Each arm is capped at 900 seconds / 60 actual generation
  attempts; the independent check at 300 seconds / 12 attempts. Exact requests,
  source/code/configuration/model identities and session snapshots are retained.
  This replaces the earlier provisional budgets in the planning note.
- Early native source review exposes a representation mismatch: one retained
  statement contains information about two people; distinct view items cite the
  relevant parts, but exclusive claim-to-fact membership rejects them. This is
  a product/data-contract question, not a reason for more wording variants.
  Asked whether one retained statement may support multiple distinct view items.
  The current fixed comparison continues unchanged while that clarification is
  pending; no broader quality or adoption result is claimed yet.
