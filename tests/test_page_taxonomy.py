from datetime import datetime

from mycelium.artifacts import ArtifactStore, ClaimProvenance, MemoryClaim
from mycelium.config import Config
from mycelium.materialization import MaterializationResult, PageMaterializer
from mycelium.models import WikiPage
from mycelium.store import WikiStore


def memory_claim(claim_id: str, text: str, claim_type: str) -> MemoryClaim:
    return MemoryClaim(
        claim_id=claim_id,
        text=text,
        kind="fact",
        about=[{"entity": "Ava"}],
        provenance=[ClaimProvenance("source-one", ["source-one#seg-0001"])],
        recorded_at="2026-08-10T10:00:00",
        claim_type=claim_type,
        confidence=0.9,
        salience=0.8,
    )


def page(slug: str, title: str, page_type: str | None) -> WikiPage:
    now = datetime.now()
    return WikiPage(
        slug=slug,
        title=title,
        content="## Key Facts",
        created=now,
        last_updated=now,
        version=1,
        confidence=0.9,
        importance=0.8,
        page_type=page_type,
    )


def test_typed_renderer_organizes_without_dropping_claim_text(tmp_path):
    materializer = PageMaterializer(
        WikiStore(tmp_path / "wiki"),
        ArtifactStore(tmp_path / "artifacts"),
        Config.defaults(),
    )
    claims = [
        memory_claim("identity", "Ava is an engineer.", "identity"),
        memory_claim("preference", "Ava prefers tea.", "preference"),
        memory_claim("event", "Ava visited Kyoto.", "event"),
    ]

    content = materializer.render(claims, page_type="person")

    assert content.startswith("## Key Facts")
    assert "### Profile" in content
    assert "### Interests & Preferences" in content
    assert "## Event Timeline" in content
    assert content.index("### Profile") < content.index("### Interests & Preferences")
    for claim in claims:
        assert content.count(claim.text) == 1


def test_typed_renderer_keeps_profile_in_key_facts_when_main_view_is_full(tmp_path):
    config = Config.defaults()
    config.dream.main_page_claim_limit = 1
    materializer = PageMaterializer(
        WikiStore(tmp_path / "wiki"),
        ArtifactStore(tmp_path / "artifacts"),
        config,
    )
    identity = memory_claim("identity", "Ava is an engineer.", "identity")
    preference = memory_claim("preference", "Ava prefers tea.", "preference")

    content = materializer.render([preference, identity], page_type="person")

    key_facts, details = content.split("## Detailed Facts", maxsplit=1)
    assert "### Profile" in key_facts
    assert identity.text in key_facts
    assert identity.text not in details


def test_you_memory_map_and_index_group_pages_without_relationships(tmp_path):
    wiki = WikiStore(tmp_path / "wiki")
    materializer = PageMaterializer(
        wiki,
        ArtifactStore(tmp_path / "artifacts"),
        Config.defaults(),
    )
    wiki.save(page("user-profile", "You", "you"))
    wiki.save(page("mycelium", "Mycelium", "project"))
    wiki.save(page("ava", "Ava", "person"))
    wiki.save(page("unclassified", "Unclassified", None))
    result = MaterializationResult({}, set(), set(), {}, set())

    materializer.refresh_you_memory_map(result)
    materializer.persist(result)

    you = wiki.get("user-profile")
    assert "### Projects\n- [[mycelium]] — Mycelium" in you.content
    assert "### People\n- [[ava]] — Ava" in you.content
    assert you.related == []
    index = wiki.get_index()
    assert index.index("## You") < index.index("## Projects") < index.index("## People")
    assert "## Unclassified" in index
