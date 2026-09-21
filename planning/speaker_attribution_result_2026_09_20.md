# Speaker attribution investigation: recurring output inconsistency, candidate rejected

Completed 2026-09-20. Baseline `55cf5df`.
[Frozen plan](speaker_attribution_plan_2026_09_20.md).
Evidence: `benchmark_runs/speaker-attribution-20260920/`, especially `review.json`,
`baseline-review.json`, `candidate-review.json`, `inputs/`, `direct/`, and
`production/baseline/`. Production behavior is unchanged.

## Conclusion

The omission is worth recognizing as a recurring output-consistency problem. This
experiment found **no justified production fix**. Reject the single candidate and
stop after ten generation requests; two remain unused.

The strongest new finding is that **the model can name a person correctly in a
retained statement while failing to declare or reference that person's identity**:

- In the longer synthetic third-party discussion, the baseline writes a correct
  statement about Leena's job and feedback role, but links it to Omar's identity.
  Omar owns the project; Leena is the speaker. Her declaration is absent.
- In the fresh full-recording Build, two retained statements explicitly say
  "Hari's content strategy" and "Hari's goal". The raw response nevertheless
  declares only six project/technical subjects. Neither a Hari identity nor his
  participant binding is created. The later page organizer receives no Hari
  identity to organize into a person page.

The name assignment was therefore available and used in prose. No validator
silently removed Hari, and the source was not truncated. The immediate defect is
in the model's selection and assignment of structured subjects during retention.
This does not establish the underlying decoding cause. The longer own-project
baseline retained the speaker, so length alone is not a sufficient explanation.

## Design and input checks

- Four synthetic cases pair own-project and third-party-project discussions at
  short and longer lengths. Speaker Leena's name appears in the reviewed speaker
  metadata, never her spoken words. Ownership, personal job/accreditation and future
  qualifications remain in both lengths. The longer versions add the same ordinary
  technical discussion around those statements.
- Short cases: 164–166 words, 33–34 segments, about 2,950–2,981 estimated input
  tokens. Longer cases: 3,214–3,216 words, 643–644 segments, about 26,513–26,547
  estimated tokens. Five-word chunks approximate short ASR segments without changing
  the concatenated words. All fit one request without omitted context.
- Production capture and retention input construction generate the source, roster,
  compact IDs and schema. Each actual request was checked against its frozen input.
  Candidate and baseline use identical evidence and the same schema fields, types,
  allowed IDs and validators.
- Model: configured `gemma4:12b`, digest
  `4eb23ef187e2c5462566d6a1d3bbbc2f1346d0b4327cbb66d58fffbcc9b2b05c`.
  Temperature 1, top-p .95, top-k 64; 65,536 context and 8,192 output tokens;
  reasoning off. Model inventories and options are saved for each case. No seed,
  fallback model, additional resolver or LLM judge was introduced.

## Results of the only candidate

The candidate changes output order from `subjects, memories, changes` to
`memories, subjects, changes` and tells the model to write memories before declaring
their identities. Hypothesis: selecting statements first might prevent premature
identity selection. This remains one generation with the same flat schema.

| Case | Baseline | Candidate |
| --- | --- | --- |
| Own project, short | Six memories; correct Leena/project relationship, participant binding, job and qualification. | One combined memory names Leena and includes personal context, but declares/references only the project. Speaker identity regresses. |
| Other person's project, short | Four memories; separates speaker Leena from builder Omar and retains personal context. | Six memories; preserves the same distinction. Some relationships are named in prose without corresponding project references. |
| Own project, longer | Twenty-five memories; correct speaker/project identities. Personal accreditation is omitted. Excessive citations and some vague technical summaries reduce concision. | One raw memory references an undeclared identity; partial admission rejects it. Leena's declaration alone remains, with no accepted memory. This fails the explicit evidence-backed-identity criterion. |
| Other person's project, longer | Nine memories. Leena is named correctly in a statement but its subject ID points to Omar; Leena is undeclared. | One project summary names Omar in prose but declares only the project. Both person identities are omitted. |

The candidate provides no general attribution improvement and introduces material
regressions. It was never integrated into production. Its much shorter outputs are
not an efficiency win when useful statements and identities disappear.

