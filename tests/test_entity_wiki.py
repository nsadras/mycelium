import pytest

from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ClaimProvenance,
    ConsolidatedFact,
    MemoryClaim,
    ReconsolidationProposal,
)
from mycelium.config import Config
from mycelium.materialization import PageMaterializer
from mycelium.organization import (
    EntityCurationService,
    FactCurationService,
)
from mycelium.store import WikiStore
from mycelium.wiki_schema import default_section


def claim(claim_id: str, text: str, claim_type: str = "state", modality: str = "speech"):
    return MemoryClaim(
        claim_id=claim_id,
        text=text,
        kind="fact",
        about=[{"entity": "Mycelium"}],
        provenance=[ClaimProvenance("source-1", [f"source-1#{claim_id}"])],
        recorded_at="2026-08-12T10:00:00-07:00",
        claim_type=claim_type,
        evidence_modality=modality,
        confidence=0.9,
        salience=0.8,
    )


def setup_store(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    wiki = WikiStore(tmp_path / "wiki")
    materializer = PageMaterializer(wiki, artifacts, Config.defaults())
    you = artifacts.create_entity("you", "You")
    project = artifacts.create_entity("project", "Mycelium")
    return artifacts, wiki, materializer, you, project


def place(artifacts, item, owner, section, *, links=None):
    artifacts.save_claim(item)
    artifacts.save_placement(ClaimPlacement(
        claim_id=item.claim_id,
        owner_entity_id=owner.entity_id,
        section_key=section,
        linked_entity_ids=list(links or []),
        status="placed",
        reason="test",
        created_at="2026-08-12T10:00:00-07:00",
        updated_at="2026-08-12T10:00:00-07:00",
        relationship_kind=(
            "project_role" if item.predicate == "project_role" else None
        ),
    ))
    artifacts.save_consolidated_fact(ConsolidatedFact(
        fact_id=f"fact-{item.claim_id}",
        text=item.text,
        member_claim_ids=[item.claim_id],
        owner_entity_id=owner.entity_id,
        section_key=section,
        linked_entity_ids=list(links or []),
        state="active",
        synthesis_origin="claim",
        confidence=item.confidence,
        reason="test",
        created_at="2026-08-12T10:00:00-07:00",
        updated_at="2026-08-12T10:00:00-07:00",
    ))


def test_entity_ids_survive_rename_and_slug_is_unique(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    service = EntityCurationService(artifacts, wiki, materializer)
    place(artifacts, claim("claim-1", "Mycelium has a transparent memory store."), project, "overview")
    materializer.regenerate({project.entity_id})

    result = service.update_entity(project.entity_id, title="MnemOS", slug="mnemos")

    assert result.entity.entity_id == "project-mycelium"
    assert result.entity.slug == "mnemos"
    assert "Mycelium" in result.entity.aliases
    assert not wiki.exists("mycelium")
    assert wiki.get("mnemos").entity_id == project.entity_id


def test_typed_projection_is_ordered_traceable_and_research_is_labeled(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    status = claim("claim-status", "Mycelium is in active development.")
    research = claim(
        "claim-research", "SQLite FTS5 supports BM25 ranking.", "observation", "tool"
    )
    place(artifacts, status, project, "current_status")
    place(artifacts, research, project, "research_references")

    materializer.regenerate({project.entity_id})
    page = wiki.get(project.slug)

    assert [section["key"] for section in page.sections] == [
        "current_status", "research_references"
    ]
    fact = page.sections[0]["items"][0]
    assert fact["claim_ids"] == ["claim-status"]
    assert fact["sources"][0]["segment_ids"] == ["source-1#claim-status"]
    assert "external research" in page.sections[1]["items"][0]["qualifiers"]


def test_project_role_has_one_canonical_placement_and_two_page_views(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    person = artifacts.create_entity("person", "Priya Raman")
    role = claim(
        "claim-role",
        "Priya Raman leads pilot evaluation and recruitment for Mycelium.",
        "relationship",
    )
    role.predicate = "project_role"
    role.about = [
        {"entity": "Priya Raman", "role": "subject"},
        {"entity": "Mycelium", "role": "project"},
    ]
    place(artifacts, role, person, "shared_projects", links=[project.entity_id])

    result = materializer.regenerate({person.entity_id})

    assert set(result.changed_pages) == {person.slug, project.slug}
    assert len(artifacts.list_claims()) == 1
    assert len(artifacts.list_placements()) == 1
    person_fact = wiki.get(person.slug).sections[0]["items"][0]
    project_fact = wiki.get(project.slug).sections[0]["items"][0]
    assert person_fact["claim_ids"] == project_fact["claim_ids"] == ["claim-role"]
    assert person_fact["sources"] == project_fact["sources"]
    assert person_fact["canonical_owner_entity_ids"] == [person.entity_id]
    assert project_fact["canonical_owner_entity_ids"] == [person.entity_id]
    assert person_fact["canonical_linked_entity_ids"] == [project.entity_id]
    assert project_fact["canonical_linked_entity_ids"] == [project.entity_id]
    assert person_fact["relationship_kind"] == "project_role"
    assert project_fact["relationship_kind"] == "project_role"
    assert person_fact["projection"] == "canonical"
    assert project_fact["projection"] == "shared_endpoint"
    assert person_fact["links"][0]["entity_id"] == project.entity_id
    assert project_fact["links"][0]["entity_id"] == person.entity_id
    assert wiki.get(person.slug).sections[0]["key"] == "shared_projects"
    assert wiki.get(project.slug).sections[0]["key"] == "people_organizations"


def test_project_role_placement_requires_person_owner_and_one_project(tmp_path):
    artifacts, _, _, _, project = setup_store(tmp_path)
    role = claim("claim-role", "Priya Raman leads Mycelium.", "relationship")
    role.predicate = "project_role"
    artifacts.save_claim(role)

    with pytest.raises(ValueError, match="Person or You owner"):
        artifacts.save_placement(ClaimPlacement(
            claim_id=role.claim_id,
            owner_entity_id=project.entity_id,
            section_key="people_organizations",
            linked_entity_ids=[],
            status="placed",
            reason="invalid role",
            created_at="2026-08-12T10:00:00-07:00",
            updated_at="2026-08-12T10:00:00-07:00",
            relationship_kind="project_role",
        ))


def test_ordinary_linked_fact_is_not_copied_to_linked_page(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    person = artifacts.create_entity("person", "Priya Raman")
    status = claim("claim-status", "Priya Raman reviewed Mycelium once.", "event")
    place(artifacts, status, person, "timeline", links=[project.entity_id])

    materializer.regenerate({person.entity_id, project.entity_id})

    assert "reviewed Mycelium" in wiki.get(person.slug).content
    assert "reviewed Mycelium" not in wiki.get(project.slug).content


def test_removing_project_role_regenerates_both_endpoint_views(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    person = artifacts.create_entity("person", "Priya Raman")
    role = claim("claim-role", "Priya Raman leads Mycelium.", "relationship")
    role.predicate = "project_role"
    role.about = [
        {"entity": "Priya Raman", "role": "subject"},
        {"entity": "Mycelium", "role": "project"},
    ]
    place(artifacts, role, person, "shared_projects", links=[project.entity_id])
    materializer.regenerate({person.entity_id})

    role.status = "superseded"
    artifacts.save_claim(role)
    result = materializer.regenerate({person.entity_id})

    assert set(result.updated_slugs) == {person.slug, project.slug}
    assert "Priya Raman leads Mycelium" not in wiki.get(person.slug).content
    assert "Priya Raman leads Mycelium" not in wiki.get(project.slug).content


def test_moving_project_role_updates_old_and_new_project_views(tmp_path):
    artifacts, wiki, materializer, _, old_project = setup_store(tmp_path)
    new_project = artifacts.create_entity("project", "MnemOS")
    person = artifacts.create_entity("person", "Priya Raman")
    role = claim("claim-role", "Priya Raman leads the memory project.", "relationship")
    role.predicate = "project_role"
    role.about = [
        {"entity": "Priya Raman", "role": "subject"},
        {"entity": "Mycelium", "role": "project"},
    ]
    place(artifacts, role, person, "shared_projects", links=[old_project.entity_id])
    materializer.regenerate({person.entity_id})
    service = EntityCurationService(artifacts, wiki, materializer)

    service.move_claim(
        role.claim_id,
        person.entity_id,
        "shared_projects",
        linked_entity_ids=[new_project.entity_id],
    )

    assert "leads the memory project" not in wiki.get(old_project.slug).content
    assert "leads the memory project" in wiki.get(new_project.slug).content
    person_fact = wiki.get(person.slug).sections[0]["items"][0]
    assert person_fact["links"][0]["entity_id"] == new_project.entity_id


def test_pending_conflict_is_withheld_from_authoritative_section(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    old = claim("claim-old", "Mycelium uses SQLite.")
    new = claim("claim-new", "Mycelium does not use SQLite.")
    place(artifacts, old, project, "current_status")
    place(artifacts, new, project, "current_status")
    artifacts.save_reconsolidation_proposal(ReconsolidationProposal(
        proposal_id="recon-1",
        incoming_claim_id=new.claim_id,
        target_claim_id=old.claim_id,
        proposed_relation="contradicts",
        explanation="Conflicting current state",
        confidence=0.9,
        dream_run_id="dream-1",
        created_at="2026-08-12T10:00:00-07:00",
        affected_entity_ids=[project.entity_id],
    ))

    materializer.regenerate({project.entity_id})
    page = wiki.get(project.slug)

    assert [section["key"] for section in page.sections] == ["needs_review"]
    assert {item["text"] for item in page.sections[0]["items"]} == {old.text, new.text}
    assert all(not item["authoritative"] for item in page.sections[0]["items"])


def test_merge_reassigns_claims_and_keeps_redirect_identity(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    duplicate = artifacts.create_entity("project", "MnemOS")
    place(artifacts, claim("claim-1", "MnemOS is a personal memory system."), duplicate, "overview")
    materializer.regenerate({project.entity_id, duplicate.entity_id})
    service = EntityCurationService(artifacts, wiki, materializer)

    service.merge(duplicate.entity_id, project.entity_id)

    assert artifacts.get_entity(duplicate.entity_id).status == "merged"
    assert artifacts.get_entity(duplicate.entity_id).merged_into_entity_id == project.entity_id
    assert artifacts.get_placement("claim-1").owner_entity_id == project.entity_id
    assert wiki.exists(project.slug)
    assert not wiki.exists(duplicate.slug)


def test_manual_placement_moves_claim_between_short_term_and_canonical_memory(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    item = claim("claim-1", "Mycelium needs a claim editor.", "plan")
    artifacts.save_claim(item)
    service = EntityCurationService(artifacts, wiki, materializer)

    service.move_claim(item.claim_id, project.entity_id, "next_steps_deadlines")

    assert artifacts.get_claim(item.claim_id).dream_disposition == "routed"
    assert artifacts.memory_tier(item.claim_id) == "canonical"
    assert artifacts.active_scope_decision(item.claim_id).origin == "manual"
    assert artifacts.facts_for_claim(item.claim_id)[0].owner_entity_id == project.entity_id

    service.move_claim(item.claim_id, None, None, reason="Needs more context")

    assert artifacts.get_claim(item.claim_id).dream_disposition == "deferred"
    assert artifacts.memory_tier(item.claim_id) == "short_term"
    assert artifacts.active_scope_decision(item.claim_id).owner_entity_id is None
    assert artifacts.facts_for_claim(item.claim_id) == []


def test_manual_fact_group_edit_and_split_preserve_claims(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    first = claim("claim-first", "Mycelium stores claims as plaintext.")
    second = claim("claim-second", "Mycelium keeps exact source references.")
    place(artifacts, first, project, "overview")
    place(artifacts, second, project, "overview")
    materializer.regenerate({project.entity_id})
    service = FactCurationService(artifacts, materializer)

    grouped = service.group(
        ["fact-claim-first", "fact-claim-second"],
        "Mycelium stores plaintext claims with exact source references.",
        reason="User combined complementary facts",
    ).facts[0]
    service.edit(
        grouped.fact_id,
        "Mycelium keeps plaintext claims and exact evidence references.",
        reason="User refined the wording",
    )
    split = service.split(
        grouped.fact_id,
        [
            {"claim_ids": [first.claim_id], "text": first.text},
            {"claim_ids": [second.claim_id], "text": second.text},
        ],
        reason="User separated the facts",
    )

    assert len(split.facts) == 2
    assert {claim.claim_id for claim in artifacts.list_claims()} >= {
        first.claim_id, second.claim_id
    }
    assert first.text in wiki.get(project.slug).content
    assert second.text in wiki.get(project.slug).content


def test_clear_projection_preserves_claims_and_removes_legacy_assignment(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    item = claim("claim-1", "Mycelium is transparent.")
    artifacts.save_claim(item)
    path = artifacts.claims_dir / "claim-1.json"
    text = path.read_text()
    path.write_text(text.replace('"links": [],', '"links": [],\n  "page_slugs": ["mycelium"],'))

    counts = artifacts.clear_projection()

    assert counts["legacy_claim_assignments_removed"] == 1
    assert counts["claims_requeued"] == 1
    assert artifacts.get_claim("claim-1").text == item.text
    assert artifacts.get_claim("claim-1").dream_disposition == "pending"


@pytest.mark.parametrize(
    ("entity_type", "claim_type", "section", "heading"),
    [
        ("series", "event", "occurrences", "Occurrences"),
        ("artifact", "state", "current_state", "Current State"),
    ],
)
def test_new_ontology_types_materialize_in_their_own_sections(
    tmp_path, entity_type, claim_type, section, heading
):
    artifacts, wiki, materializer, _, _ = setup_store(tmp_path)
    entity = artifacts.create_entity(entity_type, f"Test {entity_type.title()}")
    item = claim(f"claim-{entity_type}", "The subject has useful memory.", claim_type)
    assert default_section(entity_type, item) == section
    place(artifacts, item, entity, section)

    materializer.regenerate({entity.entity_id})

    page = wiki.get(entity.slug)
    assert page.page_type == entity_type
    assert f"## {heading}" in page.content
