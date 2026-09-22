# Protected views and compact retrieval: bounded implementation

Baseline: `ccca7e3`; protected-view fix separately validated and committed as
`50a3f9d`. User-owned guidance/notes, live stores and services stay untouched.

## Mechanical change

Prevent repeated insertion at the same exact support/destinations/heading while
preserving protected text, distinct views and unrelated pages. Three successive
refreshes for manual/pending protection plus four saved LoCoMo responses. No
inference calls. Stop once these invariants pass; no cleanup of old manual data.

## One retrieval candidate

Keep matching canonical claims selectable before optional related views. Render
shared records and exact sources once in compact JSON with reversible local IDs.
Keep text, identities, temporal/review state and citation relationships unchanged.
Preserve the actual selected records into answering; bound actual result records.
Use one admission call with whole-record budget fitting. Keep the current selection
instructions apart from passing the existing configured result limit.

The rejected shared-evidence experiment supplies reviewed structural code/tests,
not an accepted semantic result. Its verbose representation failed to save input
tokens. This candidate tests actual compaction; no identity-index or retention
change, verifier, retry or model-output field is added.

## Frozen comparison, defined before native calls

Seven paired app-style questions, with identical ordered initial search hits:

1. LoCoMo sample 7: whether both people own pets; adoption identity and timing.
2. LoCoMo sample 8: changed outlook; snake names, species and ownership.
3. Neutral two-project conversation: builders and agreed help; an unset launch date.
4. Prior workshop control: fund, expenses and keyholders (previous regression).

Use both saved five-session stores, the saved workshop store, and one explicitly
constructed neutral source/claim/view fixture. No re-encoding. Alternate arm order.
Use configured Gemma, decoding and embeddings without seed selection. Use the
ordinary app prompt and memory tools, no judge or web tools. Save full requests,
per-call timings, source snapshots, selected evidence and final workspaces.

Budget: **one candidate, seven pairs, at most 36 generation attempts and 600 seconds
of native execution** including preparation. Expected minimum is 28 attempts;
remaining allowance is for ordinary tool rounds, not tuning/repeats. Stop on budget
exhaustion and report incomplete pairs. Do not rerun successful cases.

Acceptance: aggregate native selection input at least 30% lower, no increased
selection call count or retry mechanism, useful grounded support on all three new
contexts, and no loss of the known workshop keyholder support. Judge against sources,
not questionable benchmark reference answers. Isolated reasonable answer variations
are recorded; do not chase perfect answers. Reject if recurring loss of useful
support or cost failure. Passing unit tests alone does not authorize adoption.

Mechanical checks include large shared views, selectable/returned identity, exact
ID/text compaction, result limits, concurrent edits, supersession, retraction and
incremental source budgets. Run the existing Python suite before adoption. No UI
or service changes; device checks remain the user's follow-up.

Retention/presentation quality tuning is deferred: the previous prompt trial failed,
and this work does not claim to fix retention omissions or achieve complete coverage.
