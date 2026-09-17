# Audit follow-through: longitudinal and answering controls

## Result and limits

The new longitudinal run uses substantially less model work, preserves the
corrected names and dates checked below, and retains searchable extracted
evidence. It does **not** pass the full quality gate: a failed attribution batch
leaves five claims without page updates, and truth review still misses a clear
replacement while proposing two reversed replacements. No new retrieval system
is justified by the answering controls below.

Compared runs:

- Baseline: `audit-daily-e2-fdcc767-20260917`, production `fdcc767`.
- Follow-through: `audit-daily-followthrough-e4cfc9d-20260917`, production `e4cfc9d`.
- Both use the same fixture hash, effective configuration, model digests,
  answer-judgment contract, nine checkpoints and explicit review actions.
  Gemma 4 12B, temperature 1.0, reasoning disabled, 65,536-token model context,
  32,768-token evidence ceiling; retrieval candidate/result limits 20/5.
- These are single fresh encodings with several accepted changes between them,
  not an ablation or repeated reliability estimate. Generated claims and pages
  differ. Skipped downstream work after a failed batch also lowers cost.
- Both executions terminate `complete_with_errors`, QA completes 19/19, and
  overall status is `incomplete`. Baseline encoding is complete; follow-through
  encoding is incomplete. The explicit pilot-date approval finds no proposal
  in either run. A checkpoint named “change applied” does not prove application.

## Measured work

All numbers include failed attempts. Server time sums Ollama's reported duration
for uncached attempts, including server overhead/loading; it is not overall elapsed
time or pure GPU compute. Cached decision
returns are counted separately and consume no generation tokens. The main model log includes extraction, organization, retrieval
admission and answer judgment; answering and embeddings are separate below.

| Measurement | Baseline | Follow-through |
|---|---:|---:|
| Main model inference attempts | 321 | 196 |
| Cached decision returns / seconds | 0 / 0 | 2 / 0.002 |
| Main model server seconds | 2,804.675 | 1,449.390 |
| Encoding/organization only: attempts / server seconds | 284 / 2,687.737 | 159 / 1,334.613 |
| Retrieval admission: attempts / server seconds | 18 / 85.863 | 18 / 83.692 |
| Evaluator: attempts / server seconds | 19 / 31.075 | 19 / 31.085 |
| Original client-wall trace seconds (clock-skew limitation) | 2,732.122 | 1,404.578 |
| Input / output tokens | 2,326,261 / 165,251 | 1,090,182 / 86,317 |
| Failed attempts | 11 | 3 |
| Attribution calls / server seconds | 37 / 925.444 | 14 / 237.705 |
| Subject discovery calls / server seconds | 15 / 166.750 | 7 / 69.240 |
| Identity matching calls / server seconds | 80 / 265.238 | 32 / 98.347 |
| Page routing calls / server seconds | 32 / 238.788 | 11 / 78.498 |
| Truth screening calls / server seconds | 25 / 494.076 | 21 / 388.369 |
| Truth comparison calls / server seconds | 12 / 155.060 | 14 / 141.960 |
| Retrieval elapsed seconds, 19 probes | 96.846 | 92.732 |
| Answer elapsed seconds, 19 probes | 32.159 | 31.103 |
| Answer generation: attempts / server seconds | 19 / 31.922 | 19 / 30.877 |
| Separate embedding operations / monotonic client seconds | 24 / 9.942 | 24 / 8.006 |
| Raw judged passes | 10/19 | 10/19 |

Main model server time fell 48.3%, with no change to which raw probe judgments pass.
Encoding/organization alone fell 50.3%; evaluation and answering are explicitly
separate from that product-work subtotal. Original answer-generation client-wall
trace sums were 31.107/29.862s, with the same clock-skew limitation below.
This supports continued use of the smaller work scope and simpler attribution
contract, alongside their isolated controls. It does not establish equivalent
full encoding quality or attribute the entire saving to one mechanism.

**Timing correction:** later inspection found `time.time()` differences in the
structured-call trace, vulnerable to clock adjustments. Server durations exist
for all 321/196 attempts and are now the stage-cost comparison above. Original
client-wall sums are retained explicitly, not relabelled as monotonic elapsed.
Retrieval/answer elapsed, chat-round and embedding timers already use monotonic
clocks. The timing-only production fix is `f1dfdd9`; earlier direct-probe trace
latencies also carry this limitation. Semantic findings, counts and tokens do
not change. Analysis is retained in the full sample-3 run's
`source-review/timing-comparison.json`.

## Evidence and successive page review

Review pack: the follow-through run's `source-review/` contains all nine
source-linked snapshots. Original requests and failed outputs remain in
`diagnostics/requests/` and `store/diagnostics/failures/`.

