# Evidence passages: adopt the representation for lower overhead

Completed 2026-09-21. Baseline `108ba53`.
[Frozen plan](evidence_passages_plan_2026_09_21.md).
Evidence: `benchmark_runs/evidence-passages-20260921/`, especially `manifest.json`,
`verification.json`, `review.json`, `production/*/snapshot.json`,
`render-preview.json` and `source-inspection.json`.

## Decision

Adopt bounded, reversible evidence passages. The input reduction is directly
verified and useful without more model calls or a more prescriptive prompt.
**This is an efficiency improvement, not a demonstrated identity-completeness fix.**
Quality remains variable; the candidate loses detail in one synthetic comparison
and preserves more useful context in another. Neither exact page counts nor
exhaustive coverage is an adoption target.

The original recording has 7,175 words in 884 segments. Grouping produces 36
passages, preserving every original fragment and its speaker in order. Retention
input falls from **40,882 to 11,983 native tokens (70.7% lower)**. Both Builds use
one retention and one presentation call, retain eight statements, and finish
without rejected records or failed calls. Generation request time is **48.52 vs
20.22 seconds**; whole Build plus no-op check is **49.09 vs 20.76 seconds**. The
different outputs prevent treating the entire time reduction as a pure formatting
effect or predicting a universal speedup.

## Implementation

- Join adjacent original source indices with identical source, participant,
  speaker, role, source time and remaining metadata. Stop at 1,200 characters;
  leave an already longer original segment intact. New/context evidence, missing
  indices and index gaps remain separate. No linguistic rules classify topics,
  people, ownership or usefulness.
- Keep the flat model schema and prompts unchanged. The model cites a passage ID;
  expand it to the exact original segment IDs before validation and persistence.
  Preserve the original source artifacts, timestamps and audio references.
- Use the same compaction in request budgeting and inference. Save the complete
  passage membership in `request_citations` diagnostics, including rejected-row
  diagnostics, while keeping summary warnings small.
- Display exact consecutive canonical citation IDs as ranges in generated wiki
  markdown and agent evidence references. Never fill gaps or change stored IDs.
  Source excerpts and their citation relationships remain available for inspection.

The integrated compaction module is identical to the frozen candidate used in
the native probes. Integration additionally records original indices and the
diagnostic citation map. No configuration flag, compatibility branch, owner
mandate, resolver, retry loop or new generation stage was added.

## Source-reviewed quality

| Case | Baseline | Candidate | Interpretation |
| --- | --- | --- | --- |
| Own project, short | One statement; declares Leena but names Tideboard without its identity. | One statement; declares Tideboard but names Leena without her identity. Both omit personal job/accreditation context. | Useful overview in each; the identity inconsistency remains. |
| Third-party project, short | Six statements, correct Omar-builder/Leena-reviewer distinction and personal context. Some relationship references incomplete. | Six statements, same distinction and useful context; pilot/no-date and unfinished uploads preserved. Some references still incomplete. | Comparable useful output with substantially less input and citation generation. |
| Third-party project, long | Thirteen mostly technical statements, builder/project identities; speaker and personal context omitted. Some feature/status wording overstated. | One coherent project overview naming Omar, but no person identity or personal context. Technical detail largely omitted. | Coverage regression in this sample. Do not count shorter output as equal-quality efficiency. |
| Reserved mixed example | One statement about Elise's seed dryer; other work and qualifications omitted. | Four statements preserving Elise's dryer, empty-tray testing limitation, Tomas's separate inventory project and Elise's teaching. Correct distinction between builder and helper. | Useful improvement in this sample; contradicts a simple claim that passages always reduce coverage. |
| Full recording | Eight statements and eight subject pages plus You; technical/project selection, no Hari page. Raw response binds reviewed speaker Hari to canonical You. | Eight statements and a Hari page plus You; correct Hari participant binding, no distinct project identity/page. | Person attribution improves here, but the desired person-plus-project organization is still not assured. |

The candidate Hari page is predominantly a coherent account of his platform,
curriculum, architecture and business approach. It is not factually perfect:

- A retained job-market statement says AI replaces senior-engineer roles, while
  source indices 859–863 distinguish plentiful senior opportunities from junior
  hiring pressure. This is a retention interpretation error.
