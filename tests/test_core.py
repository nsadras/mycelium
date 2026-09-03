import pytest
from unittest.mock import AsyncMock
from mycelium.core import Mycelium
from mycelium.budget import count_tokens
from mycelium.context import render_memory_context
from mycelium.models import WikiPage
from mycelium.operations import RetrievalRequest
from datetime import datetime
from mycelium.artifacts import ClaimPlacement, ClaimProvenance, EntityRecord, MemoryClaim

@pytest.fixture
def temp_mycelium(tmp_path):
    mem = Mycelium(store_path=tmp_path / "store")
    mem.llm = AsyncMock()
    async def include_all_context(_system, _user, schema, **_kwargs):
        decisions_model = schema.model_fields["decisions"].annotation
        return {"decisions": {
            alias: {
                "disposition": "include",
                "confidence": 1.0,
                "reason": "The fixture admits its generated retrieval candidate.",
            }
            for alias in decisions_model.model_fields
        }}
    mem.llm.call_structured.side_effect = include_all_context
    mem.retriever.llm = mem.llm
    mem.encoder = AsyncMock()
    return mem


async def retrieve_pages(memory, query, **kwargs):
    result = await memory.retrieve_context(RetrievalRequest(query=query, **kwargs))
    return list(result.pages)

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
        page_type="person", entity_id="person-gina"
    )
    page_jon = WikiPage(
        slug="person-jon",
        title="Jon's profile",
        content="Jon is a developer.",
        created=datetime.now(),
        last_updated=datetime.now(),
        version=1,
        page_type="person", entity_id="person-jon"
    )
    temp_mycelium.wiki.save(page_gina)
    temp_mycelium.wiki.save(page_jon)
    
    # Query mentions "Gina" but not "Jon"
    loaded = await retrieve_pages(temp_mycelium, "When did Gina get her tattoo?")
    
    # The title-weighted page index should load person-gina but not person-jon.
    loaded_slugs = [p.slug for p in loaded]
    assert "person-gina" in loaded_slugs
    assert "person-jon" not in loaded_slugs


@pytest.mark.asyncio
async def test_full_page_search_candidate_requires_structured_admission(temp_mycelium):
    now = datetime.now()
    temp_mycelium.wiki.save(WikiPage(
        slug="person-gina", title="Gina", content="Gina owns a clothing store.",
        created=now, last_updated=now, version=1,
        page_type="person", entity_id="person-gina",
    ))
    temp_mycelium.wiki.save(WikiPage(
        slug="person-jon", title="Jon", content="Jon owns a dance studio.",
        created=now, last_updated=now, version=1,
        page_type="person", entity_id="person-jon",
    ))
    loaded = await retrieve_pages(temp_mycelium, "Who owns the dance studio?")

    assert loaded[0].slug == "person-jon"
    temp_mycelium.llm.call_structured.assert_awaited_once()


@pytest.mark.asyncio
async def test_page_search_can_abstain_from_lexical_candidates(temp_mycelium):
    now = datetime.now()
    temp_mycelium.wiki.save(WikiPage(
        slug="topic-paint", title="Tea Leaf Paint",
        content="Tea Leaf Green is the selected wall color.",
        created=now, last_updated=now, version=1,
        page_type="topic", entity_id="topic-paint",
    ))
    temp_mycelium.llm.call_structured.side_effect = None
    temp_mycelium.llm.call_structured.return_value = {"decisions": {
        "M001": {
            "disposition": "exclude",
            "confidence": 1.0,
            "reason": "A paint color does not answer a beverage preference question.",
        },
    }}

    loaded = await retrieve_pages(temp_mycelium, "Which tea does the user prefer?")

    assert loaded == []


@pytest.mark.asyncio
async def test_temporal_claim_routes_generic_deadline_query(temp_mycelium):
    now = datetime.fromisoformat("2026-08-11T10:00:00-07:00")
    temp_mycelium.wiki.save(WikiPage(
        slug="project-alpha", title="Project Alpha", content="Quarterly report work.",
        created=now, last_updated=now, version=1,
        page_type="project", entity_id="project-alpha",
    ))
    deadline = MemoryClaim(
        claim_id="deadline",
        text="Ava will send the report.",
        about=[{"entity": "Ava"}],
        provenance=[ClaimProvenance("source-1", ["segment-1"])],
        recorded_at=now.isoformat(),
        claim_type="commitment",
        facets={"temporal": {
            "expression": "next Thursday", "role": "deadline",
            "status": "resolved", "certainty": "exact",
            "start": "2026-08-20", "end": "2026-08-20",
        }},
    )
    temp_mycelium.artifacts.save_claim(deadline)
    temp_mycelium.artifacts.save_entity(EntityRecord(
        entity_id="project-alpha", entity_type="project", title="Project Alpha",
        slug="project-alpha", aliases=[], status="active",
        created_at=now.isoformat(), updated_at=now.isoformat(),
    ))
    temp_mycelium.artifacts.save_placement(ClaimPlacement(
        claim_id="deadline", owner_entity_id="project-alpha",
        section_key="next_steps_deadlines", linked_entity_ids=[], status="placed",
        reason="test", created_at=now.isoformat(), updated_at=now.isoformat(),
    ))

    loaded = await retrieve_pages(
        temp_mycelium, "What is due next week?", query_time=now
    )

    assert [page.slug for page in loaded] == ["project-alpha"]


@pytest.mark.asyncio
async def test_load_context_exposes_relevant_short_term_memory_without_wiki_write(
    temp_mycelium,
):
    claim = MemoryClaim(
        claim_id="recent-claim",
        text="Gina plans to take a ceramics class.",
        about=[{"entity": "Gina", "role": "subject"}],
        provenance=[ClaimProvenance("source-recent", ["segment-recent"])],
        recorded_at=datetime.now().astimezone().isoformat(),
        claim_type="plan",
        predicate="take_ceramics_class",
    )
    temp_mycelium.artifacts.save_claim(claim)

    loaded = await retrieve_pages(
        temp_mycelium, "What class does Gina plan to take?"
    )

    recent = next(page for page in loaded if page.slug == "_short-term-memory")
    assert claim.text in recent.content
    assert not temp_mycelium.wiki.exists("_short-term-memory")


@pytest.mark.asyncio
async def test_load_context_budgets_the_authoritative_rendering(temp_mycelium):
    now = datetime.now()
    page = WikiPage(
        slug="project-orchid",
        title="Project Orchid",
        content="Orchid planning details " * 20,
        created=now,
        last_updated=now,
        version=1,
        page_type="project",
        entity_id="project-orchid",
    )
    temp_mycelium.wiki.save(page)
    exact_tokens = count_tokens(render_memory_context([page]))

    loaded = await retrieve_pages(
        temp_mycelium, "Orchid planning", budget_tokens=exact_tokens
    )
    rejected = await retrieve_pages(
        temp_mycelium, "Orchid planning", budget_tokens=exact_tokens - 1
    )

    assert [item.slug for item in loaded] == [page.slug]
    assert rejected == []
