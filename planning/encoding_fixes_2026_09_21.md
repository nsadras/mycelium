# Encoding audit implementation

Scope: implement the six fixes in [the encoding audit](encoding_audit_2026_09_21.md).
Keep the two-pass design and accept ordinary omissions. Retrieval is outside this
work. GPU contention explained the interrupted audit's timing; no runtime
investigation or continuation of that run is needed.

## Work and acceptance

1. **Identity admission (C):** discard illegal bindings before checking genuine
   conflicts; align title and singleton identity invariants. Test independent
   valid rows, fixed bindings, and genuinely conflicting people.
2. **Prior context (E):** interleave learned chunk rankings before the existing
   cap. Test disjoint and overlapping rankings and late candidates.
3. **Checkpoint recovery (D):** fail only the unchanged attempt and finalize from
   current state. Test a competing completion, independent SQLite connections,
   ordinary failure/recovery, and zero repeated extraction after completion.
4. **View scope and identity handoff (A/C):** use exact references and changed
   evidence to authorize rewriting; similarity supplies read-only context.
   Preserve selected items' complete support, protected edits and shared items.
   Offer relevant declared/bound people without making every speaker an owner.
   Test unrelated-item stability and relevant-update continuity.
5. **Presentation simplification (B):** compare one candidate that selects,
   groups and links retained text with the existing paraphrasing stage. Freeze
   three inputs (qualifications, independent context, repetition counterexample).
   Maximum six presentation calls, including baselines. Adopt only if useful
   qualifications survive and pages remain readable; otherwise close the
   experiment with the existing approach. No second candidate campaign.
6. **Cleanup and diagnostics (F):** remove unused routing helpers after checking
   consumers; distinguish cancellation and incomplete usage in recordings.
   Run relevant schema/curation and cancelled-recorder tests.

## Native validation limits

- Identity handoff: reuse the frozen own-project and third-party-project pair;
  maximum four calls (retention plus presentation for each). Correct roles matter;
  exact page counts do not.
- Final continuity: one isolated seeded three-Build check, maximum six generation
  calls and a zero-call no-op. Save per-call timing, failures, snapshots and source
  review. No QA or ideal-wiki score. Each native experiment has a 600-second cap;
  incomplete work stays explicitly incomplete, with no automatic extension.
- Model settings stay configured. No retries added to improve semantic outcomes.

Commit validated groups, preserving pre-existing user edits. Record results and
remaining limits here. Once these checks establish useful coherent memory and
stable unrelated pages, stop encoding work and move on to retrieval.

## Progress

- C admission, D recovery and E candidate merging implemented. Focused suite:
  **43 passed**; Ruff passed. The competing-completion regression also uses a
  second real SQLite snapshot/UnitOfWork. Both interleavings preserve the winning
  claims and completed checkpoint, with no second retention call on the next Build.
- The sandboxed test invocation stalled in a local index operation; it was
  interrupted and the same suite passed outside the sandbox in 7.29 seconds.
  This was test-environment behavior, not an Ollama performance finding.
- A/C view scope and handoff implemented. Unrelated candidates are read-only;
  selected items retain complete support and protected edits. Unused existing
  subject redeclarations no longer manufacture source/identity associations.
- B adopted after all six planned comparison calls: presentation selects/groups
  retained text instead of generating new prose. Candidate output tokens were
  1,101 versus 1,812; it preserved the planned chat feature that baseline made
  current. Longer pages and imperfect sharing remain explicit tradeoffs.
- C native pair completed in four calls. Own-project roles are correct. The
  third-party sample omitted the project entirely, so attribution confirmation
  for that sample is inconclusive. No repair rerun.
- Three successive native Builds completed in six calls / 88.38 seconds overall,
  with zero-call no-op. All 143 seed claims and 62 seed view items remain identical.
  Four structural warnings, zero failures/retries. Retention omissions and one
  misleading insurance statement remain; whole-artifact review is documented in
  the result report. Final handoff correction replayed all recorded decisions
  offline without inference and removed five irrelevant old people from scope.
- Integrated validation: **622 Python tests passed**, four native integration
  tests deselected; Ruff and whitespace checks passed. Ontology UI type cleanup
  also passes the frontend build and four WikiExplorer tests.
- F complete: unused routing/default-section scaffolding and stale documentation
  removed; cancellation, deadline and incomplete-usage diagnostics validated.
- All bounded work is closed. See [results and remaining limits](encoding_fixes_result_2026_09_21.md).
  The next product focus is retrieval; native identity counterexample coverage
  and some retention quality remain explicitly imperfect.
