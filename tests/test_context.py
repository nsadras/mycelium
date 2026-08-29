from datetime import datetime

from mycelium.budget import count_tokens
from mycelium.context import render_memory_context
from mycelium.models import WikiPage


def _page(slug: str, title: str, content: str = "") -> WikiPage:
    now = datetime.now()
    return WikiPage(
        slug=slug,
        title=title,
        content=content,
        created=now,
        last_updated=now,
        version=2,
        confidence=0.8,
        page_type="project",
        entity_id=slug,
    )


def test_render_memory_context_is_empty_without_renderable_pages():
    assert render_memory_context([]) == ""
    assert render_memory_context([_page("empty", "Empty")]) == ""


def test_render_memory_context_deduplicates_shared_roles_and_includes_sources():
    shared_role = {
        "kind": "fact",
        "text": "Priya leads pilot evaluation.",
        "claim_ids": ["claim-role"],
        "relationship_kind": "project_role",
        "qualifiers": [],
        "links": [],
    }
    project = _page("lantern", "Lantern")
    project.sections = [{
        "key": "people_organizations",
        "title": "People & Organizations",
        "items": [shared_role],
    }]
    project.source_context = "CANONICAL SOURCE LOG SNIPPETS:\n- exact evidence"
    person = _page("priya", "Priya")
    person.page_type = "person"
    person.sections = [{
        "key": "shared_projects",
        "title": "Shared Projects",
        "items": [shared_role, {
            "kind": "fact",
            "text": "Priya completed the rubric.",
            "claim_ids": ["claim-rubric"],
            "relationship_kind": None,
            "qualifiers": [],
            "links": [],
        }],
    }]

    context = render_memory_context([project, person])

    assert context.count("Priya leads pilot evaluation") == 1
    assert "Priya completed the rubric" in context
    assert "CANONICAL SOURCE LOG SNIPPETS" in context
    assert context.count("=== END MEMORY ===") == 1
    assert count_tokens(context) > 0
