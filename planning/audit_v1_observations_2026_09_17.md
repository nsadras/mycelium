# V1 frozen source review — completed with incomplete encoding

The predeclared unused sequence completed at frozen production revision `2c5c4fe`:
`benchmark_runs/audit-v1-heldout-2c5c4fe-20260917`. It encodes the first four
sessions of LoCoMo sample 10 (`conv-50`), snapshots each session, and runs zero
dataset questions. This is an encoding/view diagnostic, not a full-sample QA
score. No prompts or production modules changed during the run; a documentation-only
commit was made while it ran. Later citation/capacity experiments use its failures
as regression evidence and cannot replace this held-out result.

## Completed first snapshot

Session 1 finishes in 308.5s: 61 source segments, 22 claims. Six claims are left
`routing_failed` by one identity work-unit failure; the other 16 are routed.
Calvin and Dave have separate pages, and incidental objects/places remain
provisional. No canonical user is configured for this third-party conversation.

Source review finds useful coverage of Calvin's travel plan and Dave's classic
car event. The trip retains tentative collaboration with musicians, a stay of
several months, and the later Boston destination. “Next month” is correctly
represented as April 2023, without inventing a day. The combined travel sentence
is repetitive but grounded. Routine offers to help and reports that things are
going well receive undue prominence; exact inclusion is not a release metric.

The identity failure is a provenance limitation, **not an invented country**.
The extracted claim says Calvin has never visited Japan but cites only his
reply, “Never been there before,” at segment 25. The preceding question names
Japan, but that antecedent was not included in the claim's citations. The
matching request includes another same-source Japan reference as cohort context,
and the model returns Japan. Strict name-copy validation rejects it three times
because the selected subject's own cited segments do not contain that name.
Failure evidence: `structured-failure-b15e3469-attempt-{1,2,3}.json` in the first
snapshot's diagnostics. The code does not silently publish the rejected name;
the six canonical claims remain stored and searchable.

This exposes a general boundary between reference resolution and complete
citations. Current extraction instructions mention `context_segment_ids` for an
earlier reference even when the antecedent is another **new** segment in the same
batch, where that field is absent. Its separate `segment_ids` field permits such
support but lacks a field description. Two later bounded proposals tested clearer
existing domains and a unified supporting-citation field. Neither demonstrated
reliable improvement, so neither was integrated; details are below. Strict naming
validation remains. No verifier call or lexical citation repair was added.

If this sequence informs a later contract change, subsequent runs of it must be
labelled regression evidence. The saved frozen attempt remains the held-out
measurement; its failure is not replaced by a tuned rerun.

## Review scope

All four sources and successive page bodies were reviewed. Full sample 3 remains
pending. Manual device checks remain user-owned. Interim notes below retain the
state at inspection; terminal measurements follow.

## Session 2 interim evidence (publication still running)

Extraction retained 55 claims from 75 source segments. Core facts are present:
Calvin's new luxury car, Dave's Boston festival attendance and preference for
Aerosmith's performance, and Calvin's recent studio work and possible
collaboration. The extraction also retains greetings, acknowledgments, a goodbye,
an image URL, and routine positive reactions. The existing production prompt
already says to leave pure conversational acknowledgments source-only; this is a
model adherence/usefulness failure, not a missing deterministic exclusion list.
Do not add a lexical filter or another salience call to hide it.

Several normalized names lack their antecedent citations here too. For example,
`claim-daa434444cc5a48e` names Aerosmith while citing only segment 42 (“Their
performance was incredible”). `claim-60346943d1823d44` interprets the third-person
“He was jamming out” as Dave, although that line does not establish Dave as the
subject; its surrounding discussion concerns the performers. These are evidence
and reference-resolution risks, distinct from whether QA later retrieves a claim.

The second routing pass is a separate general cost lead: promoting a page and
finding any earlier dependency currently reroutes the entire incoming evidence
union. A later neutral prototype limits that pass to old exact
dependencies and initial claims explicitly describing a newly eligible page that
was absent from their first route. Already valid routes and unrelated failures
must survive the merge. Configured-model/native validation later supported this
change, documented in DEVLOG. There was no production change during this frozen run.

