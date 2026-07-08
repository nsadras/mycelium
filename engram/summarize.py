from __future__ import annotations

from pydantic import BaseModel, Field

from engram.models import MeetingSummary
from mycelium.ollama import OllamaClient


class ActionItemOutput(BaseModel):
    owner: str | None = None
    task: str
    due: str | None = None


class MeetingSummaryOutput(BaseModel):
    summary: str
    decisions: list[str] = Field(default_factory=list, max_length=20)
    action_items: list[ActionItemOutput] = Field(default_factory=list, max_length=30)
    open_questions: list[str] = Field(default_factory=list, max_length=20)


class EngramSummarizer:
    def __init__(
        self,
        *,
        ollama_url: str,
        model: str,
        temperature: float = 0.1,
        timeout: int = 180,
    ) -> None:
        self.llm = OllamaClient(
            url=ollama_url,
            model=model,
            temperature=temperature,
            timeout=timeout,
        )

    async def summarize(self, title: str, transcript: str) -> MeetingSummary:
        if not transcript.strip():
            return MeetingSummary(summary="No speech was transcribed.")

        system = (
            "You summarize meeting transcripts into structured JSON for a local memory system. "
            "Use only the transcript. Do not invent decisions, owners, deadlines, or questions. "
            "Keep action item owners null when the transcript does not identify an owner."
        )
        user = "\n".join(
            [
                f"Meeting title: {title}",
                "",
                "Transcript:",
                transcript.strip(),
            ]
        )
        response = await self.llm.call_structured(system, user, MeetingSummaryOutput, num_predict=4096)
        if isinstance(response, MeetingSummaryOutput):
            output = response
        else:
            output = MeetingSummaryOutput.model_validate(response)
        return MeetingSummary(
            summary=output.summary,
            decisions=output.decisions,
            action_items=[item.model_dump() for item in output.action_items],
            open_questions=output.open_questions,
        )
