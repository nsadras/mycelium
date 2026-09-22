# Protected views and compact retrieval — implementation result

## Decision

**Adopt both changes.** The persistence fix prevents protected items accumulating
copies without adding model work. The retrieval candidate passes the bounded cost
and usefulness gate: **59.5% less native selection input**, one selection call per
question, and useful source-backed answers across both LoCoMo stores, the neutral
project conversation and the prior workshop regression.

This closes the first two priorities in the
[replication report](locomo_investigation_2026_09_21.md) and completes its small
app-style answering check. It does not establish improved encoding coverage or
perfect answering. The [implementation plan](view_retrieval_plan_2026_09_22.md)
was written before the native comparison; there was one candidate and no tuning.

## Changes and their justification

### Protected views — committed as `50a3f9d`

At persistence, recognize an existing protected representation by exact supporting
claim IDs, destination IDs and heading. Preserve its content and skip a repeated
insertion, including when owner/link order changes. Suppress duplicates within
one response as well. Distinct destinations/headings remain possible, and existing
manual splits remain intact. No semantic text matching, new schema field or
extra model call is required.

Three successive refreshes pass for manual and pending-review protection, including
unrelated-page preservation and distinct views of shared evidence. A zero-inference
replay uses the actual sample-7 presentation responses from Builds 2–5. Starting a
copied final snapshot with one protected copy yields **1, 1, 1, 1 copies**; source,
claim text and provenance remain unchanged. This is a persistence replay, not four
new end-to-end encoding Builds. Production does not delete historical duplicates
or repair the earlier incorrectly cited app claim.

### Retrieval — shared input and consistent selectable records

- Canonical search matches appear independently, before optional related views.
  A large wiki paragraph cannot make its small underlying claim unavailable.
- Selection receives each evidence record and source excerpt once. Compact JSON
  uses reversible local identifiers only in explicit reference fields. Human
  wording, names/aliases, identity roles, dates, pending reviews, supersession and
  citation relationships are preserved. Full mappings are recorded in diagnostics.
- Selection still returns the same small schema: IDs, supported aspects and gaps.
  The prompt's instructions are unchanged apart from using the configured result
  limit. No verifier, identity-index change, extra generation stage or retry is added.
- The exact selected records reach answering. Search limits count actual records.
  Refresh preserves selected views, updates inspected sources, and carries surviving
  canonical claim states if a displayed view loses valid support.
- One bounded admission call replaces recursive chunk selection and merging. If
  needed, whole records/segments are omitted with the existing availability flag;
  an input too small for any complete candidate returns an explicit error. This
  trades exhaustive candidate examination for bounded computation on very large inputs.

The rejected earlier experiment supplied reviewed structural code/tests, not its
acceptance result. That experiment increased selection input. This candidate adds
actual compaction and was evaluated afresh before promotion. The net production
change removes the old candidate wrapper and chunk/merge machinery.

## Validation

Development and validation occurred in `/tmp/mycelium-view-retrieval-20260922`.
The adopted inference implementation matches the frozen native candidate.

- **641 Python tests passed**, one skipped, four native integration tests deselected.
- Focused tests cover repeated protected refreshes, exact ID/text compaction,
  large/shared views, selected-view handoff, result limits, budget fitting,
  invalid outputs without repair, concurrent edits, supersession and retraction.
- Existing identity-propagation, source-refresh and incremental-budget tests pass.
  Ruff and whitespace checks pass. UI code is unchanged; browser/device checks
  remain the user's follow-up.
- A separate zero-generation replay reads the real recording's copied store:

| Initial allowance | Initial segments | After first source read | Lost across two reads | Additional tokens left |
|---|---:|---:|---:|---:|
| 6,000 | 78 | 178 | 0 | 47 |
| 26,768 | 369 | 484 | 0 | 65 |

The second read adds nothing and charges nothing, with an explicit budget/availability
reason. All rendered workspaces remain within budget. Independent canonical records
use some additional interpretation space: the earlier release replay started with
87 / 390 segments and reached 185 / 484. The smaller-allowance case therefore shows
fewer excerpts, despite correct preservation and accounting. This tradeoff is
recorded rather than compensated by enlarging budgets or adding calls.

## Native comparison: completion and configuration

Seven fresh baseline/candidate pairs use frozen encoding and **identical ordered
initial search hits**. Arms alternate order. Stores:

- Sample 7: James/John, five sessions, 27 claims, 14 pages.
- Sample 8: Deborah/Jolene, five sessions, 27 claims, 20 pages.
- New neutral two-project fixture: seven explicit source-backed claims, five pages.
  The fixture is constructed to isolate retrieval; it is not an encoding result.
- Prior workshop snapshot: 166 claims, 32 pages, including the earlier keyholder
  regression. Its inherited repeated-item integrity warnings remain unchanged.

