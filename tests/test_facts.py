from datetime import datetime

from mycelium.facts import extract_recall_sections, page_recall_context, routing_recall_index
from mycelium.models import WikiPage


def test_extract_recall_sections_keeps_key_facts_and_timeline_rows():
    content = """# Caroline Profile

## Overview
Readable summary.

## Key Facts
- Caroline researched adoption agencies. Source: D2:8.
- Caroline is a transgender woman. Source: D1:5.

## Event Timeline
| Date / Relative Time | Event | People / Entities | Source |
|---|---|---|---|
| 7 May 2023 | Caroline attended an LGBTQ support group. | Caroline | D1:3 |

## Notes
- Not recall material.
"""

    sections = extract_recall_sections(content)

    assert sections["Key Facts"] == [
        "- Caroline researched adoption agencies. Source: D2:8.",
        "- Caroline is a transgender woman. Source: D1:5.",
    ]
    assert "| 7 May 2023 | Caroline attended an LGBTQ support group." in sections["Event Timeline"][1]


def test_page_recall_context_is_prompt_ready():
    page = WikiPage(
        slug="caroline-profile",
        title="Caroline Profile",
        content="## Key Facts\n- Caroline researched adoption agencies. Source: D2:8.\n\n## Event Timeline\nNo dated events recorded yet.",
        created=datetime.now(),
        last_updated=datetime.now(),
        version=1,
        confidence=0.9,
        importance=0.8,
    )

    context = page_recall_context(page)

    assert "RECALL DETAILS FOR [[caroline-profile]]" in context
    assert "Caroline researched adoption agencies" in context


def test_routing_recall_index_collects_pages_with_recall_sections():
    pages = [
        WikiPage(
            slug="caroline-profile",
            title="Caroline Profile",
            content="## Key Facts\n- Caroline researched adoption agencies. Source: D2:8.",
            created=datetime.now(),
            last_updated=datetime.now(),
            version=1,
            confidence=0.9,
            importance=0.8,
        ),
        WikiPage(
            slug="empty-page",
            title="Empty",
            content="No structured recall sections.",
            created=datetime.now(),
            last_updated=datetime.now(),
            version=1,
            confidence=0.9,
            importance=0.8,
        ),
    ]

    index = routing_recall_index(pages)

    assert "## Recall Facts And Timelines" in index
    assert "caroline-profile" in index
    assert "empty-page" not in index
