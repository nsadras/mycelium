# Audit remediation implementation status — 2026-09-15

This is a partial implementation of the accepted repair-in-place plan. It is not
an end-to-end acceptance report. Existing benchmark artifacts remain unchanged.
No server or firewall changes were executed. The first validated tranche was committed as `8139075`; reporting/upload follow-through is separately validated and committed.

## Implemented mechanisms and remaining acceptance work

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
| L. Truth scope | Global, evidence-backed comparison before owner presentation; exact per-candidate and per-pair decisions include same-batch and unplaced claims; current/persisted source-policy exclusions stay outside comparison; preserve both sides for review; approval invalidates overlapping reviews | 18 direct comparison,18 revised candidate and18 native pipeline trials passed. A daily scenario exposed an excluded-source leak, now covered by structural regressions. The retained older pilot-state failure passed3/3 independent native replays after that fix. Broad semantic and growth-cost gates remain; bounded requests still scan admitted active history. |
| M. Incremental consolidation | Durable per-request reuse; persisted groups capped at12 canonical members; independent per-group text reuse; manual text retains exact evidence membership; native9/9 scenarios across27 builds and three persisted prose-reuse checks passed | Growing-store cost and longitudinal organization gates remain. Exact request reuse and bounded groups do not bound first-build history scans or every changed-input rebuild. |
| N. Retrieval quality | Complementary ordered selection and final global admission; strict tool argument schemas and exact source-ID checks; explicit native tool requests15/15 | Autonomous source inspection failed native and structured-step probes; proposed behavioral changes withheld. Claims/raw-source grounding controls and paired multi-question QA remain. Local pruning can miss jointly useful evidence; no general recall/QA improvement established. |
| O. Scale | Indexed canonical lookups; changed-record vector updates with weight-digest invalidation; flat L2 index from10k records, probing all partitions |10k-claim/200-query measured index recall@20=100% for every query; vector median12.03ms→3.01ms. Indexed appends/deletes and weight/dimension changes tested. Broader ingestion/history costs and full retrieval/QA gates remain. |
| P. Cleanup | Public retrieval errors; config/network/architecture docs aligned with current contracts; retired work-unit/selection fields removed; database cleanup safely releases collector-thread resources while ordinary operations remain thread-affine | Removed the obsolete routing adapter/schema overlay; automatic references now replace exact successful claim scopes atomically, preserving manual decisions. Removed unused combined identity/review schemas and prompts; retained current source-first router/review tests and neutral probe inputs. |

## Validation evidence

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

## Remaining rollout order and acceptance

1. Finish A–G structural acceptance before taking benchmark scores as evidence.
2. Prove H–M contracts with the configured host Ollama model: small neutral
   positive/negative cases, three trials, no critical semantic mistakes. Retain
   exact prompts, schemas, responses, failures, model config and timings.
3. Integrate smallest proven contracts and test structural invariants. No lexical
   semantic fallbacks, benchmark-specific prompts, or legacy-store migrations.
4. Run all three version2 daily-driver scenarios three times. The user confirmed
   that extraction/search wait for Build Memory and useful independent context
   can support a page from one conversation. V2 capture and fixture checks pass;
   v1 reports remain historical evidence with different acceptance rules. The
   paraphrased v2 also repairs a truncated YAML source sentence, so that input
   comparison is unmatched. Investigate artifact quality
   as well as test scores before continuing.
5. Run full sample3: 32 sessions / 193 questions, no execution backlog, exact
   evidence integrity and manual longitudinal wiki audit. Compare only matched
   settings and clearly distinguish encoding from retrieval/QA.
6. Run held-out sample9 after sample3 gates. Target construction <=5.2h, failed
   model time <5%, warm retrieval median <=5s and p95 <=8s, context recall +20%
   without semantic score regression. These targets are **not established** by
   this change's probes.
7. Validate private-network access after the user starts the services. The user
   authorized finite tests/benchmarks, cancellation and validated commits; server
   startup and device/network checks remain user-run.

## Follow-through validation

495 structural tests passed,87 integration tests deselected. Native `audit-provenance-tiny-v1` completed one source session and QA in15.50s, with all seven model/embedding timing rows linked and no failed attempts. This is a reporting smoke test, not a full quality comparison. See DEVLOG for failed semantic probes and remaining gates.

Temporal follow-through: three native reviewed-correction runs completed in
48.26/45.62/45.96 seconds, with encoded/corrected/final snapshots and exact model
requests retained. Final snapshots have no extraction/publication backlog.
One run retained a separately extracted old payment condition after correction
of the delivery claim, and section placement drifted between builds. These are
open H/K/L findings, not a passed longitudinal quality gate. See DEVLOG for exact
paths, per-call costs, structural/component results, and rejected experiments.
