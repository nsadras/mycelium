from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from mycelium.artifacts import (
    ArtifactStore,
    ClaimEntityReference,
    ClaimProvenance,
    EpisodeManifest,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.config import Config
from mycelium.consolidation import ClaimEvidence
from mycelium.dream import DreamProcess
from mycelium.models import LogEntry
from mycelium.store import LogStore, WikiStore
from mycelium.structured_outputs import (
    CohortScopePlanOutput,
    cohort_scope_output_model,
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


def assignment(
    owner: str = "",
    *,
    disposition: str = "canonical",
    links: list[str] | None = None,
    supporting: list[str] | None = None,
    reason: str = "The cohort establishes this scope.",
) -> dict:
    value = {
        "disposition": disposition,
        "supporting_claims": list(supporting or []),
        "confidence": 0.9,
        "reason": reason,
    }
    if disposition == "canonical":
        value.update({
            "owner_entity": owner,
            "linked_entities": list(links or []),
        })
    return value


def scope_candidate(
    candidate_id: str,
    title: str,
    entity_type: str,
    supporting: list[str],
    *,
    independent: bool = True,
    basis: str | None = None,
    supporting_participants: list[str] | None = None,
) -> dict:
    bases = {
        "topic": "intentional_topic", "project": "project_continuity",
        "person": "durable_person", "organization": "lasting_organization",
        "place": "lasting_place", "event": "substantial_event",
    }
    return {
        "candidate_id": candidate_id,
        "title": title,
        "entity_type": entity_type,
        "aliases": [],
        "creation_basis": basis or bases[entity_type],
        "supporting_claims": supporting,
        "supporting_participants": list(supporting_participants or []),
        "independent_scope": independent,
        "confidence": 0.9,
        "reason": "The cited cohort establishes an independently useful page.",
    }


def scope_plan(
    assignments: dict[str, dict],
    candidates: list[dict] | None = None,
    participants: dict[str, dict] | None = None,
) -> dict:
    return {
        "candidates": list(candidates or []),
        "assignments": assignments,
        "participants": dict(participants or {}),
    }


def participant(entity: str) -> dict:
    return {
        "entity_type": "you" if entity == "you" else "person",
        "entity": entity,
        "confidence": 0.9,
        "reason": "The cohort resolves this source participant to this entity.",
    }


def new_scope(
    alias: str, title: str, entity_type: str = "topic", *, supporting: list[str] | None = None
) -> dict:
    support = list(supporting or [alias])
    return scope_plan(
        {alias: assignment("N001", supporting=support)},
        [scope_candidate("N001", title, entity_type, support)],
    )


def you_scope(alias: str = "C001") -> dict:
    return scope_plan({alias: assignment("you", supporting=[alias])})


def test_cohort_scope_contract_rejects_extra_fields():
    valid = scope_plan({"C001": assignment("you")})
    assert CohortScopePlanOutput.model_validate(valid).assignments["C001"].owner_entity == "you"
    with pytest.raises(ValidationError):
        CohortScopePlanOutput.model_validate({**valid, "routes": []})
    with pytest.raises(ValidationError):
        CohortScopePlanOutput.model_validate(scope_plan({"C001": assignment()}))


def test_runtime_cohort_contract_requires_every_exact_alias():
    output_model = cohort_scope_output_model(["C001", "C002"])
    valid = scope_plan({
        "C001": assignment("you"),
        "C002": assignment(disposition="deferred"),
    })
    assert set(output_model.model_validate(valid).model_dump()["assignments"]) == {
        "C001", "C002"
    }
    with pytest.raises(ValidationError):
        output_model.model_validate(scope_plan({"C001": assignment("you")}))


def test_runtime_cohort_contract_requires_participant_resolution():
    output_model = cohort_scope_output_model(["C001"], {"P001": "user"})
    valid = scope_plan(
        {"C001": assignment("you")},
        participants={"P001": participant("you")},
    )

    parsed = output_model.model_validate(valid).model_dump()

    assert parsed["participants"]["P001"]["entity"] == "you"
    with pytest.raises(ValidationError):
        output_model.model_validate(scope_plan({"C001": assignment("you")}))


def test_scope_evidence_preserves_extracted_roles_and_stable_references(tmp_path):
    dream, _, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    item = add_claim(
        artifacts, source, text="A relative supports a recurring endeavor.",
        about="A relative", claim_type="relationship",
    )
    item.about = [
        {"entity": "A relative", "role": "subject"},
        {"entity": "Recurring endeavor", "role": "owner"},
    ]
    artifacts.save_claim(item)
    artifacts.save_entity_reference(ClaimEntityReference(
        reference_id="ref-test",
        claim_id=item.claim_id,
        role="context",
        surface="Recurring endeavor",
        entity_id="you",
        confidence=0.9,
        reason="Structured test reference.",
        origin="scope",
        dream_run_id="dream-test",
        status="active",
        created_at="2026-08-04T10:00:00-07:00",
    ))

    rendered = dream.router._format_evidence(
        {"C001": ClaimEvidence(item, source)}, {}
    )

    assert "'A relative'[role=subject]" in rendered
    assert "'Recurring endeavor'[role=owner]" in rendered
    assert "stable_entity_references=context:you" in rendered


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
        tmp_path, llm_response=new_scope("C001", "Memory Design")
    )
    entry, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts, source, text="Memory Design favors deterministic views.",
        about="Memory Design", claim_type="plan",
    )

    report = await dream.run()

    assert report.pages_created == 1
    assert report.entries_consolidated == 1
    assert report.completed_source_ids == [entry.entry_id]
    page = wiki.get("memory-design")
    assert "## Why It Matters" in page.content
    assert claim.text in page.content
    assert page.tags == []
    assert artifacts.get_placement(claim.claim_id).owner_entity_id == "topic-memory-design"
    fact = artifacts.list_consolidated_facts()[0]
    assert fact.member_claim_ids == [claim.claim_id]
    assert fact.text == claim.text
    scope = artifacts.active_scope_decision(claim.claim_id)
    assert scope is not None
    assert scope.owner_entity_id == "topic-memory-design"
    assert scope.origin == "automatic"
    entity = artifacts.get_entity("topic-memory-design")
    assert entity.materialization_state == "materialized"
    identity = artifacts.list_entity_resolution_decisions(entity_id=entity.entity_id)
    assert identity[0].decision_type == "entity_creation"
    assert identity[0].supporting_claim_ids == [claim.claim_id]
    references = artifacts.list_entity_references(
        claim_id=claim.claim_id, status="active"
    )
    assert {(item.role, item.entity_id) for item in references} == {
        ("context", None),
        ("canonical_owner", entity.entity_id),
    }
    assert next(item for item in references if item.role == "context").surface == "Memory Design"
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
    llm.call_structured.return_value = scope_plan({
        "C001": assignment(
            disposition="deferred",
            reason="More episodic context is required.",
        )
    })

    report = await dream.run()

    assert report.completed_source_ids == [entry.entry_id]
    assert logs.get(entry.entry_id).consolidated is True
    assert artifacts.get_claim(claim.claim_id).dream_disposition == "deferred"
    assert artifacts.get_placement(claim.claim_id).status == "deferred"
    assert [page.slug for page in wiki.list_all()] == ["you"]


