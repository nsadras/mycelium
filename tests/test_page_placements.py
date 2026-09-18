from dataclasses import replace

import pytest

from mycelium.artifacts import ArtifactStore, ClaimProvenance, ConsolidatedFact, MemoryClaim, SourceDocument, SourceSegment
from mycelium.config import Config
from mycelium.context import render_memory_context
from mycelium.materialization import PageMaterializer
from mycelium.store import WikiStore


def setup_pages(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    wiki = WikiStore(tmp_path / "wiki")
    person = artifacts.create_entity("person", "Elena")
    business = artifacts.create_entity("organization", "Workshop")
    incidental = artifacts.create_entity("person", "Reporter")
    claim = MemoryClaim("c1", "Elena founded the Workshop.", [],
                        [ClaimProvenance("s1", ["seg1"])], "2026-09-04")
    artifacts.save_claim(claim)
    artifacts.save_source(SourceDocument("s1", "conversation", "session", "2026-09-04", None, [],
        [SourceSegment("seg1", 0, claim.text)]))
    fact = ConsolidatedFact("f1", claim.text, ["c1"], business.entity_id, "overview", "current",
                             [person.entity_id], "claim", 1.0, "Source statement.", "2026-09-04", "2026-09-04")
    artifacts.save_consolidated_fact(fact)
    return artifacts, wiki, PageMaterializer(wiki, artifacts, Config.defaults()), person, business, incidental


def test_one_statement_projects_to_selected_pages_without_duplicate_storage(tmp_path):
    artifacts, wiki, materializer, person, business, incidental = setup_pages(tmp_path)
    materializer.regenerate_all()
    for entity in (person, business):
        page = wiki.get(entity.slug)
        items = [i for s in page.sections for i in s["items"] if i["kind"] == "fact"]
        assert len(items) == 1
        assert items[0]["claim_ids"] == ["c1"]
        assert items[0]["sources"][0]["segment_ids"] == ["seg1"]
    assert not wiki.exists(incidental.slug)
    assert len(artifacts.list_claims()) == len(artifacts.list_consolidated_facts()) == 1
    context = render_memory_context([wiki.get(person.slug), wiki.get(business.slug)])
    assert context.count("Elena founded the Workshop.") == 1


def test_shared_view_does_not_leak_unselected_members_of_a_synthesized_fact(tmp_path):
    artifacts, wiki, materializer, person, business, _ = setup_pages(tmp_path)
    claim = MemoryClaim("c2", "The Workshop opens on Sundays.", [],
                        [ClaimProvenance("s2", ["seg2"])], "2026-09-04")
    artifacts.save_claim(claim)
    artifacts.save_source(SourceDocument("s2", "conversation", "session", "2026-09-04", None, [],
        [SourceSegment("seg2", 0, claim.text)]))
    fact = artifacts.get_consolidated_fact("f1")
    # Distinct items explicitly choose their own evidence and destinations.
    artifacts.save_consolidated_fact(replace(fact, fact_id="person-item", owner_entity_id=person.entity_id,
                                            linked_entity_ids=[]))
    artifacts.save_consolidated_fact(replace(fact, text=fact.text + " " + claim.text,
                                            member_claim_ids=["c1", "c2"], linked_entity_ids=[]))
    materializer.regenerate_all()
    assert "Sundays" in wiki.get(business.slug).content
    assert "Sundays" not in wiki.get(person.slug).content
    assert "Elena founded" in wiki.get(person.slug).content
    assert "seg2" not in wiki.get(person.slug).content


def test_retraction_regenerates_every_selected_page(tmp_path):
    artifacts, wiki, materializer, person, business, _ = setup_pages(tmp_path)
    materializer.regenerate_all()
    artifacts.save_claim(replace(artifacts.get_claim("c1"), status="retracted"))
    materializer.regenerate({business.entity_id})
    assert not wiki.exists(person.slug)
    assert not wiki.exists(business.slug)


def test_removing_a_destination_clears_the_old_page(tmp_path):
    artifacts, wiki, materializer, person, business, _ = setup_pages(tmp_path)
    materializer.regenerate_all()
    from mycelium.organization import FactCurationService
    FactCurationService(artifacts, materializer).move("f1", business.entity_id, "Overview",
        linked_entity_ids=[], reason="Remove shared destination")
    assert wiki.exists(business.slug)
    assert not wiki.exists(person.slug)


@pytest.mark.parametrize("invalid", ["missing_entity", "empty_heading", "inactive_entity", "missing_claim"])
def test_persisted_view_references_require_valid_endpoints_and_heading(tmp_path, invalid):
    artifacts, _, _, person, _, _ = setup_pages(tmp_path)
    fact = artifacts.get_consolidated_fact("f1")
    if invalid == "missing_entity":
        fact.linked_entity_ids = ["absent"]
    elif invalid == "empty_heading":
        fact.section_key = " "
    elif invalid == "missing_claim":
        fact.member_claim_ids = ["absent"]
    else:
        artifacts.save_entity(replace(person, status="archived"))
    with pytest.raises((ValueError, FileNotFoundError)):
        artifacts.save_consolidated_fact(fact)
