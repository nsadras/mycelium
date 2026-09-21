# Encoding fixes: results and stopping point

Implemented the six bounded work groups in
[the implementation plan](encoding_fixes_2026_09_21.md). Keep encoding at two
semantic passes and shift attention to retrieval next. This closes the agreed
implementation and experiments; it does **not** establish consistently complete
retention or flawless identity assignment.

Evidence: `benchmark_runs/encoding-fixes-20260921/`. No live store was rebuilt.
The original GPU-contended audit remains closed and incomplete; these are separate
runs. All native experiments used configured Gemma 4 12B, unchanged sampling,
65,536-token context and 8,192-token output allowance. All 16 generation requests
finished on their first attempt, within their declared budgets.

## What changed

| Area | Implemented mechanism | Acceptance evidence |
| --- | --- | --- |
| A: view scope | Similarity supplies read-only context. Incoming subject references, changed claims and exact support/endpoint links authorize writable items. Selected shared items bring their complete support. | Independent new-subject and relevant-update regressions; protected edits, no-page evidence decisions and shared citations survive. Frozen audit input: 94 writable memories / 31 old items becomes 9 writable memories / **zero** old items, with 46 read-only memories. |
| B: presentation fidelity | Remove generated `text` from the model response. Select, order, group, head and link retained statements; code joins their text. Human wording edits stay protected. | Six-call comparison below; qualifier/order persistence regression; native successive Builds. No extra verifier or model pass. |
| C: identity handoff | Validate binding eligibility before counting conflicts. Reject invalid singleton/type/blank-title declarations locally. Offer relevant declared people and exact speaker bindings without implicit claim ownership. Unused existing-subject redeclarations create no source association. | Valid person survives illegal project binding; real person conflicts rejected; fixed bindings and independent valid memories preserved. Native pair is **partly inconclusive**, described below. |
| D: recovery | Fail only an unchanged batch checkpoint; finalize from current stored episodes. | Competing completion survives both simulated interleaving and a separate real SQLite UnitOfWork connection. Winning claim membership remains complete; next Build does not re-extract. Ordinary failure retries once when Build is explicitly resumed. |
| E: prior context | Interleave per-chunk learned rankings, deduplicate exact IDs, then apply the existing cap. | Three disjoint chunks contribute 16 candidates each at the 48-ID cap instead of 24/24/0. Overlap and late candidates are covered. Recent/bound context remains deliberate priority. |
| F: cleanup/diagnostics | Remove unused automatic routing/default-section helpers, mappings and API/UI fields. Keep types, manual section choices and used review artifacts. Record cancellation separately, identify experiment deadline cancellations and mark incomplete usage totals. | Static consumer review, curation/API tests, cancelled/deadline/unfinished-recorder regressions, frontend build and wiki tests. Built-in timeout is classified separately from a pipeline defect. |

No semantic keyword rules, ontology expansion, required person/project pages,
generation retry mechanism or backwards compatibility layer was added.

## B: one presentation candidate, six calls

Retention was frozen. Both arms received the same evidence for each pair:

1. Nine actual retained workshop statements from the audit, including conditional
   opening and volunteer availability.
2. Four retained statements from the existing mixed seed-dryer/inventory/teaching
   example, including separate builders and limited testing.
3. Eight actual recording statements with overlapping technical/strategy context,
   used as the repetition counterexample.

| Frozen input | Baseline output tokens | Candidate output tokens | Baseline client seconds | Candidate client seconds | Rendered words, baseline → candidate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qualifications | 848 | 446 | 21.95 | 7.11 | 338 → 669 |
| Independent context | 622 | 394 | 8.77 | 6.02 | 301 → 346 |
| Repetition | 342 | 261 | 5.59 | 4.67 | 152 → 282 |
| Total | 1,812 | 1,101 | 36.30 | 17.79 | 791 → 1,297 |

