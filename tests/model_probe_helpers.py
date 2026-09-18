"""Capture and semantic judging shared by opt-in model tests."""

import json

from pydantic import BaseModel, ConfigDict

from mycelium import SourceInput
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
