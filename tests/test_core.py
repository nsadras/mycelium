import pytest
from unittest.mock import AsyncMock
from mycelium.core import Mycelium
from mycelium.models import WikiPage
from datetime import datetime

@pytest.fixture
def temp_mycelium(tmp_path):
    mem = Mycelium(store_path=tmp_path / "store")
    mem.llm = AsyncMock()
    mem.encoder = AsyncMock()
    return mem

@pytest.mark.asyncio
async def test_page_search_retrieves_named_entity(temp_mycelium):
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
    
    # Query mentions "Gina" but not "Jon"
    loaded = await temp_mycelium.load_context(query="When did Gina get her tattoo?")
    
    # The title-weighted page index should load person-gina but not person-jon.
    loaded_slugs = [p.slug for p in loaded]
    assert "person-gina" in loaded_slugs
    assert "person-jon" not in loaded_slugs


@pytest.mark.asyncio
async def test_page_search_does_not_expand_every_derived_page(temp_mycelium):
    now = datetime.now()
    temp_mycelium.wiki.save(WikiPage(
        slug="person-gina", title="Gina", content="Gina is a dancer.",
        created=now, last_updated=now, version=1, confidence=0.8, importance=0.5,
    ))
    temp_mycelium.wiki.save(WikiPage(
        slug="person-gina-timeline", title="Gina: Timeline", content="A dated event.",
        created=now, last_updated=now, version=1, confidence=1.0, importance=0.4,
        tags=["derived-memory", "timeline", "parent:person-gina"],
    ))
    loaded = await temp_mycelium.load_context(
        query="What does Gina enjoy?"
    )

    assert [page.slug for page in loaded] == ["person-gina"]


@pytest.mark.asyncio
async def test_full_page_search_routes_without_llm(temp_mycelium):
    now = datetime.now()
    temp_mycelium.wiki.save(WikiPage(
        slug="person-gina", title="Gina", content="Gina owns a clothing store.",
        created=now, last_updated=now, version=1, confidence=0.8,
        importance=0.5,
    ))
    temp_mycelium.wiki.save(WikiPage(
        slug="person-jon", title="Jon", content="Jon owns a dance studio.",
        created=now, last_updated=now, version=1, confidence=0.8,
        importance=0.5,
    ))
    loaded = await temp_mycelium.load_context(query="Who owns the dance studio?")

    assert loaded[0].slug == "person-jon"
    temp_mycelium.llm.call_structured.assert_not_awaited()
