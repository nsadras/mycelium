# Bounded experiment: readable evidence passages

Baseline `108ba53`; authorized 2026-09-21. Evidence root:
`benchmark_runs/evidence-passages-20260921/`.

## Mechanism and invariant

Represent adjacent fragments as bounded passages for retention. A model citation
to a passage expands to its exact original segment IDs before persistence.
Preserve all source wording, ordering, participant/role information, time anchors
and meaningful metadata. Never infer identity or ownership during grouping.

Only join consecutive original source indices with identical source, participant,
speaker, role, time anchor and remaining metadata. Keep new evidence and context
separate. Join fragments with a space, up to 1,200 characters per passage; leave
an already longer original segment intact. This is a fixed presentation bound,
not a topic/sentence classifier or a parameter to tune against fixture outcomes.

Original source artifacts stay intact. A source index is passed internally so
grouping cannot bridge omitted fragments; it does not enter the model request.
Keep the existing flat schema, prompts, sampling and number of generation stages.
Save the passage-to-original citation map in diagnostics. Citations become broader;
increased cited-segment coverage must not be reported as improved fact coverage.

## Fixed comparison

At most **12 generation calls / 600 client generation seconds**, one candidate:

1. Fresh baseline/candidate pairs on the frozen short own-project, short
   third-party-project and longer third-party-project conversations (six calls).
2. If promising, the frozen mixed personal/third-party conversation that previous
   experiments reserved but did not run (two calls).
3. If direct evidence supports adoption, fresh baseline and candidate Builds of
   the same original recording in isolated stores (four calls). Inspect both
   retention and pages, source preservation, exact citations and zero-call no-op.

Freeze baseline/candidate code, inputs, prompt, schema, configured model inventory
and options. No second candidate, prompt revisions, repair retries, model changes,
generated judge, automatic semantic fallback or extension to perfect a recording.

## Acceptance and implementation

- Demonstrate substantial input/citation overhead reduction on fragmented sources.
- Retain coherent useful context and distinguish speakers from people discussed.
  Ordinary omissions and identity mistakes remain acceptable; resolving every
  prior omission, creating specific pages or matching a fact count is not required.
  Reject a material attribution/utility regression or unjustified generation cost.
- Exact source words and order survive representation; citations resolve only to
  the represented original segments. Do not merge across source, participant,
  role, timestamp, metadata, index gaps or new/context boundaries.
- Before production adoption, inspect real model outputs and whole artifacts.
  Then integrate the same representation in request budgeting and inference, add
  focused structural/provenance and persistence checks, and run relevant regressions.
- Record incomplete/failed calls, per-call timings, native vs estimated tokens,
  output size, citation breadth, source review and limits in results and DEVLOG.
  If adopted for efficiency with identity omissions remaining, say so explicitly.

Preserve live data and user-owned edits. Tests and isolated probes are authorized;
do not operate app/Ollama services. Commit validated changes under standing approval.

## Closed

All twelve calls completed in 159.49 client generation seconds. Adopt the tested
representation for directly verified overhead reduction, with mixed quality and
identity omissions explicitly retained as limitations. An offline check found
expanded-ID display crowding wiki and agent evidence; exact citation ranges fix
that mechanical issue without another generation. [Results](evidence_passages_result_2026_09_21.md).
