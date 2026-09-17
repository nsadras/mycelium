# Full sample-3 comparison

**Status: current full run in progress; no terminal comparison yet.** This is development/stress data,
not an unused holdout. The separate sample-10 frozen attempt preserves the
held-out evidence.

## Prior run

`benchmark_runs/overnight-sample3-v1` retained all 32 session snapshots and
completed 193 questions. Its manifest says complete, but it predates independent
execution/encoding/QA status reporting. Known encoding failures prevent treating
it as complete, clean memory construction.

- Dataset SHA-256:
  `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`.
- Sample 3, `conv-41`; per-batch Build, no memory profile, no replay/frozen store.
- Memory and QA model names: `gemma4:12b`; session context budget 32,768.
  Recorded model calls use a **65,536-token model context window**. These are
  different settings; do not infer a 32,768 model window from the session budget.
- Old manifest has a config hash but lacks current model-digest, effective-config,
  code/evaluator provenance and honest encoding completion fields. Matching model
  names and context limits do not establish equal weights or all settings.
- Reported elapsed: 39,897.412s. Memory-store diagnostic trace: 2,004 attempts,
  440 failed attempts, 36,923.269 model seconds, 37,084,408 input tokens and
  2,302,068 output tokens. These totals include the 193 context-selection calls;
  they are not pure offline encoding. No per-stage total should be conflated
  with overall elapsed or unrecorded QA calls.
- Large traced stages: claim routing 428 attempts / 9,495.0s / 139 failures;
  identity planning 506 / 8,887.9s / 205; truth 123 / 5,950.5s / 0;
  fact synthesis 278 / 4,242.7s / 95; fact candidate selection 412 / 3,170.8s / 0;
  context selection 193 / 2,032.8s / 0. Architecture and stage boundaries changed.
- Lexical mean score: 0.468809. Reported reference-evidence recall: source 1.0,
  claim 0.633869, wiki 0.412487, retrieved context 0.284941. Source coverage does
  not prove extraction correctness or supported answers. The old mean
  `memory_construction_time` (11.557s) actually describes retrieval work and uses
  the earlier measurement contract.

## Current run and interpretation

`benchmark_runs/audit-sample3-0f9f7ee-20260917`, frozen production `0f9f7ee`,
started after the four-session holdout, accepted maintenance/capacity checks and
827 passing structural tests. The manifest records no uncommitted tracked patch,
the same dataset SHA above, all 32 sessions/193 questions, per-session snapshots,
ordinary per-batch Build, no replay store/profile, and diagnostic QA after
incomplete encoding. Retrieval context is retained. Optional existing reference
semantic scoring runs separately; it checks agreement with dataset references,
**not independent source support**, and is not added to production inference.

Configured memory/QA/scoring model: `gemma4:12b`, digest
`4eb23ef187e2c5462566d6a1d3bbbc2f1346d0b4327cbb66d58fffbcc9b2b05c`;
embedding: `embeddinggemma:latest`, digest
`85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1`.
Temperature 1.0, top-p 0.95, top-k 64, reasoning disabled, model context 65,536,
session budget 32,768; retrieval limits are in the captured effective config.
The benchmark checkout stays frozen. Separate bounded model experiments briefly
share the host during the intervals recorded below. Later primary-checkout fixes
are not loaded by this process.

Final reporting must separate encoding, retrieval, answering and judge work,
including retries/cache returns. Preserve incomplete encoding as incomplete even
when diagnostic QA finishes. Use source review to distinguish evidence loss,
identity/temporal mistakes, retrieval misses and answering failures. Aggregate
lexical scores are guideposts; this is not a single-change ablation or proof of
generalization. Architecture, prompts, validation, extraction headroom and
evaluation contracts differ from the old run; historical model weights/settings
cannot all be verified.

## Prior snapshot integrity and unfinished work

Read-only checks of all 32 prior snapshots are saved under the current run's
`source-review/prior-snapshot-inspection.json`, with the inspection script.
Final prior state is **918 claims: 605 routed and 313 routing_failed**, 337
facts, 58 pages, 87 pending identity-review decisions and six truth proposals.
There is no final extraction backlog. From session 26 through 32, routed-claim
and fact counts stay at 605/337 while newly extracted claims accumulate as failed
organization. A completed QA loop is not evidence of a complete memory build.

