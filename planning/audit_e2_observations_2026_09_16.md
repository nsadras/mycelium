# E2 longitudinal comparison and source review

Production: `fdcc767`; run `benchmark_runs/audit-daily-e2-fdcc767-20260917`.
The complete nine-checkpoint production run and frozen ranked-claims control are
terminal. This is completed diagnostic evidence, not passed product acceptance.

## Observed issues through checkpoint 6

- cp2: 5 claims, 5 facts, 2 pages; question-scoped judge correctly accepts the
  concise desktop-app answer. Source review supports the local/private/desktop
  requirements. The project page is useful; some duplication with You remains.
- cp3: 24 claims, 16 facts, 7 pages, 23 placed and one policy exclusion. The
  project keeps its ID while gaining its name. The packaged-build deadline
  resolves correctly to September 11 from September 8's Friday reference.
- New-name spelling remains broken: `organization-transapcloud` / `TransapCloud`
  was adopted although the cited source and displayed claim say TranscribeCloud.
  Existing-name updates are guarded; newly created names/descriptions are not.
  Original identity request:
  `diagnostics/requests/a4c416b2d1ce4344b79ccce5460f6f77.json`.
- cp3 project page loses requirements/privacy content as statements move to You;
  people pages retain responsibilities, but the project page provides poor access
  to the cumulative context. The old unnamed/readiness state remains current.
- Calendar source `source-e5e033d531fe71e8` hits all three extraction attempts:
  model outputs ISO timestamps in date-only AbsoluteInterval fields. JSON schema
  allows arbitrary strings while Python rejects the timestamps. Attempts cost
  11.311/12.151/12.402 seconds. Retry prompts expand from 3,628 to 11,548 tokens
  because the untagged time union reports 66 branch errors. Later builds retry
  the same source and preserve a visible extraction backlog.
- cp5's explicit pilot change is captured in claim text, but its September 22/28
  dates are incorrectly declared as weekday-in-week operations, resolving to
  September 27/25. This is a semantic time-kind error, beyond date-string syntax.
  Claim: `claim-d26287afda9d70dc`; source `source-1724d470feb8a112`.
- The relevant truth pair WAS selected. Comparison of old
  `claim-485fb41212450e53` and the new claim returns same/no_change, explaining
  that the original target and its replacement are historically compatible.
  It confuses preserved historical truth with current applicability. Original
  request `diagnostics/requests/e6871026f73c4efb93df4c1da677cb9d.json`.
  The explicit approval action consequently reports zero matching proposals;
  cp6 is not a successful reviewed transition.

## Cost / coupling evidence worth investigating

- Source attribution emits a full claim/entity matrix with a reason plus
  assertions plus relation. Sampled batches have 35–39 unrelated cells out of 48;
  their reasons occupy roughly 2,200–2,600 characters versus 400–700 characters of
  asserted content. One validation failure returns asserted content with a
  reporting-only role. A shorter explanation contract is a candidate for direct
  proof, not a reason to add another semantic stage.
- `DreamPolicy.scope_revision_claims` adds the previous whole cohort, every claim
  owned by You, every deferred placement and neighborhoods of queued-claim
  references when ANY newly materialized page triggers revision. Thus unrelated
  new pages can reroute unrelated history and cause both cost and page churn.
  Inspect `initial_scope_claims` too: it always re-adds every deferred placement,
  bypassing the caller's include_deferred choice. A narrower exact dependency
  scope may be the highest-impact S2 fix. Prove actual old-page promotion,
  unrelated addition, retained identity/no-page review and deferral behavior.
- Truth payloads include recreated reference IDs/build IDs/timestamps, page_owner
  and `canonical_owner` references. The latter carries long routing explanations.
  These are presentation/audit context, despite the product rule that ownership
  does not decide identity/truth. S1 can remove that noise, retain stable semantic
  identity fields and raw citations, and verify actual rerouting cache reuse.
- Historical full sample3 cost (old different contracts, not matched): routing
  9,494.963s/428 attempts; identity plan 8,887.854s/506; truth 5,950.508s/123;
  synthesis 4,242.693s/278; fact candidates 3,170.826s/412; extraction
  3,143.627s/64; context selection 2,032.798s/193. S1 alone cannot establish a fast
  whole pipeline. Broad rerouting and verbose attribution also need measurement.

## Unintegrated probes prepared while the model is busy