@pytest.mark.asyncio
async def test_source_policy_exclusion_is_typed_and_not_canonical_memory(tmp_path):
    dream, llm, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    entry, source = add_source(logs, artifacts)
    source.segments[0].speaker = "Assistant"
    source.segments[0].role = "assistant"
    artifacts.save_source(source)
    claim = add_claim(
        artifacts,
        source,
        text="A speculative assistant suggestion.",
        role="assistant",
    )

    report = await dream.run()

    assert report.completed_source_ids == [entry.entry_id]
    llm.call_structured.assert_not_awaited()
    assert artifacts.get_claim(claim.claim_id).dream_disposition == "excluded_source_policy"
    assert artifacts.memory_tier(claim.claim_id) == "source"
    records = artifacts.list_retention_records(claim_id=claim.claim_id)
    assert [(record.reason, record.policy_origin) for record in records] == [
        ("assistant_unadopted", "source_structure")
    ]
    assert artifacts.placement_for_claim(claim.claim_id) is None


@pytest.mark.asyncio
async def test_ineligible_identity_is_known_before_it_has_a_page(tmp_path):
    dream, _, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(
        logs, artifacts, source_type="tool_observation", suffix="tool"
    )
    claim = add_claim(
        artifacts,
        source,
        text="A tool reported a capability for an incidental library.",
        claim_type="observation",
        about="Incidental Library",
    )
    dream.llm.call_structured.return_value = scope_plan(
        {"C001": assignment("N001", supporting=["C001"])},
        [scope_candidate(
            "N001",
            "Incidental Library",
            "topic",
            ["C001"],
            basis="topic_evidence",
        )],
    )

    await dream.run()

    entity = artifacts.get_entity("topic-incidental-library")
    assert entity.materialization_state == "provisional"
    assert not wiki.exists(entity.slug)
    assert artifacts.get_placement(claim.claim_id).status == "deferred"


