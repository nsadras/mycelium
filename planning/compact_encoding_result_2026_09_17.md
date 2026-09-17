# Compact encoding: bounded experiment result

**Decision: keep the shared-evidence mechanism; do not switch the application yet.**
The two-pass approach produces useful memory at practical local cost. A malformed
citation still rejects an entire source's retention, and production editing/review
services still assume exclusive claim ownership. Those are the next integration
problems. Ordinary omissions and imperfect summaries are not a reason to add
another semantic stage or resume an open-ended benchmark campaign.

## What changed

`ac8a6bd` implements benchmark-local retention and presentation using native
capture, SQLite artifacts, search and agent answers. `2ddb536` applies the user's
decision that distinct view items may cite the same retained statement. Each item
owns its heading and destinations. Refreshing one owner cannot erase another
owner's item merely because they share evidence. Manual and pending-review items
stay protected. No new model stage or persistent schema field was added.

The application still runs the original pipeline. The experiment's renderer
adapter is not a second application mode. Its structural tests pass; its existence
does not establish support for the full correction, retraction or identity UI.

## Runs and cost

- Original: `benchmark_runs/compact-comparison-20260917T225514Z-6b46ab03`.
- Shared-evidence revision:
  `benchmark_runs/compact-shared-evidence-20260917T232020Z-13fc977d`.
- The latter's `review-evidence.json` contains request-phase totals and snapshot
  integrity observations. Each arm retains raw requests, validation failures,
  configuration, model identities, completion state and available snapshots.

All arms used the same 143-claim / 19-page seed and identical configuration:
`gemma4:12b`, temperature 1, top-p .95, top-k 64, reasoning disabled, 65,536-token
context. No judge model or alternate model was used. Three successive sources
contain 1,008, 1,002 and 993 words; the independent source contains 931 words.

| Arm | Build outcome | Build attempts | Build input / output tokens | Build server time | Total elapsed, including answers |
|---|---|---:|---:|---:|---:|
| Original candidate | All sources retained; views lag one Build | 14 | 143,003 / 33,586 | 451.23s | 514.24s |
| Current pipeline control | 0 completed Builds; stopped at 60 calls | 60 | 627,427 / 35,108 | 592.91s | 597.30s; no answers |
| Revised candidate | 2 completed Builds; third retention rejected | 8 | 122,296 / 21,838 | 294.59s | 343.90s |
| Original independent | Retained; view rejected | 4 | 27,200 / 7,488 | 100.05s | 113.79s |
| Revised independent | Complete | 2 | 16,482 / 3,291 | 45.43s | 59.11s |

The revised successful Builds took **114.49s, 63.57s and 47.52s** including local
work. The failed third Build took 119.55s. First revised Build: two retention
attempts and one presentation; second and independent: one of each. The third
source used three unsuccessful retention attempts. There were no recorded
transport failures. Original presentation failures numbered nine in the sequence
and three for the independent source. Both revised sequence presentations and the
independent presentation passed first attempt.

All reruns consumed the original allowances: candidate **858.13s / 34 attempts**
of 900s / 60; control **597.30s / 60** of 900s / 60; independent **172.90s / 10**
of 300s / 12. Native total: **1,628.34s / 104 attempts**, including answers and
failed work. Feasibility probes were separate, recorded earlier. No run remains
active, no budget was extended, and no service was started or stopped.

**Comparison limits:** the control is incomplete, so there is no matched quality
score or completed-work speedup. It extracted 64 new claims from the first source,
versus 11 in the original candidate and 9 broader statements in the revision.
Forty of its 60 requests were identity work; it never reached truth comparison.
The seed also contains one deferred claim that the current pipeline reconsiders.
The repeated independent input is not a fresh holdout; its original output was
not reviewed before the shared-evidence revision was frozen. Retention is
stochastic and changed between runs even though its prompt did not change.
Reduced recorded cost cannot establish equal quality or causal improvement from
the ownership change alone. The successful two-call path is encouraging relative
to the inspected upstream call paths, not a measured competitor comparison.

## Source and artifact review

