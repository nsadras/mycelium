# Consolidation efficiency — 2026-09-09

The safe first reduction is to share historical comparisons across incoming claims and remove reviews with an empty target domain. This reduces redundant inference while preserving the canonical evidence and the existing truth-review boundary. It does not make historical selection constant-time.

## Changes

- Historical candidate selection compares up to four incoming claims against each chunk of twelve existing facts. It retains every claim/fact pair, unions decisions by exact claim IDs, and caches canonical records within the selection operation.
- The input budget includes system text, user text, and the structured-output schema, with reserves for output and tokenizer differences. Oversized batches split along exact record boundaries. A single oversized pair fails explicitly rather than truncating evidence.
- Truth review runs only when eligible prior targets exist. A truth change requires an existing target; an empty target domain cannot produce one. Incoming claims still reach canonical synthesis. Actual replacements and contradictions retain model review and pending proposals.
- Each store appends stage-labelled attempts to `diagnostics/llm-calls.jsonl`: model, timestamp, call ID, attempt, success, latency, character counts, and native token/duration metadata. Records survive restarts and the in-memory log limit. Prompt and response text are excluded. Diagnostic write failures are logged without discarding valid model results.

## Direct evidence before integration

Configured host model: `gemma4:12b`.

| Controlled selection workload | Previous | Batched |
| --- | ---: | ---: |
| Four incoming claims, 84 existing facts | 28 calls | 7 calls |
| Wall time | 52.75 s | 34.54 s |
| Expected selected facts | All correct | All correct |

This is a 75% call reduction and approximately 35% wall-time reduction on one paired workload. Generation still costs time: batching does not imply a fourfold speedup. These measurements are not a LoCoMo score or a guarantee for long sessions.

Evidence: `benchmark_runs/consolidation-efficiency-20260909/batch-contract/`.

## Why a fixed semantic shortlist was withheld

The configured embedding model retrieved the expected fact first for three narrow queries. A correction affecting 28 historical records exposed the recall limitation: top-12 retained 12/28, top-24 retained 24/28, and top-48 retained all 28 in this particular neutral corpus. The production structured selection contract independently confirmed all 28 were relevant and excluded the other property being measured.

Increasing the cutoff to 48 would fit this example, not establish a product invariant. No fixed cutoff, lexical rescue, or benchmark-specific rule was integrated. Exhaustive batched comparisons remain until a semantic scope/completeness mechanism can justify bounded retrieval without silently losing corrections.

Evidence: `benchmark_runs/consolidation-efficiency-20260909/shortlist-recall/embedding-recall.json`.

## Validation follow-up

The integrated broad-correction probe preserved all required records but also selected twelve unrelated records under the original selection prompt. This is an over-selection failure, not lost coverage; it can nevertheless increase downstream work. Its stricter specificity assertion remains in the native regression probe. Further contract and cumulative replay results are recorded below when complete.

The revised selection prompt makes matching subject/property and temporal/event scope explicit in positive instructions. Direct probes using the actual production input and output schema passed both narrow and broad cases before integration (2 passed in 37.40 s, `refined-selection-contract/`). The broad case retained all 28 affected records and excluded the unrelated records. This is a model decision, not a deterministic semantic filter.

## Paired public three-build replay

Both versions used the prompt/context improvements already present at the start of this change. The baseline restores the previous selector and owner-step methods; the optimized version uses batching and empty-target skipping. Both used the original candidate-selection prompt, so this isolates those mechanisms from the subsequent wording refinement. Runs were serial, baseline first, against the configured host model. Neither is a corpus benchmark; sampling, cache/order, and retry variability limit conclusions from one pair.

| Measurement | Baseline | Batched + empty-target skip |
| --- | ---: | ---: |
| Capture/build/restart/retrieval + semantic checks | 193.11 s | 174.80 s |
| Consolidation LLM time (sum of Dream stages) | 147.24 s | 130.32 s |
| All recorded model attempts | 49 | 31 |
| Candidate-selection calls / time | 12 / 28.96 s | 4 / 15.57 s |
| Truth-review calls / time | 18 / 43.55 s | 8 / 30.69 s |
| Final canonical claims | 18 | 18 |
| Final display facts | 12 | 13 |
| Retention and bicycle retrieval checks | Pass | Pass |

All three builds in each run completed without pending source work, failures, or review proposals. The optimized run kept Spanish learning and its practice schedule in separate display facts; the baseline combined them. Thus these runs establish preserved evidence and useful latency improvement, not improved concision. Two optimized synthesis attempts failed exact-singleton-text validation and then recovered through the existing retry handler; baseline synthesis also made seven attempts but across seven successful calls, versus five successful optimized calls plus two failed attempts. Failure dumps preserve the evidence.

Measured total reduction was 9.5%; summed consolidation-model time fell 11.5%. Candidate selection improved more (46.3%), but routing, synthesis, truth review, and extraction still consume time. These changes do not justify declaring a fifteen-minute session necessary or the pipeline fully efficient.

Evidence: `benchmark_runs/consolidation-efficiency-20260909/paired-replay/comparison.json`, with build reports, facts, semantic judgments, retrieval evidence, and per-attempt traces alongside each replay. Harness snapshots are in `benchmark_runs/consolidation-efficiency-20260909/harness/`.

## Next LoCoMo run

Use the existing benchmark command with a fresh store. Timing traces now persist automatically inside each sample store. Compare stage attempts, native output tokens, failed attempts, and elapsed time alongside coverage/correctness/concision/organization. In particular:

- Check whether candidate selection still dominates with large history. Its coverage is exhaustive and its work still grows with history, albeit in shared batches.
- Inspect synthesis retries and unusually broad selected sets. Reducing those costs requires a proven decision/input contract, not silently dropping evidence or weakening validation.
- Compare wiki quality and completed QA before raising batch sizes further. The small probes do not establish LoCoMo-wide recall or acceptable long-session latency.

## Final integrated checks

- Backend: 401 passed, 87 opt-in checks deselected; targeted Ruff and diff checks passed.
- Configured-model suite: all six checks passed in 323.91 s at `benchmark_runs/consolidation-efficiency-20260909/final-native/`.
- Selection: exact expected matches in both narrow and broad cases, five calls each; 17.32 s and 21.27 s respectively.
- Multi-build truth handling: compatible plans had no proposal; genuine replacement and contradiction retained pending review, including isolation across an unrelated later build.
- Final three-build replay: all 18 canonical claims represented in 12 display facts, no proposals, retention and retrieval judgments passed. Two exact-singleton-text synthesis attempts still required retries. This confirms the final integrated behavior but does not replace the controlled before/after timing comparison above.

Changes remain uncommitted. The next fresh LoCoMo run is still needed to establish long-history quality and session-time improvement.
