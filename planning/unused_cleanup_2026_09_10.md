# Static cleanup — 2026-09-10

Implemented the concrete cleanup and test repairs from the September 9 unused-code audit. Initial implementation used static inspection only, as requested. The user subsequently authorized verification and committing; validation results are recorded below.

## Changes

- Removed the unused lexical module, token truncator, response helper, audit wrapper, thread-context formatter, LoCoMo JSONL reader, ontology catalog/accessor helpers, subject-candidate formatter and its sole test, unused web fake, and React/Vite starter assets.
- Removed extraction template inputs and policy text that the current templates never consumed. Active prompt text, schema definitions, and semantic decision behavior were not changed.
- Repaired the synthesis review-boundary test with an otherwise valid merged group and a control validation without review constraints. Consolidated redundant singleton-text cases.
- Repaired identity rejection fixtures so each starts from a valid resolution variant and checks the intended error field/type.
- Aligned direct synthesis probes with production reasoning and output allowance; resolve singleton claim text before semantic judging and save the judged statements. Context-dependent extraction probes now request reasoning when earlier segments are supplied.
- Preserved required nulls in page-probe artifacts, added a serialization round-trip assertion, and removed the obsolete `not_selected` filter.
- Replaced the reconsolidation response translator with explicit current-contract fixtures. Removed the unused synthesis response from the pending-review case, where production preserves the old fact and withholds the incoming claim without calling synthesis.
- Simplified dream fixtures: removed discarded fields/parameters, old type-adjudication translation, and synthetic confidence-based deferral. Identity and page decisions are explicit; remaining helpers bind fixture IDs and fill default sections. Removed an unconsumed legacy identity-verdict response and renamed its test to reflect the new-identity behavior it actually covers.
- Moved shared artifact builders and model-probe helpers into dedicated modules, updated consumers, and removed the now-unused old scope-record builder. Existing judge prompts were moved unchanged.
- Extracted shared benchmark recording/writing helpers, replaced module monkeypatching with a case callback, and gave maintained probe runners fresh output directories. Documented the historical reasoning experiment separately; historical artifacts remain untouched.

## Deliberately retained

Unreferenced public convenience APIs (`Session.build_prompt`, the two repository query methods, and PCM transcription) remain: the static audit did not establish whether external library users need them. The library-message template therefore remains too. Persisted scope enums, repository accessors used in assertions, negative SDK spies, opt-in model tests, and historical experiment inputs/reports remain useful.

## Validation

- Full test directory with host access: **427 passed, 87 skipped**, 5.68 seconds (`/tmp/cleanup-tests-host.log`). The two-case reduction is intentional: the deleted formatter test and consolidation of equivalent singleton-text cases. The sandboxed attempt stalled and was interrupted; it is not counted as a successful run.
- Ruff across application, server, Engram, benchmarks, and tests passed. Whitespace checks passed. UI TypeScript/Vite production build passed, with Vite's bundle-size advisory.
- All four experiment modules import successfully. The explicit callback collects seven contracts, and fresh output roots are unique without creating directories on import.
- Eight selected host Gemma checks: **6 passed, 2 failed**, 972.07 seconds. Passing cases: distinct/grouped synthesis, direct refusal extraction, refusal pipeline replay, shared page placement, incidental page placement. The accepted-reference direct probe and accepted-reference pipeline replay failed for the issues below. Logs and inspected artifacts are retained under `benchmark_runs/cleanup-validation-20260910/`; `artifact-review.json` summarizes coverage. An initial probe launch failed before inference because the pytest artifact parent directory was missing; it was created before the real run.
- Both replay stores retain all two extracted claims in their wiki: one combined fact for acceptance, two separate facts for refusal, with no unrepresented claim IDs. Refusal passed extraction, wiki, restart/no-work-build, and retrieval checks after recovering from one schema error. Shared placement selects person and organization pages; incidental placement selects only the organization. The passing page tests also validate JSON round trips with required nulls preserved.
- Two real Gemma benchmark smoke calls passed at `benchmark_runs/contract-simplification-20260910T073847Z-9ed453ca/`: include the relevant directions preference and exclude unrelated records; exclude all records for the unrelated query. The recorder saved requests/responses. A subsequent attempt to reuse the same output directory raised before inference, confirming stale results are not silently accepted.

## Issues exposed by model validation

The repaired probes do not establish a clean bill of health for the production pipeline:

1. **Earlier-context time anchors are rejected.** The direct accepted-reference response correctly cites the earlier proposal carrying “next month”, but `extraction_output_model` restricts `temporal_anchor_segment_id` to new segments. The first attempt took 89.9 seconds. Its correction generated 32,768 tokens over 412.8 seconds without final content and failed the output-limit check. Both attempts are preserved in `probes/test_extraction_contract_in_re0/llm-errors/`. The declined-reference replay independently encountered the same anchor restriction. Production schema/encoder behavior was not changed as part of this cleanup. A follow-up should admit a time anchor only when it is among that claim's cited evidence, including admitted context, and resolve its timestamp from the corresponding source; this needs focused schema, encoder, and real-model validation.
2. **Synthesis and the semantic judge disagree on mixed commitment wording.** The accepted-reference pipeline replay extracted the correct acceptance with current/context citations and resolved “next month” to October 2026. It rendered “The user is considering volunteering, having accepted the proposal to lead a pottery workshop next month.” The extraction judge passed; the wiki judge rejected the combined tentative/accepted wording. Manual inspection finds explicit acceptance preserved, but the mixture of earlier tentative state and later decision deserves a synthesis/judge calibration follow-up. The failed verdict is retained in `probes/test_extraction_contract_in_re2/wiki_meaning.json`; the failed assertion prevented the later restart/retrieval checks for that case. No test expectation or judge prompt was weakened to turn this result green.

These findings concern unchanged production contracts and judge behavior, now exercised with the repaired probes. They limit conclusions about cumulative quality; passing structural tests is not equivalent to passing model-quality evaluation.
