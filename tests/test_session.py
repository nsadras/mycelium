import pytest
from unittest.mock import AsyncMock, patch
from mycelium.core import Mycelium
from mycelium.models import WikiPage

@pytest.fixture
def temp_mycelium(tmp_path):
    mem = Mycelium(store_path=tmp_path / "store")
    mem.llm = AsyncMock()
    mem.encoder = AsyncMock()
    return mem

@pytest.mark.asyncio
async def test_session_lifecycle(temp_mycelium):
    # Setup mock for load_context
    with patch.object(temp_mycelium, 'load_context', new_callable=AsyncMock) as mock_load:
        mock_page = WikiPage(
            slug="test-page",
            title="Test Page",
            content="Content of test page",
            created=None,
            last_updated=None,
            version=1,
            confidence=0.8,
            importance=0.5
        )
        mock_load.return_value = [mock_page]
        
        async with temp_mycelium.session(query="test query", session_id="ses-123") as session:
            assert session.session_id == "ses-123"
            assert session.query == "test query"
            assert len(session.loaded_pages) == 1
            
            prompt = session.build_prompt("Hello assistant")
            assert "=== MEMORY: Test Page" in prompt
            assert "Content of test page" in prompt
            assert "Hello assistant" in prompt
            
            session.record("user", "Hello assistant")
            session.record("assistant", "Hello user")
            
        # On exit, encoder.encode_session should be called
        temp_mycelium.encoder.encode_session.assert_called_once()
        args, kwargs = temp_mycelium.encoder.encode_session.call_args
        assert "USER: Hello assistant" in args[0]
        assert "ASSISTANT: Hello user" in args[0]
        assert args[1] == "ses-123"


def test_memory_context_renders_nested_recall_fact_once(temp_mycelium):
    page = WikiPage(
        slug="test-page", title="Test Page",
        content="## Key Facts\n\n### Current Context\n- A single useful fact.",
        created=None, last_updated=None, version=1, confidence=0.8,
        importance=0.5,
    )
    from mycelium.session import Session

    session = Session(temp_mycelium, "test", "question")
    session.loaded_pages = [page]

    assert session.memory_context.count("A single useful fact") == 1


def test_memory_context_renders_shared_project_role_once_across_endpoint_pages(temp_mycelium):
    role = {
        "kind": "fact",
        "text": "Priya leads pilot evaluation.",
        "claim_ids": ["claim-role"],
        "relationship_kind": "project_role",
        "qualifiers": [],
        "links": [],
    }
    project = WikiPage(
        slug="lantern", title="Lantern", content="unused",
        created=None, last_updated=None, version=1, confidence=0.8, importance=0.5,
        sections=[{
            "key": "people_organizations",
            "title": "People & Organizations",
            "items": [role, {
                "kind": "fact", "text": "Lantern is ready.",
                "claim_ids": ["claim-ready"], "relationship_kind": None,
                "qualifiers": [], "links": [],
            }],
        }],
    )
    person = WikiPage(
        slug="priya", title="Priya", content="unused",
        created=None, last_updated=None, version=1, confidence=0.8, importance=0.5,
        sections=[{
            "key": "shared_projects", "title": "Shared Projects", "items": [
                role,
                {
                    "kind": "fact", "text": "Priya completed the rubric.",
                    "claim_ids": ["claim-rubric"], "relationship_kind": None,
                    "qualifiers": [], "links": [],
                },
            ],
        }],
    )
    from mycelium.session import Session

    session = Session(temp_mycelium, "test", "question")
    session.loaded_pages = [project, person]

    assert session.memory_context.count("Priya leads pilot evaluation") == 1
    assert "Lantern is ready" in session.memory_context
    assert "Priya completed the rubric" in session.memory_context
