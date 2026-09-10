# Gemma 4 reasoning and structured output policy — 2026-09-09

Selective reasoning is enabled for truth review and cumulative fact synthesis. The application continues to use the Ollama Python SDK (`AsyncClient.chat`), with top-level `think=True`. No hand-written thought delimiters or reasoning instructions are needed in production prompts.

## Guidance and diagnosis

- [Google's Gemma 4 12B model card](https://huggingface.co/google/gemma-4-12B-it#best-practices) recommends temperature 1.0, top-p 0.95 and top-k 64. These now apply consistently to structured calls and benchmark QA; the structured wrapper previously forced temperature zero. The model-specific recommendation takes precedence here over Ollama's generic low-temperature structured-output advice.
- [Ollama thinking](https://docs.ollama.com/capabilities/thinking) exposes reasoning through the `think` request parameter and a separate `message.thinking` response field. We use that API through SDK 0.6.2 against host 0.32.15, model `gemma4:12b` (Q4_K_M).
- [Google's thought-context guidance](https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4#managing_thought_context_between_turns) says to strip raw thoughts between ordinary turns but retain them within a tool-call turn. Our chat history reconstruction copies role/content only; the existing tool loop retains the assistant thinking field. Structured corrections likewise replay final content only. This also strengthens the concern about a server-generated ordinary assistant turn containing raw thinking before constrained regeneration.
- Our list syntax is correct. [Ollama's structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs) uses the same Pydantic `list[Model]` convention and `model_json_schema()` dictionary. JSON Schema `items` describes each array member; it does not limit the array to one entry. A neutral six-record control returned all six records with native format both with and without reasoning.
- That documentation also recommends including the schema in the prompt. Reasoning calls now do this explicitly. The schema remains a Pydantic validation contract after generation, including application-specific structural invariants.
- There is a plausible server-side interaction beyond list syntax. The matching [Ollama rendered chat route](https://github.com/ollama/ollama/blob/v0.32.15/server/routes.go#L2754) starts thinking without format, interrupts at the content transition, then starts a constrained generation after replaying the thinking. The [Gemma renderer](https://github.com/ollama/ollama/blob/v0.32.15/model/renderers/gemma4.go#L84) serializes this as an assistant turn followed by a new model turn. This is a source-backed explanation to investigate, not proof of a specific host bug. Ollama also has another chat execution route.
- The previous exact natural-dialogue comparison recovered nine claims instead of one when removing only `format`, retaining reasoning, schema text, sampling and input. Both modes returned six claims on the current smaller neutral extraction probe. Thus this is a context-dependent coverage problem, not an invalid array schema or a universal one-item restriction. Neither syntactic validation nor reasoning guarantees semantic completeness.

## Implemented policy

| Step | Reasoning | Output contract |
| --- | --- | --- |
| Contradiction/supersession review | On | Schema in prompt, Pydantic validation |
| Cumulative fact synthesis | On | Schema in prompt, Pydantic validation |
| Extraction, identity, routing, other structured steps | Off | Native JSON Schema format, Pydantic validation |
| QA and tool-using assistant | On | Existing chat/tool contract |

`mycelium.toml` reserves 32,768 generation tokens within a 65,536-token context and uses a 900-second request timeout. Generation includes thinking and final output. The allowance is a ceiling, not a requirement to consume those tokens. Input, schemas, tool evidence, output reserve and safety margin are checked together. API and benchmark retrieval budgets account for the larger output reserve.

`reasoning_format="prompt"` requests a single uninterrupted generation, without native `format`, for selected reasoning steps. `reasoning_format="native"` is an explicit alternative for comparison or a future server fix; there is no automatic mode switch after failure. Prompt mode requires a Pydantic response model. The existing bounded correction loop receives the schema, prior final answer and validation error, without replaying private reasoning. Exhausting the token allowance is rejected even if the response happens to parse; it is not retried unchanged three times. `reasoning_enabled=false` disables reasoning globally.

Extraction remains non-reasoning because the natural-dialogue reasoning results do not yet justify enabling it. No keyword rule, minimum expected claim count, benchmark vocabulary, or post-hoc semantic override was added.

## Direct model validation before integration

Reproducible harness: `benchmarks/reasoning_contract_probes.py`. Requests and responses: `benchmark_runs/reasoning-policy-20260909/probes/`. Neutral probes use the production decision prompts and generated schemas, recommended sampling, seed 17, 64K context and 32K output.

- Six-record native array control: six entries with thinking off and on (10.6s / 6.0s).
- Six-assertion extraction with reasoning: six claims both with native format (43s) and without it (80.2s). Both still used the semantically questionable permissive `about.role="user"`; this experiment does not establish perfect extraction correctness.
- Truth review: repainting the same bicycle correctly superseded its old color; buying a second differently colored bicycle correctly left the original fact intact. The first change response had incorrect scope nesting and passed after one model correction.
- Synthesis: kept two differently dated workshops separate, retained the relevant time/attendance details and preserved uncertainty about a sailing course. First response passed production validation.

The initial probe parser rejected Markdown fences that the production parser already handles. Raw responses were preserved and revalidated with the actual production parser in separate `*-validation.json` files. Only the genuine truth-review nesting failure required another inference. This avoids reporting a harness-only parsing failure as a production failure.

## Integrated validation

Fresh LoCoMo run: `benchmark_runs/reasoning-policy-20260909-locomo/`, sample index 1 (`conv-26`), first session, two QA questions, per-batch build. Completed in 346.2 seconds. Thirteen claims became eight facts across two correctly owned person pages. The main support-group, education/career, painting, work/children and swimming details survived. Synthesis merged related assertions without losing the support-group date or painting motivations. The wiki remains compact and separates current context, plans, interests and timeline.

Limitations: Caroline's immediately intended research and general relaxation comment were not extracted. Melanie's painting remains dated only as “last year”; QA repeated that phrase rather than resolving it against May 2023 to 2022. The date question for Caroline passed and the painting date question failed (1/2). The benchmark cites D1:12 for the painting question while the explicit painting assertion is D1:14, so its 0.5 evidence-survival score should not be read as proof that the painting fact disappeared. Manual source/artifact inspection confirms that it survived. This small run is neither a broad QA evaluation nor a paired measurement of improvement.

Memory trace: 11 attempts including retrieval selection; one correction each for extraction, synthesis and retrieval selection. All recovered. Synthesis used reasoning/prompt mode (70.1s for one page; 75.3s plus 47.8s correction for the other), 32K output and 64K context. Other memory calls had thinking off/native format. Both QA calls used thinking on with the configured reserve. No token-limit stops. The small one-session run did not require a truth review; direct changed/distinct probes cover that decision contract. A mistakenly named debug-render diagnostic request was made during this run and timed out; timings are not a controlled performance comparison.

The earlier all-on/all-off experiment remains documented separately in `planning/reasoning_comparison_2026_09_09.md`; it is not a measurement of this selective policy.


Cumulative validation completed before the next audit: `benchmark_runs/reasoning-policy-20260909/cumulative/test_cumulative_memory_keeps_i0/`. The real-model three-build/restart/retrieval test passed in 730.78 seconds. All 18 claims are represented by 12 facts; independent details and uncertain plans survive, and bicycle retrieval passed the semantic check. There were 29 calls, including one recovered singleton-text contract failure. Seven truth calls consumed 266.1s and six synthesis attempts 369.4s; maximum native generation count 7,466 and no length stops. Organization remains imperfect: recurring volunteering is under Priorities & Plans. The test uses fixed September 4 segment timestamps, so the September 3 raincoat date is correctly anchored.
