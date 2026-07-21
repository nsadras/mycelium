import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from mycelium.core import Mycelium
from mycelium.models import WikiPage
from datetime import datetime

@pytest.fixture
def temp_mycelium(tmp_path):
    mem = Mycelium(store_path=tmp_path / "store", git_commits=False)
    mem.llm = AsyncMock()
    mem.encoder = AsyncMock()
    return mem

@pytest.mark.asyncio
async def test_entity_aware_retrieval_fallback(temp_mycelium):
    # Create two pages in the wiki store
    page_gina = WikiPage(
        slug="person-gina",
        title="Gina's profile",
        content="Gina is a dancer.",
        created=datetime.now(),
        last_updated=datetime.now(),
        version=1,
        confidence=0.8,
        importance=0.5
    )
    page_jon = WikiPage(
        slug="person-jon",
        title="Jon's profile",
        content="Jon is a developer.",
        created=datetime.now(),
        last_updated=datetime.now(),
        version=1,
        confidence=0.8,
        importance=0.5
    )
    temp_mycelium.wiki.save(page_gina)
    temp_mycelium.wiki.save(page_jon)
    
    # Mock LLM to return empty routing selection (so router fails / returns nothing)
    temp_mycelium.llm.call_structured.return_value = []
    
    # Query mentions "Gina" but not "Jon"
    loaded = await temp_mycelium.load_context(query="When did Gina get her tattoo?", reconsolidate=False)
    
    # The entity fallback should match "Gina" in query against "person-gina" slug component or "Gina" in title,
    # loading person-gina but NOT person-jon
    loaded_slugs = [p.slug for p in loaded]
    assert "person-gina" in loaded_slugs
    assert "person-jon" not in loaded_slugs
