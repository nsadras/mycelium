Do a thorough, critical audit of the Mycelium codebase. Structure your findings around these seven areas:

- Architecture review — does implementation match intended design; any inconsistencies or coupling issues between components.
- Core algorithm critique — scrutinize the soundness, utility of the core encoding and retrieval pipelines. compare to existing cutting-edge projects that serve similar purposes (e.g. mem0), ensure that we're not re-inventing the wheel.
- LLM Calls - are LLM calls being used appropriately and efficiently? are prompts clear and concise? are structured outputs properly scoped and validated?
- Code quality — dead code, inconsistent patterns, missing error handling, untested paths.
- Data & correctness risks — race conditions, data loss, inconsistent state, silent failures
- Scalability & maintainability — bottlenecks as the memory store grows; long-term maintainability for a solo dev.
- Benchmark review — inspect the latest run's completion status, configuration, metrics, per-call timings, failures/retries, and session snapshots; check evidence and wiki artifacts against source conversations for coverage, correctness, concision, organization, and coherence across successive builds. Compare with relevant prior runs under comparable settings, distinguish encoding quality from retrieval/QA issues, and identify whether recent changes improved quality or justified their compute cost; state any limits of incomplete runs or unmatched comparisons.

Summarize your findings and then rank issues by severity with concrete fixes.
