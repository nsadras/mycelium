# Agent Guidance

- Prefer fixing the intended mechanism over adding fallback paths. 
- When changing existing features, do not add backwards compatibility unless explicitly asked.
- When performing test driven development, prefer solutions that are generalizable and serve the end goal of the project, instead of overfitting to the test.
- Check with the user if goals are not clear - ensure that you are aligned with the user's goals and vision before implementing anything.
- Do not run or kill server processes / scripts yourself unless explicitly asked. The user will run these in another shell to view output for debugging.
- Do not commit anything to git unless explicitly asked to

## Semantic decision guardrails

- Do not use hard-coded natural-language strings, keyword lists, regular expressions, token overlap, fuzzy
  matching, or benchmark-derived vocabulary to make semantic decisions. This includes entity discovery,
  identity resolution, claim ownership, page admission, consolidation, contradiction handling, and decisions
  to override `deferred` or `source_only`.
- Exact IDs and declared schema values may be validated deterministically. Human-language meaning must come
  from a structured model decision or explicit user review, with the cited evidence preserved for inspection.
- Benchmarks and fixtures are evaluation inputs, not product specifications. Keep fixture names, phrases,
  aliases, and expected artifacts out of production code and production prompts.
- If a model misses an expected entity or assignment, improve the structured representation, contract, or
  review workflow. Do not reconstruct the expected output with lexical fallbacks or post-hoc overrides.
- Before adding a deterministic semantic rule, state the product-level invariant it implements. If the rule
  cannot be justified without referring to a benchmark example, stop and ask the user.

## Host Ollama access

- The host Ollama server at `http://localhost:11434` may be unreachable from the filesystem/network sandbox even when it is running normally.
- Do not conclude that Ollama is down from a sandboxed connection failure. Verify it with a read-only `/api/tags` request using sandbox/network escalation.
- Run Ollama-dependent tests and benchmarks with the same escalation so they can reach the host loopback interface. Do not start another Ollama process, change the configured URL, or use a fallback model to work around sandbox isolation.

## LLM semantic development workflow

- For changes to prompts, ontologies, or divisions of model labor, prove the proposed decision contract with
  direct calls to the configured host Ollama model before integrating it into the production pipeline.
- Direct probes should use the real production prompt and structured-output schema whenever possible. Start with
  small, neutral examples that isolate the decision, then include a relevant counterexample. Keep benchmark names,
  expected answers, and fixture-specific vocabulary out of prompts and production code.
- Integrate the smallest proven mechanism in situ only after the direct output has the intended meaning and shape.
  Add focused contract and pipeline tests for structural invariants; mocked tests do not establish model behavior.
- Record direct-probe findings, in-situ run paths, meaningful failures, and validation results in `DEVLOG.md`.