Candidate output tokens fell **39.2%**; total input tokens were 4,533 versus
4,230. The first baseline includes **10.14 seconds loading**, so the raw 51%
client-time reduction is not a clean speedup estimate. Generation durations total
23.48 versus 14.17 seconds, still a single stochastic sample with different
organization choices.

**Fidelity:** baseline again described Hari's envisioned central chat feature as
something the platform already includes. Candidate retains the exact vision
wording. The opening dependency, tentative volunteering, unreliable sensor,
empty-tray testing and distinction between lending a printer and designing the
inventory system survive. Pre-existing retention errors also survive: selection
cannot repair the recording's senior/junior job-market inversion or the workshop
claim that calls donated bicycle tools borrowed.

**Readability:** candidate pages remain readable, but are longer and sometimes
less focused. The independent example shares a combined personal-activities item
onto both project and teaching pages, alongside more specific items. The workshop
candidate shares volunteer availability broadly, including onto Amal's page.
The recording page has longer paragraphs and repeated architecture context.
Baseline also duplicates teaching/inventory content. These are presentation
limitations, not evidence of semantic perfection.

**Decision:** adopt the tested simpler candidate for fidelity and lower generated
output. It removes another opportunity to invent a commitment. Accept the longer
pages and imperfect grouping; no second candidate campaign or deduplication call.
The production prompt matches the frozen candidate. Source text is retained
independently, multiple items/pages can still cite it, and manual split/group/edit
operations remain available. Automatic presentation now cannot rewrite a long
retained statement into separate tailored sentences; that is an explicit tradeoff.

## C: native identity pair

Reused the frozen own-project and third-party-project conversations from
`evidence-passages-20260921/inputs/`, through capture, retention and presentation
in separate fresh stores. Four calls total, **15.78 client seconds**, 5,975 input /
960 output tokens. Both stores pass structural integrity checks; both no-ops
make zero calls. No warnings or failures.

- **Own project:** six statements retain Leena as Tideboard's builder, Omar as a
  reviewer who is not building it, local saving versus future unattended uploads,
  the conditional pilot/no launch date, and Leena's technician/accreditation
  context. The resulting person and project views keep those roles distinct.
  Sharing a larger project bundle onto Omar's page is broader than necessary.
- **Third party:** one statement retains only Leena's technician/accreditation
  context. Omar and the project are omitted entirely. There is no erroneous
  speaker-as-builder attribution, but **this is not positive confirmation of
  builder/reviewer distinction**. The intended native counterexample is
  inconclusive because retention did not keep the relevant subject matter.

The mechanical handoff is covered by tests that supply a builder, a separately
bound speaker and a project while the claim references only the project. Both
people remain optional choices, without new implicit subject references or pages.
Do not interpret the native omission as a reason to reopen identity prompt tuning.

## Final successive-Build check

Three existing workshop conversations, 1,008 / 1,002 / 993 words, in order, from
the same 143-claim / 19-page seed used by the prior audit. Same source settings
and configured models; no QA. Complete in **88.38 seconds overall**, with six
generation calls taking **79.60 client / 79.58 server seconds**. The generation
model was warm. Embeddings: 21 requests, 6.35 seconds, all successful.

| Build / stage | Input tokens | Output tokens | Client seconds |
| --- | ---: | ---: | ---: |
| 1 retention | 11,166 | 146 | 5.26 |
| 1 presentation | 6,979 | 89 | 3.46 |
| 2 retention | 8,797 | 1,588 | 24.37 |
| 2 presentation | 6,890 | 455 | 8.60 |
| 3 retention | 9,176 | 1,974 | 29.05 |
| 3 presentation | 7,748 | 491 | 8.85 |
| Total | 50,756 | 4,743 | 79.60 |

All Builds complete, with no pending sources and a zero-call final no-op. Four
structural warnings: three illegal project participant bindings in Build 1 and
one invalid change reference in Build 3. Independent valid records survive;
no retries, transport errors, cancellations or output exhaustion. Saved request
responses contain complete usage totals. Rejected records remain inspectable.