| Prior snapshot | Claims | Routing failures | Facts | Pages | Pending identity decisions |
|---|---:|---:|---:|---:|---:|
| 1 | 13 | 0 | 9 | 2 | 0 |
| 8 | 221 | 0 | 104 | 11 | 0 |
| 16 | 477 | 51 | 159 | 17 | 3 |
| 24 | 684 | 82 | 331 | 58 | 81 |
| 32 | 918 | 313 | 337 | 58 | 87 |

Session 22 temporarily retains 48 pending extraction segments, recovered in
session 23. Two intermediate snapshots (19/20) each contain one unresolved item
link; final checked references resolve. Exact IDs/citations do not establish
semantic support or completeness. Review-decision counts can include several
decisions about one identity; they are not necessarily distinct user actions.

Additional fact-membership checks, added after the current session-7 defect,
find duplicated membership in the old run too: eight claims at session 15,
a peak of 94 at session 20, and six in the final store. There are 96
fact/placement owner disagreements at session 20 and six at the end. These
are stored facts, distinct from legitimate projections of one fact onto several
pages. The records are retained in
`source-review/overnight-sample3-v1-fact-integrity.json`. The older pipeline and
its pending proposals need separate causal analysis; this shared symptom does
not establish that every historical occurrence had the same failure mechanism.
All six final duplicated claims are under pending truth review. A second current
production reproduction shows how this can happen even without a model failure:
the original protected fact survives, but a new owner receives another direct
fact for the same member. Commit `1883fb6` checks protected membership globally
and lets existing placement-based rendering show the original fact on the new
page. Seventy focused tests pass. A retained fact's original grouping owner may
legitimately differ from its current page placement under review; that difference
alone is diagnostic, not proof of corruption. Duplicate stored membership is
distinct from legitimate multi-page projection of a single fact.

Prior pending truth proposals also need semantic review, not just a count. The
first treats planning taekwondo as superseding kickboxing, although the person
can do both. Another treats a positive opinion of rock climbing as superseding
never having tried it; those statements are compatible. A later successful
aptitude-test attempt is proposed to replace the earlier failure, even though
both historical events can remain true. Human approval prevents automatic loss,
but these are real review-noise risks. Compare source-supported transitions and
distinct events, not simply the number of proposals emitted by the new run.

## Current source review (interim)

### Timing integrity

Session/overall/retrieval timers are monotonic. The structured-call client trace
at this frozen revision still uses wall-clock differences. Session 2 exposes a
negative duration (`bf34f654`, -169ms, versus 1.117s from the server). Do not clamp
the trace or call its sum accurate elapsed time. A separately validated fix,
`f1dfdd9`, changes only elapsed timers and stays outside this frozen checkout.

Old run: all 2,004 attempts have independently recorded server durations, totaling
39,460.313s, versus 36,923.269 client-wall seconds (four negative entries). Server
median/p95/max are 13.750/54.088/128.420s. These totals include context selection;
they are not just offline encoding. Server time includes loading/overhead and
does not equal client elapsed or pure GPU compute. Compare the same measurement
in both arms, retaining missing-duration coverage and failures. Historical daily
and held-out analyses are also preserved in `source-review/timing-comparison.json`.

The store trace excludes the separate answering trace. The prior run's complete
recorded cost components are:

| Component | Attempts | Server seconds |
|---|---:|---:|
| Extraction and organization | 1,811 | 37,263.297 |
| Retrieval admission | 193 | 2,197.016 |
| Answer generation | 194 | 228.779 |
| Embeddings | 232 | 22.845 |
| Semantic evaluator | 0 | 0 |

Every listed attempt has server-duration metadata. The 194 answer calls include
one second round: question 49 uses `memory_sources` successfully, but the shown
source refers only to unspecified baked goods and the answer still abstains.
Only one of 193 questions uses a memory tool. Prior retrieval elapsed totals
2,230.435s and answering elapsed 229.581s; these are measured with monotonic clocks
and are separate from offline encoding and server-time sums. Current evaluator
cost will be reported separately because the old run did not use it. Embeddings
can appear in either the store's `llm-calls.jsonl` or `embedding-calls.jsonl`; the
inspection includes both without counting them as text generation.

