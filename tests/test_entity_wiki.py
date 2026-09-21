from tests.extraction_support import stored_time
from dataclasses import replace
import pytest
from mycelium.artifacts import (
    ArtifactStore,
    ClaimEntityReference,
    ClaimPlacement,
    ClaimProvenance,
    ClaimScopeDecision,
    ConsolidatedFact,
    EntityEncounter,
    EntityResolutionDecision,
    IdentityWorkUnit,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
    OrganizationProposal,
    ReconsolidationProposal,
    ScopeCohort,
)
from mycelium.config import Config
from mycelium.materialization import PageMaterializer
from mycelium.organization import EntityCurationService, FactCurationService
from mycelium.store import WikiStore


def claim(
    claim_id: str,
    text: str,
    claim_type: str = "state",
    modality: str = "speech",
    *,
    facets: dict | None = None,
):
    return MemoryClaim(
        claim_id=claim_id,
        text=text,
        about=[{"entity": "Mycelium"}],
        provenance=[ClaimProvenance("source-1", [f"source-1#{claim_id}"])],
        recorded_at="2026-08-12T10:00:00-07:00",
        claim_type=claim_type,
        evidence_modality=modality,
        confidence=0.9,
        facets=facets or {},
    )


def setup_store(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    wiki = WikiStore(tmp_path / "wiki")
    materializer = PageMaterializer(wiki, artifacts, Config.defaults())
    you = artifacts.create_entity("you", "You")
    project = artifacts.create_entity("project", "Mycelium")
    return (artifacts, wiki, materializer, you, project)


def place(artifacts, item, owner, section, *, links=None):
    try:
        source = artifacts.get_source("source-1")
    except FileNotFoundError:
        source = SourceDocument("source-1", "agent_conversation", "session", item.recorded_at, None, [], [])
    source.segments.append(SourceSegment(item.provenance[0].segment_ids[0], len(source.segments), item.text))
    artifacts.save_source(source)
    artifacts.save_claim(item)
    artifacts.save_placement(
        ClaimPlacement(
            claim_id=item.claim_id,
            owner_entity_id=owner.entity_id,
            section_key=section,
            linked_entity_ids=list(links or []),
            status="placed",
            reason="test",
            created_at="2026-08-12T10:00:00-07:00",
            updated_at="2026-08-12T10:00:00-07:00",
            relationship_kind="project_role"
            if item.predicate == "project_role"
            else None,
            page_sections={
                owner.entity_id: section,
                **(
                    {entity_id: "people_organizations" for entity_id in links or []}
                    if item.predicate == "project_role"
                    else {}
                ),
            },
        )
    )
    artifacts.save_consolidated_fact(
        ConsolidatedFact(
            fact_id=f"fact-{item.claim_id}",
            text=item.text,
            member_claim_ids=[item.claim_id],
            owner_entity_id=owner.entity_id,
            section_key=section,
            state="current",
            linked_entity_ids=list(links or []),
            synthesis_origin="claim",
            confidence=item.confidence,
            reason="test",
            created_at="2026-08-12T10:00:00-07:00",
            updated_at="2026-08-12T10:00:00-07:00",
        )
    )


def test_entity_ids_survive_rename_and_slug_is_unique(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    service = EntityCurationService(artifacts, wiki, materializer)
    place(
        artifacts,
        claim("claim-1", "Mycelium has a transparent memory store."),
        project,
        "overview",
    )
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
    assert {section["key"] for section in page.sections} == {"current_status", "research_references"}
    fact = next(s for s in page.sections if s["key"] == "current_status")["items"][0]
    assert fact["claim_ids"] == ["claim-status"]
    assert fact["sources"][0]["segment_ids"] == ["source-1#claim-status"]
    assert "external research" in next(s for s in page.sections if s["key"] == "research_references")["items"][0]["qualifiers"]


def test_timeline_uses_normalized_time_and_markdown_cites_exact_evidence(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    later = claim(
        "claim-later",
        "The launch review is next Friday.",
        "event",
        facets=stored_time('source-1#claim-later', 'next Friday', {'kind':'day_offset','days':9}, '2026-08-12', target='Scheduled event'),
    )
    earlier = claim(
        "claim-earlier",
        "The planning session is tomorrow.",
        "event",
        facets=stored_time('source-1#claim-earlier', 'tomorrow', {'kind':'day_offset','days':1}, '2026-08-12', target='Scheduled event'),
    )
    place(artifacts, later, project, "timeline")
    place(artifacts, earlier, project, "timeline")
    materializer.regenerate({project.entity_id})
    page = wiki.get(project.slug)
    items = page.sections[0]["items"]
    assert [item["fact_id"] for item in items] == [
        "fact-claim-earlier",
        "fact-claim-later",
    ]
    assert items[0]["event_time"] == "2026-08-13"
    assert items[0]["temporal_evidence"][0]["expression"] == "tomorrow"
    assert "event time for Scheduled event: 2026-08-13" in items[0]["qualifiers"]
    assert "[^e1]" in page.content
    assert "[^e1]: `source-1` · `source-1#claim-earlier`" in page.content


def test_you_page_omits_link_only_recent_changes(tmp_path):
    artifacts, wiki, materializer, you, project = setup_store(tmp_path)
    place(
        artifacts,
        claim("claim-status", "Mycelium is in active development."),
        project,
        "current_status",
    )
    materializer.regenerate({project.entity_id, you.entity_id})
    page = wiki.get(you.slug)
    assert "recent_changes" not in {section["key"] for section in page.sections}


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
    assert {person.slug, project.slug} <= set(result.changed_pages)
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
    assert person_fact["projection"] == "canonical"
    assert project_fact["projection"] == "shared_endpoint"
    assert person_fact["links"][0]["entity_id"] == project.entity_id
    assert project_fact["links"][0]["entity_id"] == person.entity_id
    assert wiki.get(person.slug).sections[0]["key"] == "shared_projects"
    assert wiki.get(project.slug).sections[0]["key"] == "shared_projects"




def test_explicit_shared_destination_displays_the_same_item(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    person = artifacts.create_entity("person", "Priya Raman")
    status = claim("claim-status", "Priya Raman reviewed Mycelium once.", "event")
    place(artifacts, status, person, "timeline", links=[project.entity_id])
    materializer.regenerate({person.entity_id, project.entity_id})
    assert "reviewed Mycelium" in wiki.get(person.slug).content
    assert "reviewed Mycelium" in wiki.get(project.slug).content


def test_links_follow_destination_lifecycle_and_leave_canonical_references_available(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    person = artifacts.create_entity("person", "Rae")
    mention = claim("mention", "Rae reviewed the project.")
    place(artifacts, mention, person, "timeline", links=[project.entity_id])
    materializer.regenerate({person.entity_id, project.entity_id})

    def shown_links():
        return [link for section in wiki.get(person.slug).sections
                for item in section["items"] for link in item.get("links", [])]

    assert shown_links() and wiki.exists(project.slug)
    assert artifacts.get_consolidated_fact("fact-mention").linked_entity_ids == [project.entity_id]

    artifacts.save_entity(replace(project, title="Revised project name"))
    renamed = materializer.regenerate({project.entity_id})
    assert person.slug in renamed.updated_slugs
    assert shown_links()[0]["title"] == "Revised project name"

    artifacts.save_entity(replace(artifacts.get_entity(project.entity_id), status="archived"))
    removed = materializer.regenerate({project.entity_id})
    assert project.slug in removed.deleted_slugs and person.slug in removed.updated_slugs
    assert not shown_links() and f"[[{project.slug}]]" not in wiki.get(person.slug).content
    assert artifacts.get_consolidated_fact("fact-mention").linked_entity_ids == [project.entity_id]
    version = wiki.get(person.slug).version
    unchanged = materializer.regenerate({person.entity_id, project.entity_id})
    assert not unchanged.changed_pages and wiki.get(person.slug).version == version


def test_pages_created_together_can_link_to_later_rendered_destinations(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    person = artifacts.create_entity("person", "Rae")
    assert person.entity_id < project.entity_id
    place(artifacts, claim("mention", "Rae reviewed the project."), person, "timeline",
          links=[project.entity_id])
    place(artifacts, claim("context", "The project organizes local records."), project, "overview")
    result = materializer.regenerate({person.entity_id, project.entity_id})
    assert {person.slug, project.slug} <= result.created_slugs
    assert f"[[{project.slug}]]" in wiki.get(person.slug).content
    for page in wiki.list_all():
        assert all(wiki.exists(edge.target) for edge in page.related)
        for section in page.sections:
            for item in section["items"]:
                if item["kind"] == "link":
                    assert wiki.exists(item["slug"])
                assert all(wiki.exists(link["slug"]) for link in item.get("links", []))


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
    assert result.deleted_slugs == {person.slug, project.slug}
    assert not wiki.exists(person.slug)
    assert not wiki.exists(project.slug)


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
    FactCurationService(artifacts, materializer).move("fact-claim-role", person.entity_id,
        "shared_projects", linked_entity_ids=[new_project.entity_id], reason="Manual move")
    assert not wiki.exists(old_project.slug)
    assert "leads the memory project" in wiki.get(new_project.slug).content
    person_fact = wiki.get(person.slug).sections[0]["items"][0]
    assert person_fact["links"][0]["entity_id"] == new_project.entity_id


def test_pending_conflict_stays_visible_in_its_section(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    old = claim("claim-old", "Mycelium uses SQLite.")
    new = claim("claim-new", "Mycelium does not use SQLite.")
    place(artifacts, old, project, "current_status")
    place(artifacts, new, project, "current_status")
    artifacts.save_reconsolidation_proposal(
        ReconsolidationProposal(
            proposal_id="recon-1",
            incoming_claim_ids=[new.claim_id],
            target_claim_ids=[old.claim_id],
            proposed_relation="contradicts",
            explanation="Conflicting current state",
            confidence=0.9,
            dream_run_id="dream-1",
            created_at="2026-08-12T10:00:00-07:00",
            affected_entity_ids=[project.entity_id],
        )
    )
    materializer.regenerate({project.entity_id})
    page = wiki.get(project.slug)
    assert [section["key"] for section in page.sections] == ["current_status"]
    assert {item["text"] for item in page.sections[0]["items"]} == {old.text, new.text}
    assert all((not item["authoritative"] for item in page.sections[0]["items"]))
    assert all(
        (
            item["reconciliation_proposal_ids"] == ["recon-1"]
            for item in page.sections[0]["items"]
        )
    )


def test_merge_reassigns_claims_and_keeps_redirect_identity(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    duplicate = artifacts.create_entity("project", "MnemOS")
    place(
        artifacts,
        claim("claim-1", "MnemOS is a personal memory system."),
        duplicate,
        "overview",
    )
    materializer.regenerate({project.entity_id, duplicate.entity_id})
    service = EntityCurationService(artifacts, wiki, materializer)
    service.merge(duplicate.entity_id, project.entity_id)
    assert artifacts.get_entity(duplicate.entity_id).status == "merged"
    assert (
        artifacts.get_entity(duplicate.entity_id).merged_into_entity_id
        == project.entity_id
    )
    assert artifacts.get_consolidated_fact("fact-claim-1").owner_entity_id == project.entity_id
    assert wiki.exists(project.slug)
    assert not wiki.exists(duplicate.slug)


@pytest.mark.parametrize("merge_into_user", [False, True])
def test_merge_redirects_every_live_entity_reference_and_preserves_history(
    tmp_path, merge_into_user
):
    artifacts, wiki, materializer, you, _ = setup_store(tmp_path)
    source = artifacts.create_entity("person", "Ava Duplicate")
    target = you if merge_into_user else artifacts.create_entity("person", "Ava")
    item = claim("claim-merge", "Ava coordinates the launch.")
    other = claim("claim-other", "The launch begins next week.")
    section = "profile"
    place(artifacts, item, source, section)
    artifacts.save_claim(other)
    artifacts.save_entity_reference(
        ClaimEntityReference(
            reference_id="ref-source",
            claim_id=item.claim_id,
            role="subject",
            surface="Ava",
            entity_id=source.entity_id,
            confidence=0.9,
            reason="fixture",
            origin="scope",
            dream_run_id="dream-1",
            status="active",
            created_at="2026-08-12T10:00:00-07:00",
        )
    )
    artifacts.save_entity_resolution_decision(
        EntityResolutionDecision(
            decision_id="decision-source",
            decision_type="entity_creation",
            entity_id=source.entity_id,
            proposed_entity_type="person",
            proposed_title="Ava Duplicate",
            source_ids=["source-1"],
            supporting_claim_ids=[item.claim_id],
            supporting_segment_ids=["source-1#seg-1"],
            confidence=0.9,
            reason="fixture",
            review_state="accepted",
            dream_run_id="dream-1",
            created_at="2026-08-12T10:00:00-07:00",
        )
    )
    artifacts.save_encounter(
        EntityEncounter(
            encounter_id="encounter-source",
            entity_id=source.entity_id,
            source_id="source-1",
            raw_log_entry_id=None,
            occurred_at="2026-08-12",
            title="Launch meeting",
            created_at="2026-08-12T10:00:00-07:00",
        )
    )
    artifacts.save_scope_cohort(
        ScopeCohort(
            cohort_id="cohort-source",
            dream_run_id="dream-1",
            claim_ids=[item.claim_id],
            source_ids=["source-1"],
            revision_entity_ids=[source.entity_id],
            created_at="2026-08-12T10:00:00-07:00",
        )
    )
    artifacts.save_scope_decision(
        ClaimScopeDecision(
            decision_id="scope-source",
            claim_id=item.claim_id,
            owner_entity_id=source.entity_id,
            section_key=section,
            linked_entity_ids=[],
            supporting_claim_ids=[item.claim_id],
            confidence=0.9,
            reason="fixture",
            origin="automatic",
            dream_run_id="dream-1",
            status="active",
            created_at="2026-08-12T10:00:00-07:00",
        )
    )
    artifacts.save_organization_proposal(
        OrganizationProposal(
            proposal_id="organization-source",
            proposal_type="assign_claim",
            explanation="fixture",
            confidence=0.7,
            created_at="2026-08-12T10:00:00-07:00",
            claim_id=other.claim_id,
            proposed_owner_entity_id=source.entity_id,
            proposed_section_key=section,
        )
    )
    artifacts.save_reconsolidation_proposal(
        ReconsolidationProposal(
            proposal_id="recon-source",
            incoming_claim_ids=[item.claim_id],
            target_claim_ids=[other.claim_id],
            proposed_relation="contradicts",
            explanation="fixture",
            confidence=0.7,
            dream_run_id="dream-1",
            created_at="2026-08-12T10:00:00-07:00",
            affected_entity_ids=[source.entity_id],
        )
    )
    artifacts.save_identity_work_unit(
        IdentityWorkUnit(
            unit_id="unit-source",
            claim_ids=[item.claim_id],
            source_ids=["source-1"],
            status="pending",
            entity_plan={"resolved_entity_id": source.entity_id},
        )
    )
    materializer.regenerate({source.entity_id, target.entity_id})
    EntityCurationService(artifacts, wiki, materializer).merge(
        source.entity_id, target.entity_id
    )
    original_reference = artifacts.get_entity_reference("ref-source")
    assert original_reference.status == "superseded"
    active_references = artifacts.list_entity_references(status="active")
    assert [reference.entity_id for reference in active_references] == [
        target.entity_id
    ]
    assert (
        artifacts.get_entity_resolution_decision("decision-source").entity_id
        == target.entity_id
    )
    assert artifacts.get_encounter("encounter-source").entity_id == target.entity_id
    assert artifacts.get_scope_cohort("cohort-source").revision_entity_ids == [
        target.entity_id
    ]
    assert (
        artifacts.active_scope_decision(item.claim_id).owner_entity_id
        == target.entity_id
    )
    assert (
        artifacts.get_organization_proposal(
            "organization-source"
        ).proposed_owner_entity_id
        == target.entity_id
    )
    assert artifacts.get_reconsolidation_proposal(
        "recon-source"
    ).affected_entity_ids == [target.entity_id]
    assert (
        artifacts.get_identity_work_unit("unit-source").entity_plan[
            "resolved_entity_id"
        ]
        == target.entity_id
    )


def test_manual_curation_rejects_inactive_entity_endpoints(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    archived = artifacts.create_entity("project", "Archived Project")
    archived.status = "archived"
    artifacts.save_entity(archived)
    item = claim("claim-inactive-owner", "The project has a plan.", "plan")
    artifacts.save_claim(item)
    with pytest.raises(ValueError, match="active owner"):
        EntityCurationService(artifacts, wiki, materializer).move_claim(
            item.claim_id,
            archived.entity_id,
            "objective",
        )
    assert artifacts.placement_for_claim(item.claim_id) is None
    assert artifacts.get_entity(project.entity_id).status == "active"






def test_manual_fact_group_and_split_preserve_claims(tmp_path):
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
        first.claim_id,
        second.claim_id,
    }
    assert first.text in wiki.get(project.slug).content
    assert second.text in wiki.get(project.slug).content


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
    place(artifacts, item, entity, section)
    materializer.regenerate({entity.entity_id})
    page = wiki.get(entity.slug)
    assert page.page_type == entity_type
    assert f"## {section}" in page.content
