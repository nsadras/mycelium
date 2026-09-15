from tests.session_support import configure_sessions, read_sessions, seed_sessions
import asyncio

import pytest

from mycelium.budget import count_message_tokens
from mycelium.core import Mycelium
from mycelium.ollama import ChatResponse
from mycelium.claim_index import ClaimSearchHit
from mycelium.operations import RetrievalRequest
from server import runtime
from server.api import memory_curation, sessions
from server.api.memory_contracts import (
    ClaimCorrectionRequest,
    SourceRetractionRequest,
)


class DeterministicProductionModel:
    """Schema-aware fake used only to exercise the real server/storage path."""

    def __init__(self) -> None:
        self.context_window_tokens = 32768
        self.generation_started = asyncio.Event()
        self.finish_generation = asyncio.Event()
        self.messages: list[list[dict]] = []
        self.context_disposition = "include"

    async def call_messages(self, messages, **_kwargs):
        self.messages.append(messages)
        self.generation_started.set()
        await self.finish_generation.wait()
        return ChatResponse("I will keep that deadline in mind.")

    async def call_structured(self, _system, user, output_type, **_kwargs):
        if "segments" in output_type.model_fields:
            segment_ids = list(
                output_type.model_fields["segments"].annotation.model_fields
            )
            segment_id = segment_ids[0]
            from tests.extraction_support import extraction_response

            return extraction_response(
                [
                    {
                        "text": "The user will send the Cedar brief tomorrow.",
                        "claim_type": "commitment",
                        "predicate": None,
                        "evidence_modality": "speech",
                        "temporal_status": "future",
                        "temporal_anchor_segment_id": segment_id,
                        "about": [{"entity": "user", "role": "subject"}],
                        "segment_ids": [segment_id],
                        "facets": {
                            "when": "tomorrow",
                            "deadline": None,
                            "inference_basis": None,
                        },
                    }
                ],
                segment_ids[1:],
            )
        if _kwargs.get("debug_label") in {
            "memory-correction",
            "dream-identity-plan",
            "dream-claim-routing",
            "dream-fact-synthesis",
            "dream-fact-candidate-selection",
        }:
            from tests.lifecycle_support import lifecycle_response

            return lifecycle_response(_system, user, output_type, **_kwargs)
        from typing import get_args

        aliases = get_args(get_args(output_type.model_fields["selected_ids"].annotation)[0])
        return {
            "selected_ids": list(aliases)[:5] if self.context_disposition == "include" else [],
            "supported_aspects": [],
            "remaining_gaps": [],
        }


class ArtifactBackedTestIndex:
    def __init__(self, artifacts) -> None:
        self.artifacts = artifacts
        self.embedder = type("Embedder", (), {"model": "test-embedding"})()
        self.candidate_limit = 20

    async def search(self, _query):
        return [
            ClaimSearchHit(
                claim.claim_id,
                claim.text,
                self.artifacts.memory_tier(claim.claim_id),
                None,
                None,
                None,
                None,
                1.0,
            )
            for claim in self.artifacts.list_claims(status="active")
        ]


