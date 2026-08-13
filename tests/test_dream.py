from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    EpisodeManifest,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.config import Config
from mycelium.dream import DreamProcess
from mycelium.models import LogEntry
from mycelium.store import LogStore, WikiStore
from mycelium.structured_outputs import (
    consolidation_output_model,
    entity_discovery_output_model,
)


def route(alias: str, page: str, page_type: str = "topic") -> dict:
    if page == "user-profile":
        owner = "you"
    elif page_type == "entity":
        owner = f"person-{page}"
    elif page_type == "event":
        owner = f"event-{page}"
    else:
        owner = f"topic-{page}"
    return {
        alias: {
            "owner_entity": owner,
            "linked_entities": [],
            "reason": "The claim changes this entity.",
        },
    }


def discover(alias: str, title: str, entity_type: str = "topic") -> dict:
    bases = {
        "topic": "intentional_topic", "project": "project_continuity",
        "person": "durable_person", "organization": "lasting_organization",
        "place": "lasting_place", "event": "substantial_event",
    }
    return {alias: {
        "candidate": {
            "title": title,
            "entity_type": entity_type,
            "aliases": [],
            "creation_basis": bases[entity_type],
        },
        "reason": "The evidence establishes a durable page subject.",
    }}


def no_discovery(alias: str = "C001") -> dict:
    return {alias: {"reason": "The claim does not establish a new entity."}}


def test_consolidation_schema_requires_one_destination_for_every_exact_alias():
    output_model = consolidation_output_model(["C001", "C002"])
    valid = {
        **route("C001", "ava", "entity"),
        **route("C002", "tea", "topic"),
    }

    assert set(output_model.model_validate(valid).model_dump()) == {"C001", "C002"}
    for invalid in (
        route("C001", "ava", "entity"),
        {**valid, **route("C003", "extra")},
        {"routes": []},
        {"C001": {"page": "", "page_type": "entity"}, **route("C002", "tea")},
        {"C001": {"page": "ava"}, **route("C002", "tea")},
    ):
        with pytest.raises(ValidationError):
            output_model.model_validate(invalid)


def test_entity_discovery_allows_omitted_nulls_but_enforces_type_basis():
    output_model = entity_discovery_output_model(["C001", "C002"])
    valid = {
        "C001": {"reason": "No new entity."},
        "C002": discover("C002", "Dance Studio", "project")["C002"],
    }

    parsed = output_model.model_validate(valid).model_dump()

    assert parsed["C001"]["candidate"] is None
    assert parsed["C002"]["candidate"]["entity_type"] == "project"
    invalid = discover("C002", "Dance Studio", "project")
    invalid["C002"]["candidate"]["creation_basis"] = "durable_person"
    with pytest.raises(ValidationError):
        output_model.model_validate({"C001": {"reason": "none"}, **invalid})


def build_dream(tmp_path, *, llm_response: dict):
    wiki = WikiStore(tmp_path / "wiki")
    logs = LogStore(tmp_path / "logs")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    llm = AsyncMock()
    llm.call_structured.return_value = llm_response
    artifacts.create_entity("you", "You")
    dream = DreamProcess(llm, wiki, logs, Config.defaults(), artifacts)
    dream.materializer.regenerate({"you"})
    return dream, llm, wiki, logs, artifacts


def add_source(
    logs: LogStore,
    artifacts: ArtifactStore,
    *,
    suffix: str = "one",
    source_type: str = "agent_conversation",
    extraction_status: str = "complete",
    participants: list[str] | None = None,
) -> tuple[LogEntry, SourceDocument]:
    entry_id = f"2026-08-04#session-{suffix}"
    source_id = f"source-{suffix}"
    entry = LogEntry(
        entry_id=entry_id,
        session_id=f"session-{suffix}",
        timestamp=datetime(2026, 8, 4, 10, 0),
        content="Raw canonical transcript",
        importance=0.8,
        status="raw",
        durability="durable",
        consolidated=False,
    )
    logs.append(entry)
    source = SourceDocument(
        source_id=source_id,
        source_type=source_type,
        session_id=entry.session_id,
        recorded_at="2026-08-04T10:00:00",
        occurred_at=None,
        participants=participants or [],
        segments=[SourceSegment(
            segment_id=f"{source_id}#seg-0001",
            index=0,
            speaker=(participants or ["user"])[0],
            role="user" if source_type == "agent_conversation" else None,
            content="A durable fact",
        )],
        raw_log_entry_id=entry_id,
    )
    artifacts.save_source(source)
    artifacts.save_episode(EpisodeManifest(
        episode_id=f"episode-{suffix}",
        source_id=source_id,
        source_type=source_type,
        occurred_at=None,
        participants=participants or [],
        segment_ids=[source.segments[0].segment_id],
        extraction_status=extraction_status,
        extraction_error=("one segment uncovered" if extraction_status == "partial" else None),
    ))
    return entry, source


