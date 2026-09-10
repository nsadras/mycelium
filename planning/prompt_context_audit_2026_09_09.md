# Prompt and input-context audit — 2026-09-09

The inspected configuration uses `gemma4:12b` with a 32,768-token context. The six memory-construction stages
use structured calls with `think=False`; the benchmark memory-tool QA path explicitly enables thinking.
This audit examines our instructions and evidence presentation, rather than attributing the wiki errors to model size.

## Findings by call

| Call | Findings |
| --- | --- |
| Extraction | The system template accumulated 1,206 words before injected policies. It mixes admission, identity, temporal classification, fidelity, and accounting. New evidence precedes earlier context, followed by repeated prohibitions. Segment IDs, speaker roles, and exact accounting are useful and should remain. |
| Identity planning | The 903-word template repeats several rules, but those rules protect real distinctions: the configured user versus external speakers, uncertain identity versus multiple distinct actors, and independent endeavors versus components. A shorter rewrite regressed behavior; brevity alone is insufficient. |
| Page placement | Section definitions for every ontology type are supplied even when the actual registry has only people. Claim records mix semicolon fields, Python-style values, and shared source snippets. The evidence formatter includes only the claim's primary source, omitting cited context from other sources. Placement also receives the full cohort's identity plan, including aliases outside its current batch. |
| Prior-fact selection | Canonical members and occurrence times are present, which is good. The old display text and members are formatted as dense inline records. A 12-fact batch can contain many canonical claims; a fact-count limit is not a token bound. |
| Truth review | The instruction says establish scope before deciding, but Pydantic inheritance puts `disposition` before the dynamically added `scope`. Incoming and target records include source occurrence anchors; recording time is correctly excluded. The same evidence is repeated per claim, and previous display prose can add noise. |
| Synthesis | Canonical claims, temporal classifications, and source occurrence times are available. Existing display prose is also supplied. Free-text `memory_scope` permits broad labels that can rationalize merging independent memories. This remains reproducible with a small mixed-history input, well below the nominal context limit. |
| Assistant context selection | The prompt is concise and task-specific. Candidates have explicit aliases and JSON fields. Each candidate is truncated to 1,200 estimated tokens; aggregate candidates plus schema still deserve an explicit total-budget check. |
| Assistant / benchmark tool QA | The current request is explicit and the accumulated memory workspace is refreshed after tools. Earlier workspaces become receipts. This is a useful separation of current evidence from tool history. Errors in stored membership/prose can still contaminate retrieval; clearer answer instructions cannot repair omitted source facts. |
| Grounded benchmark answer | The question and memory evidence have separate sections, with explicit source/context labels and temporal guidance. No prompt defect here explains construction-time wiki errors. |
| Engram summary / reduction | Separate transcript and chronological partial-summary inputs; token-based batching is present. These calls are outside the LoCoMo memory construction path and were inspected, not changed. |

There are no few-shot demonstrations in the six active memory-construction system templates. The dominant problem
is accumulated instructions and unclear division of evidence, identity, and presentation—not examples to remove.
Some negative instructions express essential constraints; a replacement must preserve their meaning in direct tests.

## Direct model experiments

Candidate templates and harnesses were staged outside production before testing against the configured host model.
Requests, schemas, responses, and successful-call metadata are retained under
`benchmark_runs/prompt-clarity-20260909/`.

- `candidate-contracts`: shorter affirmative templates and structured identity/placement evidence. 34 passed; four semantic regressions and one transport timeout. The first
  synthesis rewrite split the schedule and capacity of one event; identity changes mishandled a configured user
  and two ambiguous-referent cases. The timeout is separate from those semantic regressions. Several suites were
  initially submitted concurrently; final verification is serial to avoid queue-related timeouts.
- `refined-contracts`: scope-first truth schema and refined synthesis instructions. Mixed-history truth probes
  retain an unchanged habit, distinguish identical relative-time reports from different months, retain compatible
  activities, and recognize an explicit exclusive-state replacement.
- `input-regressions`: 29 passed, including all identity and temporal checks. Two extraction regressions remained:
  a tentative plan became a commitment, and a question without personal facts was admitted as a claim. The shorter
  extraction and identity templates were therefore withheld; their original production wording remains.
- `synthesis-refinement` and `synthesis-controls`: a 14-claim input contains separate occurrences, complementary
  event details, equivalent preferences, independent plans, and recurring activities. Broad “future goals” grouping
  persists in shorter variants. The controlled comparison isolates previous display prose: the identical original system prompt produced
  8 groups with old prose, merging independent plans and routines, versus the expected 10 with canonical claims
  alone. The shorter final prompt also produced the correct 10 groups without old prose. The original system
  hashes match across the two controls (`8e9ec47dda1d`). This is evidence for an input repair, not just more wording.

The initial test invocation failed during pytest temporary-directory setup, before any model calls. Its parent
folder was created and the run restarted. This was a harness error, not evidence about Gemma.

## Remaining constraints

Passing focused probes establishes specific behavior, not long-run wiki quality. The overnight LoCoMo run has no
completed QA score to compare. These experiments preserve that store and do not rebuild its artifacts. The next
fresh user-run benchmark remains the appropriate end-to-end quality check.

## Accepted changes

- Truth comparison now declares per-target scope before the verdict in the generated schema. Both branches retain
  exact alias validation and the requirement that a truth-change target have model-established shared scope.
- Placement, truth, and synthesis instructions use concise affirmative task steps, with no added few-shot examples.
  Their system templates shrink from 443/539/565 words to 253/260/311 words respectively.
- Placement receives JSON records for page subjects and section definitions for the actual active types. For the
  latest four-person registry, the catalog drops from 919 to 328 estimated tokens (the project tokenizer, not a
  native Gemma token count). Identity and placement retain exact citations across source documents and include
  shared source text once per source/segment pair. Unavailable citations remain visible in claim records.
- Synthesis receives canonical members and explicit manual presentation constraints. Automatically generated old
  display groups are excluded; their member evidence remains available and normal fact-ID reuse still applies.
  Manual presentation preservation and review boundaries have focused structural regression tests.

The unresolved input-budget and full-cohort identity-plan findings above remain follow-up work. No lexical semantic
filter, benchmark vocabulary, or automatic reinterpretation of `source_only` / `deferred` decisions was introduced.

## Final validation

`final-input-replay`: **6 passed in 264.43s**, including four mixed-history truth checks using the real claim
formatter, the 14-claim synthesis check, and three public capture/build/restart cycles plus retrieval. All 18 claims
were represented as 12 facts, with no build failures or review proposals. Backend: **395 passed**, with opt-in
model checks deselected. Truth/selection claim evidence and existing-fact records now use JSON as well, preserving
per-claim citations while deduplicating shared source text. Source occurrence times accompany the cited segments.

The next benchmark should specifically compare unrelated page fan-out, separate occurrences merged into one fact,
false truth-change proposals, and retained substantive details. These tests support the repairs; they do not yet
establish an improvement in LoCoMo QA or coverage across all 25 sessions.
