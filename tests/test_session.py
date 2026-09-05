import pytest
from unittest.mock import AsyncMock, patch
from mycelium.core import Mycelium
from mycelium.operations import (
    EvidenceRecord,
    IngestionResult,
    MemoryEvidence,
    RetrievalResult,
    WikiPageReference,
)


@pytest.fixture
def temp_mycelium(tmp_path):
    mem = Mycelium(store_path=tmp_path / "store")
    mem.llm = AsyncMock()
    mem.encoder = AsyncMock()
    return mem


@pytest.mark.asyncio
async def test_session_lifecycle(temp_mycelium):
    with (
        patch.object(
            temp_mycelium, "retrieve_context", new_callable=AsyncMock
        ) as mock_retrieve,
        patch.object(
            temp_mycelium, "ingest_source", new_callable=AsyncMock
        ) as mock_ingest,
    ):
        mock_page = WikiPageReference(
            slug="test-page",
            title="Test Page",
            entity_id="test-page",
            version=1,
        )
        evidence = MemoryEvidence(
            records=(
                EvidenceRecord(
                    record_id="claim-test",
                    record_type="claim",
                    statement="Content of test page",
                    subject_entity_id="test-page",
                    subject_name="Test Page",
                    claim_ids=("claim-test",),
                ),
            )
        )
        mock_retrieve.return_value = RetrievalResult(
            page_references=(mock_page,), evidence=evidence, rendered_context=""
        )
        mock_ingest.return_value = IngestionResult(status="captured")

        async with temp_mycelium.session(
            query="test query", session_id="ses-123"
        ) as session:
            assert session.session_id == "ses-123"
            assert session.query == "test query"
            assert len(session.page_references) == 1

            session.record("user", "Hello assistant")
            session.record("assistant", "Hello user")

        mock_ingest.assert_awaited_once()
        source_input = mock_ingest.await_args.args[0]
        assert "USER: Hello assistant" in source_input.transcript
        assert "ASSISTANT: Hello user" in source_input.transcript
        assert source_input.session_id == "ses-123"
        assert source_input.occurred_at == source_input.segments[0].timestamp
        assert all(segment.timestamp for segment in source_input.segments)


def test_memory_context_renders_typed_records_without_wiki_pages(
    temp_mycelium,
):
    from mycelium.session import Session

    session = Session(temp_mycelium, "test", "question")
    session.memory_evidence = MemoryEvidence(
        records=(
            EvidenceRecord(
                record_id="claim-role",
                record_type="claim",
                statement="Priya leads pilot evaluation",
                subject_entity_id="person-priya",
                subject_name="Priya",
                claim_ids=("claim-role",),
            ),
            EvidenceRecord(
                record_id="claim-lantern",
                record_type="claim",
                statement="Lantern is ready",
                subject_entity_id="project-lantern",
                subject_name="Lantern",
                claim_ids=("claim-lantern",),
            ),
            EvidenceRecord(
                record_id="claim-rubric",
                record_type="claim",
                statement="Priya completed the rubric",
                subject_entity_id="person-priya",
                subject_name="Priya",
                claim_ids=("claim-rubric",),
            ),
        )
    )

    assert session.memory_context.count("Priya leads pilot evaluation") == 1
    assert "Lantern is ready" in session.memory_context
    assert "Priya completed the rubric" in session.memory_context
