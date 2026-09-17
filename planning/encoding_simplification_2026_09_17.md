# Encoding simplification: bounded comparison

**Status: experimental; not adopted.** User direction on 2026-09-17: prioritize
simplifying encoding, use Mem0/Graphiti/Hindsight as a practical cost reference,
and keep the configured Gemma model. Benchmarks remain diagnostic inputs.

**Product acceptance, clarified by the user:** useful, largely coherent memory
for humans and agents at practical local cost. Exhaustive extraction, perfect
identity decisions and a uniquely correct organization are not requirements.
Missed details and reasonable semantic mistakes are observations to weigh against
the whole result, not automatic reasons to add stages or block the next task.
Keep durable sources, inspectable references and explicit user control; do not
confuse these structural guarantees with perfect model interpretation.

**Implementation checkpoint:** the approved execution plan uses a directional
five-minute Build target per roughly 1,000-word conversation, at most ten minutes
for feasibility including one revision, then 15 minutes / 60 attempts per native
arm and five minutes / 12 attempts for a reserved source. These supersede the
provisional budgets below. The first direct check completed six calls; the one
revision fixed redundant identity selection but exposed a view-membership
restriction. A fixed native comparison is running; application adoption remains
open. See `DEVLOG.md` for paths, failures and the pending product clarification.

## What the external implementations establish

Pinned upstream source was read, not installed or run. These are static call-path
estimates for ordinary successful operations, excluding retries, embeddings,
database/search work, optional features and provider internals. They are not
latency or accuracy comparisons on this machine.