**Shared-model limitation:** a separate bounded validator proof used the same
host model during session 5, at 10:15:23–10:18:22 and 10:20:57–10:21:14 UTC on
Sept 17. It made nine real requests (eight paired direct calls and one production
caller check). Their costs are not added to the benchmark's own traces, but
queue/cache effects can affect its call and elapsed timings. Session 5 is not an
uncontended measurement; the full elapsed total also includes any resulting wait.
The benchmark's code, prompts, schema, data and configuration remain frozen.
Windows and probe roots are retained in `source-review/model-contention.json`.

Three later shortlist experiments also share the host: ten direct calls at
11:31:04–11:33:27 UTC and ten downstream calls at 11:38:18–11:40:21 during session
8; then 16 started requests (15 completed, one cancelled) at 11:48:36–11:54:19
during sessions 8–9. These sessions likewise cannot be presented as uncontended.
The proposal is not adopted: its fresh production-caller gate exhausts its
six-minute budget. See the separate decision record in `DEVLOG.md`; isolated
output-token savings do not establish a full-pipeline quality or cost gain.

### Session 1

Completes in 162.5s: 43 segments, 13 claims (12 routed, one deferred), eight facts,
two people pages, no pending identity/truth reviews or terminal build failures.
Attribution needs one retry. Core volunteering, aerial yoga, kickboxing, political
goals/motivation and return from the road trip are present. Exact checked IDs and
links resolve. The new canonical road-trip statement preserves **returning**
yesterday, which the old statement reduced to going on the trip yesterday; its
temporal target still says the trip rather than the return, so temporal scope is
not fully repaired. This is a local source observation, not an aggregate win.

There is a specific new provenance error: `claim-b956ec98e7d1a894` says school
funding enabled repairs and a safer environment, but cites Maria's question at
segment 32 (`D1:11`). John's actual answer is segment 33 (`D1:12`). The claim's
speaker metadata therefore also points to Maria. It is deferred from pages but
remains an incorrectly cited searchable claim. The old run cited the answer.
Several campaign-update claims also omit the antecedent of the acknowledgment.
This is source-to-claim failure, independent of retrieval or later QA.

Page organization remains weak in both runs: routine acknowledgment of a campaign
update is a prominent “Shared Projects” item, while useful interests are collapsed
as supporting detail. The current run repeats the update on both people pages.
These are salience/organization observations; exact layout is not a gate.

### Sessions 2–3

Session 2 finishes in 847.3s, with 52 total claims (51 routed, one deferred),
23 facts, three pages and two pending identity decisions. Source coverage includes
Maria's car donation on Dec 21, friends' activities and peach cobbler, plus John's
networking, family support/activities and pizza. Both kickboxing and taekwondo
survive without the old run's false supersession proposal. The run has no truth
proposals at this point; absence of a proposal is not evidence of general recall.

Identity continuity is worse: a second Maria is created for the new source. The
decision says her newly described interests do not overlap the older aerial-yoga
and volunteering evidence. By session 3 there are three Maria pages, each exposing
pending identity review. The sources are successive conversations between the
same dataset participants; the adapter supplies names/session metadata but no
stable external participant IDs. This is a significant organization/review-burden
failure. It does not authorize exact-name merging or treating every matching name
as the same person. Another review treats a pizza-making event's participants as
possible alternative identities for that event despite explaining they are
different types of subject; false alternatives spread uncertainty to family facts.

The people pages retain useful content, but John's family paragraph is one long
list of near-duplicate sentiments. The pizza fact introduces the precise
conversation timestamp as if it were the event time, unsupported by the source.
Routine campaign acknowledgment remains a prominent shared-project item.

Session 3 finishes in 294.7s: 63 claims, all routed, 31 facts, five pages, three
pending identity decisions. The new online group, shelter visit/toy drive,
tentative education/mentorship/job-training projects, failed aptitude test and
childhood camera are preserved. Maria's beach photo retains month precision for
December 2022. However, “last week” for joining the group becomes the exact day
Dec 25, which the source does not support; the old run retained a week range.
The previously deferred funding claim now appears on a school-funding page,
still with its incorrect question citation. A useful view cannot cure bad
canonical provenance. All checked exact links and IDs resolve in these snapshots.