The unseen baseline/candidate pair was frozen but **not run** after this rejection.
There was no remaining adoption decision for that pair to resolve. The reserved
two-call production check ran the unchanged baseline on the real recording instead.
No second candidate was attempted.

## Full recording check

The isolated unchanged production Build receives all 884 source segments in order,
including 882 labelled Hari. Exact submitted text matches the frozen original;
no optional context is omitted. It completes with six retained statements, six
subject pages and You's memory map. There are no rejected records or failed calls.
A subsequent no-op Build makes zero calls.

Hari appears in retained prose and on the project page, but not as an identity or
person page. The six selected subjects are the project, hosting/auth/payment
providers, backend infrastructure and an architecture topic. The raw model output
already has this selection: persistence and presentation do not remove a person.

This also retains an existing meaning problem outside this investigation's fix
scope: content updates are described as automatic, although source indices 29–30
say full automation is an eventual goal. Presentation repeats that overstatement.
Passing structural validation is not a factual correctness judgment.

The previous full-recording run at `55cf5df` also omitted Hari's identity. That is
recurrence on the same source and contract, not a population error rate. Prior
100-segment runs used different contracts/workloads and cannot establish that
smaller batches would fix the issue.

## Per-call computation

Each row below is one completed generation request, attempt one.

| Variant / case | Input tokens | Output tokens | Client seconds |
| --- | ---: | ---: | ---: |
| Baseline own-short | 3,041 | 789 | 19.00 |
| Baseline other-short | 3,004 | 793 | 11.30 |
| Baseline own-long | 28,305 | 7,089 | 110.29 |
| Baseline other-long | 28,266 | 1,433 | 28.36 |
| Candidate own-short | 3,053 | 224 | 4.64 |
| Candidate other-short | 3,016 | 840 | 11.55 |
| Candidate own-long | 28,317 | 237 | 11.02 |
| Candidate other-long | 28,278 | 219 | 10.90 |
| Production baseline retention | 40,883 | 1,302 | 30.85 |
| Production baseline presentation | 1,726 | 810 | 11.92 |
| **Total** | **167,889** | **13,736** | **249.83** |

Server duration totals 249.80 seconds. The first baseline call includes 8.30
seconds of loading; subsequent calls are warm. All transport requests completed,
no automatic retry occurred, and no output hit its generation limit. One candidate
record was rejected for an undeclared identity. The own-long baseline includes a
400-segment citation list on one broad statement, accounting for substantial output
cost. This outlier does not justify a new citation rule from one sample.

Fresh stores and explicit empty prior context avoid embedding work in the direct
probes; the fresh production store emits no embedding requests. End-to-end Build
time is 43.17 seconds; no-op inference cost is zero. Detailed load, prompt evaluation
and generation timings are in `review.json` and raw request records.

## What this establishes, and what it does not

- A clean synthetic transcript can produce a related identity omission/misattribution.
  The missing second half of the real audio is not necessary for this failure class.
- In the failing examples, names and supporting statements reached the model, and
  the model used the names in its text. More context delivery alone would not fix
  the observed structured-reference mismatch.
- Output order is not a proven remedy. The only tested revision made attribution
  less reliable in these cases; production retains its existing contract.
- Each condition has one stochastic sample. Synthetic speech is clearer, ownership
  more explicit, and input shorter than the real recording. Those limitations prevent
  attributing the difference solely to length or estimating general reliability.
- No candidate follow-on Build, retrieval/QA test, large-store trial or model change
  was performed. The unseen pair was not used as evidence of generalization.

## Decision

Keep the current pipeline and use explicit identity correction for affected retained
statements. Record this as a known limitation, rather than dismissing it as an audio
artifact or declaring it solved. Do not automatically assign every statement to its
speaker, create unsupported person pages, add retries or introduce another model stage.

Stop this investigation. If ordinary use across additional recordings shows frequent
harmful attribution loss, a future bounded change should address consistency between
retained statements and their person/project references. Do not keep adjusting this
one recording until it produces a preferred page layout.

Validation here consists of configured-model probes, manual source/output review,
exact frozen-input/schema checks, full-recording text preservation and the production
no-op check. No production code changed, so the application test suite was not rerun.
