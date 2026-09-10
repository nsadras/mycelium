# Prompt/schema audit and Gemma–Qwen comparison — 2026-09-09

## Prompt and output-contract audit

The project uses valid Ollama/Pydantic structured-output syntax. It is not yet consistently minimal. The main issues are repeated instructions, redundant output bookkeeping and permissive fields alongside elaborate branch schemas. There is no universal evidence-backed maximum of three nesting levels or a fixed safe field count; the useful test is whether each field serves a decision, preserves evidence or enforces an invariant.

[Ollama's documentation](https://docs.ollama.com/capabilities/structured-outputs) recommends a JSON Schema dictionary, a matching validation model and schema grounding in the prompt. Its list example uses the same `list[Model]` syntax we use. The current reasoning mode includes the schema in the prompt and validates afterward; non-reasoning steps retain native format. Schema conformance does not establish semantic coverage or correctness.

Measured representative contracts (`benchmark_runs/model-contract-comparison-20260909/schema-audit.json`):

| Contract | Field/shape burden | Schema characters | Maximum output container depth |
| --- | --- | ---: | ---: |
| Extraction, 48 new / 8 context IDs | 14 claim fields, nested entity objects, open facets dictionary | 4,072 | 5 |
| Truth, one incoming / six targets | 4 comparison fields per target, then 4 or 10 decision fields | 3,387 | 5 |
| Synthesis, 24 claims | Two seven-field branches | 2,420 | 4 |
| Identity, small registry | Eleven fields repeated across five variants | 9,162 | 4 |
| Routing, 24 claims | Five claim fields plus four fields per destination | 2,846 | 5 |
| Retrieval selection, 24 records | Three fields per record | 2,640 | 3 |

Depth counts object/array containers in the emitted value after resolving schema references, not nesting of JSON Schema keywords. Identity size grows with the registry's distinct entity types. These are representative sizes, not maximums.

Prioritized changes to prove before integration:

1. **Flatten the single-decision truth contract.** `FactResolver` already calls once per incoming claim, but still requests `decisions → incoming ID → scope → target ID → comparison`. The outer decision mapping and echoed incoming ID are application-known. A direct decision object can remove two containers while retaining exact target IDs, scope comparisons and the same-scope guard. Also test a `comparisons` array with an explicit `target_id` field instead of dynamic target-ID property nesting; validate exact target coverage in code. Preserve one evidence-backed explanation; assess overlap between per-target reason, transition evidence and final explanation. Earlier direct testing and this fresh Gemma comparison actually misplaced the target wrapper, so this is grounded in a repeated real failure.
2. **Simplify extraction's obligations and make temporal data explicit.** Put the extraction objective first; it currently follows multiple paragraphs of corrective edge-case instructions. Consolidate repeated acceptance/refusal, context-citation and assertion-strength guidance into one ordered contract. Keep readable text, evidence IDs, explicit identity roles and temporal scope. `facets` is an untyped dictionary even though downstream temporal handling expects particular keys; missing `when` contributed to the observed unresolved painting date. `about.role` accepts any string despite a declared subject/owner/participant vocabulary. Tightening these two areas is more useful than just shrinking the schema. `slot` is stored/copied but no active truth-resolution consumer was found; it is a candidate for removal from model output. Do not infer missing semantic fields with lexical defaults.
3. **Reduce identity schema duplication and fixed output values.** Existing identity/type mappings, empty candidate lists and the explicitly bound You fields are often known to the application. Have the model decide referent/evidence/resolution, while the application attaches values implied by explicit IDs. Preserve unresolved referents, candidate identities, supporting evidence and participant bindings. Do not replace these semantic judgments with name matching.
4. **Consolidate routing explanations.** `subject_evidence`, destination `reason`, claim `reason` and a confidence score impose repeated generation. One concise evidence-backed explanation per relevant destination plus an explanation for deferral is a clearer contract. Keep complete endpoint coverage and explicit owner/section selection.
5. **Retain synthesis scope; test a smaller surrounding contract.** Seven fields alone are not excessive. `memory_scope` makes distinct-event grouping inspectable and should stay. Confidence is uncalibrated metadata rather than a demonstrated quality estimate, and reason often repeats scope/text. Singleton null versus combined text is a real preservation invariant, but the two nearly identical branches duplicate schema and produce verbose union validation errors. Test a common object plus the existing structural validator before replacing the native union. The last cumulative run needed one correction because singleton entries supplied text.

Positive features: tasks are separated into extraction, identity, routing, truth and synthesis; source context is labeled; exact citations and aliases are validated; prose distinguishes uncertainty from completed action; prompts contain no few-shot fixture answers; correction attempts are bounded. Candidate selection, retrieval selection, QA and meeting-summary prompts are comparatively concise. Negative instructions are most concentrated in extraction and identity; their requirements should be expressed once as positive decision rules, not simply deleted.

The audit changes no production prompts or schemas. Simplifications above require neutral direct probes and counterexamples before integration under AGENTS.md.

## Comparison design

Harness: `benchmarks/model_contract_comparison.py`. Artifacts: `benchmark_runs/model-contract-comparison-20260909/`.

Installed models: Gemma `gemma4:12b`, 11.9B reported parameters, Q4_K_M, digest `4eb23ef187e2c5462566d6a1d3bbbc2f1346d0b4327cbb66d58fffbcc9b2b05c`; Qwen `qwen3.5:9b`, 9.7B reported parameters, Q4_K_M, digest `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`. Host Ollama 0.32.15, Python SDK 0.6.2. Requests run serially, with a separate warmup before each model. No model was downloaded and no server was started/stopped.

Both use identical production prompts/contracts, seed 17, 64K context, 32K reasoning generation allowance, 8K direct non-reasoning extraction allowance, and the same selective reasoning policy. Four isolated cases cover six-claim extraction, same-object truth change, distinct-object non-change, and two separate events plus uncertain intent. Three fresh memory builds cover enrichment, repeated preferences, tentative plans and retrieval after restarts.

Each model uses its publisher's general-task sampling recommendations. [Gemma's model card](https://huggingface.co/google/gemma-4-12B-it#best-practices): temperature 1, top-p .95, top-k 64. [Qwen's model card](https://huggingface.co/Qwen/Qwen3.5-9B#best-practices): thinking temperature 1/top-p .95; non-thinking .7/.8; top-k 20, min-p 0, presence penalty 1.5 and repetition penalty 1. Qwen options are applied only in the comparison transport; the production model/config stays unchanged. This compares recommended operating configurations, not an isolated architecture-only effect. The card recommends 32K output for ordinary queries; both receive that reasoning allowance.

Raw request/response records retain elapsed time, loading time, prompt/decode counters, output and thinking. Report task latency and actual semantic outcomes; token throughput alone cannot compare useful output because tokenizers and reasoning verbosity differ. One seed and this small corpus cannot establish general model superiority.

## Results

| Isolated production contract | Gemma seconds | Qwen seconds | Manual quality review |
| --- | ---: | ---: | --- |
| Six-claim extraction, reasoning off/native format | 9.5 | 6.7 | Both retained six supported statements and citations. Qwen's metadata was weaker: studying geology became a preference; every about.role was person. Gemma omitted role, and both omitted structured April timing. |
| Same-object color change, reasoning on/prompt schema | 32.1 | 39.7 | Both correctly chose supersession for the same bicycle. Gemma needed one nested target-ID correction; Qwen passed first attempt. |
| Second distinct bicycle, reasoning on/prompt schema | 25.6 | 39.1 | Both preserved the original bicycle and correctly identified distinct scope. |
| Separate events and uncertain intention, reasoning on/prompt schema | 19.6 | 35.3 | Both produced three correct groups, preserving dates, 9 a.m., twelve participants, and undecided sailing interest. |

Qwen decoded at approximately 115–117 native tokens/s on the reasoning probes versus Gemma's 82–83. However, Qwen generated 4,090–4,603 tokens per reasoning probe versus 1,533–2,546 for Gemma (the upper Gemma number includes its correction). Faster decoding did not produce faster decisions on these examples. All direct outcomes eventually validated; Gemma used five attempts for four tasks, Qwen four. None exhausted its allowance. Qwen was resident fully in VRAM at a reported 8.04 GB/64K context (`host-ps-qwen-start.json`).

The isolated extraction case retains its catalog name `extraction-native-False` in the artifact paths for traceability; the recorded actual request is **think=false, native format**, matching production extraction. The name is inherited from the earlier catalog's variant naming and is not the actual setting in this comparison.

| Three-build cumulative workload, including final retrieval | Gemma | Qwen |
| --- | ---: | ---: |
| Elapsed | 270.7s | 275.2s |
| Stored claims / final facts | 9 / 5 | 9 / 5 |
| Unique represented claim IDs | 9 | 9 |
| Model attempts | 20 | 20 |
| Failed format attempts, recovered | 1 | 2 |
| Token-limit stops | 0 | 0 |

Manual wiki review found equivalent useful coverage: ten-year librarian tenure, blue bicycle with wicker basket, watercolor landscape preference, written directions and an explicitly undecided pottery interest. Repeated painting evidence merged into one fact. Both returned the bicycle fact plus both canonical claims after restart. Gemma's prose was slightly shorter; neither introduced unsupported commitments or lost substantive details in this corpus. A roughly 1.7% runtime difference is not a meaningful speed win from a single run.

Gemma's correction concerned singleton text. Qwen's two corrections were in one truth call: it first echoed the JSON Schema instead of producing an instance, then omitted scope. This adds a concrete prompt improvement to test: put the schema in a clearly labeled contract block and finish with a positive instruction to produce the populated decision for the supplied evidence. Currently the raw schema is the last material in the message. More fields or more repeated prohibitions are not the right response to that failure.

The cumulative arms use the same source statements and segment timestamps. Generated facts, aliases, decisions and subsequent context naturally differ by model; ingestion occurrence timestamps are recorded at each run's wall clock. The corpus has no relative event-date assertion, so the minute-scale clock difference does not change its intended answers. These are practical pipeline comparisons, not byte-identical later requests.

Across cumulative calls Qwen generated 30,346 native tokens versus Gemma's 20,488. Weighted decoding rates were 114.9 versus 81.8 tokens/s. Qwen's roughly 40% decoding advantage was offset by roughly 48% more generated tokens. The model's smaller parameter count does not by itself establish a latency win for this pipeline.

### Natural-dialogue check

Ran `PYTHONPATH=. .venv/bin/python benchmarks/model_contract_comparison.py --natural-only` after both cumulative arms, serially with separate warmups. Uses the same first 48 stored segments from LoCoMo sample `conv-26` session 1, the production segment renderer, source policy and extraction schema. This is a direct extraction check, not another full wiki build or QA score. Inputs and contracts are identical between models; sampling follows each publisher as above.

| Natural extraction | Gemma | Qwen |
| --- | ---: | ---: |
| Elapsed, including correction | 82.8s | 84.4s |
| Claims | 11 | 21 |
| Attempts | 2 | 2 |

Manual source review favors Gemma on correctness and concision in this sample:

- Both retained the support-group visit, career exploration, painting date and painting motivations. Both left structured temporal facets empty. Neither result resolves the earlier temporal-data weakness.
- Gemma retained Melanie being swamped with children and work; Qwen put that segment in source-only. Qwen retained Caroline's immediate research plan and more comments/image-caption details, which Gemma omitted. Higher claim count is therefore neither uniform higher coverage nor automatically worse output.
- Qwen changed the source's present effect, “given me courage to embrace myself,” into a future intention to embrace herself. It also strengthened wanting to help people into intending to do so. These are assertion-strength errors under the existing contract.
- Qwen cited segment 37 for the painting being special, but that assertion is in segment 38. Its relaxation-agreement claim cites only the brief agreement, without the statement being agreed with. Gemma also extends its segment-43 painting claim to relaxation without citing segment 44 there (it does preserve segment 44 in a separate claim). The validator checks ID validity/accounting, not whether a valid citation actually entails every clause.
- Qwen created several generic “photo exists” / “associated with person” claims, and lost speaker attribution in some evaluative statements. Gemma's readable claims were better attributed, although its two relaxation claims overlap. Qwen marked primary personal subjects as participant in this batch; the neutral probe had used the undeclared person role. The schema currently admits both semantic mistakes.
- Both needed accounting corrections. Qwen's first response omitted the two image-URL segments from the accounting partition; correction recovered them. No length stops or transport failures occurred.

### Recommendation

Keep Gemma as the current production default. Qwen is competitive on the small neutral cumulative workload and faster per generated token, but provided no useful end-to-end speed advantage here and made more substantive errors on the dialogue batch. This is evidence about these contracts and this host, not a general ranking of the models.

First prove the smaller truth shape and clearer schema/instance boundary; then simplify extraction's repeated instructions and tighten temporal/identity-role decisions. Recompare the models afterward with more dialogue samples and seeds. A Qwen production trial would also need explicit configuration for its sampling/presence-penalty settings; this benchmark's transport supplies those without changing application defaults. No production model switch or prompt/schema rewrite was made during this audit.