**Successive artifacts:** Build 1 retains only one project overview; Build 2 adds
eleven statements covering inspection, opening, equipment, insurance, library
outreach and staffing. Build 3 adds eleven statements about the completed opening,
spending, keys, later tentative events and personal context. Existing subject IDs
are reused for the project, event and people. The final opening view contains the
conditional plan followed by the actual opening and fourteen visitors. July 20
remains a proposal; the lease is not extended. Librarian Theo is distinguished in
prose, but does not get a separate identity record. Older inspection/planning text
remains visible beside later outcomes; presentation does not infer approved
supersession or remove historical evidence.

**Remaining quality limits:** the first Build's single overview misses much of
the conversation. Retention turns the insurer's extended quote into an accepted
quote, despite the source saying it is a planned expense. Presentation preserves
that misleading retained wording; it also omits some useful new spending/keyholder
details from pages even though they remain searchable claims. The library and
inspection pages retain stale future-tense plans; grouping historical and current
evidence can be repetitive. Paper-notebook preference is stronger than the
source's tentative suggestion. These are concrete limits, not hidden successes.

**Unrelated state:** all **143 seed claims and 62 seed view records remain exactly
unchanged** in every native snapshot. The first two Builds select zero seed items
for refresh; the third selects only nine items from the new workshop Builds.
The native third Build did mechanically regenerate fourteen old cached pages:
unused redeclarations had created spurious source associations for five existing
people, pulling their connected pages into materialization. No old evidence/view
text was semantically rewritten, but this was unnecessary projection churn.

The final deterministic correction stops manufacturing those associations. A
fresh offline replay of all recorded decisions passes the final contracts, removes
those five people from the third Build's affected set (18 → 13), preserves all seed
claims/items, and leaves **every seed page byte-identical**. This replay used zero
additional model or embedding calls. It validates the narrower handoff and
persistence, not the counterfactual model response to the slightly narrower input.
The old seed's four repeated-item projection warnings remain when those pages are
left untouched; they are inherited artifacts, not new encoding failures.

## Comparison limits and compute judgment

The prior native audit stopped during the first presentation under user-confirmed
GPU contention. It cannot be used as a latency baseline. Its exact frozen evidence
does establish the view-scope improvement: nine incoming claims previously exposed
31 unrelated seed items for rewriting; current code exposes none. The declaration
handoff offers ten relevant subjects versus the old twenty affected subjects.

The September 18 product run used the same initial sources/seed but an older
pipeline, different retained content and an injected second-presentation failure
plus recovery. Its first two normal Builds took 108.29 / 98.22 seconds; current
Builds take 14.24 / 34.30 / 38.78 seconds. These are **unmatched observations**,
not an equivalent-quality speedup. In particular, the old first Build retained
twelve statements versus one now. The two-call pattern is unchanged. The matched
frozen presentation comparison supports a narrower claim: less generation and
better preservation of selected statement wording, with more displayed text.

Across the three closed experiments: **16 generation calls**, 65,494 input /
8,616 output tokens, **149.48 client seconds**. No added production model calls.
The experiments do not establish broad identity accuracy, stable coverage,
large-store performance, retrieval/QA quality or device behavior.

## Verification and stopping decision

- Full non-integration Python suite: **622 passed**, four native integration tests
  deselected, 26.77 seconds. Focused failure/recovery, citations, page reviews,
  concurrent edits, input compaction, API and curation checks also passed.
- Ruff and whitespace checks passed.
- Frontend production build passed; four WikiExplorer tests passed. The existing
  bundle-size warning remains unrelated to this change.
- Services were not started or stopped. Original stores, sources and pre-existing
  user guidance/notes edits were preserved.

The structural fixes are complete. Encoding is practical enough to move on to
retrieval, with these semantic weaknesses recorded rather than expanded into a
new benchmark campaign. Watch for recurring misleading retention and unusable
grouping in ordinary use. Do not require perfect coverage, a prescribed page
count, every speaker's page, or a clean ideal-wiki match before proceeding.
