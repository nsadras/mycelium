"""Capture and semantic judging shared by opt-in model tests."""

import json

from pydantic import BaseModel, ConfigDict

from mycelium import SourceInput
from mycelium.fact_groups import (
    FactText, fact_groups_model, fact_groups_prompt, fact_text_prompt,
)


async def grouped_statements(memory, owner, canonical, sections, path):
    """Exercise current grouping/rendering contracts without mandating a layout."""
    system, user = fact_groups_prompt(owner, json.dumps(canonical), sections)
    schema = fact_groups_model(canonical, ["profile", "history"])
    result = schema.model_validate(await memory.llm.call_structured(
        system, user, schema, num_predict=4096, debug_label="grouping-probe",
    )).model_dump()
    path.write_text(json.dumps(result, indent=2))
    statements = []
    for group in result["groups"]:
        members = [canonical[alias] for alias in group["member_claim_aliases"]]
        if len(members) == 1:
            statements.append(members[0]["text"])
        else:
            system, user = fact_text_prompt(owner, json.dumps(members))
            response = FactText.model_validate(await memory.llm.call_structured(
                system, user, FactText, num_predict=1024, debug_label="fact-text-probe",
            ))
            statements.append(response.text)
    path.with_name("statements.json").write_text(json.dumps(statements, indent=2))
    return statements


class MeaningVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_supported: bool
    forbidden_asserted: bool
    reason: str


async def check_meaning(memory, case, statements, path):
    # A model judge handles paraphrases; exact source IDs and batch accounting
    # are checked separately. This judge is evaluation-only, not product logic.
    verdict = await memory.llm.call_structured(
        "Evaluate whether the supplied stored assertions entail the expected assertion and "
        "whether they assert the forbidden assertion. Mere mention or explicit negation is "
        "not assertion. Do not infer agreement from a proposal, consideration, or refusal. "
        "Use strict entailment, not topic similarity. Preserve the expected assertion's commitment level: "
        "an unqualified 'plans to' or 'will' does not preserve 'is considering' or 'might'. "
        "Tentativeness and conditions must be stated, not inferred from absent evidence of a decision. "
        "Return schema-valid JSON and explain the evidence.",
        json.dumps({"statements": statements, "expected": case["expected"], "forbidden": case["forbidden"]}),
        MeaningVerdict, num_predict=2048,
    )
    path.write_text(json.dumps(verdict, indent=2))
    assert verdict["expected_supported"], verdict
    assert not verdict["forbidden_asserted"], verdict


async def capture(memory, messages, key, context_ids=()):
    return await memory.ingest_source(SourceInput(
        transcript="\n".join(f"{m['role']}: {m['content']}" for m in messages),
        session_id="conversation", idempotency_key=key,
        segments=tuple({**m, "segment_id": "", "index": i, "speaker": m["role"],
                        "timestamp": "2026-09-04T12:00:00+00:00"} for i, m in enumerate(messages)),
        metadata={"context_source_ids": list(context_ids)},
    ))
