from __future__ import annotations

import json

from pydantic import BaseModel, Field

from engram.models import MeetingSummary
from mycelium.batching import batch_items, split_text_by_tokens, structured_input_budget
from mycelium.budget import count_tokens
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
        context_window_tokens: int = 32768,
    ) -> None:
        self.llm = OllamaClient(
            url=ollama_url,
            model=model,
            temperature=temperature,
            timeout=timeout,
            context_window_tokens=context_window_tokens,
        )
        self.context_window_tokens = context_window_tokens

    async def summarize(self, title: str, transcript: str) -> MeetingSummary:
        if not transcript.strip():
            return MeetingSummary(summary="No speech was transcribed.")

        system = (
            "You summarize meeting transcripts into structured JSON for a local memory system. "
            "Use only the transcript. Do not invent decisions, owners, deadlines, or questions. "
            "Keep action item owners null when the transcript does not identify an owner."
        )
        transcript = transcript.strip()

        def prompt(text: str) -> str:
            return "\n".join([f"Meeting title: {title}", "", "Transcript:", text])

        input_budget = structured_input_budget(self.context_window_tokens, num_predict=4096)
        if count_tokens(f"{system}\n{prompt(transcript)}") <= input_budget:
            output = await self._summarize_prompt(system, prompt(transcript), num_predict=4096)
        else:
            static_tokens = count_tokens(f"{system}\n{prompt('')}")
            piece_budget = max(256, input_budget - static_tokens - 256)
            pieces = split_text_by_tokens(transcript, piece_budget)
            batches = batch_items(
                pieces,
                lambda items: f"{system}\n{prompt(''.join(items))}",
                input_budget,
            )
            partials = [
                await self._summarize_prompt(system, prompt("".join(batch)), num_predict=4096)
                for batch in batches
            ]
            output = await self._reduce_summaries(title, partials)

        output = self._dedupe_output(output)
        return MeetingSummary(
            summary=output.summary,
            decisions=output.decisions,
            action_items=[item.model_dump() for item in output.action_items],
            open_questions=output.open_questions,
        )

    async def _summarize_prompt(
        self,
        system: str,
        user: str,
        *,
        num_predict: int,
    ) -> MeetingSummaryOutput:
        response = await self.llm.call_structured(
            system,
            user,
            MeetingSummaryOutput,
            num_predict=num_predict,
        )
        if isinstance(response, MeetingSummaryOutput):
            return response
        return MeetingSummaryOutput.model_validate(response)

    async def _reduce_summaries(
        self,
        title: str,
        summaries: list[MeetingSummaryOutput],
    ) -> MeetingSummaryOutput:
        system = (
            "Combine structured summaries from consecutive portions of one meeting. "
            "Preserve every supported decision, action item, and open question, remove duplicates, "
            "and do not invent facts. Return one structured meeting summary."
        )
        input_budget = structured_input_budget(self.context_window_tokens, num_predict=4096)
        current = summaries
        while len(current) > 1:
            serialized = [item.model_dump_json() for item in current]

            def render(items: list[str]) -> str:
                return self._reduction_user(title, items)

            batches = batch_items(
                serialized,
                lambda items: f"{system}\n{render(list(items))}",
                input_budget,
            )
            if len(batches) == len(current):
                raise ValueError("partial meeting summaries cannot be reduced within the context window")
            current = [
                await self._summarize_prompt(system, render(batch), num_predict=4096)
                for batch in batches
            ]
        return current[0]

    def _reduction_user(self, title: str, summaries: list[str]) -> str:
        return "\n".join(
            [
                f"Meeting title: {title}",
                "",
                "Partial summaries in chronological order:",
                *[f"PART {index}:\n{value}" for index, value in enumerate(summaries, start=1)],
            ]
        )

    def _dedupe_output(self, output: MeetingSummaryOutput) -> MeetingSummaryOutput:
        action_items = []
        seen_actions: set[str] = set()
        for item in output.action_items:
            key = json.dumps(item.model_dump(), sort_keys=True)
            if key not in seen_actions:
                seen_actions.add(key)
                action_items.append(item)
        return output.model_copy(
            update={
                "decisions": list(dict.fromkeys(output.decisions)),
                "action_items": action_items,
                "open_questions": list(dict.fromkeys(output.open_questions)),
            }
        )
