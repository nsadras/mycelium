# Bounded test: preserve relationships in identity references

Authorized 2026-09-20. Baseline `6ad948a` (production contract unchanged from
`55cf5df`). This is a new experiment; the preceding output-order experiment is
closed. Evidence root: `benchmark_runs/relationship-reference-20260920/`.

## Hypothesis and scope

A retained statement can correctly name a person while omitting or misassigning
their structured identity. Test whether explicitly asking for the identities in
an already-retained relationship improves this consistency. Do not mandate a
project owner, a page for every person, or exhaustive entity/fact coverage.

Test exactly one prompt addition, after the existing instruction to reference
subjects using supplied or declared IDs:

> When a retained statement describes a meaningful relationship between identified
> subjects, reference each of them; naming them in text alone does not preserve
> their identity.

All schema fields, field order, validators, sampling options, and model calls
remain unchanged. The candidate exists only inside the isolated probe process.
No name matching, semantic postprocessing, additional resolver, or repair retry.

## Frozen comparison and budget

- Maximum **12 generation requests / 600 client generation seconds**.
- Six calls: fresh baseline/candidate pairs for a short own-project discussion,
  a short third-party discussion, and a new unknown-owner discussion. The last
  includes an organization running an event, which does not establish project
  ownership. Speaker names appear in reviewed metadata rather than spoken words.
- Two calls: a fresh baseline/candidate pair for the previous longer third-party
  discussion, where prose and person references disagreed. Reuse its frozen input
  unchanged. Do not count old responses as fresh controls.
- If the candidate remains promising, two calls on the previously frozen mixed
  personal/third-party case, not run in the prior experiment. Its text is already
  available to the investigator; this is a reserved case, not a blind holdout.
- If direct results support the change, two calls for an isolated candidate Build
  of the original full recording. Compare with the recorded unchanged-baseline
  Build as a historical stochastic sample, not a fresh paired control.
- Freeze prompt, inputs, schemas, model inventory and configuration before calls.
  No second candidate, repeated sampling until success, or budget extension.

## Review and decision

Review retained prose, declared subjects, participant bindings, exact subject
references, citations and resulting pages. Distinguish source interpretation from
reference consistency, structural rejection, persistence and presentation.

A useful result preserves source-backed relationships without making the speaker
an owner by default, inventing ownership, losing useful personal context, or
creating a material cost regression. Missing incidental details is acceptable;
exact page counts and exhaustive coverage are not targets. A declaration without
useful supporting statements does not resolve the omission.

Evaluate the four initial pairs before deciding whether the reserved checks are
worth their cost. Stop early if there is no demonstrated general benefit or a
material regression. One stochastic sample per condition cannot establish a
reliability rate or prove the prompt caused every difference.

Deliver a source-reviewed result and recommendation in planning and DEVLOG. This
request verifies a proposal; production adoption is a separate decision. Preserve
the live store, user-owned guidance/notes and running services.

## Closed

Stop after eight calls / 188.49 client generation seconds. The candidate regresses
own-project references in the short case and exhausts output in the long case.
Skip the reserved mixed-case pair and production Build. Keep production unchanged.
[Results and causes](relationship_reference_result_2026_09_21.md).
