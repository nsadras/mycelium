"""Opt-in reference-based answer judgments, separate from retrieval coverage."""

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mycelium.config import LLMConfig
from mycelium.ollama import OllamaClient
from mycelium.prompting import render_prompt


class ReferenceJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["correct", "partial", "incorrect", "ungradable"]
    reason: str = Field(min_length=1, max_length=800)


class SemanticScorer:
    def __init__(self, config: LLMConfig, trace_path: Path):
        config = replace(config)
        self.system = render_prompt("benchmarks/reference_judgment.system.jinja")
        self.specification = {
            "version": "reference-semantic-v1",
            "config": asdict(config),
            "system_prompt": self.system,
            "schema": ReferenceJudgment.model_json_schema(),
        }
        self.specification["digest"] = hashlib.sha256(
            json.dumps(self.specification, sort_keys=True).encode()
        ).hexdigest()
        self.llm = OllamaClient(
            url=config.url, model=config.model, temperature=config.temperature,
            timeout=config.timeout_seconds, context_window_tokens=config.context_window_tokens,
            top_p=config.top_p, top_k=config.top_k, reasoning_enabled=config.reasoning_enabled,
            reasoning_output_tokens=config.reasoning_output_tokens, reasoning_format=config.reasoning_format,
            trace_path=trace_path,
        )

    async def judge(self, *, question: str, reference, prediction: str, answerable: bool) -> dict:
        response = await self.llm.call_structured(
            self.system,
            json.dumps({"question": question, "reference_answer": reference,
                        "predicted_answer": prediction, "answerable": answerable}, ensure_ascii=False),
            ReferenceJudgment,
            num_predict=512,
            debug_label="benchmark-reference-judgment",
        )
        return ReferenceJudgment.model_validate(response).model_dump()


def summarize_judgments(rows: list[dict], *, enabled: bool) -> dict:
    if not enabled:
        return {"status": "disabled"}
    counts = {verdict: 0 for verdict in ("correct", "partial", "incorrect", "ungradable")}
    errors, pending = 0, 0
    for row in rows:
        judgment = row.get("semantic_judgment", {})
        if judgment.get("status") == "complete":
            counts[ReferenceJudgment.model_validate(judgment["judgment"]).verdict] += 1
        elif judgment.get("status") == "failed":
            errors += 1
        else:
            pending += 1
    graded = counts["correct"] + counts["partial"] + counts["incorrect"]
    return {
        "status": "not_run" if not rows else "incomplete" if errors or pending else "complete",
        "question_count": len(rows), "graded_questions": graded,
        "failed_questions": errors, "pending_questions": pending,
        "verdict_counts": counts,
        "grading_coverage": graded / len(rows) if rows else None,
        "strict_accuracy": counts["correct"] / graded if graded else None,
    }
