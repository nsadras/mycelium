# V1 source review — in progress

The predeclared unused sequence is running at frozen revision `2c5c4fe`:
`benchmark_runs/audit-v1-heldout-2c5c4fe-20260917`. It encodes the first four
sessions of LoCoMo sample 10 (`conv-50`), snapshots each session, and runs zero
dataset questions. This is an encoding/view diagnostic, not a full-sample QA
score. No prompts or production modules are changed during this run.

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
support but lacks a field description. A possible small fix is to clarify these
existing evidence domains and retain antecedent citations at extraction, keeping
strict naming validation. An unintegrated neutral direct probe is prepared at
`/tmp/mycelium_reference_citation_probe.py`; it has not run yet. No relaxed name
validation, extra model call, or new response field is proposed.

If this sequence informs a later contract change, subsequent runs of it must be
labelled regression evidence. The saved frozen attempt remains the held-out
measurement; its failure is not replaced by a tuned rerun.

## Remaining review

Sessions 2–4, final completion/coverage, per-stage cost, citations/links, pending
reviews and successive page coherence remain to be assessed. Full sample 3 is
still pending. Manual device checks remain user-owned.

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
union. A prepared, unintegrated neutral prototype limits that pass to old exact
dependencies and initial claims explicitly describing a newly eligible page that
was absent from their first route. Already valid routes and unrelated failures
must survive the merge. Direct configured-model/native comparison is pending;
there is no production change during this frozen run.

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