- **Coverage/integrity:** all 54 source segments are accounted for; 51 support
  claims and three are source-only. There is no extraction backlog or unresolved
  exact citation. Final state: 57 claims, 53 active, 35 facts, 13 pages; five
  `routing_failed` claims. All 48 rendered item links resolve. These counts are
  diagnostic, not desired page/claim counts.
- **First build:** the private local app objective and desktop/privacy constraint
  appear on the project page. Useful first-conversation context is retained.
- **Middle builds:** the same project ID adopts the source name Lantern, and
  TranscribeCloud's source spelling is preserved. The earlier objective and
  constraint stay in the project view; linked people and pilot context are
  inspectable. The final project view still omits several relevant privacy,
  responsibility and consent details that are available on other pages.
- **Date checks:** September 22 and September 28 are encoded as those exact
  dates; both packaged-build references resolve to September 11. Calendar
  extraction finishes in one call instead of seven. This fixes observed syntax
  and calendar failures, not every possible relative-date interpretation.
- **Transitions:** “not ready to name” remains prominently current after naming.
  The project has the new pilot date while the user page still presents the old
  target without a pending replacement. The consent issue shows open in Current
  State and its later closure in Timeline. These are coherence failures, not
  harmless alternative layouts.
- **Truth review:** the earlier conditional transcription choice is incorrectly
  proposed as replacing the later final choice in two pending proposals. Both
  sides remain visible as unresolved; canonical evidence is not silently replaced.
  The pilot-date change is still missed. Human review protects against automatic
  deletion but does not make these proposals correct or complete.
- **Failed attribution:** call `d12b30cd` emits nonempty assertions together with
  `reporting_only` in three attempts, spending 67.969s. Five claims remain
  searchable without their intended page updates, including the explicitly
  unknown next interview date and the pilot-readiness statement. No invalid
  model output is silently repaired or published.
- **Concision/organization:** smaller attribution output does not remove verbose
  fact prose. The user page repeats subject prefixes and a consent statement adds
  an unnecessary calendar explanation. Priya's accumulated responsibilities are
  repetitive. These editorial defects do not justify another generation stage.
- **Source uncertainty:** a separate Maya Chen identity remains. The configured
  alias and similar responsibility make a match plausible, but the raw history
  does not directly establish self-identification. Forcing the fixture's expected
  merge would be inappropriate; uncertainty/review is preferable.

## Retrieval versus answering: use existing behavior first

`daily-runtime-qa-control-20260917T072149Z-09655d90` compares seven questions using
the exact saved initial evidence from the baseline's fourth/final checkpoints.
Settings and model digests are asserted equal. The static daily benchmark and
tool-enabled benchmark answer paths share inputs; neither reruns initial search.

`daily-app-qa-control-20260917T072637Z-d8775dfa` then uses the real app prompt,
prompt-budget builder and memory-tool loop on those same inputs, with empty chat
history. Web tools are omitted. This is not a browser/device test or a fresh
end-to-end retrieval run. All three arms retain the baseline's encoding defects.

| Question area | Static benchmark | Tool-enabled concise benchmark | App response style |
|---|---|---|---|
| Packaged-build deadline | Unnecessary abstention | September 11, supported | September 11, supported |
| Local storage/export rules | Unnecessary abstention | Correct rule | Correct rule and cloud restriction |
| Transcription choice and reason | Choice only | Choice only | Choice plus supported local/privacy reason |
| Pilot-date history | Unnecessary abstention | Correct “No,” no history | Original date and recruitment reason |
| Next family interview | Wrongly reuses prior date | Same error | Same error |
| Retracted acquisition | Abstains | Abstains | Abstains |
| Readiness and later decision | Supported answer | Omits direct readiness conclusion | Supported answer |

**No tool calls occurred in either tool-enabled arm.** Their improvements come
from response contracts/prompting over already available evidence, not source
expansion. The benchmark's “one value”/yes-no style underrepresents multipart
answers; raw benchmark scores should not be treated as app success rates.

The transcription performance claim is present in the store but outside the
initial top 20 candidates. Its source line is adjacent to a retrieved decision,
so the existing source tool could expose it. These trials do not prove that the
model will choose that tool. The unknown interview date is already explicit in
retrieved source evidence, so that error cannot be repaired by adding an index.

**R1 decision:** retain existing retrieval and its resource budgets. Do not add a
source index, entity/time search branch, or reranker dependency on this evidence.
Continue to measure tool use and answer coverage in V1; temporal/current-state
interpretation and truthful page transitions remain the more consequential limits.

The original E2 report's source-based disagreements still apply: a simple “No”
can answer the family-project separation question, and admitted calendar/tool
observations can support the dentist and issue-owner answers. Those fixture
expectations do not warrant new product exclusions.
