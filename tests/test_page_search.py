from datetime import datetime

from mycelium.models import WikiPage
from mycelium.page_search import PageSearchIndex


def _page(slug: str, content: str, *, version: int = 1) -> WikiPage:
    now = datetime.now()
    return WikiPage(
        slug=slug,
        title=slug.title(),
        content=content,
        created=now,
        last_updated=now,
        version=version,
        page_type="person",
    )


def test_page_search_ranks_matching_full_page():
    index = PageSearchIndex()

    hits = index.search(
        [
            _page("gina", "Gina owns a clothing store."),
            _page("jon", "Jon owns a dance studio."),
        ],
        "Who owns the clothing store?",
        limit=2,
    )

    assert [hit.slug for hit in hits] == ["gina", "jon"]
    assert hits[0].score > hits[1].score


def test_page_search_refreshes_changed_page_content():
    index = PageSearchIndex()
    pages = [_page("gina", "Gina owns a clothing store.")]
    assert index.search(pages, "internship", limit=1) == []

    changed = [_page("gina", "Gina accepted a design internship.", version=2)]

    assert [hit.slug for hit in index.search(changed, "internship", limit=1)] == ["gina"]


def test_page_search_boosts_page_titles():
    index = PageSearchIndex()
    titled = _page("dance-studio", "A venue for weekly workshops.")
    body_only = _page("workshops", "Dance studio classes are available.")

    hits = index.search([body_only, titled], "dance studio", limit=2)

    assert hits[0].slug == "dance-studio"