## Completed second snapshot

Session 2 finishes in 1,901.2s (31.7 minutes), recovers all six earlier routing
failures and has no terminal routing failures of its own. The snapshot contains
77 routed claims, 34 consolidated facts, 11 identities (eight materialized), and
zero truth-reconciliation proposals. Recovery does not repair the missing
antecedent citations in the retained canonical statements.

All eight page bodies were reviewed against the two sources. Core travel, car
and festival information survives, including tentative collaboration and the
Japan month range. Presentation is poorly prioritized: Japan travel and studio
work are collapsed supporting detail, while routine offers to help, acknowledgments
and conversational requests are prominent. “Shared Projects” contains an update
promise without describing a shared project. Long combined sentences group
unrelated reactions. Image/event and performer-image pages fragment the same
conversation while the Boston festival identity remains provisional. Exact page
counts are not the problem; the useful event lacks a coherent independent view.

There are factual time failures, not merely editorial differences. “Last week”
for studio sessions is declared as `day_offset: -7`, becomes March 19, and the
fact renderer repeats that unsupported exact day. “Last weekend” for the Boston
festival becomes March 26 (the conversation date), and is then repeated as the
event date. Yesterday's car ride correctly becomes March 25; April travel retains
month precision. These failures show incomplete generalization of the existing
calendar contract. The source expressions and declarations remain inspectable;
they must not be scored as correct solely because calendar arithmetic agrees
with a wrong model declaration.

The potentially misresolved third-person performer reference is amplified into
Dave jamming to Aerosmith hits in his published festival summary. Canonical source
coverage and valid segment IDs do not prove that an assertion is supported by
those segments. No test-specific correction is applied to this frozen evidence.

## Session 3 interim evidence

The third source has 68 segments and 27 extracted claims. It preserves Calvin's
world-tour aspiration, a Boston visit after the Frank Ocean tour, Dave's interest
in auto engineering and arrangements to eat/explore together. However, the model
marks the first 24 segments source-only, losing the reported Tokyo music event,
meeting artists/industry professionals and the producer's advice about a unique
sound. This is a substantial extraction recall failure despite complete segment
accounting and a successful, nontruncated request (3,502 output tokens; stop
reason `stop`). Later retrieval cannot reliably recover these through the claim
index. Source text remains intact. No lexical reinstatement or override of the
model's `source_only` decisions is applied.

Both over-extraction of routine chat in session 2 and omission of useful event
content in session 3 need to remain in the quality assessment. A small citation
contract repair does not establish a remedy for these broader extraction errors.

## Completed third snapshot

Session 3 finishes in 786.3s (13.1 minutes): 104 routed claims and 43 facts, the
same 11 identities/eight pages, and no truth proposals. One pending identity
review concerns the Boston festival versus the image-derived concert. It remains
visible; the run does not silently approve the merge.

The new aspirations, tour prerequisite and meal arrangement appear in the people
pages, but coherence weakens. Both people gain a “Relationship to You” section
for their relationship to each other although this third-party run has no
configured user. Calvin's car page now includes a claim about seeing Dave's car
and Dave showing other cars; this conflates independently owned objects. The
source does not clearly establish Dave's ownership either. The source-to-claim,
identity and attribution layers need to be distinguished when diagnosing this.

The old March car-event evidence and April “last weekend” visit are combined
into a long timeline item without separating the event occurrences. Earlier
Japan plans remain future-framed; the omitted Tokyo-event claims prevent the
normal encoded evidence from marking the visit's realization. Explicit source
time wording remains present, but prose alone is an unreliable current-state
summary. These are broader semantic limitations; neither the citation-domain
proposal nor narrower promotion work is claimed to fix them.

## Final snapshot and completion