All 32 source conversations have been read; review anchors are retained in
`source-review/source-notes.md`. Current page review covers snapshots 1–7 so far.
Later sources include distinct pets, events and charities, an actual job loss
versus a tentative new opportunity, and compatible historical activities. These
will be assessed as source-supported distinctions, not required page names/counts.

### Session 4

This session finishes in 1,362.6s with a failed organization result: 106 total
claims (93 routed, one deferred, 12 routing-failed), 45 facts, 17 identities,
ten pages and five pending identity decisions. All 261 source segments are
accounted for, with no extraction backlog or unresolved checked ID/link. The
fourth Maria page and an organization representing their generic teamwork add
fragmentation rather than useful independent context. “Relationship to You” is
used despite there being no declared user.

The community meeting is retained, but “next week” becomes the exact Jan 16
instead of the Jan 16–22 interval. “Last week” for the incident becomes exact
Jan 2 instead of Jan 2–8. These are source-to-claim date-precision errors. Calmly
seeking assistance, returning safely and subsequent relief are canonical claims
but absent from published views after fact-group failure. The image page combines
the laptop/table caption at segment 58 with the later URL at segment 64 (whose
adjacent caption is a handshake at segment 63); valid source IDs alone do not
establish the right image association.

Fact grouping request `926da14a` omits exactly `C027` on each of three attempts:
44 allowed IDs, 43 returned, no duplicates, largest group 11. The retry error
says every claim must belong to one group but never names the missing ID.
Reporting the exact missing/duplicate IDs is a small structural-feedback
hypothesis: it neither assigns meaning nor invents an omitted group. Separate
proof subsequently passed three neutral controls and this retained repair, while
the generic-error control still failed the retained case. The production-caller
check also passed. Commit `4429889` adds only that error feedback in the primary
checkout, with 70 focused structural tests; it is not loaded into this run.
The resulting 12 failed additions include useful incident evidence along with
routine agreements. They remain canonically searchable and retryable, and older
published facts survive. This demonstrates honest failure handling, not successful
organization or evidence that three retries were productive.

### Session 5

The build completes in 1,857.5s, including the shared-model limitation above.
It clears the prior 12-claim publication backlog: 143 total claims, 142 routed,
one deferred, 62 facts, 30 identities, 19 pages, eight pending identity decisions
and no truth proposals. No extraction backlog or checked exact-reference defect
remains. The retained-ID retry fix is **not** in this checkout, so this recovery
cannot be credited to that fix; later changed grouping inputs succeeded.

Source review confirms useful separation of Maria's aunt, the lonely child and
John's own childhood doll. Source 5 reuses the fourth Maria identity rather than
creating a fifth, but does not resolve the earlier fragmentation. The aunt's
inspiration/help, shelter event and comfort offered to the child are preserved.
At the same time, generic agreement and thanks remain prominent, long person-page
paragraphs concatenate independent sentiments, and brief subjects such as a
handshake photograph or generic teamwork receive their own pages. This is a
salience/readability failure, independent of exact page-count expectations.

A consequential omission occurs at source segment 1 (`D5:1`): John explicitly
says he went to the community meeting. It becomes source-only, with no claim.
The page retains the older future meeting plan. This is an extraction miss,
not a retrieval problem or a missed comparison between two retained statements.
The prior run also omits this attendance update, so it is a shared failure,
not a demonstrated regression introduced by the current changes.
“Last week” for the shelter event becomes unsupported exact Jan 21; the child's
page also dates sitting/talking to the conversation's exact Jan 28 timestamp.
Canonical coverage and derived prose therefore remain untrustworthy despite a
completed build. “Accounted for” means claimed/source-only/pending bookkeeping,
not complete useful recall; one cited segment also has a source-only disposition,
so those counts are overlapping sets, not a partition of 321 source segments.

### Session 6

The session finishes in 1,003.4s: 401 segments, 164 claims (151 routed, ten
routing-failed, three deferred), 69 facts, 31 identities and 21 pages. Eight
identity decisions remain pending, with no truth proposals. The 103 rendered
items and 66 links pass the exact-reference checks; extraction has no backlog.