@pytest.mark.asyncio
async def test_production_session_lifecycle_acceptance(tmp_path, monkeypatch):
    sessions_file = tmp_path / "sessions_meta.json"
    store_path = tmp_path / "store"
    configure_sessions(monkeypatch, runtime, sessions_file)
    monkeypatch.setattr(runtime, "_meta_lock", None)
    monkeypatch.setattr(runtime, "_session_locks", {})
    memory = Mycelium(store_path=store_path)
    # Fit the production system/evidence envelope while still forcing the long
    # transcript below to be trimmed.
    memory.config.context_budget_tokens = 1024
    memory.config.retrieval.tool_evidence_budget_tokens = 20
    fake = DeterministicProductionModel()
    memory.llm = fake
    memory.encoder.llm = fake
    memory.retriever.llm = fake
    memory.retriever.claim_index = ArtifactBackedTestIndex(memory.artifacts)
    memory.consolidator.llm = fake
    memory.consolidator.fact_resolver.llm = fake
    memory.consolidator.router.llm = fake
    monkeypatch.setattr(runtime, "get_mem", lambda: memory)
    monkeypatch.setattr(sessions, "get_mem", lambda: memory)
    monkeypatch.setattr(memory_curation, "get_mem", lambda: memory)

    created = await sessions.create_session(sessions.SessionCreate(query="Cedar brief"))
    session_id = created["id"]
    meta = read_sessions(runtime)
    record = runtime.ensure_session_record(meta[session_id], session_id)
    record["transcript"] = [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"Older conversation material {index}. " * 20,
            "timestamp": f"2026-08-30T10:{index:02d}:00+00:00",
        }
        for index in range(12)
    ]
    record["captured_turns"] = (
        6  # Older turns belong to the already captured history fixture.
    )
    seed_sessions(runtime, meta)
    timestamps = iter(
        [
            "2026-08-31T23:55:00+00:00",
            "2026-08-31T23:55:02+00:00",
        ]
    )
    monkeypatch.setattr(sessions, "iso_now", lambda: next(timestamps))

    # Surface a chat failure even if generation never starts, and bound a real
    # deadlock. TaskGroup also cleans up sibling tasks when an assertion fails.
    async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
        chat_task = tasks.create_task(
            sessions.chat(
                session_id,
                sessions.ChatRequest(message="I will send the Cedar brief tomorrow."),
            )
        )
        await fake.generation_started.wait()
        fake.finish_generation.set()
        chat_result = await chat_task

    assert chat_result["response"] == "I will keep that deadline in mind."
    assert chat_result["capture_status"] == "captured"
    assert memory.artifacts.list_claims() == []
    assert (
        await memory.retrieve_context(RetrievalRequest("Cedar"))
    ).evidence.records == ()
    await memory.encoder.extract_pending()
    assert count_message_tokens(fake.messages[0]) <= memory.config.context_budget_tokens
    assert len(fake.messages[0]) < len(record["transcript"]) + 2
    assert fake.messages[0][-1]["content"].endswith(
        "I will send the Cedar brief tomorrow."
    )
    saved = read_sessions(runtime)[session_id]
    assert saved["captured_turns"] == 7
    assert "active_episode" not in saved

    active_claims = memory.artifacts.list_claims(status="active")
    assert active_claims, [
        (episode.extraction_status, episode.extraction_error)
        for episode in memory.artifacts.list_episodes()
    ]
    claim = active_claims[0]
    temporal = claim.facets["temporal"]
    assert temporal["anchor"] == "2026-08-31T23:55:00+00:00"
    assert temporal["start"] == "2026-09-01"
    assert temporal["end"] == "2026-09-01"
    assert len(memory.artifacts.list_ingestion_operations()) == 1

    fake.context_disposition = "include"
    recalled = await memory.retrieve_context(
        RetrievalRequest(query="When will the Cedar brief be sent?")
    )
    assert recalled.page_references == ()
    assert claim.text in [record.statement for record in recalled.evidence.records]

    fake.context_disposition = "exclude"
    assert (
        await memory.retrieve_context(
            RetrievalRequest(query="What kind of cedar tree grows near the coast?")
        )
    ).evidence.records == ()

    correction = await memory_curation.correct_claim(
        claim.claim_id,
        ClaimCorrectionRequest(
            text="The user will send the Cedar brief on Tuesday.",
            reason="The deadline was moved by one day.",
            temporal_status="future",
        ),
    )
    replacement_id = correction["claim_ids"][0]
    correction_source_id = correction["source_ids"][0]
    assert memory.artifacts.get_claim(claim.claim_id).status == "superseded"
    assert memory.artifacts.get_claim(replacement_id).status == "active"

    await memory_curation.retract_source(
        correction_source_id,
        SourceRetractionRequest(reason="The correction was entered in error."),
    )
    assert memory.artifacts.get_claim(replacement_id).status == "retracted"

    restarted = Mycelium(store_path=store_path)
    assert restarted.artifacts.get_claim(claim.claim_id).status == "superseded"
    assert restarted.artifacts.get_claim(replacement_id).status == "retracted"
    assert restarted.artifacts.get_source(correction_source_id).status == "retracted"
    assert restarted.artifacts.list_ingestion_operations()[0].status == "complete"