**Original sequence:** all three sources yield retained memory and three useful
agent answers. But the first Build publishes no new pages; subsequent Builds
publish the preceding source's view before failing on the new one. The final wiki
still describes the opening as conditional although the latest retained source
says it happened. Shared citations, including separate people's responsibilities
within one retained statement, caused valid presentations to be rejected.

**Revised first two Builds:** nine new statements each, stable four introduced
identities, and four readable pages; existing seed claims are unchanged. The
project view retains its purpose, constraints, budget, equipment, event and
volunteer arrangements. The second Build updates the opening date while keeping
its inspection condition. Several generated items are copied across participant
pages, making those pages repetitive. The old meeting remains phrased as the
next meeting. These are organization weaknesses, not new acceptance targets.

There are meaningful presentation mistakes despite sound retained statements:
the shelf's price becomes “35 lbs”; the second view says Ruth will meet the
electrician although its cited claim correctly says Theo takes over. The source
and retained claim remain inspectable. The second agent answer recovers Theo
from canonical/source evidence. This distinguishes view synthesis from extraction
and shows why reference access matters more than adding a verification model.

**Revised third source:** all retention attempts include malformed segment IDs
such as `#seg-00041`, which was never supplied. Exact validation correctly rejects
them. The source remains durable, but none of its new statements become searchable.
The final snapshot therefore remains at 161 claims / 23 pages, with a failed
extraction episode. Source 2's wiki is unchanged. The opening-status and next-event
answers are outdated because the latest source was not encoded; this is primarily
an encoding failure, not proof that retrieval failed to find an existing memory.
The answer layer does not warn about the missing Build, another practical limit.

**Independent source:** eight retained statements and seven added pages give a
usable outline of the tentative holiday, leave dependency, guesthouse quote,
budget, vouchers and dog's constraints. The quote is correctly distinguished from
a held room. The plant helper is incorrectly titled “Marcus's Sister,” and the car
offer is compressed into a stronger refusal than the source supports. Inez's
workplace change and some booking checks are omitted. No further tuning follows
these observations. The concise answer mentions leave and voucher compatibility
but misses other useful checks, including the guesthouse and vet, even though
its initial retrieval supplies both. That is an answer omission alongside the
encoding omissions, not an extraction or retrieval failure for those details.

Across saved candidate snapshots, canonical citations reference existing source
segments, fact members/endpoints exist, and seed claims remain unchanged. Four
focused mechanical tests cover shared ownership, protected items, rollback/retry
and rendering after support becomes inactive. These checks do not establish
semantic completeness or application lifecycle safety.

## Next work, in order

1. **Make reference selection reliable without changing semantic labor.** Bind
   citation fields to exact request-local IDs in the structured schema; use an
   explicit lookup if shorter handles are needed. No ID guessing, lexical repair,
   new verification stage or larger retry allowance. Acceptance: legal references
   are representable, unknown references cannot enter canonical memory, and one
   bounded configured-model check exercises the actual native contract. Stop
   after assessing that mechanism; do not perfect individual retained facts.
2. **Integrate the evidence/view boundary through existing lifecycle services.**
   Correction/retraction currently find affected owners through claim placements;
   manual moves rewrite those placements; split requires exclusive membership;
   identity review reopens claims that the prototype's completed-build shortcut
   ignores. Replace those assumptions together, preserve date review and exact
   evidence-specific no-page decisions, and remove displaced main Build stages.
   Acceptance: capture stays behind Build; source/claim durability and publication
   recovery pass; editing one view preserves others; correction, retraction and
   identity review update every affected view; manual edits survive regeneration.
   Also preserve source role metadata, bounded chunking and truthful Build status.
3. **Use the resulting product end to end.** Inspect successive views and a few
   source-grounded answers, including one failed Build and one human correction.
   Acceptance: largely coherent artifacts, visible incomplete work and practical
   local cost. Then hand the existing browser/microphone/network checklist to the
   user. Defer small wording, name and organization errors to real use; a perfect
   benchmark or a completed full stress run is not the target.

This closes the planned experiment. The integration gates remain open because of
the concrete reference and lifecycle gaps, not because memory must be perfect.
