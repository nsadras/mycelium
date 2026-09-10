# Gemma reasoning on/off experiment — 2026-09-09

The recommended sampling settings resolved the observed reasoning loops on both
neutral probes. A completed cumulative pair showed better consolidation with
reasoning, at roughly six times the elapsed time. A subsequent natural-dialogue
extraction lost substantial coverage, so the larger comparison was intentionally
stopped for a targeted schema-grounding diagnosis. These results do not justify
enabling reasoning everywhere without further integration work.

## Setup

- Production baseline: commit `2bc590f`; configured `gemma4:12b`, Q4_K_M.
- Host Ollama 0.32.15; model digest
  `4eb23ef187e2c5462566d6a1d3bbbc2f1346d0b4327cbb66d58fffbcc9b2b05c`.
- Host `/api/show` advertises thinking support and a 262144-token maximum.
- Initial controls: 32768-token context, 16384-token output allowance,
  temperature 0, seed 17, 900-second request timeout.
- Expanded-budget control: 49152-token context, 32768-token output allowance.
- Within each direct pair, actual API payloads differ only in `think`.
- Actual production extraction prompt and Pydantic JSON schema; neutral
  acceptance/refusal of a contextual proposal. No prompt modifications.
- Full requests, responses, native usage, stop reasons, and parsed outputs:
  `benchmark_runs/reasoning-comparison-20260909/`.
- Reproduction harness: `benchmarks/reasoning_comparison.py`.

The experiment overrides the transport and structured-call output allowance in
its own process. Production defaults have not been changed. The failed calls
below have native `eval_count` equal to `num_predict`, nonempty thinking, and
empty content. Successful reasoning-plus-schema calls report native evaluation
counts much smaller than their returned thinking text; these counters therefore
cannot be treated as total reasoning-plus-answer tokens on this host. The
experiment also records separate cl100k estimates and wall time. The estimates
are not the model's native tokenizer counts.

## Initial results

| Acceptance probe | Thinking | Output allowance | Native generated tokens | Request time | Result |
|---|---|---:|---:|---:|---|
| Production sampling | Off | 16384 | 160 | 10.9s | Valid, correct assertion |
| Production sampling, three attempts | On | 16384 each | 49152 total | 617.1s total | All three hit output limit; no final JSON |
| Expanded budget | Off | 32768 | 160 | 7.7s | Same valid, correct assertion |
| Expanded budget | On | 32768 | 32768 | 416.0s | Hit output limit; no final JSON |

The successful assertion preserves Mira's decision, the garden gate, cedar
boards, next Saturday, and citations to both her acceptance and the proposal.
The failed reasoning calls repeatedly revisit already-resolved constraints.
These are generation-limit failures, not HTTP timeouts or a lack of thinking
support. Increasing the allowance did not yield a final answer in this case.
This does not establish that reasoning cannot improve memory quality under
different sampling settings.

## Sampling controls

