"""One semantic admission pass over shared, budgeted memory evidence."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass

from mycelium import prompts
from mycelium.budget import ContextBudgetError, require_request_budget
from mycelium.ollama import OllamaClient
from mycelium.memory_inputs import RequestIds
from mycelium.operations import MemoryEvidence
from mycelium.retrieval_context import fit_memory_evidence
from mycelium.structured_outputs import complementary_selection_model
from mycelium.telemetry import trace_operation

logger = logging.getLogger(__name__)


def compact_evidence(evidence, aliases):
    """Share evidence once and shorten references without rewriting human text."""
    ids = RequestIds()
    ids.forward = {canonical: alias for alias, canonical in aliases.items()}
    ids.reverse = dict(aliases)
    single = {"record_id", "claim_id", "source_id", "segment_id", "entity_id",
              "subject_entity_id", "proposal_id", "evidence_segment_id", "anchor_segment_id"}
    multiple = {"claim_ids", "segment_ids", "incoming_claim_ids", "target_claim_ids"}
    direct = {r.record_id for r in evidence.records if r.record_type == "claim"}

    def encode(value):
        if isinstance(value, (list, tuple)):
            return [encode(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if item is None or item == [] or item == () or key == "revision":
                continue
            if key in single:
                result[key] = ids.reference(item)
            elif key in multiple:
                result[key] = [ids.reference(identifier) for identifier in item]
            elif key == "canonical_claims":
                # The full assertion is already present in its selectable record.
                remaining = [c for c in item if c["claim_id"] not in direct]
                if remaining:
                    result[key] = encode(remaining)
            else:
                result[key] = encode(item)
        return result

    return json.dumps(encode(asdict(evidence)), ensure_ascii=False, separators=(",", ":")), ids.reverse


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
        candidates = [r.record_id for r in evidence.records]
        if not candidates:
            return AssistantContextSelection((), {})
        aliases = {f"M{index:03d}": cid for index, cid in enumerate(candidates, start=1)}
        schema = complementary_selection_model(aliases, limit)

        def prompt(trial):
            return prompts.assistant_context_selection_prompt(
                query, compact_evidence(trial, aliases)[0], limit=limit
            )

        def fits(trial):
            system, user = prompt(trial)
            try:
                require_request_budget(
                    [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    context_window=self.llm.context_window_tokens, output_tokens=1024,
                    schema=schema.model_json_schema(),
                )
                return True
            except ContextBudgetError:
                return False

        try:
            fitted = fit_memory_evidence(evidence, fits)
            available = {r.record_id for r in fitted.records}
            aliases = {alias: cid for alias, cid in aliases.items() if cid in available}
            if not aliases:
                return AssistantContextSelection((), {}, "No complete candidate fits the request budget")
            schema = complementary_selection_model(aliases, limit)
            system, user = prompt(fitted)
            with trace_operation("selection", request_ids=compact_evidence(fitted, aliases)[1]):
                response = await self.llm.call_structured(
                    system, user, schema, num_predict=1024, debug_label="assistant-context-selection"
                )
            decision = schema.model_validate(response).model_dump()
        except Exception as exc:
            logger.warning("Assistant context selection failed: %s: %s", type(exc).__name__, exc)
            return AssistantContextSelection((), {}, f"{type(exc).__name__}: {exc}")
        selected = tuple(aliases[alias] for alias in decision["selected_ids"])
        return AssistantContextSelection(
            selected,
            {cid: {"disposition": "include" if cid in selected else "exclude"} for cid in candidates},
            supported_aspects=tuple(decision["supported_aspects"]),
            remaining_gaps=tuple(decision["remaining_gaps"]),
        )
