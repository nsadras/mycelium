from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ClaimProvenance,
    MemoryClaim,
    ReconsolidationProposal,
)
from mycelium.config import Config
from mycelium.consolidation import ClaimEvidence, ClaimRouter
from mycelium.materialization import PageMaterializer
from mycelium.organization import EntityCurationService, OrganizationAuditor
from mycelium.store import WikiStore
from mycelium.artifacts import SourceDocument, SourceSegment


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


def test_deferred_claim_gets_review_suggestion_only_for_exact_unique_entity(tmp_path):
    artifacts, _, _, _, project = setup_store(tmp_path)
    item = claim("claim-1", "Mycelium needs a claim editor.", "plan")
    artifacts.save_claim(item)
    artifacts.save_placement(ClaimPlacement(
        item.claim_id, None, None, [], "deferred", "no owner", "now", "now"
    ))

    proposals = OrganizationAuditor(artifacts).audit()

    assert len(proposals) == 1
    assert proposals[0].proposal_type == "assign_claim"
    assert proposals[0].proposed_owner_entity_id == project.entity_id


def test_manual_placement_moves_claim_between_short_term_and_canonical_memory(tmp_path):
    artifacts, wiki, materializer, _, project = setup_store(tmp_path)
    item = claim("claim-1", "Mycelium needs a claim editor.", "plan")
    artifacts.save_claim(item)
    service = EntityCurationService(artifacts, wiki, materializer)

    service.move_claim(item.claim_id, project.entity_id, "next_steps_deadlines")

    assert artifacts.get_claim(item.claim_id).dream_disposition == "routed"
    assert artifacts.memory_tier(item.claim_id) == "canonical"

    service.move_claim(item.claim_id, None, None, reason="Needs more context")

    assert artifacts.get_claim(item.claim_id).dream_disposition == "deferred"
    assert artifacts.memory_tier(item.claim_id) == "short_term"


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


def test_direct_named_participants_bootstrap_person_entities(tmp_path):
    source = SourceDocument(
        source_id="meeting-1", source_type="meeting_transcript", session_id="session-1",
        recorded_at="2026-08-12T10:00:00", occurred_at=None,
        participants=["Ava", "Ben"],
        segments=[SourceSegment("meeting-1#seg-1", 0, "Ava proposed a launch.", speaker="Ava")],
    )
    item = MemoryClaim(
        "claim-1", "Ava proposed a launch.", "plan", [{"entity": "Ava"}],
        [ClaimProvenance("meeting-1", ["meeting-1#seg-1"], speaker="Ava")],
        "2026-08-12T10:00:00", claim_type="plan",
    )

    entities = ClaimRouter._participant_entities([ClaimEvidence(item, source)], [])

    assert [(entity.entity_id, entity.title) for entity in entities] == [
        ("person-ava", "Ava"), ("person-ben", "Ben")
    ]


def test_owner_grounding_rejects_tangential_context_but_accepts_title_terms(tmp_path):
    artifacts, _, _, _, project = setup_store(tmp_path)
    source = SourceDocument(
        source_id="source-1", source_type="multi_party_conversation",
        session_id="session-1", recorded_at="2026-08-12T10:00:00",
        occurred_at=None, participants=["Ava"], segments=[],
    )
    unrelated = claim("claim-1", "A bulletin board is depicted in a photo.")
    unrelated.about = [{"entity": "bulletin board"}]
    relevant = claim("claim-2", "The online Mycelium project is expanding.")

    assert not ClaimRouter._owner_is_grounded(project, unrelated, source)
    assert ClaimRouter._owner_is_grounded(project, relevant, source)


def test_discovery_preserves_explicit_qualified_surface_aliases(tmp_path):
    source = SourceDocument(
        source_id="source-1", source_type="multi_party_conversation",
        session_id="session-1", recorded_at="2026-08-12T10:00:00",
        occurred_at=None, participants=["Ava"], segments=[],
    )
    item = claim("claim-1", "Gina's online clothing store is growing.")
    item.about = [{"entity": "Gina's online clothing store", "role": "owner"}]

    aliases = ClaimRouter._surface_aliases("Clothing Store", [ClaimEvidence(item, source)])

    assert aliases == ["Gina's online clothing store"]