Production structured calls hard-code temperature 0. Google's model card
recommends temperature 1.0, top-p 0.95, and top-k 64 across use cases. The latter
two already match the configured model's defaults. Separate paired controls
at temperature 0.2 and 1.0 test sampling without changing the prompt or schema.
[Google model card](https://huggingface.co/google/gemma-4-12B-it#best-practices).

| Temperature | Probe | Thinking | Time | Usable JSON | Quality observation |
|---|---|---|---:|---|---|
| 0.2 | Acceptance | Off | 7.1s | Yes | Correct scope and citations |
| 0.2 | Acceptance | On | 208.6s | No | 16384-token limit, empty final content |
| 0.2 | Refusal | On | 201.4s | No | 16384-token limit, empty final content |
| 0.2 | Refusal | Off | 5.3s | Yes | Two assertions; future possibility labeled atemporal/preference |
| 1.0 | Acceptance | Off | 2.5s | Yes | Retains action/scope; weaker expression of the decision |
| 1.0 | Acceptance | On | 30.4s | Yes | Explicit decision, full scope, both citations |
| 1.0 | Refusal | On | 34.0s | Yes | One coherent assertion retains refusal and later possibility, both citations |
| 1.0 | Refusal | Off | 5.0s | Yes | Refusal lacks contextual citation; future possibility labeled atemporal/preference |

Both temperature-1 thinking calls stopped normally, with approximately 2112 and
2293 estimated thinking tokens respectively. Both arms explicitly requested
top-k 64 and top-p 0.95. Earlier controls inherited these same model defaults.
At this seed, temperature 1 resolves the observed failures and reasoning improves
the refusal's coherence and provenance. Two examples and one seed do not prove
that every production stage will behave well.

### SDK and request verification

Production and experiment inference both use Ollama Python SDK 0.6.2,
`AsyncClient.chat()`. Raw urllib requests only inspected host capabilities and
status. Inspection of the installed SDK and a captured mock HTTP transport
verify that `think=True` is serialized at the top level of `/api/chat`, with
sampling/context/output settings inside `options`. The host's nonempty thinking
responses independently verify that the flag takes effect. Capture:
`benchmark_runs/reasoning-comparison-20260909/sdk-wire-check.json`.

Production `call_structured()` hard-codes `think=False` and temperature 0, so
changing only `mycelium.toml` does not fix those calls. The experiment overrides
both explicitly. Google-style thinking control tokens should not be manually
added to these SDK messages: the Ollama thinking interface handles the model
formatting.

The schema is passed through `format` but is absent from the message text.
Ollama recommends also including it in the prompt. This is a separate potential
improvement, not a proven cause: the recommended-temperature probes succeeded
without changing schema visibility. Grounded neutral probes also passed
structural validation. Acceptance took 18.2s, but refusal took 104.1s and split
the assertion again. Both grounded reasoning outputs used `role=user` in
`about`, although the prompt's semantic role is `subject`. The permissive string
schema accepts this. Grounding therefore does not uniformly improve the contract.
[Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

## Completed cumulative comparison

Fresh stores, identical three source batches, durable reload between builds,
temperature 1/top-p .95/top-k 64 in both arms, seed 17, context 32768 and output
16384. Requests and snapshots are under
`benchmark_runs/reasoning-comparison-20260909/pipeline-temperature-10/neutral/`.

| Measure | Off | On |
|---|---:|---:|
| Total elapsed seconds | 149.3 | 897.7 |
| Model attempts | 25 | 27 |
| Contract corrections | 0 | 2 |
| Active / represented claims | 18 / 18 | 18 / 18 |
| Display facts | 14 | 11 |
| Words in display assertions | 108 | 95 |
| Estimated thinking tokens | 0 | 55121 |
| Output-limit stops | 0 | 0 |
| Unresolved build failures | 0 | 0 |

Manual source comparison found every supplied detail visible in both final
wikis. Reasoning merged occupation/tenure, language learning/practice, and choir
joining/rehearsal more coherently. It avoided off's “enjoys and still enjoys”
watercolor phrasing. It added unsupported emphasis “just” to the ten-year tenure,
and placed volunteering under Preferences & Working Style. Coverage is equal;
concision improves; correctness and organization remain mixed. Two on calls
needed correction for omitted segments/claim memberships, and both recovered.

## Natural-dialogue integration failure

The first 48-segment batch of sample 9's first session returned only the new
Prius ownership claim. It relegated supported assertions about the old car's
breakdown and repair/sale decision, the Rockies trip, hiking with a parent,
painting interest, and a friend's introduction to watercolor to `source_only`.
The model recognized these assertions during reasoning. This is a semantic
coverage loss despite valid structural accounting. The next batch added three
generic social/update assertions, leaving only four claims from the session.

The schema allows 128 claims, and the failing request stopped normally after
about 7741 estimated thinking tokens; neither an array cap nor a generation
limit explains the omission. The comparison client was interrupted deliberately
before finishing this build. Ollama itself was not stopped. The incomplete store
must not be reported as a completed benchmark or a host crash. The exact failing
request and subsequent targeted replays are preserved; remaining LoCoMo arms
were not run.

### Exact-batch grounding controls

The first natural-dialogue request was replayed through the same SDK, production
prompt, exact Pydantic schema, seed, recommended sampling, and 16K output reserve.
Single attempts isolate behavior; validation failures are not silently repaired
or accepted. Adding schema text raised estimated full input to 11042 tokens,
below the 14336-token available input budget.

| Schema in prompt | Thinking | Time | Claims / source-only records | Contract |
|---|---|---:|---|---|
| No | Off | 45.1s | 10 / 37 | Failed: one unaccounted segment |
| No, original pipeline call | On | 139.8s | 1 / 47 | Passed, severe semantic omissions |
| Yes | On | 171.7s | 1 / 46 | Passed, severe semantic omissions remain |
| Yes | Off | 44.4s | 9 / 37 | Failed: one unaccounted segment |
| Yes, native `format` omitted | On | 192.6s | 9 / 37 | Passed, coverage substantially recovered |

Grounding does not fix the omission. The ungrounded off control also upgrades
the repair/sale decision to a completed repair and sale. Neither arm is a clean
quality baseline at this setting. The final diagnostic removed only native
`format`, retaining exact grounded messages and Pydantic validation. Actual
request comparison confirms `format` is the only differing key. It recovered
the trip, hiking history, painting interest/experience, and friend introduction,
and passed all structural validation. It still incorrectly described the
repair/sale decision as completed repair and sale, and omitted other details
such as the long interval since Sam last hiked. This is an experiment, not a
production fallback or a proposed removal of validation.

The unconstrained call stopped normally at 14858 native generated tokens
(approximately 9979 thinking plus 2426 content tokens under cl100k) with 8806
native prompt tokens. The 16384 allowance was sufficient for this call, but
has only about 9% generation margin; larger workloads need appropriately larger
bounded reserves. The 32768-token context was not exhausted. Native accounting
here includes reasoning, unlike the successful constrained responses above.

## Conclusions and next work

1. **SDK and thinking flag are correct.** All inference used `AsyncClient.chat`;
   `think=True` reaches the native endpoint and produces thinking. Tool rounds
   retain assistant thinking; ordinary structured retries retain final content
   rather than past reasoning.
2. **Production sampling overrides need correction.** The hard-coded
   temperature 0 bypasses the configured model's recommended temperature 1.
   On these probes, using recommended sampling resolves the observed loops.
   The application must expose and honor thinking, sampling, and output reserves
   together; changing only TOML is insufficient today.
3. **Native constrained generation needs investigation before rollout.** At one
   fixed seed, removing only `format` changes severe omission to much broader
   coverage. This isolates a sensitivity to the constrained-output path, not
   definitive proof of a particular Ollama implementation bug. SDK transport is
   unchanged. Preserve this exact replay when checking the host's generation
   behavior; do not infer supported claims with lexical overrides.
4. **Reasoning has a demonstrated but limited benefit.** Cumulative consolidation
   improved on neutral inputs at roughly six times the runtime. Natural-dialogue
   correctness and coverage are still inadequate for blanket enablement.
   Schema text alone is not the fix. Any revised mechanism needs fresh direct
   probes and an in-situ short benchmark with artifact review before commitment.

No production settings or client behavior were changed, and nothing was
committed. The experiment harness passed Ruff and `git diff --check`; no full
backend suite was rerun because the product code is unchanged. Host-model
results above are the behavioral validation, not mocked tests.

Ollama exposes reasoning separately in `message.thinking`; the experiment
records that field and the final content independently.
[Ollama thinking documentation](https://docs.ollama.com/capabilities/thinking).

## Evaluation limits

The direct probes isolate contextual extraction and schema completion. They
cannot establish full-wiki quality, long-horizon retention, or general benchmark
accuracy. Pipeline comparisons are gated on obtaining usable reasoning-enabled
structured output. Structural segment accounting will not be reported as
semantic coverage, and additional claims will not automatically count as an
improvement.