- Retention describes the centralized course-generation chat as a vision; the
  page presents it as a current feature. This is a presentation qualification loss.
- Personal certification requirements and some business/personal context are
  omitted. The project name appears in prose without a separate identity.

These limitations remain recorded rather than triggering more prompt tuning.
The unchanged baseline also contains questionable binding, thin/overlapping topic
pages and incompletely qualified technical summaries. No single stochastic output
establishes the general quality effect of grouping.

## Downstream citation problem found and fixed before adoption

Broad passages make citations less precise: the recording candidate emits 27
passage references across its memories, which expand to 651 original references
(with overlap between claims); the baseline emits 50 original references. One
candidate memory cites 155 original segments. This is **not** a fact-coverage gain.

Initially the wiki printed every expanded ID, inflating Hari's page to 25,490
characters. Exact-range display reduces it to 2,627 without changing statements
or structured citations. The saved original native snapshots remain unchanged;
the deterministic re-render is in `render-preview.json`.

An offline source-inspection check also found that a candidate view's reference
lists alone exceeded the ordinary 6,000-token evidence budget, so the existing
budget fitter returned no record/source. Apply the same range display to agent
evidence references. The actual candidate now returns its view, three supporting
claims and 87 cited source fragments in **5,978 tokens**, with `more_available=true`.
Every returned citation and source fragment was checked against stored originals.
Both isolated stores pass artifact integrity checks. No extra model calls were
needed to find or fix this deterministic representation problem.

The first inspection assertion incorrectly excluded the source tool's documented
surrounding context and related claims; correcting that test assumption exposed
the actual candidate budget failure above. This was not a native-model retry.

## Per-call cost and completion

Configured `gemma4:12b`, digest
`4eb23ef187e2c5462566d6a1d3bbbc2f1346d0b4327cbb66d58fffbcc9b2b05c`;
temperature 1, top-p .95, top-k 64, context 65,536, output 8,192, reasoning off.

| Call | Input tokens | Output tokens | Client seconds |
| --- | ---: | ---: | ---: |
| Baseline own-short | 3,041 | 120 | 13.23 |
| Candidate own-short | 1,914 | 118 | 3.13 |
| Baseline other-short | 3,004 | 859 | 12.72 |
| Candidate other-short | 1,910 | 444 | 7.03 |
| Baseline other-long | 28,266 | 2,075 | 37.96 |
| Candidate other-long | 5,819 | 136 | 4.64 |
| Baseline reserved mixed | 2,020 | 92 | 3.77 |
| Candidate reserved mixed | 1,850 | 572 | 8.27 |
| Baseline recording retention | 40,882 | 1,561 | 35.49 |
| Baseline recording presentation | 2,119 | 889 | 13.03 |
| Candidate recording retention | 11,983 | 729 | 13.15 |
| Candidate recording presentation | 1,855 | 457 | 7.08 |
| **Total** | **104,663** | **8,052** | **159.49** |

Close at the planned **12/12 calls**; server duration 159.46 seconds. Every call
finishes on attempt one with `done_reason=stop`; no transport failures, output
exhaustion, rejected rows or automatic retries. First baseline includes 10.52
seconds loading; the recording pair is warm. Both no-op Builds make zero calls.
No source text or optional context is omitted. The long synthetic input drops
from 643 fragments to 17 passages and uses 79.4% fewer native input tokens.

## Validation and limits

- Native prompt/schema/options verified for all twelve requests; all retention
  inputs preserve source words and order. Replay validates citation expansion and
  persistence.
- Mechanical boundary, size, immutability, duplicate-citation, role/source/date/gap,
  diagnostic, persistence/no-op, citation-range and evidence-budget regressions.
- Source inspection of the real candidate under the normal budget; both stores
  have healthy artifact integrity. No retrieval-ranking or QA-accuracy claim.
- Single stochastic samples; clearer synthetic speech and different extraction
  choices limit causal and general quality conclusions. No native successive
  content Build, model change, large-store trial or device check.
- All **608 Python tests pass**, with four native integration tests deselected;
  Ruff and whitespace checks pass. Frontend code is unchanged; no UI suite or
  services were run.

Use the simpler representation in ordinary use and keep explicit identity
correction available. This experiment ends here; do not extend it to perfect
Hari's page or recover every omitted fact.
