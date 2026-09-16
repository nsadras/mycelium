# Audit remediation implementation status — 2026-09-15

This is a partial implementation of the accepted repair-in-place plan. It is not
an end-to-end acceptance report. Existing benchmark artifacts remain unchanged.
No server or firewall changes were executed. The first validated tranche was committed as `8139075`; reporting/upload follow-through is separately validated and committed.

## Implemented mechanisms and remaining acceptance work

| Area | Implementation in this change | Remaining work / acceptance gate |
|---|---|---|
| A. Benchmark integrity | Independent encoding/QA/execution status; default QA block on incomplete encoding; explicit diagnostic override; invocation start/end journal and cumulative completed-invocation time; effective configuration, Git patch, scorer/coverage version; automatic structured failure dumps; typed context citation coverage | Model digests, operation/session/question linkage, and rendered-projection citation coverage are now implemented. Remaining: semantic scorer alongside legacy score and complete longitudinal session artifact audit. Interrupted invocation duration is unknown, not zero compute. |
| B. Configuration | Explicit overrides > requested TOML > dataclass defaults; missing requested files fail; invalid limits/sampling settings rejected | Engram model strings, numeric settings and requested-file validation implemented. Remaining: command-specific effective configuration round trips. |
| C. Retrieval consistency | Snapshot admission uses canonical ownership/tier and validates cited sources plus fact members; reselect once after owner/source/consolidation mutation, then typed error; missing provenance is an explicit integrity failure | Owner moves, consolidation, source retraction/deletion and repeated conflicts now tested. Recovery errors remain separately surfaced. |
| D. Workspace correctness | Revision-aware claim and source merges; canonical text/citation/status refresh on successful and failed tools; broken provenance clears stale evidence with an explicit error; whole-record budget and eight-operation history bounds | Source edits/deletions, citation promotion and stale replies now tested. Two browser component tests cover exact citation inspection, replaced text/status and elided failure history. |
| E. Errors and Engram | Retrieval errors reach HTTP 503 and tools; bounded uploads before parsing/copying; typed durable warning history; source admission freezes inputs; per-meeting operations and native-worker cancellation boundaries; deletion waits for resource release | Ten concurrency/recovery tests now cover active/queued deletion, repeated cancellation, upload cleanup, frozen admission, warning persistence and retryable file-deletion failure. Real device/network rollout remains a user-run check. |
| F. Private networking | Same-origin API/audio; allowlisted hosts; no wildcard CORS; loopback backend default; configurable Vite host with proxy; built UI mount; README deployment boundary | User-run Wi-Fi/Tailscale chat/audio/inspection checks. No authentication by explicit user preference. |
| G. UI races | Cancel obsolete wiki fetches; chat generation guards; correction editor retains retryable reviews; Engram tracks selection generations and request order, hides old transcripts, rejects delayed mutation/status updates, and preserves selection after deletion | Fourteen UI component tests cover correction review, evidence inspection and seven Engram request-order/warning cases. Remaining: wiki/chat request-order tests and draft restoration if chat-history loading fails. |
| H. Extraction | Integrated the directly probed multiple-time contract and per-message timestamps described in I | Broader subject/citation/coverage gates remain open. Vague “recently” may remain text-only; one native run split a condition into a duplicate claim. No lexical repair or fixture vocabulary added. Daily-driver trials remain pending. |
| I. Temporal representation | Model-declared multiple temporal entries, exact citation IDs, distinct targets/roles, calendar-only arithmetic, unresolved vague/missing/overflow dates; schema 2 fresh stores; explicit reference-date review for relative corrections with durable, stale-checked idempotent drafts | Direct metadata/encoding probes and three fresh-store temporal lifecycle runs completed. Automatic correction-reference selection failed neutral and in-situ counterexamples and was rejected. Full semantic coverage, duplicate-condition lifecycle and organization gates remain open; small probes establish no general quality/cost improvement. |
| J. Identity scaling | Not implemented | Bounded semantic candidate index (24), structured existing/new/unresolved, reviewed bindings, revision-aware durable caches, avoid unchanged impossible retries; direct probes before integration. |
| K. Page admission and organization | Not implemented | Separate identity from page admission, entity-specific section contracts, coherent event scope; longitudinal source-to-wiki audit. |
| L. Truth scope | Not implemented | Compare relevant claims across owners and within incoming batches; ownership must not restrict contradiction discovery; neutral coexistence/replacement tests. |
| M. Incremental consolidation | Not implemented | Persist bounded group membership; synthesize only changed groups; resume successful work without inference; growing-store cost tests. |
| N. Retrieval quality | Proven complementary ordered selection with supported-aspect/gap traces; lower output allowance; admitted order preserved in rendering | Global reranking when candidates require budget splitting; tool contracts and claims/raw-source controls; paired multi-question QA evaluation. |
| O. Scale | Indexed UnitOfWork field lookup with staged-write overlay; retrieval fact/source lookup avoids full scans | ANN switch only after 10k-claim experiment achieves >=95% recall@20; cache pending review lookups; broader load tests. |
| P. Cleanup | New retrieval error exported publicly; network/config docs updated; retired identity work-unit fields and unused selection contracts removed with schema 2; historical experiment imports aligned | Continue cleanup only where exercised by the remaining mechanisms. |

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
4. Run all three daily-driver scenarios three times. Investigate artifact quality
   as well as test scores before continuing.
5. Run full sample3: 32 sessions / 193 questions, no execution backlog, exact
   evidence integrity and manual longitudinal wiki audit. Compare only matched
   settings and clearly distinguish encoding from retrieval/QA.
6. Run held-out sample9 after sample3 gates. Target construction <=5.2h, failed
   model time <5%, warm retrieval median <=5s and p95 <=8s, context recall +20%
   without semantic score regression. These targets are **not established** by
   this change's probes.
7. Validate private-network access after the user starts the services. Do not
   start servers, alter firewall rules or commit without explicit instructions.

## Follow-through validation

495 structural tests passed,87 integration tests deselected. Native `audit-provenance-tiny-v1` completed one source session and QA in15.50s, with all seven model/embedding timing rows linked and no failed attempts. This is a reporting smoke test, not a full quality comparison. See DEVLOG for failed semantic probes and remaining gates.

Temporal follow-through: three native reviewed-correction runs completed in
48.26/45.62/45.96 seconds, with encoded/corrected/final snapshots and exact model
requests retained. Final snapshots have no extraction/publication backlog.
One run retained a separately extracted old payment condition after correction
of the delivery claim, and section placement drifted between builds. These are
open H/K/L findings, not a passed longitudinal quality gate. See DEVLOG for exact
paths, per-call costs, structural/component results, and rejected experiments.
