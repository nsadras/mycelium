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
    page_taxonomy_output_model,
)


def route(alias: str, page: str, page_type: str = "topic") -> dict:
    return {
        alias: {
            "page": page,
            "page_type": page_type,
        },
    }


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


def test_page_taxonomy_schema_requires_exact_aliases_and_known_types():
    output_model = page_taxonomy_output_model(["P001", "P002"])
    valid = {
        "P001": {"page_type": "person"},
        "P002": {"page_type": "project"},
    }

    assert output_model.model_validate(valid).model_dump() == valid
    for invalid in (
        {"P001": {"page_type": "person"}},
        {**valid, "P003": {"page_type": "topic"}},
        {"P001": {"page_type": "entity"}, **{"P002": valid["P002"]}},
    ):
        with pytest.raises(ValidationError):
            output_model.model_validate(invalid)


def build_dream(tmp_path, *, llm_response: dict):
    wiki = WikiStore(tmp_path / "wiki")
    logs = LogStore(tmp_path / "logs")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    llm = AsyncMock()
    llm.call_structured.return_value = llm_response
    dream = DreamProcess(llm, wiki, logs, Config.defaults(), artifacts)
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
) -> MemoryClaim:
    claim = MemoryClaim(
        claim_id=claim_id,
        text=text,
        kind="fact",
        about=[{"entity": source.participants[0] if source.participants else "The user"}],
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
        tmp_path, llm_response=route("C001", "memory-design")
    )
    entry, source = add_source(logs, artifacts)
    claim = add_claim(artifacts, source)

    report = await dream.run()

    assert report.pages_created == 1
    assert report.entries_consolidated == 1
    assert report.completed_source_ids == [entry.entry_id]
    page = wiki.get("memory-design")
    assert "## Memory" in page.content
    assert claim.text in page.content
    assert page.tags == ["page-type-topic"]
    assert artifacts.get_claim(claim.claim_id).page_slugs == ["memory-design"]
    assert logs.get(entry.entry_id).consolidated is True
    assert llm.call_structured.await_count == 2
    assert report.taxonomy_failures
    assert page.page_type is None


@pytest.mark.asyncio
async def test_dream_rejects_incomplete_alias_coverage_and_keeps_source_pending(tmp_path):
    dream, _, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response={}
    )
    entry, source = add_source(logs, artifacts)
    add_claim(artifacts, source)

    report = await dream.run()

    assert report.pending_source_ids == [entry.entry_id]
    assert report.failures[0]["stage"] == "routing"
    assert wiki.list_all() == []
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
        text="The user prefers tea.",
    )
    second_entry, second_source = add_source(logs, artifacts, suffix="second")
    add_claim(
        artifacts,
        second_source,
        claim_id="claim-second",
        text="The user prefers coffee.",
    )

    async def respond(system, user, output_type, **kwargs):
        if "claim=The user prefers tea." in user:
            return {}
        return route("C001", "coffee")

    llm.call_structured.side_effect = respond
    report = await dream.run()

    assert report.pending_source_ids == [first_entry.entry_id]
    assert report.completed_source_ids == [second_entry.entry_id]
    assert logs.get(first_entry.entry_id).consolidated is False
    assert logs.get(second_entry.entry_id).consolidated is True
    assert wiki.exists("coffee")
    assert llm.call_structured.await_count == 3


@pytest.mark.asyncio
async def test_partial_extraction_routes_available_claims_without_repair(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=route("C001", "partial-memory")
    )
    entry, source = add_source(logs, artifacts, extraction_status="partial")
    add_claim(artifacts, source)

    report = await dream.run()

    assert report.completed_source_ids == [entry.entry_id]
    assert wiki.exists("partial-memory")
    assert llm.call_structured.await_count == 2


@pytest.mark.asyncio
async def test_failed_extraction_never_falls_back_to_raw_evidence(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    entry, _ = add_source(logs, artifacts, extraction_status="failed")

    report = await dream.run()

    assert report.pending_source_ids == [entry.entry_id]
    assert report.failures[0]["stage"] == "extraction"
    assert wiki.list_all() == []
    llm.call_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_extraction_without_claims_stays_pending(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    entry, _ = add_source(logs, artifacts, extraction_status="partial")

    report = await dream.run()

    assert report.pending_source_ids == [entry.entry_id]
    assert report.failures[0]["stage"] == "extraction"
    assert wiki.list_all() == []
    llm.call_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_named_participant_claim_cannot_route_to_user_profile(tmp_path):
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

    assert report.pending_source_ids == [entry.entry_id]
    assert "Named-participant" in report.failures[0]["reason"]


@pytest.mark.asyncio
async def test_dream_dry_run_reports_but_does_not_write(tmp_path):
    dream, _, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=route("C001", "preview-page")
    )
    entry, source = add_source(logs, artifacts)
    claim = add_claim(artifacts, source)

    report = await dream.run(dry_run=True)

    assert report.pages_created == 1
    assert not wiki.exists("preview-page")
    assert logs.get(entry.entry_id).consolidated is False
    assert artifacts.get_claim(claim.claim_id).page_slugs == []
    assert artifacts.list_dream_runs() == []


@pytest.mark.asyncio
async def test_dream_regenerates_existing_page_without_rewrite_call(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=route("C001", "stable-page")
    )
    _, source = add_source(logs, artifacts, suffix="first")
    add_claim(artifacts, source, claim_id="claim-first", text="The user prefers tea.")
    await dream.run()

    _, source_two = add_source(logs, artifacts, suffix="second")
    add_claim(artifacts, source_two, claim_id="claim-second", text="The user prefers coffee.")
    llm.call_structured.side_effect = [
        route("C001", "stable-page"),
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
    assert "prefers tea" in page.content
    assert "prefers coffee" in page.content
    assert llm.call_structured.await_count == 5


@pytest.mark.asyncio
async def test_page_taxonomy_is_non_blocking_and_retries_pending_pages(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=route("C001", "memory-design")
    )
    entry, source = add_source(logs, artifacts)
    add_claim(artifacts, source)

    first = await dream.run()

    assert first.completed_source_ids == [entry.entry_id]
    assert first.taxonomy_failures
    assert wiki.get("memory-design").page_type is None

    llm.call_structured.return_value = {"P001": {"page_type": "project"}}
    second = await dream.run()

    page = wiki.get("memory-design")
    assert second.entries_consolidated == 0
    assert second.pages_updated == 1
    assert second.taxonomy_failures == []
    assert page.page_type == "project"
    assert page.title == "Memory Design"
    assert "## Key Facts" in page.content
    assert "### Design Choices" in page.content


@pytest.mark.asyncio
async def test_user_profile_taxonomy_does_not_require_an_llm_call(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=route("C001", "user-profile", "entity")
    )
    entry, source = add_source(logs, artifacts)
    add_claim(artifacts, source)

    report = await dream.run()

    assert report.completed_source_ids == [entry.entry_id]
    assert report.taxonomy_failures == []
    assert wiki.get("user-profile").page_type == "you"
    assert wiki.get("user-profile").title == "You"
    assert "## Key Facts" in wiki.get("user-profile").content
    assert "## Memory Map" in wiki.get("user-profile").content
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
        route("C001", "user-profile", "entity"),
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
    assert proposal.affected_page_slugs == ["user-profile"]
    assert artifacts.get_claim("claim-old").status == "active"
    assert artifacts.get_claim("claim-new").status == "active"
    page = wiki.get("user-profile")
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
    assert "no longer" not in wiki.get("user-profile").content
    assert artifacts.list_reconsolidation_proposals() == []