| Implementation | Generative work in the inspected path | Important differences |
|---|---|---|
| [Mem0 `f135cb9`](https://github.com/mem0ai/mem0/blob/f135cb994979170401d4e62d37fd043ed01ac5f8/mem0/memory/main.py#L918-L1199) | One extraction call per ordinary inferred addition, with retrieved existing memories and recent messages in its input | ADD-only retention; embeddings, spaCy entity extraction, normalization and similarity linking add non-generative computation. Its identity heuristics are outside Mycelium's guardrails; it does not provide our exact evidence/review/page contract. |
| [Hindsight `bcca388`](https://github.com/vectorize-io/hindsight/blob/bcca388b3a1125896d3f0b78578b798968e1f29c/hindsight-api-slim/hindsight_api/engine/retain/fact_extraction.py) | One successful fact-extraction request per text chunk; splitting/retries can multiply requests | The documented default chunk is 3,000 characters. Entities and temporal information are extracted in that call. Entity resolution also uses name/co-occurrence heuristics, which we will not copy. Observation consolidation and knowledge-page refresh are additional work, not free parts of this count. |
| [Graphiti `de8eb5b`](https://github.com/getzep/graphiti/blob/de8eb5b896c05ed1b5b329d4cb52015446d65e21/graphiti_core/graphiti.py) | Node extraction and edge extraction, conditional batched node resolution, per-edge resolution/timestamps when needed, optional attribute/summary work | Several calls per episode, with growth by extracted edges and optional attributes. It is not a universal one-call baseline. Its default node resolution can use similarity shortcuts; custom ontology is optional. |

Additional primary references: [Hindsight retain configuration](https://hindsight.vectorize.io/developer/configuration),
[knowledge pages](https://hindsight.vectorize.io/developer/knowledge-pages),
[Graphiti node operations](https://github.com/getzep/graphiti/blob/de8eb5b896c05ed1b5b329d4cb52015446d65e21/graphiti_core/utils/maintenance/node_operations.py),
[edge operations](https://github.com/getzep/graphiti/blob/de8eb5b896c05ed1b5b329d4cb52015446d65e21/graphiti_core/utils/maintenance/edge_operations.py).
Research source snapshots and revision metadata are in
`/tmp/mycelium-upstream-20260917/`; production has no new dependency.

The useful inference is a **small number of generative passes per bounded source
chunk**, plus measured view maintenance. An API operation is not necessarily one
LLM call, parallel calls still consume computation, and smaller call counts can
hide oversized prompts. We will measure actual calls, input/output tokens,
retries, server time and elapsed time together. Extra work for inspectable
evidence and explicit review is justified only where it provides that value.

## Current workload and stopping decision

The frozen `audit-sample3-0f9f7ee-20260917` run was deliberately interrupted during
session 16 after preserving 15 session snapshots. The invocation records
49,118.062 monotonic seconds (13.64 hours), failed execution / `CancelledError`;
QA never started. This is a terminal **incomplete diagnostic**, not completion of
the declared 32-session/193-question comparison. No new full-run QA score exists.

Session 15 contains 462 canonical claims, 306 routed, 153 routing-failed and
three deferred; 151 facts, 93 identities, 55 pages and 46 pending identity
decisions. There is no extraction backlog at that snapshot. Recent sessions
take over two hours each. Grouping failures repeatedly queue older evidence for
organization. Truth work consumes about 74% of the pre-stop recorded model time;
the session-15 cache contains 40,258 screened candidate cells and 15,359 final
comparisons, all final relations `no_change`. This is not proof that the sources
contain no relevant change. The direct controls already show semantic misses.

Stopping avoids extending a growing, already-failed organization workload while
the user has selected simplification. The prior permission to cancel tests
applies. Only the identified benchmark process received SIGINT; services were
not started or stopped. Original snapshots and traces remain unchanged. Later
main-branch retry/publication fixes were not loaded by the frozen process.
Detailed source/view review currently covers sessions 1–8; the later snapshots'
counts/integrity checks do not substitute for their semantic review.

## Product hypothesis

Let a model read source evidence and a bounded set of prior memories once to
retain useful statements, identify their subjects, and propose any supported
changes. Refresh affected readable views separately using retained evidence.
Avoid repeatedly rediscovering, attributing, classifying and comparing the same
statements through independent taxonomies. No new repair, verification or
semantic fallback layer.

The experimental contract is deliberately small:

1. **Retain:** flat lists of source-grounded subjects, memories, and pending
   change proposals, with exact citations. Reuse
   supplied subject IDs only when supported. Ambiguous identity stays explicit.
   Preserve conditions and relative-time wording with source timestamps. The
   prototype does not invent normalized dates or silently replace canonical
   memory. It does not yet prove normalized temporal retrieval.
   No exhaustive segment partition is required from the model. Unselected source
   segments remain saved; their absence from citations is not a semantic claim
   that they are unimportant or permanently excluded.
2. **Present:** one bounded refresh for affected subjects, using source-derived
   headings and cited memory IDs. A subject need not have a page. Existing
   memories remain available regardless of page admission. No fixed taxonomy
   or claim-by-subject relevance matrix is imposed in this arm.

Both are model decisions; code validates exact references and declared states.
Names cannot establish identity through matching code. Source roles, explicit
human identity bindings, evidence-specific no-page exclusions, and pending
canonical review remain requirements. Any production adoption must preserve
the durable capture / explicit Build boundary, correction preview, retraction,
manual edits, interrupted publication and independently searchable claims.

## Frozen experiment and acceptance

First prove the contract in a benchmark-only module with the configured host
`gemma4:12b`, normal temperature/context/retry settings and unchanged request
recording. No alternative model, benchmark vocabulary in prompts, model judge,
or extra inference stage. Save raw requests/responses, model digest, input cases,
prompt/schema and exact code in a new run root.

- Direct phase: small neutral source cases covering conditional acceptance,
  context-dependent replies, identity continuity through topic changes, distinct
  namesakes, historical versus tentative future events, and explicit changed
  plans. Include assistant suggestions that were never adopted. Review source
  meaning manually; deterministic checks only assess structural invariants.
- Budget: at most **48 actual generation attempts / 12 minutes** for the direct
  phase, including the existing retry allowance. The expected successful path
  is one retain and one presentation call per case/source chunk. Complete the
  fixed cases despite isolated semantic mistakes, then assess overall usefulness.
  Stop at the budget or an unusable structural contract; no stream of wording
  variants to perfect familiar examples.
- If the direct phase produces broadly usable artifacts, run one paired native comparison
  on a short successive-source sequence: current full pipeline versus the
  proposed path. Use the same sources, role/time metadata, initial evidence,
  model/configuration, retrieval/answer budgets and human-review actions.
  Budget at most **120 attempts / 20 minutes** across both arms. Reserve one
  independently written sequence before seeing outcomes and do not tune on it.
- Assess useful facts, attribution/identity continuity, conditions, temporal
  precision and unresolved changes together. Require inspectable citations.
  Exact titles, number of pages and benchmark wording are not targets.
  Compare readable pages and source-grounded answers as well as retained claims.
- Seek at least **50% fewer generation attempts and output tokens** over the
  full paired workload, without increased input tokens, and assess overall
  artifact coherence and usefulness against the control. This is a directional
  target, not a benchmark score to optimize or an asserted competitor SLA.
  Isolated omissions/identity mistakes need not reject the simpler approach.
  Lost sources, invalid references or silent destructive changes do block adoption.
  Report weaknesses and unmatched features; do not demand a perfect score.
- Adopt only after an in-situ run and structural storage/review tests. A useful
  direct result can justify integration work, not a release claim. An incomplete
  comparison cannot satisfy adoption. If the proposal fails, record it and stop;
  do not retain a dormant production mode or compatibility layer.

The earlier flat truth-shortlist proposal remains rejected. This experiment
tests the broader source-to-memory/view boundary; it is not another wording
variant of that shortlist or a commitment to replace the database.