@pytest.mark.asyncio
async def test_new_entity_revises_prior_you_scope_without_string_matching(tmp_path):
    dream, _, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=you_scope()
    )
    _, first_source = add_source(logs, artifacts, suffix="early")
    early = add_claim(
        artifacts,
        first_source,
        claim_id="claim-early",
        text="The user chose a local-only delivery constraint for an unnamed effort.",
        claim_type="plan",
        about="unnamed effort",
    )
    await dream.run()
    assert artifacts.get_placement(early.claim_id).owner_entity_id == "you"

    _, named_source = add_source(logs, artifacts, suffix="named")
    identity = add_claim(
        artifacts,
        named_source,
        claim_id="claim-identity",
        text="The effort is now named Atlas.",
        claim_type="identity",
        about="Atlas",
    )
    state = add_claim(
        artifacts,
        named_source,
        claim_id="claim-state",
        text="Atlas is a local desktop application.",
        claim_type="state",
        about="Atlas",
    )
    initial_support = ["C001", "C002"]
    revision_support = ["C001", "C002", "C003"]
    dream.llm.call_structured.side_effect = [
        scope_plan(
            {
                alias: assignment("N001", supporting=initial_support)
                for alias in initial_support
            },
            [
                scope_candidate(
                    "N001", "Atlas", "project", initial_support,
                    independent=True, basis="named_project",
                ),
                scope_candidate(
                    "N002", "Supporting Concept", "topic", ["C002"],
                    independent=True, basis="topic_evidence",
                ),
            ],
        ),
        scope_plan({
            alias: assignment("project-atlas", supporting=revision_support)
            for alias in revision_support
        }),
    ]

    await dream.run()

    assert artifacts.get_placement(early.claim_id).owner_entity_id == "project-atlas"
    assert artifacts.get_placement(identity.claim_id).owner_entity_id == "project-atlas"
    assert artifacts.get_placement(state.claim_id).owner_entity_id == "project-atlas"
    assert wiki.exists("atlas")
    assert len(artifacts.list_scope_decisions(claim_id=early.claim_id)) == 2
    scope_calls = [
        call for call in dream.llm.call_structured.await_args_list
        if call.kwargs.get("debug_label") == "dream-cohort-scope"
    ]
    revision_prompt = scope_calls[-1].args[1]
    assert "topic-supporting-concept" in revision_prompt


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
    llm.call_structured.return_value = scope_plan({
        "C001": assignment(
            disposition="deferred",
            reason="One mention does not yet establish a continuing project.",
        )
    })
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
    support = ["C001", "C002"]
    llm.call_structured.return_value = scope_plan(
        {
            "C001": assignment("N001", supporting=support),
            "C002": assignment("N001", supporting=support),
        },
        [scope_candidate("N001", "Ava's Adoption", "project", support)],
    )

    report = await dream.run()

    assert report.pages_created == 1
    assert artifacts.get_placement(first.claim_id).owner_entity_id == "project-ava-s-adoption"
    assert artifacts.get_placement(second.claim_id).owner_entity_id == "project-ava-s-adoption"
    page = wiki.get("ava-s-adoption")
    assert first.text in page.content
    assert second.text in page.content