All are temporary hypotheses, not production changes. Run serially AFTER the
full E2 invocation and comparison, so timing is not polluted by competing jobs.

- `/tmp/mycelium_name_origin_probe.py`: current/proposed, 12 neutral boundaries
  plus the saved new-name failure (26 calls before retries). One flat title_basis
  distinguishes copied source names from unnamed descriptions; exact spelling
  validation only applies to the model's declared source-name choice. No new
  call, nesting or lexical identity inference. Adopt only with correct bases,
  namesakes, descriptive titles and actual native routing validation. Reject
  if the model merely relabels wrong proper names as descriptions.
- `/tmp/mycelium_date_shape_probe.py`: current/proposed, four neutral clock/date
  cases plus the saved calendar source (10 calls before retries). Adds the
  existing YYYY-MM-DD requirement to decoding via JSON-schema pattern. No
  date parsing from natural language and no new temporal kind. This alone does
  NOT address explicit dates being misclassified as relative weekdays.
- `/tmp/mycelium_truth_compact_probe.py`: three arms over six neutral pairs plus
  the saved missed transition, one batch call per arm. Compact input removes
  page ownership, canonical_owner bindings and reference bookkeeping, preserving
  stable role/entity/surface/confidence/reason/origin/review identity. A separate
  arm clarifies supersession as changed current applicability with preserved
  historical truth. No new output field or model stage. Preserve compatible,
  hypothetical and independent historical-event counterexamples.

## Comparison and rollout notes

The ranked-claims control matches candidate and token budgets; it fills context
without the production five-fact cap, because one generated fact can bundle many
claims. The original five-claim draft would have unfairly restricted this arm.
This was corrected before any native baseline result was observed. Shared
extraction/identity/review work and cold snapshot index rebuilding are separate
from attributable retrieval/presentation cost; this is not a Mem0 benchmark.

UI: 24 component tests, lint and build passed. Existing bundle-size warning
remains. Read-only host socket check found no app listeners at 8000/5173. An async
question asks whether the user will do browser/microphone/Wi-Fi/Tailscale checks
later or start services now; no response has arrived yet. No server was started.

Additional prepared probe: `/tmp/mycelium_revision_scope_probe.py` compares the
current pipeline with an instance-patched exact-dependency revision policy after
one shared neutral seed build, then an unrelated named project addition. It
records old-claim re-attribution, canonical/fact equality, actual calls and
snapshots. This is a native prototype, not an integrated policy. A page-promotion
counterexample and explicit deferral/source-scope tests are still needed before
adoption. Existing `include_deferred=True` queue behavior remains intentional;
the bug is unconditionally adding deferred records after that explicit filtering.

The date prototype now has three arms (current, date syntax, plus explicit-date
kind description), five neutral cases, and supports multiple saved sources.
Use the failed calendar source and explicit-date transition source: 21 calls
before retries for seven inputs. This separately tests syntax and interpretation.
No additional temporal variant, call stage or natural-language regex is proposed.

Attribution simplification candidate: `/tmp/mycelium_attribution_compact_probe.py`
compares current and assertions+relation (removing the repeated reason field),
using the existing neutral cases plus a named-user compound counterexample.
It retains complete pair accounting, reporting-only restrictions and assertion/
relation consistency. This saves output and next-stage input without adding a
call/union/nesting level. Adopt only if assertions retain source coverage and
native routing/manual-review behavior, with measured token/time savings.


## Completed comparison

- Production: `audit-daily-e2-fdcc767-20260917`, frozen production `fdcc767`.
  Execution `complete_with_errors`; final encoding and all 19 QA probes complete.
  The explicit pilot-date approval could not execute: no matching proposal was
  generated. Final store: 16 sources, 57 claims (54 active), 38 facts, 14 pages.
  All 54 source segments accounted for; zero extraction/publication backlog and
  zero unresolved exact citations/provenance IDs. Four active statements remain
  unplaced/policy-excluded, and one statement awaits truth review. These states
  must not be combined with failed execution into a quality score.
- Control: `audit-daily-e2-ranked-cccbe23-20260917`, all 19 probes complete.
  Same immutable snapshots, model digests, effective configuration, evaluator,
  source policy, reviews, candidate count and maximum evidence token budget.
  Source-review packs: `audit-daily-e2-fdcc767-20260917-source-review`.
