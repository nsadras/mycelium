"""One semantic admission pass over shared, budgeted memory evidence."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from mycelium import prompts
from mycelium.budget import ContextBudgetError, require_request_budget
from mycelium.ollama import OllamaClient
from mycelium.memory_inputs import compact_selection_evidence
from mycelium.operations import MemoryEvidence
from mycelium.evidence_budget import fit_memory_evidence
from mycelium.structured_outputs import complementary_selection_model
from mycelium.telemetry import trace_operation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssistantContextSelection:
    selected_ids: tuple[str, ...]
    decisions: dict[str, dict]
    error: str | None = None
    supported_aspects: tuple[str, ...] = ()
    remaining_gaps: tuple[str, ...] = ()


class AssistantContextSelector:
    """Select complete records using deduplicated views and exact cited sources."""

    def __init__(self, llm: OllamaClient) -> None:
        self.llm = llm

    async def select_with_trace(
        self, query: str, evidence: MemoryEvidence, *, limit: int = 5
    ) -> AssistantContextSelection:
        candidate_ids = [record.record_id for record in evidence.records]
        if not candidate_ids:
            return AssistantContextSelection((), {})
        aliases = {
            f"M{index:03d}": cid for index, cid in enumerate(candidate_ids, start=1)
        }
        schema = complementary_selection_model(aliases, limit)

        def selection_prompt(candidate_evidence: MemoryEvidence) -> tuple[str, str]:
            return prompts.assistant_context_selection_prompt(
                query,
                compact_selection_evidence(candidate_evidence, aliases)[0],
                limit=limit,
            )

        def selection_fits_budget(candidate_evidence: MemoryEvidence) -> bool:
            system, user = selection_prompt(candidate_evidence)
            try:
                require_request_budget(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    context_window=self.llm.context_window_tokens,
                    output_tokens=1024,
                    schema=schema.model_json_schema(),
                )
                return True
            except ContextBudgetError:
                return False

        try:
            fitted = fit_memory_evidence(evidence, selection_fits_budget)
            available = {r.record_id for r in fitted.records}
            aliases = {alias: cid for alias, cid in aliases.items() if cid in available}
            if not aliases:
                return AssistantContextSelection(
                    (), {}, "No complete candidate fits the request budget"
                )
            schema = complementary_selection_model(aliases, limit)
            system, user = selection_prompt(fitted)
            with trace_operation(
                "selection", request_ids=compact_selection_evidence(fitted, aliases)[1]
            ):
                response = await self.llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=1024,
                    debug_label="assistant-context-selection",
                )
            decision = schema.model_validate(response).model_dump()
        except Exception as exc:
            logger.warning(
                "Assistant context selection failed: %s: %s", type(exc).__name__, exc
            )
            return AssistantContextSelection((), {}, f"{type(exc).__name__}: {exc}")
        selected = tuple(aliases[alias] for alias in decision["selected_ids"])
        return AssistantContextSelection(
            selected,
            {
                cid: {"disposition": "include" if cid in selected else "exclude"}
                for cid in candidate_ids
            },
            supported_aspects=tuple(decision["supported_aspects"]),
            remaining_gaps=tuple(decision["remaining_gaps"]),
        )
