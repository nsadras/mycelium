# Bounded investigation: retaining people in meeting memory

Authorized 2026-09-20. Baseline `55cf5df`.
Evidence root: `benchmark_runs/speaker-attribution-20260920/`.

## Question

Why can a named speaker's useful personal/project context disappear when a long
meeting is retained? Distinguish input loss, source interpretation, selection,
identity references, and later presentation. The preceding recording requests
included the reviewed name and all source text; the missing person began in retention.

## Frozen comparison

- Four synthetic transcripts: own project / another person's project, each short
  and longer. The same ownership and personal evidence remains in each length pair;
  longer versions insert ordinary technical discussion. The speaker's reviewed name
  appears in production metadata, not their spoken words. Use production capture,
  retention input construction, prompt, compact IDs, schema and partial admission.
- One separately authored unseen transcript mixes personal work with someone else's
  work. Keep it out of initial prompt selection and compare baseline/candidate once.
- Use the previously frozen real 884-segment recording for one isolated production
  Build after direct proof. Its prior baseline artifacts remain available; they
  are a historical stochastic sample, not a new matched control.
- Freeze input files, config/model digest, prompt and schema before native calls.
  Use configured Gemma sampling; no seed/model change, generated judge, repair retry,
  artificial missing-name instruction, fixture vocabulary in prompts, or exact page
  layout assertions. Do not generate audio: this experiment starts after diarization.

## Budget and decision

- Maximum **12 generation requests and 600 seconds of generation request time**:
  four baseline, four candidate, two unseen baseline/candidate, two production
  retention/presentation. Each direct case has its own one-request ceiling.
- At most one prompt or representation revision, chosen after inspecting baseline
  results. No new schema fields, runtime generation stages, ontology or semantic
  fallback. If no defensible small candidate emerges, stop early and report that.
- Judge source-backed attribution, speaker/owner separation, useful personal
  context, unsupported relationships, valid references and output cost. An identity
  without supporting statements is not success. Page count and total fact coverage
  are not targets. One sample per condition cannot establish a general error rate.
- Adopt only if the direct outputs support the mechanism without a material
  ownership regression, and the isolated Build demonstrates useful behavior.
  Otherwise preserve the production prompt and record the limitation. No second
  candidate or extension of the budget to polish the recording.

## Deliverable

Source review and per-call timings/results, including meaningful failures and
comparison limits, in a results note and DEVLOG. If adopting a change, run focused
and appropriate regression checks and commit validated work. Preserve the live
store, user-owned guidance edits and notes; do not operate app services.

## Candidate frozen after four baseline calls

Both short cases retained the speaker correctly. In the longer third-party case,
memory `m9` correctly describes the speaker's job and feedback role, but its
`subject_ids` points to the project builder; the speaker's declaration is absent.
The longer own-project case retains the speaker but emits a 400-segment citation
list and 7,089 output tokens. Input loss was ruled out for these requests.

Test exactly one contract revision: serialize `memories` before `subjects`, and
state that order in the prompt. All fields, types, allowed IDs and validators
stay the same. Hypothesis: declaring identities after selecting statements reduces
premature identity selection. This is a hypothesis about output consistency, not
a claim that context length alone caused the failure or that every speaker needs
a page. The candidate is isolated in the probe until the acceptance checks finish.

## Closed

The candidate regressed own-short and both longer cases and was rejected. The unseen
pair was skipped once adoption was ruled out. The reserved production check used the
unchanged baseline on the frozen recording, which again omitted Hari's identity while
naming him in retained text. Stop at **10 requests / 249.83 client seconds**; no
second candidate. [Results and decision](speaker_attribution_result_2026_09_20.md).