- Frozen automatic answer result: production 10/19, control 13/19. The control
  recovers build deadline, privacy/export rule and pilot history, with no paired
  regressions. Source review identifies the concise “No” to the family-research
  question as correct in both arms: the frozen fixture still requires an
  unasked-for purpose fact. Both arms also answer dentist/issue-owner questions
  correctly from real tool evidence, despite fixture-specific abstention rules.
  These are evaluation disagreements, not a reason to suppress useful evidence.
  The raw score is retained unchanged; it is not a trusted product accuracy rate.
- Retrieval wall time totals: 96.85s production, 4.07s control. Answer totals:
  32.16s vs 55.62s. Evidence characters: 40,365 vs 332,294 (8.23×); median 2,069
  vs 19,058. Character counts are explicitly not tokenizer measurements.
  Cold cloned-index work and stochastic QA prevent a matched latency/causal
  accuracy claim. The control removes generative admission and generated-fact
  presentation, but shares expensive upstream work; it is not an end-to-end
  Mem0 replacement or proof that all 20 claims should always be returned.

### Stage cost, including retries

The production memory trace records 321 attempts, 2,732.122 model seconds,
2,326,261 input tokens and 165,251 output tokens. It includes retrieval selection
and the answer judge, but the 19 answer calls are recorded separately. There are
11 failed structured attempts: six calendar extraction and five attribution.
No cache-hit attempts occurred in this trace.

| Stage | Attempts | Model seconds |
|---|---:|---:|
| Source attribution | 37 | 897.700 |
| Truth candidate selection | 25 | 481.406 |
| Identity | 80 | 258.731 |
| Claim routing | 32 | 233.806 |
| Subject discovery | 15 | 164.283 |
| Truth comparison | 12 | 150.823 |
| Retrieval admission | 18 | 81.720 |
| Fact grouping | 23 | 76.098 |
| Prior fact candidates | 16 | 42.249 |
| Page admission | 7 | 39.659 |
| Fact synthesis | 15 | 17.115 |

Calendar extraction eventually succeeded on its seventh attempt across builds;
this clears the final backlog but does not excuse the repeated failures/cost.
The prior full sample3 run has different contracts and workload. Its stage costs
above are scale context, not a matched before/after quality or speed comparison.

### Source-reviewed diagnosis and next decisions

1. **Dates and current state:** explicit date text survives in claims, but the
   resolved qualifiers can disagree with it. The pilot update was compared and
   misclassified as historically compatible. The final interview query reuses
   the completed September 13 event as the next interview even though the newer
   source says its date is undecided. That uncertainty is present in the claim's
   time annotation and retrieved raw source: this is not missing source capture.
2. **Identity:** the project retains its ID/name transition, but a new service
   spelling is unsupported. A separate Maya Chen person is created from a tool
   assignee although the canonical user already has that alias. Source roles
   must not make a known user unmatchable in a third-party observation; alias
   equality can propose candidates, never decide identity automatically.
3. **Pages:** early project requirements are useful. Mid-build they migrate to
   You, leaving only a purpose sentence and intent. Final constraints partially
   return but privacy, responsibility and readiness context remain difficult to
   find from the project. The long You page mixes plans, completed events and
   stale unnamed state. Family history remains substantively distinct; absence
   of an exact separate-project page is not itself a failure. A negative link
   stating that two projects are separate is not cross-project contamination.
4. **Retrieval/QA:** production already renders the correct deadline, privacy
   rule and old/new pilot dates, but QA abstains. The small excerpts omit some
   referential context. Both arms omit the benchmark reason in the system-choice
   answer; inspect candidate recall separately. Do not assume a reranker fixes
   a correct evidence context or use aggregate QA to blame extraction.
5. **Concision/authority:** duplicate or sprawling fact prose and incidental
   sponsored content merit proportionate maintenance, not exact page-count rules.
   One appropriate completed-work proposal stays pending and visible. Retraction
   removes the wrong-workspace acquisition from answers and derived pages while
   retaining its source/review history. The final structural check resolves all
   45 item links across 14 pages; valid links alone do not establish useful scope.

Priority remains small mechanism fixes: source-grounded new names, native date
syntax, current-applicability truth reasoning, exact dependency rerouting,
compact attribution and bounded truth search. No new inference stage, reranker
model, or source-index subsystem is justified by this run alone.