@pytest.mark.asyncio
async def test_dream_rejects_incomplete_alias_coverage_claim_locally(tmp_path):
    dream, _, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response={}
    )
    entry, source = add_source(logs, artifacts)
    add_claim(
        artifacts, source, text="An unidentified system has a durable property.",
        about="unidentified system",
    )

    report = await dream.run()

    assert report.pending_source_ids == []
    assert report.completed_source_ids == [entry.entry_id]
    assert report.failures[0]["stage"] == "routing"
    assert [page.slug for page in wiki.list_all()] == ["you"]
    assert logs.get(entry.entry_id).consolidated is True
    assert artifacts.get_claim("claim-one").dream_disposition == "routing_failed"


@pytest.mark.asyncio
async def test_invalid_owner_defers_one_claim_without_blocking_its_sibling(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    first_entry, first_source = add_source(logs, artifacts, suffix="first")
    add_claim(
        artifacts,
        first_source,
        claim_id="claim-first",
        text="Tea is a durable subject.",
        about="Tea",
        claim_type="plan",
    )
    second_entry, second_source = add_source(logs, artifacts, suffix="second")
    add_claim(
        artifacts,
        second_source,
        claim_id="claim-second",
        text="Coffee is a durable subject.",
        about="Coffee",
        claim_type="plan",
    )

    llm.call_structured.return_value = scope_plan(
        {
            "C001": assignment("N999", supporting=["C001"]),
            "C002": assignment("N001", supporting=["C002"]),
        },
        [scope_candidate("N001", "Coffee", "topic", ["C002"])],
    )
    report = await dream.run()

    assert report.pending_source_ids == []
    assert report.completed_source_ids == [first_entry.entry_id, second_entry.entry_id]
    assert logs.get(first_entry.entry_id).consolidated is True
    assert logs.get(second_entry.entry_id).consolidated is True
    assert wiki.exists("coffee")
    assert artifacts.get_claim("claim-first").dream_disposition == "deferred"
    assert llm.call_structured.await_count == 1


@pytest.mark.asyncio
async def test_partial_extraction_routes_available_claims_without_repair(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=new_scope("C001", "Partial Memory")
    )
    entry, source = add_source(logs, artifacts, extraction_status="partial")
    add_claim(
        artifacts, source, text="Partial Memory has a durable property.",
        about="Partial Memory", claim_type="plan",
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
async def test_named_participants_receive_encounter_pages_and_claim_ownership(tmp_path):
    dream, _, wiki, logs, artifacts = build_dream(
        tmp_path,
        llm_response=scope_plan(
            {"C001": assignment("N001", supporting=["C001"])},
            [
                scope_candidate(
                    "N001", "Ava", "person", ["C001"],
                    supporting_participants=["P001"],
                ),
                    scope_candidate(
                        "N002", "Ben", "person", [],
                        basis="meeting_participant",
                        supporting_participants=["P002"],
                ),
            ],
            {"P001": participant("N001"), "P002": participant("N002")},
        ),
    )
    entry, source = add_source(
        logs,
        artifacts,
        source_type="multi_party_conversation",
        participants=["Ava", "Ben"],
    )
    source.segments.append(SourceSegment(
        segment_id=f"{source.source_id}#seg-0002",
        index=1,
        speaker="Ben",
        content="Ben acknowledged the discussion.",
    ))
    artifacts.save_source(source)
    add_claim(artifacts, source, text="Ava adopted a dog.")

    report = await dream.run()

    assert report.completed_source_ids == [entry.entry_id]
    assert report.failures == []
    assert artifacts.get_placement("claim-one").owner_entity_id == "person-ava"
    assert wiki.exists("ben")
    assert "Participated in a recorded meeting" in wiki.get("ben").content
    assert len(artifacts.list_encounters(entity_id="person-ben")) == 1


@pytest.mark.asyncio
async def test_undeclared_participant_identity_requires_review_without_failing_claims(tmp_path):
    dream, _, _, logs, artifacts = build_dream(
        tmp_path,
        llm_response=scope_plan(
            {"C001": assignment("you", supporting=["C001"])},
            participants={"P001": participant("person-undeclared")},
        ),
    )
    entry, source = add_source(
        logs,
        artifacts,
        source_type="meeting_transcript",
        participants=["Ava"],
    )
    add_claim(artifacts, source, text="The user recorded a durable meeting fact.")

    report = await dream.run()

    assert report.completed_source_ids == [entry.entry_id]
    assert report.failures == []
    assert artifacts.get_placement("claim-one").owner_entity_id == "you"
    decisions = artifacts.list_entity_resolution_decisions(
        review_state="review_required"
    )
    assert len(decisions) == 1
    assert decisions[0].participant_surface == "Ava"
    assert decisions[0].entity_id is None


def test_subordinate_project_and_single_tool_topic_are_not_independent_pages(tmp_path):
    dream, _, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, first_source = add_source(logs, artifacts, suffix="first")
    _, second_source = add_source(logs, artifacts, suffix="second")
    first = add_claim(
        artifacts, first_source, claim_id="claim-pilot-one",
        text="The pilot starts next week.", claim_type="plan", about="Pilot Program",
    )
    second = add_claim(
        artifacts, second_source, claim_id="claim-pilot-two",
        text="The pilot will recruit three teams.", claim_type="commitment",
        about="Pilot Program",
    )
    pilot = scope_candidate(
        "N001", "Pilot Program", "project", ["C001", "C002"],
        independent=False,
    )
    assert not dream.router._candidate_is_eligible(
        pilot,
        [ClaimEvidence(first, first_source), ClaimEvidence(second, second_source)],
    )

    _, tool_source = add_source(
        logs, artifacts, suffix="tool", source_type="tool_observation"
    )
    tool_claim = add_claim(
        artifacts, tool_source, claim_id="claim-whisperx",
        text="WhisperX supports diarization.", claim_type="observation",
        about="WhisperX",
    )
    topic = scope_candidate("N002", "WhisperX", "topic", ["C003"])
    assert not dream.router._candidate_is_eligible(
        topic, [ClaimEvidence(tool_claim, tool_source)]
    )


def test_named_project_is_admitted_from_structured_identity_and_support(tmp_path):
    dream, _, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    identity = add_claim(
        artifacts, source, claim_id="claim-name",
        text="The design initiative has a stable name.",
        claim_type="identity", about="Atlas",
    )
    description = add_claim(
        artifacts, source, claim_id="claim-description",
        text="The initiative has an approved operating constraint.",
        claim_type="state", about="Atlas",
    )
    candidate = scope_candidate(
        "N001", "Atlas", "project", ["C001", "C002"],
        independent=True,
        basis="named_project",
    )
    assert dream.router._candidate_is_eligible(
        candidate,
        [ClaimEvidence(identity, source), ClaimEvidence(description, source)],
    )
    candidate["independent_scope"] = False
    assert not dream.router._candidate_is_eligible(
        candidate,
        [ClaimEvidence(identity, source), ClaimEvidence(description, source)],
    )


@pytest.mark.asyncio
async def test_candidate_support_includes_claims_assigned_to_candidate(tmp_path):
    dream, llm, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    identity = add_claim(
        artifacts, source, claim_id="claim-name",
        text="The design initiative has a stable name.",
        claim_type="identity", about="Atlas",
    )
    description = add_claim(
        artifacts, source, claim_id="claim-description",
        text="The initiative has an approved operating constraint.",
        claim_type="state", about="Atlas",
    )
    llm.call_structured.return_value = scope_plan(
        {
            "C001": assignment("N001", supporting=["C001"]),
            "C002": assignment("N001", supporting=["C002"]),
        },
        [scope_candidate(
            "N001", "Atlas", "project", ["C001"], independent=True,
            basis="named_project",
        )],
    )

    result = await dream.router.route([
        ClaimEvidence(description, source), ClaimEvidence(identity, source),
    ])

    assert [entity.title for entity in result.new_entities] == ["Atlas"]
    assert {route.owner_entity_id for route in result.routes} == {"project-atlas"}


def test_scope_contract_rejects_model_authored_source_only():
    output_model = cohort_scope_output_model(["C001"])

    with pytest.raises(ValidationError):
        output_model.model_validate(scope_plan({
            "C001": assignment(disposition="source_only"),
        }))


@pytest.mark.asyncio
async def test_dream_dry_run_reports_but_does_not_write(tmp_path):
    dream, _, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=new_scope("C001", "Preview Page")
    )
    entry, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts, source, text="Preview Page has a durable property.",
        about="Preview Page", claim_type="plan",
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
        tmp_path, llm_response=new_scope("C001", "Stable Page")
    )
    _, source = add_source(logs, artifacts, suffix="first")
    add_claim(
        artifacts, source, claim_id="claim-first",
        text="Stable Page records a tea preference.", about="Stable Page",
        claim_type="plan",
    )
    await dream.run()

    _, source_two = add_source(logs, artifacts, suffix="second")
    add_claim(
        artifacts, source_two, claim_id="claim-second",
        text="Stable Page records a coffee preference.", about="Stable Page",
        claim_type="plan",
    )
    llm.call_structured.side_effect = [
        scope_plan({"C001": assignment("topic-stable-page", supporting=["C001"])}),
        {"decisions": [{
            "incoming_alias": "N001",
            "relation": "additive",
            "target_alias": "",
            "explanation": "A separate preference.",
            "confidence": 0.9,
        }]},
        {"facts": [
            {"claim_aliases": ["F001"], "text": "Stable Page records a tea preference.", "confidence": 0.9, "reason": "Separate preference."},
            {"claim_aliases": ["F002"], "text": "Stable Page records a coffee preference.", "confidence": 0.9, "reason": "Separate preference."},
        ]},
    ]
    report = await dream.run()

    assert report.pages_updated == 1
    page = wiki.get("stable-page")
    assert "tea preference" in page.content
    assert "coffee preference" in page.content
    assert llm.call_structured.await_count == 4


@pytest.mark.asyncio
async def test_entity_type_is_authoritative_at_creation_without_taxonomy_pass(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=new_scope("C001", "Memory Design")
    )
    entry, source = add_source(logs, artifacts)
    add_claim(
        artifacts, source, text="Memory Design favors deterministic views.",
        about="Memory Design", claim_type="plan",
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
    assert "## Why It Matters" in page.content
    assert llm.call_structured.await_count == 1


@pytest.mark.asyncio
async def test_you_entity_is_typed_without_a_taxonomy_call(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=you_scope()
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
        tmp_path, llm_response=you_scope()
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
        you_scope(),
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
async def test_invalid_reconsolidation_is_claim_local_and_source_history_completes(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=you_scope()
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
        you_scope(),
        {"decisions": []},
    ]

    report = await dream.run()

    assert report.completed_source_ids == [second_entry.entry_id]
    assert report.pending_source_ids == []
    assert report.failures[0]["stage"] == "reconsolidation"
    assert logs.get(second_entry.entry_id).consolidated is True
    assert artifacts.get_claim("claim-new").dream_disposition == "routing_failed"
    assert "no longer" not in wiki.get("you").content
    assert artifacts.list_reconsolidation_proposals() == []
