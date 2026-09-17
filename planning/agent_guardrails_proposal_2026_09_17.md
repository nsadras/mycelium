# Proposed agent and audit guidance

**Proposal only.** These edits have not been applied to `AGENTS.md` or
`AGENT_PROMPTS/AUDIT.md`. They preserve the existing semantic decision guardrails,
host-model requirements and permission rules. The audit prompt's current local
edits are left intact.

## AGENTS.md: add after Agent Guidance

### Product objective and acceptable imperfection

- Mycelium creates a coherent, useful view of memory for humans and agents, at
  practical cost on a local machine. Optimize the whole experience: capture,
  Build, readable memory, retrieval, and correction.
- Exhaustive extraction, perfect identity resolution, and uniquely correct page
  organization are not requirements. Reasonable omissions and interpretation
  mistakes are expected. Judge their practical impact and recurrence in the
  resulting memory; do not make every semantic miss a release blocker.
- Distinguish mechanical guarantees from model quality. Preserve durable sources,
  valid references, user decisions, and recoverable publication. Test these
  guarantees directly. Assess semantic quality through representative artifacts
  and tasks, not a requirement for every example to pass.
- Prefer source-derived organization and a small number of model passes. Every
  additional call, semantic stage, schema field, taxonomy, or retry mechanism
  needs a concrete product benefit that justifies its computation and maintenance.
  First consider removing or combining existing work. A missed benchmark answer
  alone is not sufficient justification.
- Benchmarks are diagnostic guideposts. Expected page counts, headings, fact
  coverage, aliases, or exact answers do not define product behavior. Keep
  benchmark-specific accommodations out of production, including prompts.

### Bounded progress and evaluation

- Before an experiment, state the product question, a small representative sample,
  computation/time budget, and the decision it will inform. Use the same frozen
  inputs for a comparison. Evaluate the whole result after the fixed sample;
  do not repeatedly tune one example or silently enlarge the budget.
- Use a representative end-to-end check to expose tradeoffs between stages.
  Perfecting one stage is not a prerequisite for trying the next. Record lesser
  limitations and continue when artifacts are broadly useful and the mechanical
  guarantees hold. Investigate recurring failures that make memory misleading
  or unusable before chasing isolated omissions.
- Measure total calls, input/output tokens, elapsed time, and retries together.
  Use established memory systems as contextual cost references, accounting for
  their different features. Neither a universal call cap nor a benchmark score
  substitutes for useful artifacts at a reasonable local cost.
- A full benchmark, repeated trial, new evaluation harness, or more detailed
  scoring must answer an unresolved product decision. Reuse existing diagnostics
  when they suffice. Stop collecting evidence once it is adequate for that
  decision, within the existing process-control permissions.
- Prefer a short explanation of a tradeoff over a new approval checklist. When a
  bounded experiment is inconclusive, record that limit and move to another
  useful task or identify the smallest missing check; do not expand indefinitely.

## AGENTS.md: replace LLM semantic development workflow

The existing requirement to use the configured model before integration remains.
Replace language that can be read as demanding proof of perfect semantics with:

### LLM semantic development workflow

- Before integrating changes to prompts, ontologies, or divisions of model labor,
  run a bounded direct experiment with the configured host Ollama model. Use the
  proposed real prompt and schema, small neutral examples, and a relevant
  counterexample. Freeze the inputs and budget before inspecting results.
- Inspect whether outputs have a usable structure and broadly useful meaning.
  Mocked tests do not establish model behavior. Isolated semantic errors are
  recorded tradeoffs, not automatic reasons for another stage, field, or prompt
  variant. An unusable contract or broadly incoherent output needs redesign.
- Integrate the smallest promising mechanism in situ and check the end-to-end
  artifacts and cost. Add focused tests for mechanical invariants. Production
  adoption requires evidence of practical usefulness, not perfect benchmark
  performance; remove displaced mechanisms when adopting a replacement.
- Keep benchmark names, expected answers and fixture-specific vocabulary out of
  production prompts and code. Preserve evidence for inspection; do not repair
  semantic misses using lexical rules or post-hoc overrides.
- Record the question, budget, direct observations, meaningful failures, in-situ
  run paths, cost, validation and adoption decision in `DEVLOG.md`. State any
  unmatched features or incomplete comparisons without treating uncertainty as
  a reason for unlimited testing.

## AGENT_PROMPTS/AUDIT.md: prepend this framing

Audit against the product objective: **a largely coherent, useful view of memory
for humans and agents, produced at practical local cost**. Thoroughness means
examining the whole system and supporting important conclusions; it does not
mean exhaustive conversation annotation or treating every model error as a bug
that must be fixed before progress can continue.

Distinguish data loss, broken references, ignored user decisions and unrecoverable
state from ordinary model omissions, identity mistakes and editorial choices.
For semantic issues, assess recurrence and practical effect on understanding and
using memory. Prefer simplification, deletion and explicit deferral when another
layer of inference would cost more than the improvement warrants.

Retain the seven existing audit areas, with the following changes.

## AGENT_PROMPTS/AUDIT.md: replace the LLM Calls bullet

- **LLM calls and complexity:** Map a representative source-to-memory-to-answer
  path. Count actual generation attempts, retries, input/output tokens and time;
  identify repeated semantic work and broad or deeply nested output contracts.
  For each costly stage or top-down classification, ask what user-visible benefit
  it provides and whether it can be combined, simplified or removed. Compare
  ordinary call paths in Mem0, Graphiti, Hindsight or similar systems using
  current primary sources. Distinguish API operations from model calls and
  static estimates from measured performance; account for feature differences.

## AGENT_PROMPTS/AUDIT.md: replace the Benchmark review bullet

- **Benchmark and artifact review:** Inspect the latest run's status,
  configuration, total cost, retries and failures. Review a bounded,
  representative sample of source conversations and successive memory views
  for coherence, useful retained context, supported interpretation, concision
  and navigability. Include ordinary successes as well as failures. Report
  consequential gaps without demanding exhaustive coverage or exact editorial
  matches. Compare relevant prior runs under comparable settings; separate
  encoding, retrieval and answering problems. State sampling limits, incomplete
  runs and unmatched features. Do not launch more runs or deepen annotation
  unless that work could change a concrete recommendation.

## AGENT_PROMPTS/AUDIT.md: replace the closing instruction

Summarize overall product usefulness and cost before individual defects. Rank
issues by practical impact, recurrence, confidence and the cost of fixing them,
not simply by benchmark failure count. Identify no more than three immediate
priorities, and explicitly list what to simplify/remove and what to defer or
accept. For each priority, give evidence, the smallest useful fix, a bounded
validation check, and a stopping criterion. Separate required mechanical checks
from qualitative acceptance. Do not turn every audit observation into an
implementation requirement or introduce another inference layer by default.
