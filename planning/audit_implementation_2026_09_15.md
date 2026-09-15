# Audit remediation implementation status — 2026-09-15

This is a partial implementation of the accepted repair-in-place plan. It is not
an end-to-end acceptance report. Existing benchmark artifacts remain unchanged.
No server or firewall changes were executed. The first validated tranche was committed as `8139075`; reporting/upload follow-through is separately validated and committed.

## Implemented mechanisms and remaining acceptance work

| Area | Implementation in this change | Remaining work / acceptance gate |
|---|---|---|
| A. Benchmark integrity | Independent encoding/QA/execution status; default QA block on incomplete encoding; explicit diagnostic override; invocation start/end journal and cumulative completed-invocation time; effective configuration, Git patch, scorer/coverage version; automatic structured failure dumps; typed context citation coverage | Model digests, operation/session/question linkage, and rendered-projection citation coverage are now implemented. Remaining: semantic scorer alongside legacy score and complete longitudinal session artifact audit. Interrupted invocation duration is unknown, not zero compute. |
| B. Configuration | Explicit overrides > requested TOML > dataclass defaults; missing requested files fail; invalid limits/sampling settings rejected | Engram model strings, numeric settings and requested-file validation implemented. Remaining: command-specific effective configuration round trips. |
| C. Retrieval consistency | Snapshot reads during admission; validate consulted state after model call; retry once, then typed error; drop retracted claims; current tier rendering; explicit query/index/admission errors | More interleavings: owner moves, consolidation and source retraction during selection. Recovery errors remain separately surfaced. |
| D. Workspace correctness | Equal-revision canonical claims/citations merge; newer interpretations replace older; canonical refresh between tools; whole-record fit includes workspace envelope | Bound operation-history growth under repeated rejected tools; source revisions and deleted-source races; browser inspection tests. |
| E. Errors and Engram | Retrieval errors reach HTTP 503 and tool errors; diarization warning retained; retry speaker detection without ASR or changing transcript; streamed upload copy with size enforcement and partial-file cleanup | Pre-parser request-size enforcement and spool cleanup implemented. Remaining: explicitly typed warning history; deletion/processing cancellation interleavings. |
| F. Private networking | Same-origin API/audio; allowlisted hosts; no wildcard CORS; loopback backend default; configurable Vite host with proxy; built UI mount; README deployment boundary | User-run Wi-Fi/Tailscale chat/audio/inspection checks. No authentication by explicit user preference. |
| G. UI races | Cancel obsolete wiki fetches; chat generation guards; preserve failed drafts and remove failed optimistic message; ignore delayed reply/status updates | Component tests for all request orders; Engram mutation responses; hide stale transcript while loading another session; draft restoration if history fetch fails. |
| H. Extraction | No extraction prompt/schema change integrated | Baseline and generic clarification each tested on12 neutral calls; neither passes citation/subject/time-anchor gates. Clarification not integrated. Required-anchor probe fixes omitted IDs but fails temporal meaning/attribution checks; no semantic variant integrated. Daily-driver trials remain pending. |
| I. Temporal representation | Not implemented | Replace lexical time inference with model-declared multiple temporal entries; preserve event time and deadline; vague expressions remain unresolved; schema bump/fresh stores; date/provenance tests and direct probes. |
| J. Identity scaling | Not implemented | Bounded semantic candidate index (24), structured existing/new/unresolved, reviewed bindings, revision-aware durable caches, avoid unchanged impossible retries; direct probes before integration. |
| K. Page admission and organization | Not implemented | Separate identity from page admission, entity-specific section contracts, coherent event scope; longitudinal source-to-wiki audit. |
| L. Truth scope | Not implemented | Compare relevant claims across owners and within incoming batches; ownership must not restrict contradiction discovery; neutral coexistence/replacement tests. |
| M. Incremental consolidation | Not implemented | Persist bounded group membership; synthesize only changed groups; resume successful work without inference; growing-store cost tests. |
| N. Retrieval quality | Proven complementary ordered selection with supported-aspect/gap traces; lower output allowance; admitted order preserved in rendering | Global reranking when candidates require budget splitting; tool contracts and claims/raw-source controls; paired multi-question QA evaluation. |
| O. Scale | Indexed UnitOfWork field lookup with staged-write overlay; retrieval fact/source lookup avoids full scans | ANN switch only after 10k-claim experiment achieves >=95% recall@20; cache pending review lookups; broader load tests. |
| P. Cleanup | New retrieval error exported publicly; network/config docs updated | Remove retired identity work-unit fields with deliberate schema bump; retire unused selection contracts and align historical experiment imports. |

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
  existing bundle-size warning remains. No browser component tests yet.

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
