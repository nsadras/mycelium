# Cumulative quality repairs — 2026-09-08

The changes address the mechanisms diagnosed in `wiki_quality_causes_2026_09_08.md`.
The original LoCoMo artifacts are unchanged. These are bounded neutral evaluations, not a new LoCoMo score.

| Problem | Implemented mechanism | Behavioral evidence |
| --- | --- | --- |
| Missing time scope and false truth changes | Carry cited source/segment times into comparison and synthesis; require a per-target referent comparison before accepting a truth change | Separate events/objects remain compatible; explicit corrections/transitions remain reviewable; 11 truth probes/repeated-build tests passed |
| Unsupported completion, omitted concrete details, ambiguous temporal defaults | Required temporal classification and evidence-first extraction; retain concrete experiences, modality, direction, and contextual decision scope | Six neutral assertions retained; intention/direction checks passed; contextual acceptance/refusal exercised through builds |
| Irrelevant cross-page sharing | Full per-page subject evidence and relevance decisions, including deferred claims; selection requires model-declared substantive relevance | Five placement regression probes passed, including growing registry and shared relationships |
| Duplicate unnamed referents during revisiting | Carry accepted founding decisions and cited canonical claims across work units and scope revision; retain founding plus recent grounding in the identity catalog | Actual staged-identity router replay retained the same ID and placement; ambiguity counterexamples passed with the original identity prompt |
| Over-broad groups and insufficient historical context | Prior-fact selection receives canonical members and temporal anchors; synthesis names each concrete memory scope before grouping and may repartition old groups | Nine synthesis regressions and an explicit old-group repartition check passed |

## Validation and reproduction

All model calls used the configured host `gemma4:12b`, without changing models or starting a server.
Artifacts are under `benchmark_runs/cumulative-contracts-20260908/`. Successful output is retained for new direct
contract probes; test directories also hold build results and meaning judgments. DEVLOG.md records failed variants.
The final backend suite passed 389 tests. The final direct extraction/admission sweep passed 17 cases;
final contextual refusal direct/build checks passed 2 cases.

The final three-build replay (`final-cumulative-replay`) passed in 296.70 seconds. It retained 18 claims as 13 facts,
completed every build without failures, checked placed-claim coverage and duplicate-free page membership, restarted
between builds, and retrieved the bicycle/basket detail correctly. It exercised extraction, routing, cumulative
synthesis, persistence, materialization, and retrieval. It did not run benchmark QA.

Relevant opt-in test switches:

- `MYCELIUM_RUN_CUMULATIVE_PROBES=1` with `tests/test_cumulative_quality.py`
- `MYCELIUM_RUN_EXTRACTION_REPLAYS=1` with `tests/test_extraction_replays.py`
- `MYCELIUM_RUN_PAGE_REPLAYS=1` with `tests/test_page_plan_replays.py`
- `MYCELIUM_RUN_IDENTITY_REPLAYS=1` with `tests/test_identity_plan_replays.py`
- `MYCELIUM_RUN_SYNTHESIS_PROBES=1` with `tests/test_synthesis_probes.py`
- `MYCELIUM_RUN_LONG_MEMORY_REPLAY=1` with `tests/test_long_memory_replay.py`

Run host-dependent tests with host loopback access. Use a fresh output/store directory for the next LoCoMo run so
new extraction is evaluated, rather than reusing frozen claims from the previous run.

## What the next benchmark should assess

Compare concrete assertion retention, unsupported claims, unrelated page memberships, duplicate identities,
false truth-review holds, temporal classification, group coherence, and repeated wording. Complete segment
accounting alone is not a semantic coverage score.

The changes improve local cumulative synthesis; they do not add a separate briefing/detail representation or a
full-store rewrite. Unselected historical groups remain stable. Per-page reasons and scope labels remain model
judgments, not proof of correctness. One replay assertion describing a ten-year ongoing role was still classified
as past and remained separate from the role statement: temporal classification and compression need continued
measurement. Historical member context and very large candidate sets also remain a scaling concern.
