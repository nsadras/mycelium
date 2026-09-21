# Whole-conversation Build and first-attempt diagnostics

Baseline: `53a8ac5`. Authorized 2026-09-20.

## Scope

- Size the compacted request, including prompt/schema and output reserve. Prefer
  the whole source or pending turns from one chat session. Preserve capture IDs,
  provenance, completed batches and explicit participant bindings.
- Keep earlier processed turns as context; they must not produce fresh extraction.
  Split only when the request budget requires it. Record omitted optional context.
- Accept independently valid model records, reject broken references/bindings and
  their dependent records, and preserve exact rejected output for inspection.
  No inferred repairs, semantic heuristics or extra model judging calls.
- Stop automatic regeneration after invalid structured output. Bounded retries
  remain for transient transport errors. Report capacity, transport, model-output
  contract and persistence failures separately; semantic correctness needs source review.

## Validation and stopping rules

- Direct configured-host proof before changing model input/labor: two neutral
  combined-conversation cases, including reported work and unresolved references.
- Maximum 12 native generation requests / 10 minutes of request time for this
  tranche. Each scenario has its own cap. Reserve two calls for the full recording,
  two for combined chat, two for a follow-on Build; the remaining four are only
  for a meaningful failed check or counterexample. No quality-polishing loop.
- Structural tests: whole-request fit; necessary split with complete coverage;
  grouped capture/restart/retraction/stale writes; correct source-specific timestamps
  and bindings; valid partial records saved once; invalid references never committed;
  no validation retries; transport retries classified; no-op Build makes no calls.
- Review saved source, actual prompt, output and artifacts. Distinguish input loss,
  restrictive validation, invalid model references, and unsupported semantic claims.
  Do not infer semantic correctness from passing the schema.
- Run relevant full checks after focused tests. Record results/limits in DEVLOG and
  commit validated changes. Do not rebuild the live store or operate app services.

## Completion

Implemented and validated. See [results and remaining limits](conversation_build_result_2026_09_20.md).
Stop at 11 generation requests / 118.58 client seconds; leave one request unused.
The three reserved requests tested one discovered contract weakness: the prompt
left the existing person-only participant-binding rule implicit. One neutral
direct probe preceded the two-call production check of its short clarification.
No schema expansion, additional generation stage, or semantic repair rule was added.
