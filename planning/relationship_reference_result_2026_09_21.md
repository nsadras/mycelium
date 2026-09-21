# Relationship-reference test: clarification not justified for adoption

Completed 2026-09-21. Baseline `6ad948a`.
[Frozen plan](relationship_reference_plan_2026_09_20.md).
Evidence: `benchmark_runs/relationship-reference-20260920/`, including exact
requests, frozen inputs/prompts, `verification.json`, `review.json`,
`partial-output-inspection.json`, and `input-overhead.json`.

## Decision

**Do not adopt the tested prompt addition.** Preserving meaningful relationships
remains a reasonable product goal, but this wording does not reliably improve
identity references. Stop at eight generation calls, with four reserved calls
unused. Production code, prompts, schemas and the live store are unchanged.

The candidate adds only this general instruction to the existing retention prompt:

> When a retained statement describes a meaningful relationship between identified
> subjects, reference each of them; naming them in text alone does not preserve
> their identity.

No owner requirement, new schema field, output-order change, resolver, semantic
fallback, additional generation stage or retry was introduced.

## Source-reviewed comparison

Each row is a fresh baseline/candidate pair with the same input and schema.
Names supplied as speaker metadata are absent from the speakers' own words.

| Case | Baseline | Candidate | Assessment |
| --- | --- | --- | --- |
| Speaker's own project, short | Six memories; Leena and Tideboard identities, job/accreditation and project status. Omar is mentioned in feedback without an identity. | One combined memory retains Leena and personal context but names Tideboard without declaring/referencing it. Prototype status and pilot context disappear. | The target inconsistency persists in the opposite direction: the person survives, the project does not. Material regression in this sample. |
| Another person's project, short | Separates builder Omar from speaker/reviewer Leena. Some statements name both person and project but reference only one. | Preserves their separation and adds useful joint references in several memories. Leena's project-feedback statement still references only Leena. | Partial improvement; no speaker-as-builder error, but no consistent relationship-reference behavior. |
| Project owner unspecified | Retains only Nisha's job/hobby. Omits the board and the cooperative running the workshop. | Also retains only Nisha's job/hobby. | No invented owner, but omission makes this a weak counterexample: it does not show useful project retention with ownership left unspecified. |
| Another person's project, longer | One memory about Omar building Tideboard; only Omar is declared/referenced. Leena and her useful personal context are omitted. | Generates a large technical extraction and runs out of output space. Its completed subject array includes Omar, project/topics/artifacts and no Leena. | Failed call with no accepted result; no attribution improvement worth adoption. |

The long candidate uses its entire 8,192-token allowance in 130.09 seconds and
ends with incomplete JSON. Sixteen complete memory fragments precede the truncation;
one lists **498 segment citations**, another 104. These fragments were inspected
only as failure diagnostics and were never repaired, admitted or persisted as
memory. The wrapper correctly reports `output_capacity` and makes no retry.

The short outputs also sometimes cite incomplete five-word spans while their
claims are supported by the fuller source. This is citation selection weakness,
not evidence that those facts were invented or absent from the input.

## Issues and likely causes

1. **Prose and identity references disagree.** The model can correctly write a
   person's/project's name without declaring or referencing it. In the previous
   study it also linked the speaker's personal statement to another person. This
   begins in the raw retention response, before admission or page creation.
   Hypothesis: independently selecting subjects, composing prose and assigning IDs
   in one response leaves room for inconsistent choices. The observed location is
   established; this explanation of why it happens is not experimentally isolated.
2. **Selection and level of detail vary greatly.** The unchanged long baseline
   produced nine memories in the previous study and one now. The candidate ranges
   from a single combined memory to excessive technical extraction. Configured
   stochastic sampling and an open-ended usefulness judgment plausibly contribute.
   We did not compare sampling settings or establish a causal effect of the wording.
3. **Evidence representation adds substantial mechanical work.** The long input has
   3,214 words in 643 tiny segments. With the same cl100k estimator, source text alone
   is about 4,200 tokens, serialized segments 20,920, the full payload 21,195 and
   the output schema another 3,433. Actual Gemma input is 28,266/28,297 tokens; its
   tokenizer differs, so do not mix those estimates into an exact overhead ratio.
   Repeated segment wrappers and explicit citation IDs consume real input/output
   capacity. Whether they cause identity omissions remains unproven.
4. **Missing people cannot be recovered by presentation.** The organizer receives
   retained identities. If retention omits a person, later pages cannot restore that
   identity from the recording without another decision. A mandatory project-owner
   rule would not address the observed unrelated-speaker omission and could invent
   ownership where none is established.

All submitted source text, participant metadata, IDs and schemas matched the frozen
inputs. No optional context was omitted. The evidence does not support blaming a
dropped speaker name, a transport failure, automatic retries or insufficient input
capacity for these specific failures. It also does not prove that the missing half
of the original audio is irrelevant to every ambiguity in that recording.

## Cost and completion

Configured `gemma4:12b`, digest
`4eb23ef187e2c5462566d6a1d3bbbc2f1346d0b4327cbb66d58fffbcc9b2b05c`;
temperature 1, top-p .95, top-k 64, context 65,536, output 8,192, reasoning off.

| Variant / case | Input tokens | Output tokens | Client seconds | Result |
| --- | ---: | ---: | ---: | --- |
| Baseline own-short | 3,041 | 814 | 19.42 | Complete |
| Candidate own-short | 3,072 | 180 | 3.83 | Complete |
| Baseline other-short | 3,004 | 579 | 8.69 | Complete |
| Candidate other-short | 3,035 | 851 | 12.26 | Complete |
| Baseline unknown-owner | 1,975 | 95 | 2.45 | Complete |
| Candidate unknown-owner | 2,006 | 90 | 2.03 | Complete |
| Baseline other-long | 28,266 | 109 | 9.73 | Complete |
| Candidate other-long | 28,297 | 8,192 | 130.09 | Output exhausted |
| **Total** | **72,696** | **10,910** | **188.49** | **7 complete, 1 failed** |

Server duration is 188.47 seconds. The first baseline includes 8.10 seconds of
model loading; all later loads are negligible. Every native request is attempt
one. No transport failure, repair regeneration or embedding request occurred.
Reserved mixed-case probes and the full-recording Build were skipped after the
candidate failed the initial comparison. No new wiki, follow-on Build, retrieval/QA
or correction-quality result is implied.

## Limits and next step

One stochastic sample per condition supports rejecting this candidate for adoption;
it does not estimate error rates or prove that the added sentence caused each
regression. Both contracts show unstable selection, and the long synthetic source
uses unusually fine, fixed-width segmentation. Earlier baseline citation inflation
also prevents treating the candidate's verbosity as a new failure class.

Keep ordinary use and explicit correction available. Do not add mandatory owners,
more identity rules or retry loops on the strength of this test. If a further
bounded implementation experiment is warranted, reducing the mechanical burden of
tiny source segments and long citation lists is a more concrete hypothesis to test
than accumulating prompt constraints. Preserve links to original evidence and check
quality as well as cost; that experiment is not implemented or proven here.

Validation: all eight native requests match frozen input/schema/model/options,
paired requests differ only in their system prompt, failure/truncation is recorded,
manual source review is saved, and probe Ruff/whitespace checks pass. No production
change was made, so the application test suite was not rerun.