All four sessions and snapshots finish in **3,807.956s (63.5 minutes)**. Manifest:
`execution_status=complete`, `encoding_status=incomplete`, `qa_status=not_run`,
scoring disabled. Zero questions were requested; the empty summary's zero score
is **not an accuracy measurement**. The final session takes approximately 812s.

The fourth source preserves Dave opening a car-maintenance shop, his motivation,
and prior restoration work. Its second extraction batch, 41 of 89 segments,
exhausts the 8,192-token allowance and fails after one attempt. The pipeline
rejects truncated output and leaves that batch pending. This loses the later
shop-service details and Calvin's necklace gift from extracted memory while raw
source text remains available. Finalize under `per-batch` does not retry it.
This is a visible capacity failure, distinct from session 3's successful request
silently choosing source-only for useful content. Last year's restoration stays
unresolved even though a dated conversation anchor is present; it does not invent
an exact date in this case.

Final state: four sources / 293 segments; 126 claims, all routed; 47 facts;
11 identities / eight materialized pages; one pending identity review and zero
truth proposals. Of the segments, 128 are cited by claims, 124 are exclusively
source-only, and 41 await extraction. Two earlier source-only declarations also
have later citations, so raw category counts overlap. No unresolved exact citations
were found among the 70 rendered items; all 43 item links resolve. No checked claim/fact/page
cross-reference is missing. These checks **do not prove semantic support**.
Read-only SQL/YAML inspection and per-stage summaries are saved in the run's
`source-review/inspection.json`; original snapshots are unchanged.

The final people pages retain the unsupported precise dates, ambiguous event
merging, misleading “Relationship to You” sections and cross-owned car content
noted above. Opening the shop is usefully prominent. Several other paragraphs
combine repeated feelings into long sentences. This sequence fails broad quality
acceptance; its factual and recall defects are more important than exact page
counts or stylistic differences.

## Calls, retries and cost

Configured `gemma4:12b`, temperature 1.0, reasoning disabled, model context
65,536, session budget 32,768. Dataset/config/model provenance is in the manifest.
The main model performs **314 inference attempts**, comprising 308 unique
requests and six retries: eight failed attempts total. Six cache returns take
0.007s and are excluded from inference counts. Tokens: 2,527,628 input and
234,640 output. Original client-wall trace total is 3,634.789s; those durations
use a clock vulnerable to adjustment, discovered later in the full sample-3 run.
Use the independently recorded **3,770.842 server-total seconds** for stage cost
below: all 314 attempts have server metadata. Server median 9.087s, nearest-rank
p95 27.016s, maximum 112.733s (the truncated extraction). Server totals include
server overhead/loading; they are not overall elapsed or pure GPU-compute time.
The production timer fix is `f1dfdd9`; it does not rewrite this frozen run.

| Stage | Attempts | Failed attempts | Server seconds |
|---|---:|---:|---:|
| Extraction | 8 | 1 | 532.035 |
| Subject discovery | 14 | 0 | 152.913 |
| Identity matching | 65 | 3 | 259.038 |
| Page admission | 7 | 0 | 39.718 |
| Attribution | 26 | 4 | 524.042 |
| Routing | 22 | 0 | 268.567 |
| Truth screening | 68 | 0 | 1,399.148 |
| Truth comparison | 30 | 0 | 308.481 |
| Fact candidate selection | 16 | 0 | 126.961 |
| Fact grouping | 15 | 0 | 108.848 |
| Fact text | 43 | 0 | 51.092 |

Separate embeddings: 117 recorded operations / 18.841s / 94,432 input tokens.
Original traces and the later independent-server analysis are both retained.
The latter is in the full sample-3 run's `source-review/timing-comparison.json`.
Earlier direct-probe client latencies quoted below have the same clock limitation;
counts, tokens, semantic findings and acceptance decisions are unchanged.
Full per-call traces and
failed request/response dumps are retained. Unlike the daily-driver recorder,
this ordinary runner does not save every successful prompt/response; persisted
claims, work units, cached decisions and snapshots support source review, but the
successful-call archive is not complete.