Useful new evidence includes David's housing difficulties and support referral,
Maria's family money problems and aunt's assistance, and her conditional offer
to help with future events when available. Source 6 attaches Maria to the first
identity while source 5 attached her to the fourth; continuity remains fragmented.
An independent page for the generic belief that something must be done about
social problems adds little accessible context. This is a utility observation,
not a requirement for a particular page count.

“Last Friday” correctly resolves to Feb 3 from the Feb 5 source. However, the
new charity event is assigned to the existing identity for the earlier shelter
event without evidence that they are the same occurrence. Correct calendar
arithmetic does not establish event identity.

Fact-grouping request `645cd207` returns 37 of 40 IDs on all three attempts,
omitting exactly `C025`, `C035` and `C038`, without duplicates or an oversized
group. Its generic validation feedback has the same limitation as session 4;
the separately committed fix is still outside this frozen run. Ten claims remain
retryable while John's previous published facts survive. The affected additions
include his initiative's unemployment motivation and volunteer response as well
as generic support/thanks; missing publication is not uniformly low-impact.

### Session 7

The session finishes in 1,261.2s: 450 segments, 176 claims (157 routed, 14
routing-failed, five deferred), 74 facts, 34 identities and 24 pages. Nine
identity decisions remain pending, with no truth proposals or extraction backlog.
Source review confirms the creative-writing class, renewed candidacy, Jean's
history and values, and the yoga invitation remain canonical. “Yesterday” resolves
correctly to Feb 24; “not too soon” stays unresolved. Jean's history/value claims
still omit the cited antecedent naming her. A fifth Maria page holds her writing
class while volunteering remains on the first, including within this same source.
The app's explicitly declared user is bound directly; this third-party import
does not declare a user or stable external participant IDs. The fragmentation
does not demonstrate that the app duplicates its declared user.

Grouping request `c2a6c113` omits `C048` and `C049` from 59 IDs in all three
attempts; the first also repeats `C038`. John's earlier facts survive. The
workload remains frozen before the separate exact-ID feedback fix.

**A publication-integrity defect is also exposed.** Ownership of
`claim-2b3349eda8df63fd` changes from `person-john` to `topic-resource-inequality`.
John's grouping fails, but the destination's new fact and placement override
still publish. The claim belongs to both `fact-53cd1c38258a` and
`fact-4945c545dd8b`, and appears twice on the destination page. Filtering failed
routes alone did not filter the independent fact/placement result. This is a
transaction-scope bug, independent of semantic grouping quality or the desired
number of pages. The inspection now checks duplicate fact membership and
fact/placement owner disagreement as well as resolvable references.

A separate primary-checkout fix, `dbddc04`, holds both sides of a failed transfer, including
chains of transfers, while independent additions can publish. Global truth-review
failure also holds staged maintenance. Tests exercise source/destination failure,
successful transfer, retry and preserved old pages through the real Build commit.
The fix adds no model call, schema, or semantic decision and stays outside this
frozen workload. Full structural validation passes 839 tests with 75 integration
tests deselected; this does not establish the model's semantic correctness.

### Session 8

Completes in 2,437.9s, with the shared-model intervals above. All 535 source
segments are accounted for and none awaits extraction. There are 215 claims:
181 routed, 33 routing-failed, one deferred; 87 facts, 42 identities, 31 pages,
135 rendered items, 97 item links, 11 pending identity decisions and no truth
proposal. The existing duplicate membership from session 7 persists; other
checked references/links resolve. Checked source-coverage sets overlap and are
not a partition of the 535 segments.

Source 8 and all changed page bodies were reviewed against session 7. Useful
retained additions include Kyle's name/age, family park activities, Maria's
childhood activities, London/England inspiration for her home decor, and how
she developed shelter relationships. The London claim adds a context citation,
but cites the earlier question about the picture's inspiration (`seg-0048`)
rather than the nearer England question (`seg-0056`) or trip statement
(`seg-0050`). Exact citation validity alone still does not establish complete
antecedent support. Maria's related England and London assertions split across
`maria` and `maria-2`; five Maria identities remain, with warnings on uncertain
assignments. Fragmentation continues within one conversation.