def add_claim(
    artifacts: ArtifactStore,
    source: SourceDocument,
    *,
    claim_id: str = "claim-one",
    text: str = "The user prefers deterministic memory views.",
    claim_type: str = "preference",
    role: str | None = "user",
    about: str | None = None,
) -> MemoryClaim:
    claim = MemoryClaim(
        claim_id=claim_id,
        text=text,
        kind="fact",
        about=[{"entity": about or (source.participants[0] if source.participants else "The user")}],
        provenance=[ClaimProvenance(
            source_id=source.source_id,
            segment_ids=[source.segments[0].segment_id],
            raw_log_entry_id=source.raw_log_entry_id,
            speaker=role,
        )],
        recorded_at=source.recorded_at,
        claim_type=claim_type,
        predicate="prefers",
        confidence=0.9,
        salience=0.8,
    )
    artifacts.save_claim(claim)
    episode = next(ep for ep in artifacts.list_episodes() if ep.source_id == source.source_id)
    episode.claim_ids.append(claim.claim_id)
    artifacts.save_episode(episode)
    return claim


@pytest.mark.asyncio
async def test_dream_routes_claim_and_materializes_deterministic_page(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=discover("C001", "Memory Design")
    )
    entry, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts, source, text="Memory Design favors deterministic views.",
        about="Memory Design",
    )

    report = await dream.run()

    assert report.pages_created == 1
    assert report.entries_consolidated == 1
    assert report.completed_source_ids == [entry.entry_id]
    page = wiki.get("memory-design")
    assert "## Preferences & Positions" in page.content
    assert claim.text in page.content
    assert page.tags == []
    assert artifacts.get_placement(claim.claim_id).owner_entity_id == "topic-memory-design"
    assert logs.get(entry.entry_id).consolidated is True
    assert llm.call_structured.await_count == 1
    assert report.taxonomy_failures == []
    assert page.page_type == "topic"


@pytest.mark.asyncio
async def test_dream_defers_claim_without_a_clear_owner_and_completes_episode(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    entry, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts,
        source,
        text="A loosely described effort may become important later.",
        about="loosely described effort",
    )
    llm.call_structured.side_effect = [
        no_discovery(),
        {"C001": {
            "owner_entity": "",
            "linked_entities": [],
            "reason": "More episodic context is required.",
        }},
    ]

    report = await dream.run()

    assert report.completed_source_ids == [entry.entry_id]
    assert logs.get(entry.entry_id).consolidated is True
    assert artifacts.get_claim(claim.claim_id).dream_disposition == "deferred"
    assert artifacts.get_placement(claim.claim_id).status == "deferred"
    assert [page.slug for page in wiki.list_all()] == ["you"]


@pytest.mark.asyncio
async def test_later_dream_discovers_page_from_claims_across_episodes(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, first_source = add_source(logs, artifacts, suffix="first")
    first = add_claim(
        artifacts,
        first_source,
        claim_id="claim-first",
        text="Ava researched agencies for adopting a child.",
        claim_type="event",
        about="Ava's adoption effort",
    )
    llm.call_structured.side_effect = [
        no_discovery(),
        {"C001": {
            "owner_entity": "",
            "linked_entities": [],
            "reason": "One mention does not yet establish a continuing project.",
        }},
    ]
    await dream.run()

    _, second_source = add_source(logs, artifacts, suffix="second")
    second = add_claim(
        artifacts,
        second_source,
        claim_id="claim-second",
        text="Ava scheduled an adoption interview.",
        claim_type="plan",
        about="Ava's adoption effort",
    )
    candidate = discover("C001", "Ava's Adoption", "project")["C001"]
    placement = {"C001": {
        "owner_entity": "project-ava-s-adoption",
        "linked_entities": [],
        "reason": "The claim advances the continuing adoption project.",
    }}
    llm.call_structured.side_effect = [
        {"C001": candidate, "C002": candidate},
        placement,
        placement,
    ]

    report = await dream.run()

    assert report.pages_created == 1
    assert artifacts.get_placement(first.claim_id).owner_entity_id == "project-ava-s-adoption"
    assert artifacts.get_placement(second.claim_id).owner_entity_id == "project-ava-s-adoption"
    page = wiki.get("ava-s-adoption")
    assert first.text in page.content
    assert second.text in page.content


@pytest.mark.asyncio
async def test_dream_rejects_incomplete_alias_coverage_and_keeps_source_pending(tmp_path):
    dream, _, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response={}
    )
    entry, source = add_source(logs, artifacts)
    add_claim(
        artifacts, source, text="An unidentified system has a durable property.",
        about="unidentified system",
    )

    report = await dream.run()

    assert report.pending_source_ids == [entry.entry_id]
    assert report.failures[0]["stage"] == "routing"
    assert [page.slug for page in wiki.list_all()] == ["you"]
    assert logs.get(entry.entry_id).consolidated is False
    assert artifacts.list_dream_runs()[0].status == "failed"