Both use the ordinary app chat prompt and memory tools. No benchmark-specific
answer instructions, judge, web tools, seed selection or fallback model are used.
Configuration matches: `gemma4:12b`, digest `4eb23ef187e2…`, reasoning off,
temperature 1, top-p .95, top-k 64, model context 65,536. Embeddings use
`embeddinggemma:latest`, digest `85462619ee72…`. Initial evidence allowance is
26,768 tokens, with 6,000 additional tokens, three searches and six records per
tool search. Full digests, configuration and code hashes are saved.

All **28 generation attempts completed first attempt** in **139.52 seconds** of
overall comparison time (108.06 model-reported server seconds). There were no
failures, retries, cancellations, unfinished requests or incomplete pairs. The
predeclared limit was 36 attempts / 600 seconds; unused capacity was not spent.
Candidate preparation used 19 embedding requests, 234 items, 6.90 client seconds,
with no failures. That includes cold index construction; it is not steady-state
embedding latency.

Canonical exports remain unchanged before/after all 14 answers. Every selected
record reaches the final workspace. No answer calls a memory tool; autonomous
exploration remains unvalidated by this panel. Source tools are exercised by the
separate recording replay and regression tests.

## Cost

Native selection input tokens / server seconds:

| Question | Baseline | Candidate |
|---|---:|---:|
| Sample 7 pets | 24,520 / 14.83 | 10,068 / 4.67 |
| Sample 7 adoption | 25,416 / 8.31 | 9,226 / 4.08 |
| Sample 8 outlook | 30,508 / 9.30 | 9,908 / 4.28 |
| Sample 8 snakes | 32,353 / 10.35 | 10,036 / 4.42 |
| Neutral roles/help | 4,291 / 3.07 | 2,565 / 2.33 |
| Neutral unset date | 4,288 / 2.61 | 2,562 / 2.59 |
| Workshop money/keys | 22,738 / 8.12 | 14,005 / 5.45 |
| **Total** | **144,114 / 56.58** | **58,370 / 27.83** |

Both arms use seven selection and seven answer calls. Answer input is nearly
unchanged: 11,285 → 11,198 tokens. Total generation input falls 155,399 → 69,568
tokens (**55.2%**). Baseline includes 7.17 seconds of reported model loading;
candidate includes .03 seconds. Excluding loading, selection server time falls
49.43 → 27.81 seconds (**43.7%**), and total generation time falls 61.09 → 39.77
seconds (**34.9%**). These single-run timings are indicative, not a latency SLA.

## Manual answer review against source

| Question | Findings |
|---|---|
| Both James and John have pets? | Both correctly describe James's dogs and give uncertainty about John. Neither selects John's explicit “not there yet” line, which is attached to an incorrectly retained app claim. Source-only support selection is still imperfect. |
| James's adoption and timing | Both give dog Ned, Stamford shelter, “last week” relative to the April 12 conversation. No unsupported exact adoption date. |
| Jolene's outlook | Both attribute the change to her retreat. Candidate omits the confidence detail even though its selected claim and final exact excerpts contain it. This is an answering omission, not missing retrieval context. |
| Susie and Seraphim | Both correctly identify Jolene's snakes. |
| Neutral builders/help | Both distinguish Omar/controller from Leena/map app, and Kai's agreed map review from unagreed controller work. |
| Neutral controller date | Both correctly say no launch date is set; neither borrows the other project's April 20 test date. |
| Workshop fund/expenses/keys | Both give £420 original, £250 remaining, £35 shelving, £28 lock, £95 insurance, £12 labels/paper, and shop-owner/Amal keyholders. The prior candidate's keyholder regression does not recur here. |

This supports adopting the efficiency improvement with preserved usefulness.
It is not a measured accuracy increase. One stochastic pair per question cannot
estimate error rates. Initial ranking was pinned and indexing was not changed,
so this also does not establish better index recall or large-store scalability.
Earlier differently worded or benchmark-style QA panels are not matched comparisons.

## Remaining priorities and stopping point

1. **Everyday use and source exploration:** try the changed retrieval in normal
   chats and inspect recurring misses. A future small unpinned/tool-use check can
   cover discovery; do not require tools when the current evidence is sufficient.
2. **View granularity and retention variability:** retain the known limitations.
   The earlier presentation clarification failed its gate. Reopen only for recurring
   misleading or unusable memory across ordinary inputs, with one economical candidate.
3. **Identity/alias discovery:** current exact bindings reach context, but identity
   metadata is not indexed separately. The prior ranking experiment was rejected;
   a future bounded test may examine this without expanding claim embedding text.
4. **Device checks:** real browser, microphone, network/Tailscale checks remain with
   the user. No services were started and no live store was rebuilt or edited.

Stop this tranche here. No perfect-coverage target, follow-on prompt sweep,
retention retry or extra model-stage work is queued.

Artifacts: `benchmark_runs/view-retrieval-20260922/`, including the protected-view
replay, native plan, complete source/code snapshots, configuration/model digests,
ordered candidates, full requests/responses, per-call timing summary, selected
evidence, final workspaces, completion record and zero-generation source replay.