Her grandmother's death is retained canonically with the appropriate Feb 27–Mar 5
week range, but deferred because only the grandmother is attributed and has no
eligible page. A related grief statement appears on `maria-2`. This demonstrates
a page-coverage consequence of attribution/admission, not missing extraction.
In contrast, the park's “last weekend” becomes **March 3**, from model-declared
`day_offset(-3)`, and the test retake's “last week” becomes **Feb 27** as an exact
day. Neither exact day is supported. The calendar calculator executes the
declared operations; the semantic interpretation remains wrong.

The retake claim also omits the source's “great results,” while the old failed
test remains the visible history. No truth proposal is required just because a
later, distinct test succeeds; the issue is preserving and publishing both
historical events. New picnic, violin-concert, parenting and service-goal claims
are routing-failed along with routine acknowledgments. Old John facts survive,
but useful additions do not reach his page. Grouping request `b825ca77` omits
`C009` and `C015` from its 48-ID partition in all three attempts; there are no
duplicates and the largest group has 12 members. This is the same generic retry
feedback defect targeted by the separately validated `4429889`, which is not
loaded by this frozen run.

Organization still gives generic agreement and encouragement substantial space,
including “Relationship to You” with no configured user. The index describes
John with “Maria agrees with John”; this is an unhelpful summary of a rich page.
New places/artifacts can provide navigable context, but their count is not a
quality gain and long combined sentiment paragraphs remain hard to scan.

### First-five-conversation cost/quality checkpoint

This prefix uses the same five conversations (321 segments). Trace boundaries
are the first extraction request for source 6, so no later-session or QA work is
included. Old model/code provenance remains incomplete, and current session 5
has the explicit shared-model interval above: this is not an isolated ablation.

| First-five checkpoint | Prior | Current frozen run |
|---|---:|---:|
| Text-generation attempts / failed attempts | 100 / 6 | 387 / 5 |
| Input tokens | 839,982 | 3,143,541 |
| Output tokens | 107,165 | 268,468 |
| Server seconds | 1,670.497 | 4,482.670 |
| Canonical claims | 138 | 143 |
| Routed / deferred / failed claims | 138 / 0 / 0 | 142 / 1 / 0 |
| Facts / identities / pages | 68 / 6 / 5 | 62 / 30 / 19 |
| Pending identity / truth reviews | 0 / 1 | 8 / 0 |

The current pipeline uses 3.87× as many generation attempts and 2.51× the output
tokens, with nearly the same retained claim count. Larger page counts are not a
benefit by themselves. Source review shows worse identity fragmentation, wrong
date precision, an omitted meeting update and substantial generic prose. The old
truth proposal incorrectly treats taekwondo as replacing kickboxing; its absence
in the new run is a local improvement, not enough to justify the extra work.
At this checkpoint, a broad quality or cost improvement is **not demonstrated**.
The daily follow-through saving is against a different, already-expanded
baseline and must not be substituted for this comparison.

Current prefix cost is concentrated in truth screening (96 calls / 1,877.897
server seconds) and comparison (46 / 480.978), together 52.6% of server time.
Extraction uses nine calls / 482.937s; discovery/identity/admission 92 / 545.793s;
attribution/routing 54 / 715.282s; fact selection/grouping/text 90 / 379.783s.
The bounded candidate cap prevents exhaustive growth but does not make the
pipeline cheap. These observations favor simplifying duplicated interpretation
and improving useful source retention before another expansion of retrieval or
review machinery. They are prefix findings, not a claim about the unfinished
32-session/193-question result.

A later trace checkpoint during session 9 contains 276 truth-screening and 215
truth-comparison calls, with **zero cache returns in either stage**. Successful
validated responses are present in the decision cache, keyed by the full request
digest; the normal benchmark trace stores call metadata and failures but no
successful request bodies. Consequently, this run shows no observed reuse of
whole truth requests at that checkpoint, but does not establish how many
individual unchanged pairs were repeated. Estimating a per-pair cache saving
from response aliases alone would be invalid. Pair-level reuse is not adopted
on this evidence; its semantic input and invalidation contract would need proof.

### Prior-run final views and failure profile

