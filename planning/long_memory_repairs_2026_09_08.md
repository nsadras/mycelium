# Longer-memory repairs — 2026-09-08

## Scope and method

The product goal is durable, user-correctible statements with readable, source-grounded wiki views and useful
agent retrieval. Compression and benchmark answers are diagnostics, not the definition of successful memory.

The interrupted sample9 run is preserved at
`benchmark_runs/locomo-sample9-semantic-repairs-20260907-204715/stores/conv-49`.
It contains 15 extracted sessions, 178 active claims, and 14 completed build attempts: eight successful and six
failed. Only 109 active claims are represented by its 60 canonical display facts. Two further placed claims are
intentionally held for review; one placed claim is missing presentation without that explanation. Later extracted
sessions largely failed to reach the wiki. Complete segment accounting did not imply semantic extraction recall.

The new organization replay uses exactly those frozen source/episode/claim/log artifacts in a fresh store. It does
not preserve old page assignments or facts. It therefore isolates downstream accumulation and organization, but
cannot repair extraction omissions or incorrect temporal records already present in the frozen claims. QA is
disabled for this comparison; no QA score or extraction-recall improvement is inferred from it.

## Implemented increments

| Commit | Mechanism | Verification |
| --- | --- | --- |
| `adec9f2` | Replan history only on actual creation/first materialization, not routine identity updates | Structural regression and real repeated-build probes |
| `eef5aa3` | Exclude review-held incoming claims and protected prior facts before synthesis, instead of discarding mixed groups afterward | Direct synthesis probes, preservation/accounting tests, real third-build additions during pending review |
| `1dfc298` | Smaller batches against existing history; successful addition batches survive another batch's failure | First/late failure injection, unchanged-placement counterexample, commit/retry test, real cumulative capture/build/reload/retrieval |
| `9223254` | Clarify that concrete temporary experiences can remain useful as history; encouragement is not a personal assertion | Existing and new extraction probes, long multi-person probe, three capture/wiki/retrieval replays |
| `230d7d1` | Report unexplained presentation gaps separately from review holdbacks; check canonical and within-page duplication | Structural diagnostics/API tests and read-only original-store audit |
| `1fd16de` | Remove the invented one-year offset for an unspecified relative-year quantity | Facet/text-path regressions and existing temporal tests |
| `e5b3df1` | Bound placement responses by claims times eligible pages; keep routing-failed sources pending | Five real page-contract probes, growing-registry and failure/retry tests |
| `5f9e1a6` | Scope broader experience admission to conversation, preserving targeted tool extraction | Source-policy probes and full established chat replay |
| `fd13a42` | Skip already review-held statements before candidate selection; shrink batches once initial history accumulates | Pending/released review tests, failure injection, three real repeated-build cases |

Initial synthesis work units admit at most 12 new claims; additions against existing history admit at most four.
Selected historical facts retain all their evidence. These are workload boundaries, not semantic grouping rules.
The model still decides which prior memories are related and which claims belong together. Existing-placement
changes retain owner-scoped atomicity. A failed addition batch remains visible and retryable; it is not replaced
with raw transcript text or an unchecked generated fact.

## Validation evidence

- Backend: 367 passed, 73 opt-in skipped; targeted Ruff and diff checks passed.
- Three real review replays: compatible plans, explicit replacement, and contradiction. The latter two also add an
  unrelated third conversation and verify complete eligible representation with review-held statements excluded.
- Neutral cumulative replay: 18 statements over three builds become 13 facts. It retains profession duration,
  painting preference, bicycle color/basket, language-practice schedule, and independent later activities. It reloads
  the store between builds and retrieves the bicycle details in a fresh session. Every eligible placed claim is
  represented; no canonical claim repeats on a page.
- Extraction: 15 regression probes, including the 48-segment accounting case, passed. The external-participant
  probe retains all eight concrete assertion segments and none of the filler; its initial test indexing error is
  retained and explained in DEVLOG.md. Three new public capture/build/wiki/retrieval cases pass.
- A neutral synthesis probe keeps separate occurrences of the same activity and their respective details apart.
  This passing small case is not evidence that all long-page grouping is correct.
- Full established chat replay passes at `benchmark_runs/long-memory-20260908-chat-source-policy` (438.33s): one
  populated You, tool-grounded restaurant/person pages, shared founding evidence, within-page uniqueness, and fresh
  cooking-source retrieval. Two earlier failures remain available: an oversized placement response, then an omitted
  restaurant identity after overly broad tool admission. The latter repair restores the original tool-source policy;
  no fixture-name filter or relaxed expected-output assertion was introduced.

Run paths and failures are recorded in `DEVLOG.md`. Timings of concurrently running model tests must not be used
as a clean latency comparison.

## Larger replay comparison

Final organization replay:
`benchmark_runs/long-memory-20260908-replay-after-batching/stores/conv-49`.

An intermediate-code replay at `benchmark_runs/long-memory-20260908-replay-before-batching` completed seven builds
without failures and was intentionally stopped during the eighth to free model capacity. It is a partial diagnostic,
not a completed 15-session result. The original interrupted run is the main baseline.

The replay completed all 15 builds, with no build-level failures, in 5,088 seconds (84.8 minutes). Four invalid
synthesis responses were rejected and recovered through existing structured retries; diagnostics remain in the
run's `llm-errors` directory. The final source/episode/claim/fact/page integrity check is healthy.

