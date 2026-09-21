# Retrieval fixes: validation before adoption

Scope: [retrieval audit](retrieval_audit_2026_09_21.md), priorities R1–R4.
Production starts at `9991447`. Candidate development is isolated in
`/tmp/mycelium-retrieval-fixes-20260921`; saved evaluation artifacts are under
`benchmark_runs/retrieval-fixes-20260921/`. Preserve the user's existing guidance,
notes, live memory and services.

## Gates and order

1. **R1 — source budgeting.** Refresh only already inspected excerpts, fit whole
   segments inside the final envelope, and advance source reads through unseen
   segments without charging again for existing evidence. Validate neutral
   boundary/retraction/changed-source cases and replay the audit's recording at
   both 6,000 tokens and the app's default initial allowance. Promote only after
   the regression suite passes. No model calls are needed for this gate.
2. **R2/R3 — independent claims and identity context.** Give matching canonical
   claims priority over optional view context. Bound the actual returned record
   count. Include existing subject references and names/aliases, with correct
   invalidation on reference and identity edits. Preserve exact role distinctions
   and useful related evidence. Validate shared/large views, deferred claims,
   renames, namesakes and concurrent edits in the isolated candidate.
3. **R4 — bounded model comparison.** Compare the validated candidate with the
   preceding production path using frozen source/claim/view evidence and four
   questions: spending/keyholders, opening history, an unsupported purchase, and
   a visitor-outreach detail present only in the cited source. Keep the initial
   ranked candidate IDs fixed for the paired comparison so input presentation
   can be evaluated separately from changes to indexing. Use the app prompt and
   existing memory tools, configured models/decoding, and no web tools or judge.
   Include one ordinary unpinned retrieval check if the shared allowance permits.

The entire native comparison is limited to **20 generation attempts and five
minutes of execution**, including unsuccessful requests and tool rounds. Run one
baseline and one candidate per question, without prompt variants or retries of
completed semantic decisions. Record wall, load, input/output and embedding
costs separately; preserve incomplete results. A fixed candidate list is not a
claim about end-to-end index recall.

## Adoption and stopping rules

- R1: valid prior excerpts survive unchanged refresh, new reads add evidence or
  explain why they cannot, and retraction still removes withdrawn evidence.
- R2: a view cannot hide an otherwise fitting claim; shared membership respects
  the declared record limit; useful cited related context remains available.
- R3: current assigned identities are discoverable before publication; renamed,
  reassigned and deleted references cannot leave stale index metadata. No
  speaker-to-owner inference or identity-resolution model call is introduced.
- R4: use materially less selection input work with broadly coherent, grounded
  answers and appropriate uncertainty. Ordinary omissions are recorded, not
  converted into new stages, lexical rules, or a perfect-score target. Do not
  adopt an inconclusive semantic candidate merely because its inputs are smaller.
- Keep one shared selection pass where justified; reduce duplicated work before
  adding anything. No new graph service, reranker dependency or expanded ontology.
- Validate and commit each adopted unit. Close after the bounded comparison and
  final affected checks; device validation remains user-owned.

## Progress

- R1 candidate: six new boundary checks plus existing focused tests. Recording
  replay preserves all 87 initial excerpts and adds 98 within the existing 6,000
  additional-token allowance; the second read stops explicitly at the limit.
  At the app allowance, 390 initial excerpts become 484, with no loss and 1,173
  additional tokens left. Zero model calls. Isolated full suite: 627 passed,
  one skipped, four native integration tests deselected. Adopted after this gate.
- R3 evidence propagation adopted separately: existing names, aliases and exact
  roles reach direct claim evidence, revision refresh, UI and real page links.
  Identity-aware indexing failed the ordinary recall check and was not adopted.
- R2/R4 candidate passed structural checks but failed the model adoption gate:
  larger aggregate selection input and missing available keyholder evidence.
  The final two attempts checked a mechanical handoff repair; that also failed
  the quality/cost gate. Stop at 20 attempts. Keep the candidate off production.
- Release gate: 632 Python tests passed, one skipped, four native integration
  tests deselected; nine focused UI tests, frontend build, Ruff and final recording
  replay passed. [Results, limitations and remaining priorities](retrieval_fixes_result_2026_09_21.md).

The first full-suite attempt exposed the isolated filesystem copy's missing Git
metadata, which benchmark-provenance tests require. The candidate now has its own
local Git clone metadata; the main checkout is unaffected. One old test expected
refresh to discover new sources, contrary to R1. It now verifies refreshed
interpretation/citations followed by explicit source inspection.