The prior final index and both main participant pages were reviewed, alongside
early/middle snapshots. They retain useful interests, community work, family
context and earlier dated events. Organization nevertheless obscures utility:
routine encouragement dominates “Relationship to You” despite no configured user,
some plans appear twice through shared-page references, and long paragraphs
combine many similar sentiments. The final index even associates the charity-run
page with a road trip and the shelter-fundraiser page with the veterans petition.
These are scope errors, not objections to particular page counts or titles.

The final people pages still present June's promotion, old car repairs and May's
upcoming fundraiser as current, and omit late job loss, prospective hardware
work, distinct newly adopted dogs and firefighting activity. The prior snapshot
checks show that routing/fact publication had stopped advancing after session 25,
with 313 claims routing-failed at the end. These omissions therefore cannot be
ascribed solely to retrieval or the question-answering model. Canonical claims
remain available even when their derived pages are stale.

Of 2,004 main-model attempts in the old store trace, 440 failed: 205 in the old
identity-plan stage, 139 in routing, 95 in fact synthesis and one in extraction.
Those older stage names/contracts differ from today's pipeline. The trace lacks
exception messages and the store has no per-failure request files, limiting
retrospective diagnosis; failed-attempt count is not terminal-failed-request count.

### Reference/evaluator limits identified before current QA

Review of the prior questions/predictions confirms that the lexical score is
not grounded answer accuracy. For example, the correct “Maria had dinner with
her mother” receives 0.5 at zero-based question 0, and “July 4th” receives zero
against “Independence Day” at question 39. A wrong Aug 3 answer against Aug 4
still receives 0.667 at question 54. Keep the raw metric for comparison, but do
not optimize production toward its token overlap.

There are also problems in the supplied references themselves:

- Questions 68–69 ask about **December 2023**, while their cited turns `D1:3`
  (aerial yoga) and `D2:1` (car donation) are from December **2022**. A date-aware
  qualification or abstention can disagree with the expected answer correctly.
- Question 63 expects exactly two weeks between dog adoptions. `D30:1` says
  Coco arrived two weeks before Aug 11; `D31:2` says Shadow arrived “last week”
  as of Aug 13. These statements do not establish that exact interval.
- Category-3 references include speculative financial status, degree subject
  and willingness to move abroad. Local political/military goals do not prove
  that a person would refuse to live abroad. Source-grounded uncertainty must
  remain permissible; satisfying these reference guesses is not a product gate.

The current reference-only semantic judge can reduce wording sensitivity but
cannot adjudicate these source defects. Neither raw lexical scores nor semantic
reference agreement will be called source-grounded accuracy. Questions and
references remain unchanged in the frozen run, with these limitations visible.

All 193 prior question/reference/prediction rows were read. A selected evidence
review, fixed before the current QA phase, separates distinct mechanisms:

| Prior question (zero-based) | Evidence and failure location |
|---|---|
| 28, supported causes | Admitted context contains veterans and generic motivation, omitting already-published education/infrastructure evidence; answer mirrors the incomplete selection. |
| 54, church community-work date | Admitted canonical metadata correctly says Aug 4. The answer says Aug 3: this is a QA error, not a missing claim or incorrect encoded date. |
| 87, Pacific Northwest trip | Admitted facts incorrectly add Maria to John's family trip; answering repeats that upstream synthesized error. |
| 95, dinner with mother | The relevant fact exists and was admitted for question 0, but this query admits only fundraiser evidence and abstains. This is a retrieval/selection loss. |
| 137, job loss | Correct answer uses two unorganized canonical claims. Stale wiki pages did not prevent this recall. |
| 147, second puppy | Both names and Shadow's relationship to the other dog are admitted, but the naming claim lacks an explicit owner and the answer abstains. Available facts do not automatically yield a coherent answer. |
| 167, meal with father | Admitted meal content lacks the mother context; the answer accepts an unsupported father premise. |
| 189, John's puppy | Admitted unowned “The puppy's name is Shadow” becomes an incorrect answer about John. This spans incomplete canonical context and QA failure to establish ownership. |

These are diagnostic examples, not eight scored acceptance targets. Their saved
workspaces expose no memory-tool calls; tool availability alone does not establish
that the model will seek missing relationships or check a false premise.