| Measure | Original interrupted store | Accumulation replay |
| --- | ---: | ---: |
| Extracted sessions / active claims | 15 / 178 | 15 / 178 |
| Persisted build outcomes | 8 completed, 6 failed; 15th interrupted | 15 completed, 0 failed |
| Claims represented by canonical facts | 109 | 166 |
| Incoming claims explicitly held for review | 2 | 12 |
| Unplaced claims | 66 | 0 |
| Placed, non-held claims missing facts | 1 | 0 |
| Canonical display facts | 60 | 107 |
| Repeated claim IDs within a page | 0 | 0 |
| Total audited claim decisions | 1,161 | 197 |
| Persisted identity work units | 106 | 20 |

The final 166 represented claims plus 12 review-held claims account for all 178. This is representation accounting,
not a finding that all review holds are justified or all fact prose is faithful. Session 12 initially deferred all
eight claims without a build exception; session 13 retried and placed all eight. No semantic override was used.

| Source session | Extracted claims | Originally represented | Replay represented | Replay review-held |
| --- | ---: | ---: | ---: | ---: |
| 1–7 | 67 | 67 | 67 | 0 |
| 8 | 24 | 22 | 22 | 2 |
| 9 | 14 | 5 | 12 | 2 |
| 10 | 13 | 9 | 11 | 2 |
| 11 | 18 | 6 | 16 | 2 |
| 12 | 8 | 0 | 6 | 2 |
| 13 | 12 | 0 | 11 | 1 |
| 14 | 13 | 0 | 13 | 0 |
| 15 | 9 | 0 | 8 | 1 |

**Coverage:** later knee-recovery activity, Tahoe travel, and the ER/gastritis event now reach facts. Original
extraction omissions remain unchanged: the same 209 of 977 segments support claims, with 768 marked source-only.
The separate fresh-extraction probes, not this frozen replay, test the revised experience-admission policy.

**Conciseness:** not yet a clean improvement. Evan grows from 29 to 71 bullets, Sam from 35 to 63, partly because
previously missing information is now present. Some useful consolidation occurs, but the painting bullet is still
overlong; weightlifting duration is combined with painting's relaxation benefit, and separate travel experiences
still share an over-broad dated bullet. Exact-ID uniqueness does not remove semantic repetition across claims.

**Organization:** mixed, with a serious remaining defect. One Canadian-woman page replaces the original duplicate
pair, and a bonsai topic page is useful. However, the woman's page has 31 bullets, mostly unrelated facts about the
two conversation participants. Sam-only facts also appear on Evan's page. Cross-page projections and inappropriate
`Relationship to You` sections make these pages less focused. Valid citations do not justify those placements.

This long-running process started at the batching increment,
before the later placement-grid and review-scheduling repairs. Those later changes have their own real probes and
public replays above; this is not a complete final-code A/B run. Frozen extraction also excludes the new admission
and temporal behavior by design. Concurrent real-model tests affected throughput, so the run is not a clean speed
comparison. The last three builds took 7.48, 6.07, and 4.75 minutes respectively; this is observational evidence,
not a scaling guarantee. QA was intentionally disabled (`count: 0`); the emitted zero score is not a QA result.

Reproduce the accumulation check in a fresh run directory:

```bash
.venv/bin/python -m benchmarks.mycelium_bench locomo \
  --locomo-path ../locomo/data/locomo10.json --sample-index 9 \
  --system mycelium --config-path mycelium.toml \
  --qa-model gemma4:12b --memory-model gemma4:12b \
  --dream-policy per-batch --max-sessions 15 --max-questions 0 \
  --replay-store benchmark_runs/locomo-sample9-semantic-repairs-20260907-204715/stores/conv-49 \
  --run-id long-memory-verification-NEW
```

Use a unique run ID. A new run exercises the checked-out code, including the later independently verified repairs.

## Remaining boundaries to evaluate

1. **Page relevance and organization.** Pages in the new replay still project some personal statements onto
   the listener's page merely because they shared a conversation. The retained placement rationale explicitly says
   this for Sam's travel-history statement. Cross-page sharing is allowed; mere co-attendance is not sufficient
   evidence that a statement describes both subjects. The Canadian woman's page also accumulates unrelated facts
   about Evan and Sam (painting, health, and hiking), a substantial organization defect despite valid source links.
   Person-section selection remains uneven, and index summaries inherit irrelevant first bullets. This should be
   the next semantic-contract repair, not papered over with name matching or indiscriminate page deletion.
2. **Historical event scope and prose.** Grouping can still combine separate experiences too broadly, especially when
   frozen canonical claims carry misleading dates. Structural membership checks cannot prove prose fidelity.
3. **Truth review and unnamed identities.** These repairs preserve evidence and prevent review-related coverage loss;
   they do not prove that every proposed truth change or recurring unnamed-person resolution is correct. The replay
   still holds apparent elaborations for review (for example, being determined to maintain a diet versus being
   determined to change). Review isolation fixes collateral loss, not the semantic precision of the truth decision.
4. **Scaling limits.** New-claim work is bounded, but prior-fact candidate selection still scans growing history, and
   a selected fact can contain many supporting claims. Hard interruption retains raw inputs and extracted claims,
   but does not persist every in-progress synthesis step independently of the build commit.
5. **Human correction flow.** Keep the underlying statement authoritative. Do not make generated wiki prose an
   independently editable truth source while addressing these remaining quality issues.

The original and live stores have not been rebuilt or cleared. User-run UI smoke testing remains separate from the
automated replays; no application or model server was started or stopped.
