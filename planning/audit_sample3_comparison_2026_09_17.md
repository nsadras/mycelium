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
The benchmark checkout stays frozen and no other model-dependent experiments
run alongside it. A timing-only correction is validated in the separate primary
checkout; it is not loaded by this process.

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
`source-review/source-notes.md`. Current page review covers snapshots 1–4 so far.
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
hypothesis worth testing after this frozen workload; it would neither assign
meaning nor invent an omitted group. It is not integrated during this run.
The resulting 12 failed additions include useful incident evidence along with
routine agreements. They remain canonically searchable and retryable, and older
published facts survive. This demonstrates honest failure handling, not successful
organization or evidence that three retries were productive.

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