Truth work consumes 45.3% of main-model time, without producing a truth proposal.
This alone does not make the comparisons incorrect, but shows that bounded
candidate work remains expensive on routine, overlapping conversation. Redundant
page-promotion work and extraction output capacity are concrete mechanisms to
check next. Do not add another salience or verifier call to make this sample look
perfect. Citation quality, temporal precision and distinct-entity attribution
remain real product limitations requiring evidence beyond narrow direct probes.

## First citation proposal rejected

`reference-citation-contract-20260917T084001Z-1f6ff9df` compares the unchanged
contract with clearer existing-field descriptions across eight small neutral
cases and one dense conversation. Both pass only **4/9 citation checks**, with
no malformed responses. The proposal still omits antecedents for resolved places,
accepted/refused proposals and pronouns. It also drops nearly all content in the
dense case; its lower time/output is not an efficiency gain. The proposal is not
integrated. Current/proposed model seconds are 115.488/37.480, input tokens
35,153/35,855, output 8,260/1,999. The dense control's synthetic IDs sort
lexically, unlike production's padded IDs; both arms receive the same ordering.
These small controls do not establish general extraction recall.

## Unified supporting-citation proposal also rejected

`unified-reference-contract-20260917T085010Z-f5532aec` uses one flat
`supporting_segment_ids` field for additional new/older evidence, retaining the
enclosing segment as the primary citation. It changes no call count or nesting.
The predeclared stop rule fires after four small neutral cases: **1/4 passes**,
with no malformed output. The standalone proper-name case passes; resolved-place,
acceptance and refusal cases still omit necessary support. Four calls use
14.990s / 13,905 input / 723 output tokens; the remaining five cases are not run.
The proposal stays outside production. Stop this round of citation-contract
experiments; failed small cases do not justify more wording or another LLM stage.

## Output-capacity follow-through (regression evidence)

A separate operational proposal raises extraction's output ceiling from 8,192 to
16,384 tokens. The prompt, schema and call sequence stay unchanged; output reserve
is at most one quarter of the configured context window, and the existing batch
planner budgets that actual allowance. Larger requests may split sooner where
input and generation cannot fit together. This is a capacity bound, not an
instruction to produce more claims or accept low-value conversation.

- Neutral dense control, `extraction-output-reserve-20260917T085401Z-2932b6c2`:
  both limits preserve 32 claims from 32 segments. At 8,192/16,384, actual output
  is 6,028/6,060 tokens and time 77.944/76.772s, with the same 8,407 input tokens.
  This control does not need the higher ceiling and shows no meaningful extra
  generation. A retained-request replay in that first experiment accidentally
  appended the schema instructions twice. Its empty-claim result is **invalid
  comparison evidence**, retained as a harness failure.
- Corrected `extraction-reserve-exact-replay-20260917T090129Z-e3234344` asserts
  exact equality of the original messages, schema, model and options, changing
  only `num_predict`. The failed request now completes in one call: 17,068 input,
  8,770 output tokens, 116.774 traced seconds, stop reason `stop`. Original:
  17,068 input, 8,192 output, 107.886s, truncated. Actual output exceeds the old
  limit by 578 tokens. This is one stochastic replay, not a general latency gain.
- Source review confirms the recovered batch includes the shop's maintenance
  and restoration services and the artist's necklace gift. It also produces
  claims for all 41 segments, including routine encouragement, thanks and image
  URLs. Citation omissions persist. Finishing a request restores useful evidence
  but does not establish good salience, complete provenance or concise memory.

The frozen incomplete run above remains the held-out result. A retry on its
copied store is a regression/operational check, never a replacement holdout.

Integrated production retry:
`extraction-reserve-integrated-20260917T091010Z-39ca977b`. One call, 117.068s,
17,068 input / 8,342 output tokens, 41 new claims; extraction backlog clears.
Original claims, sources and completed batches stay unchanged. Service/gift
coverage returns, alongside routine chat. New claims await organization because
this check runs extraction only. No held-out snapshot is overwritten.
