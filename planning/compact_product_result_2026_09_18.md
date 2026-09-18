# Two-pass Build: production check and handoff

**Outcome: implementation is ready for the user-owned device checks and limited
ordinary use.** The reference and lifecycle integration gates are complete. The
bounded product check completed after repairing one transaction-order bug. Its
artifacts are useful at practical local cost, with visible quality limitations;
this is not a claim of perfect organization or a fully validated rollout.

## Implementation and validation

- `0bc6c95`: constrain exact reference selection during generation; the separate
  three-request native reference check completed without retries.
- `6c97904`: integrate retention plus presentation into production Build, editing,
  correction/retraction, review and UI. Remove displaced stages and their probes.
  One statement can support multiple distinct cited items. No extra semantic
  verification stage, retry allowance, fixed heading ontology or lexical repair.
- `6e21c72`: validate correction evidence before superseding its target. The native
  model correctly proposed the replacement being applied; the earlier ordering
  incorrectly rejected that response. A neutral regression test reproduced it.
  The failed transaction left claims, sources, entities, view items and wiki
  records identical to the pre-correction snapshot. The fix changes ordering
  inside the existing transaction, with no prompt or schema change.
- Final checks: **577 Python tests passed**, four opt-in integrations excluded
  (25.72s). **24 UI tests passed**, UI lint/build passed, Ruff and whitespace checks
  passed. Automated checks do not establish browser/audio/network behavior.

## Frozen inputs, limits and results

Original run: `benchmark_runs/compact-product-20260918T021618Z-9b18cef0`.
Continuation: `benchmark_runs/compact-product-resume-20260918T022442Z-2484c84d`.
Both contain exact code, configuration, model inventory, requests, timings,
completion state and snapshots. `review-evidence.json` joins their phase costs,
per-call timings and integrity observations. The original run remains recorded
as incomplete; its continuation resumes only the unfinished correction and answer.

The test copies the earlier 143-claim / 19-page seed read-only, then captures the
same first two conversations (1,008 and 1,002 words). Configuration is unchanged:
`gemma4:12b`, temperature 1, top-p .95, top-k 64, reasoning off, 65,536-token model
context and 32,768-token retrieval budget. Model digest starts `4eb23ef187e2`;
embedding model is `embeddinggemma:latest`, digest starts `85462619ee72`. No judge
or alternate model is used.

| Action | Generation requests | Wall time | Outcome |
|---|---:|---:|---|
| First Build | 2 | 108.29s | 12 statements retained; four new pages |
| Second Build with injected publication failure | 2 | 98.22s | 11 statements retained; previous views preserved; pending status visible |
| Answer while views are pending | 2 | 8.43s | Correct new opening/inspection account from retained evidence |
| Resume second Build | 1 | 36.62s | Views recovered without repeating retention |
| First correction attempt | 2 | Not separately recorded | Transaction-order failure; safe rollback |
| Correction after ordering fix | 3 | 37.13s | Exact submitted text saved; original superseded; views refreshed |
| Final answer | 2 | 29.74s | Useful but incomplete constraints summary |
| No-op Build | 0 | 0.009s | No repeated model work |

**Total: 334.27 seconds / 14 generation requests**, including both failures and
recovery, within the original 600-second / 18-request allowance. This sums benchmark
execution time, excluding implementation/testing time between runs. Generation
consumed 159,222 input / 20,457 output tokens and 319.80 server seconds. There were
no transport failures or structured-output retries. Embedding work is separate:
20 requests / 11.76 seconds, including index rebuilding for copied stores.

Final store: 167 claims, 166 active, 24 pages, no pending Build. All 143 seed claims
retain their text, provenance, status, facets and links; generated views and routing
metadata can change. Final structural integrity checks pass. These checks validate
references and state, not the truth of every generated sentence.

## Source and successive-artifact review

The retained evidence covers project purpose, room conditions, budget, equipment,
opening dependencies, volunteer responsibilities and changed availability. The
second source reuses the four introduced identities and adds Len. It correctly
retains the June 29 opening, June 21 inspection, Theo's handover, conditional
staffing, unpaid planned expenses and the event-only insurance constraint.

The pages remain navigable and recognizable, but their presentation has costs:

- Twenty of the first presentation's 27 items rewrite seed-only evidence. Retrieved
  prior context expands the refresh beyond the new subjects, consuming output and
  introducing unnecessary changes to existing views. The first presentation alone
  takes 65.20 seconds. This is an efficiency observation, not justification for an
  additional model-selection stage.
- The second retention confuses the librarian Theo with the project's Theo. A
  presentation then puts noticeboard duties on the organizer's page. This begins
  in retention/reference assignment, not retrieval. Existing seed identity
  fragmentation is inherited, not newly created by these two sources.
- Presentation changes “must confirm by June 24” into “quote confirmed by June 24,”
  although retained evidence preserves the condition. Older dates remain visible
  with pending-review markers. Len's page repeats broader equipment context that
  is only loosely useful to him. Headings remain rather mechanical.
- After correction, generated items repeat some protected pending-review text with
  new IDs. The exact correction is stored and searchable, but its provisional
  qualifier is not consistently expressed in the wiki prose. Valid citations and
  passing structural integrity do not establish semantic deduplication or faithful
  rendering of every correction.

The first answer recovers the correct updated date and inspection responsibility
while publication is pending. Its input includes the incomplete-Build warning;
the answer does not repeat that warning. Since retention succeeded, its substantive
answer is supported. This does not test how well the model warns after failed
retention of an entirely new source.

The final answer includes useful date, insurance, staffing, lending and access
constraints. It treats pocket-mending as a firm activity, although the latest source
says an instructor still needs to agree. That overstatement starts in retained
memory and is carried through presentation and answering. It also omits the June 24
insurance deadline supplied in source context. The answer used its initial evidence
without further memory-tool calls; omissions do not all imply failed retrieval.

## Comparison limits and next priority

The prior shared-evidence prototype's first two Builds took 114.49s / three requests
and 63.57s / two requests. The current first Build takes 108.29s / two requests; the
second deliberately fails publication and needs recovery. Production integration,
segmentation and view-context changes, stochastic output and fault injection prevent
an isolated speedup or quality claim. The earlier 60-request control never completed
its first Build, so it still supplies no matched completed-quality comparison.
These repeated sources are not a fresh holdout or a large-store scaling test.

**Close this bounded tranche.** There is no further prompt variant or full benchmark
run scheduled to polish these individual mistakes.

1. Complete the [device checklist](audit_device_acceptance_2026_09_17.md) using
   user-started services, then try a few ordinary conversations and corrections.
2. If real use reproduces the observed clutter or cost, first narrow which existing
   view items a Build refreshes and how shared/protected items enter retrieval.
   Prefer reducing unnecessary work over adding semantic stages. The final answer's
   context-selection request used about 50,000 input tokens; view repetition can
   increase retrieval cost as well as page clutter. Require a small bounded check
   showing less churn/cost without losing independently useful cited items.
3. Prioritize recurring misleading commitments or ineffective human corrections
   over individual omissions or cosmetic headings. Preserve source inspection and
   review; do not turn every observed name/date error into another ontology or call.

Browser, microphone/upload/playback and Wi-Fi/Tailscale checks remain unverified.
No app or Ollama service was started or stopped for this work.