@pytest.mark.asyncio
async def test_dream_routes_sources_separately_so_one_invalid_response_is_isolated(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    first_entry, first_source = add_source(logs, artifacts, suffix="first")
    add_claim(
        artifacts,
        first_source,
        claim_id="claim-first",
        text="Tea is a durable subject.",
        about="Tea",
    )
    second_entry, second_source = add_source(logs, artifacts, suffix="second")
    add_claim(
        artifacts,
        second_source,
        claim_id="claim-second",
        text="Coffee is a durable subject.",
        about="Coffee",
    )

    async def respond(system, user, output_type, **kwargs):
        if kwargs.get("debug_label") == "dream-entity-discovery":
            return {
                "C001": {"reason": "Tea does not establish a page."},
                **discover("C002", "Coffee"),
            }
        if "claim=Tea is a durable subject." in user:
            return {}
        raise AssertionError("Coffee should route deterministically after discovery")

    llm.call_structured.side_effect = respond
    report = await dream.run()

    assert report.pending_source_ids == [first_entry.entry_id]
    assert report.completed_source_ids == [second_entry.entry_id]
    assert logs.get(first_entry.entry_id).consolidated is False
    assert logs.get(second_entry.entry_id).consolidated is True
    assert wiki.exists("coffee")
    assert llm.call_structured.await_count == 2


@pytest.mark.asyncio
async def test_partial_extraction_routes_available_claims_without_repair(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=discover("C001", "Partial Memory")
    )
    entry, source = add_source(logs, artifacts, extraction_status="partial")
    add_claim(
        artifacts, source, text="Partial Memory has a durable property.",
        about="Partial Memory",
    )

    report = await dream.run()

    assert report.completed_source_ids == [entry.entry_id]
    assert wiki.exists("partial-memory")
    assert llm.call_structured.await_count == 1


@pytest.mark.asyncio
async def test_failed_extraction_never_falls_back_to_raw_evidence(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    entry, _ = add_source(logs, artifacts, extraction_status="failed")

    report = await dream.run()

    assert report.pending_source_ids == [entry.entry_id]
    assert report.failures[0]["stage"] == "extraction"
    assert [page.slug for page in wiki.list_all()] == ["you"]
    llm.call_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_extraction_without_claims_stays_pending(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    entry, _ = add_source(logs, artifacts, extraction_status="partial")

    report = await dream.run()

    assert report.pending_source_ids == [entry.entry_id]
    assert report.failures[0]["stage"] == "extraction"
    assert [page.slug for page in wiki.list_all()] == ["you"]
    llm.call_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_named_participant_claim_is_deterministically_owned_by_person(tmp_path):
    dream, _, _, logs, artifacts = build_dream(
        tmp_path, llm_response=route("C001", "user-profile")
    )
    entry, source = add_source(
        logs,
        artifacts,
        source_type="multi_party_conversation",
        participants=["Ava", "Ben"],
    )
    add_claim(artifacts, source, text="Ava adopted a dog.")

    report = await dream.run()

    assert report.completed_source_ids == [entry.entry_id]
    assert report.failures == []
    assert artifacts.get_placement("claim-one").owner_entity_id == "person-ava"


@pytest.mark.asyncio
async def test_dream_dry_run_reports_but_does_not_write(tmp_path):
    dream, _, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=discover("C001", "Preview Page")
    )
    entry, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts, source, text="Preview Page has a durable property.",
        about="Preview Page",
    )

    report = await dream.run(dry_run=True)

    assert report.pages_created == 1
    assert not wiki.exists("preview-page")
    assert logs.get(entry.entry_id).consolidated is False
    assert artifacts.placement_for_claim(claim.claim_id) is None
    assert artifacts.list_dream_runs() == []


@pytest.mark.asyncio
async def test_dream_regenerates_existing_page_without_rewrite_call(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=discover("C001", "Stable Page")
    )
    _, source = add_source(logs, artifacts, suffix="first")
    add_claim(
        artifacts, source, claim_id="claim-first",
        text="Stable Page records a tea preference.", about="Stable Page",
    )
    await dream.run()

    _, source_two = add_source(logs, artifacts, suffix="second")
    add_claim(
        artifacts, source_two, claim_id="claim-second",
        text="Stable Page records a coffee preference.", about="Stable Page",
    )
    llm.call_structured.side_effect = [
        no_discovery(),
        {"decisions": [{
            "incoming_alias": "N001",
            "relation": "additive",
            "target_alias": "",
            "explanation": "A separate preference.",
            "confidence": 0.9,
        }]},
    ]
    report = await dream.run()

    assert report.pages_updated == 1
    page = wiki.get("stable-page")
    assert "tea preference" in page.content
    assert "coffee preference" in page.content
    assert llm.call_structured.await_count == 3


@pytest.mark.asyncio
async def test_entity_type_is_authoritative_at_creation_without_taxonomy_pass(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=discover("C001", "Memory Design")
    )
    entry, source = add_source(logs, artifacts)
    add_claim(
        artifacts, source, text="Memory Design favors deterministic views.",
        about="Memory Design",
    )

    first = await dream.run()

    assert first.completed_source_ids == [entry.entry_id]
    assert first.taxonomy_failures == []
    assert wiki.get("memory-design").page_type == "topic"

    second = await dream.run()

    page = wiki.get("memory-design")
    assert second.entries_consolidated == 0
    assert second.pages_updated == 0
    assert second.taxonomy_failures == []
    assert page.page_type == "topic"
    assert page.title == "Memory Design"
    assert "## Preferences & Positions" in page.content
    assert llm.call_structured.await_count == 1


@pytest.mark.asyncio
async def test_you_entity_is_typed_without_a_taxonomy_call(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=route("C001", "user-profile", "entity")
    )
    entry, source = add_source(logs, artifacts)
    add_claim(artifacts, source)

    report = await dream.run()

    assert report.completed_source_ids == [entry.entry_id]
    assert report.taxonomy_failures == []
    assert wiki.get("you").page_type == "you"
    assert wiki.get("you").title == "You"
    assert "## Preferences & Working Style" in wiki.get("you").content
    assert llm.call_structured.await_count == 1


@pytest.mark.asyncio
async def test_dream_persists_contradiction_proposal_and_marks_both_claims_pending(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=route("C001", "user-profile", "entity")
    )
    _, first_source = add_source(logs, artifacts, suffix="first")
    add_claim(
        artifacts,
        first_source,
        claim_id="claim-old",
        text="The user prefers tea.",
    )
    await dream.run()

    second_entry, second_source = add_source(logs, artifacts, suffix="second")
    add_claim(
        artifacts,
        second_source,
        claim_id="claim-new",
        text="The user dislikes tea.",
    )
    llm.call_structured.side_effect = [
        no_discovery(),
        {"decisions": [{
            "incoming_alias": "N001",
            "relation": "contradicts",
            "target_alias": "E001",
            "explanation": "The new preference conflicts with the existing preference.",
            "confidence": 0.94,
        }]},
    ]

    report = await dream.run()

    assert report.completed_source_ids == [second_entry.entry_id]
    assert len(report.reconsolidation_proposal_ids) == 1
    proposal = artifacts.get_reconsolidation_proposal(
        report.reconsolidation_proposal_ids[0]
    )
    assert proposal.status == "pending"
    assert proposal.incoming_claim_id == "claim-new"
    assert proposal.target_claim_id == "claim-old"
    assert proposal.proposed_relation == "contradicts"
    assert proposal.affected_entity_ids == ["you"]
    assert artifacts.get_claim("claim-old").status == "active"
    assert artifacts.get_claim("claim-new").status == "active"
    page = wiki.get("you")
    assert "prefers tea" in page.content
    assert "dislikes tea" in page.content
    assert page.content.count("pending reconciliation") == 2


@pytest.mark.asyncio
async def test_dream_fails_source_closed_when_reconsolidation_response_is_invalid(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=route("C001", "user-profile", "entity")
    )
    _, first_source = add_source(logs, artifacts, suffix="first")
    add_claim(artifacts, first_source, claim_id="claim-old")
    await dream.run()

    second_entry, second_source = add_source(logs, artifacts, suffix="second")
    add_claim(
        artifacts,
        second_source,
        claim_id="claim-new",
        text="The user no longer prefers deterministic memory views.",
    )
    llm.call_structured.side_effect = [
        route("C001", "user-profile", "entity"),
        {"decisions": []},
    ]

    report = await dream.run()

    assert report.completed_source_ids == []
    assert report.pending_source_ids == [second_entry.entry_id]
    assert report.failures[0]["stage"] == "reconsolidation"
    assert logs.get(second_entry.entry_id).consolidated is False
    assert "no longer" not in wiki.get("you").content
    assert artifacts.list_reconsolidation_proposals() == []
