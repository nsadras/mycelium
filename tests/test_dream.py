from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from mycelium.artifacts import (
    ArtifactStore,
    ClaimEntityReference,
    ClaimProvenance,
    EntityResolutionDecision,
    EpisodeManifest,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.config import Config
from mycelium.consolidation import ClaimEvidence, ClaimRouter, slugify
from mycelium.consolidation_models import ClaimRoute, RoutingResult
from mycelium.consolidation_formatting import RoutingFormatter
from mycelium.dream import DreamProcess
from mycelium.dream_policy import DreamPolicy
from mycelium.models import LogEntry
from mycelium.store import LogStore, WikiStore
from mycelium.structured_outputs import (
    claim_routing_output_model,
    entity_plan_output_model,
    identity_matching_output_model,
    new_identity_verification_output_model,
    identity_type_verification_output_model,
    subject_node_output_model,
)


def assignment(
    owner: str = "",
    *,
    disposition: str = "canonical",
    links: list[str] | None = None,
    supporting: list[str] | None = None,
    reason: str = "The cohort establishes this scope.",
    relationship_kind: str = "none",
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
            "relationship_kind": relationship_kind,
        })
    return value


def scope_candidate(
    candidate_id: str,
    title: str,
    entity_type: str,
    supporting: list[str],
    *,
    supporting_participants: list[str] | None = None,
) -> dict:
    value = {
        "title": title,
        "entity_type": entity_type,
        "type_adjudication": "accepted",
        "type_reason": "The supplied evidence supports this entity type.",
        "supporting_evidence": [*supporting, *(supporting_participants or [])],
        "participant_evidence": list(supporting_participants or []),
        "confidence": 0.9,
        "reason": "The cited cohort establishes an independently useful page.",
    }
    value["candidate_id"] = candidate_id
    return value


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


def split_scope_plan(plan: dict) -> list[dict]:
    assignments = dict(plan.get("assignments", {}))
    candidates = list(plan.get("candidates", []))
    candidate_entities = {
        candidate["candidate_id"]: (
            f"{candidate['entity_type']}-{slugify(candidate['title'])}"
        )
        for candidate in candidates
    }
    identity_keys = {
        candidate["candidate_id"]: f"I{candidate['candidate_id'][1:]}"
        for candidate in candidates
    }

    def stable(value: str) -> str:
        return candidate_entities.get(value, value)

    provisional_candidates = {
        stable(candidate["candidate_id"])
        for candidate in candidates
        if candidate["confidence"] < 0.7
    }

    routing = {"decisions": {
        alias: (
            {
                "route_kind": "deferred",
                "confidence": decision["confidence"],
                "reason": decision["reason"],
            }
            if (
                decision.get("disposition") != "canonical"
                or stable(decision.get("owner_entity", ""))
                in provisional_candidates
            )
            else {
                "route_kind": "project_role",
                "owner_entity": stable(decision["owner_entity"]),
                "project_entity": stable(decision["linked_entities"][0]),
                "confidence": decision["confidence"],
                "reason": decision["reason"],
            }
            if decision.get("relationship_kind") == "project_role"
            else {
                "route_kind": "general",
                "owner_entity": stable(decision["owner_entity"]),
                "relationship_kind": decision.get("relationship_kind", "none"),
                "subject_entity": stable(decision.get("subject_entity", "")),
                "object_entities": [
                    stable(value) for value in decision.get("object_entities", [])
                ],
                "contextual_entities": [
                    stable(value) for value in decision.get(
                        "contextual_entities", decision.get("linked_entities", [])
                    )
                ],
                "confidence": decision["confidence"],
                "reason": decision["reason"],
            }
        )
        for alias, decision in assignments.items()
    }}
    census = {
            "nodes": [
                {
                    "node_id": candidate["candidate_id"],
                    "title": candidate["title"],
                    "supporting_evidence": candidate["supporting_evidence"],
                    "participant_evidence": candidate["participant_evidence"],
                }
                for candidate in candidates
            ],
    }
    if not candidates:
        return [
            census,
            {"decisions": {}},
            {"decisions": {}},
            {"decisions": {}, "participants": dict(plan.get("participants", {}))},
            routing,
        ]
    return [
        census,
        {"identities": [
            {
                "identity_key": identity_keys[candidate["candidate_id"]],
                "node_ids": [candidate["candidate_id"]],
                "resolution": "new",
                "entity_id": "",
                "candidate_entity_ids": [],
                "preferred_title": candidate["title"],
                "aliases": [],
                "confidence": candidate["confidence"],
                "reason": "The evidence describes a new identity.",
            }
            for candidate in candidates
        ]},
        {"decisions": {
            identity_keys[candidate["candidate_id"]]: {
                "entity_type": candidate["entity_type"],
                "reason": candidate["type_reason"],
                "supporting_evidence": candidate["supporting_evidence"],
            }
            for candidate in candidates
        }},
        {"decisions": {
            identity_keys[candidate["candidate_id"]]: {
                "verdict": (
                    "supported"
                    if candidate["type_adjudication"] == "accepted"
                    else "ambiguous"
                ),
                "alternative_types": (
                    [] if candidate["type_adjudication"] == "accepted" else ["topic"]
                ),
                "reason": candidate["type_reason"],
                "supporting_evidence": candidate["supporting_evidence"],
            }
            for candidate in candidates
        }},
        {"decisions": {
            identity_keys[candidate["candidate_id"]]: (
                {
                    "admission": "materialized",
                    "basis": (
                        {"continuity_basis": "direct_encounter"}
                        if candidate["participant_evidence"]
                        and candidate["entity_type"] == "person"
                        else {
                            "continuity_basis": "explicit_prior_history",
                            "prior_state": "The prior state is explicitly stated.",
                            "prior_evidence": candidate["supporting_evidence"],
                            "continuation_state": (
                                "Present or future continuation is explicitly stated."
                            ),
                            "continuation_evidence": candidate["supporting_evidence"],
                        }
                    ),
                    "confidence": candidate["confidence"],
                    "reason": "The supplied evidence establishes page maturity.",
                }
                if candidate["confidence"] >= 0.7
                else {
                    "admission": "provisional",
                    "confidence": candidate["confidence"],
                    "reason": "The supplied evidence does not establish continuity.",
                }
            )
            for candidate in candidates
        }},
        {"decisions": {
            identity_keys[candidate["candidate_id"]]: {
                "verdict": (
                    "supported"
                    if candidate["confidence"] >= 0.7
                    and not (
                        candidate["participant_evidence"]
                        and candidate["entity_type"] == "person"
                    )
                    else "not_required"
                ),
                "reason": "The maturity basis was independently checked.",
            }
            for candidate in candidates
        }},
        {
            "decisions": {
                identity_keys[candidate["candidate_id"]]: {
                    "entity_id": "",
                    "scope": (
                        "materialized"
                        if candidate["confidence"] >= 0.7
                        else "provisional"
                    ),
                    "parent_entity": "",
                    **(
                        {"continuity_basis": (
                            "direct_encounter"
                            if candidate["participant_evidence"]
                            and candidate["entity_type"] == "person"
                            else "explicit_prior_history"
                        )}
                        if candidate["confidence"] >= 0.7
                        else {}
                    ),
                    "adjudication": "accepted",
                    "confidence": candidate["confidence"],
                    "reason": candidate["reason"],
                }
                for candidate in candidates
            },
            "participants": {
                alias: {
                    **decision,
                    "entity": identity_keys.get(decision["entity"], decision["entity"]),
                }
                for alias, decision in plan.get("participants", {}).items()
            },
        },
        routing,
    ]


def use_multiple_episode_maturity(responses: list[dict], node_id: str) -> None:
    identity_key = f"I{node_id[1:]}"
    responses[4]["decisions"][identity_key] = {
        "admission": "materialized",
        "basis": {"continuity_basis": "multiple_episodes"},
        "confidence": 0.9,
        "reason": "The identity is supported across source episodes.",
    }
    responses[5]["decisions"][identity_key] = {
        "verdict": "not_required",
        "reason": "The structural basis does not require verification.",
    }
    responses[6]["decisions"][identity_key]["continuity_basis"] = "multiple_episodes"


def use_existing_identity(
    responses: list[dict], entity_id: str, *, title: str, aliases: list[str]
) -> list[dict]:
    group = responses[1]["identities"][0]
    group.update({
        "resolution": "existing",
        "entity_id": entity_id,
        "candidate_entity_ids": [],
        "preferred_title": title,
        "aliases": aliases,
        "confidence": 0.95,
        "reason": "The evidence identifies the existing canonical entity.",
    })
    responses[6]["decisions"]["I001"]["entity_id"] = entity_id
    verification = {"decision": {
        "verdict": "existing",
        "entity_id": entity_id,
        "candidate_entity_ids": [],
        "confidence": 0.95,
        "reason": "Independent evidence confirms the canonical identity.",
    }}
    return [responses[0], responses[1], verification, *responses[4:]]


def set_scope_response(llm, plan: dict) -> None:
    llm.call_structured.side_effect = split_scope_plan(plan)
    llm.call_structured.return_value = None


def test_identity_review_catalog_only_exposes_human_adjudications(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    source = SourceDocument(
        source_id="source-test",
        source_type="chat",
        session_id="session-test",
        recorded_at="2026-08-31T12:00:00-07:00",
        occurred_at=None,
        participants=[],
        segments=[],
    )
    claim = MemoryClaim(
        claim_id="claim-test",
        text="A claim.",
        about=[],
        provenance=[ClaimProvenance(
            source_id=source.source_id,
            segment_ids=["source-test#seg-0001"],
        )],
        recorded_at=source.recorded_at,
        claim_type="event",
        confidence=0.9,
    )
    evidence = {"C001": ClaimEvidence(claim, source)}
    artifacts.save_source(source)
    artifacts.save_claim(claim)
    common = {
        "decision_type": "entity_creation",
        "entity_id": None,
        "proposed_entity_type": "project",
        "proposed_title": "Test Project",
        "source_ids": [source.source_id],
        "supporting_claim_ids": [claim.claim_id],
        "supporting_segment_ids": ["source-test#seg-0001"],
        "confidence": 0.9,
        "reason": "Test decision.",
        "review_state": "accepted",
        "dream_run_id": "dream-test",
        "created_at": "2026-08-31T12:00:00-07:00",
    }
    artifacts.save_entity_resolution_decision(EntityResolutionDecision(
        decision_id="identity-automatic",
        **common,
    ))

    assert RoutingFormatter(artifacts).identity_review_catalog(evidence) == "none"

    artifacts.save_entity_resolution_decision(EntityResolutionDecision(
        decision_id="identity-reviewed",
        reviewed_at="2026-08-31T12:05:00-07:00",
        reviewer_note="Confirmed by the user.",
        **common,
    ))

    catalog = RoutingFormatter(artifacts).identity_review_catalog(evidence)
    assert "Confirmed by the user." in catalog
    assert catalog.count("review_state=accepted") == 1


def fact_resolution_plan(
    facts: dict[str, tuple[list[str], str, str]],
    *,
    truth_changes: list[dict] | None = None,
    incoming_aliases: list[str] | None = None,
) -> list[dict]:
    keyed = {
        fact_key: f"F{index:03d}"
        for index, fact_key in enumerate(facts, start=1)
    }
    presentations = {
        keyed[fact_key]: {
            "state": "current",
            "section_key": section,
            "text": text,
            "confidence": 0.9,
            "reason": "Source-grounded test resolution.",
        }
        for fact_key, (_, text, section) in facts.items()
    }
    changes_by_incoming = {
        alias: change
        for change in truth_changes or []
        for alias in change["incoming_claim_aliases"]
    }
    incoming_aliases = incoming_aliases or (
        sorted(changes_by_incoming)
        if changes_by_incoming
        else sorted({alias for aliases, _, _ in facts.values() for alias in aliases})
    )
    return [
        {"decisions": {
            alias: (
                {
                    "disposition": "truth_change",
                    "relation": changes_by_incoming[alias]["relation"],
                    "target_claim_aliases": changes_by_incoming[alias][
                        "target_claim_aliases"
                    ],
                    "explanation": changes_by_incoming[alias]["explanation"],
                    "confidence": changes_by_incoming[alias]["confidence"],
                }
                if alias in changes_by_incoming
                else {
                    "disposition": "no_change",
                    "reason": "No accepted truth is changed.",
                    "confidence": 0.9,
                }
            )
            for alias in incoming_aliases
        }},
        {"assignments": {
            alias: {"fact_key": keyed[fact_key]}
            for fact_key, (aliases, _, _) in facts.items()
            for alias in aliases
        }},
        {"facts": presentations},
        {"decisions": {
            key: {
                "verdict": "supported",
                "reason": "The presentation is self-contained and source-grounded.",
            }
            for key in presentations
        }},
    ]


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


def test_subject_node_contract_rejects_extra_fields():
    output_model = subject_node_output_model(["C001"])
    valid = {"nodes": []}
    assert output_model.model_validate(valid).nodes == []
    with pytest.raises(ValidationError):
        output_model.model_validate({**valid, "edges": []})


def test_identity_matching_contract_partitions_nodes_and_prevents_competing_matches():
    output_model = identity_matching_output_model(
        ["N001", "N002"], ["project-atlas"]
    )
    merged = {
        "identities": [{
            "identity_key": "I001",
            "node_ids": ["N001", "N002"],
            "resolution": "existing",
            "entity_id": "project-atlas",
            "candidate_entity_ids": [],
            "preferred_title": "Atlas",
            "aliases": ["Atlas Project"],
            "confidence": 0.95,
            "reason": "Both nodes cite the same continuing identity.",
        }],
    }
    assert output_model.model_validate(merged).identities[0].node_ids == [
        "N001", "N002"
    ]

    competing = {
        "identities": [
            {**merged["identities"][0], "node_ids": ["N001"]},
            {
                **merged["identities"][0],
                "identity_key": "I002",
                "node_ids": ["N002"],
            },
        ],
    }
    with pytest.raises(ValidationError):
        output_model.model_validate(competing)


def test_identity_type_verifier_preserves_ambiguity_for_review():
    output_model = identity_type_verification_output_model(
        {"I001": "project"}, {"I001": ["C001"]}
    )
    parsed = output_model.model_validate({
        "decisions": {"I001": {
            "verdict": "ambiguous",
            "alternative_types": ["series"],
            "reason": "The evidence supports both a finite effort and recurring frame.",
            "supporting_evidence": ["C001"],
        }},
    })
    assert parsed.decisions.I001.verdict == "ambiguous"

    supported = output_model.model_validate({
        "decisions": {"I001": {
            "verdict": "supported",
            "alternative_types": ["series"],
            "reason": "Project is clearly best; Series was considered but is weaker.",
            "supporting_evidence": ["C001"],
        }},
    })
    assert supported.decisions.I001.alternative_types == ["series"]


def test_claim_routing_contract_requires_exact_claims_and_registry_values():
    output_model = claim_routing_output_model(
        ["C001", "C002"],
        {"you": "you", "project-cedar": "project"},
    )
    decision = {
        "route_kind": "general",
        "owner_entity": "you",
        "relationship_kind": "none",
        "subject_entity": "you",
        "object_entities": [],
        "contextual_entities": [],
        "confidence": 0.9,
        "reason": "The claim changes the user's profile.",
    }
    valid = {"decisions": {"C001": decision, "C002": {
        **decision,
        "owner_entity": "project-cedar",
        "subject_entity": "project-cedar",
    }}}

    assert set(output_model.model_validate(valid).decisions.model_dump()) == {
        "C001", "C002"
    }
    with pytest.raises(ValidationError):
        output_model.model_validate({"decisions": {"C001": decision}})
    with pytest.raises(ValidationError):
        output_model.model_validate({"decisions": {
            **valid["decisions"],
            "C001": {**decision, "owner_entity": "source_only"},
        }})
    project_role = {
        "route_kind": "project_role",
        "owner_entity": "you",
        "project_entity": "project-cedar",
        "confidence": 0.9,
        "reason": "The user has an accountable role in the project.",
    }
    parsed = output_model.model_validate({
        "decisions": {"C001": project_role, "C002": valid["decisions"]["C002"]}
    })
    assert parsed.decisions.C001.route_kind == "project_role"
    with pytest.raises(ValidationError):
        output_model.model_validate({
            "decisions": {
                "C001": {**project_role, "owner_entity": "project-cedar"},
                "C002": valid["decisions"]["C002"],
            }
        })


def test_claim_decision_batches_preserve_every_alias_once():
    aliases = {f"C{index:03d}": object() for index in range(1, 27)}

    batches = list(ClaimRouter._alias_batches(aliases))

    assert [len(batch) for batch in batches] == [24, 2]
    assert [alias for batch in batches for alias in batch] == list(aliases)


def test_revision_cannot_overwrite_identity_blocked_deferral():
    initial = RoutingResult(routes=[ClaimRoute(
        claim_id="claim-kitchen",
        owner_entity_id=None,
        section_key=None,
        linked_entity_ids=(),
        raw_log_entry_id="log-1",
        reason="The kitchen identity requires review.",
        disposition="deferred",
        identity_blocker_ids=("identity-kitchen-review",),
    )])
    revision = RoutingResult(routes=[ClaimRoute(
        claim_id="claim-kitchen",
        owner_entity_id="person-rosa",
        section_key=None,
        linked_entity_ids=(),
        raw_log_entry_id="log-1",
        reason="The claim discusses project work.",
    )])

    merged = DreamPolicy.merge_revision_routing(initial, revision)

    assert merged.routes == initial.routes


@pytest.mark.asyncio
async def test_invalid_routing_batch_does_not_discard_other_batches(tmp_path):
    dream, llm, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    claims = [
        add_claim(
            artifacts,
            source,
            claim_id=f"claim-{index:02d}",
            text=f"The user recorded preference {index}.",
        )
        for index in range(1, 26)
    ]
    routing_calls = 0

    async def response(system, user, output_type, **kwargs):
        nonlocal routing_calls
        if "nodes" in output_type.model_fields:
            return {"nodes": []}
        if "participants" in output_type.model_fields:
            return {"decisions": {}, "participants": {}}
        decision_field = output_type.model_fields.get("decisions")
        annotation = getattr(decision_field, "annotation", None)
        fields = getattr(annotation, "model_fields", {})
        if not fields:
            return {"decisions": {}}
        routing_calls += 1
        if routing_calls == 1:
            return {"decisions": {}}
        return {"decisions": {
            alias: {
                "route_kind": "general",
                "owner_entity": "you",
                "relationship_kind": "none",
                "subject_entity": "you",
                "object_entities": [],
                "contextual_entities": [],
                "confidence": 0.9,
                "reason": "The claim changes the user's durable preferences.",
            }
            for alias in fields
        }}

    llm.call_structured.side_effect = response

    result = await dream.router.route([
        ClaimEvidence(item, source) for item in claims
    ])

    assert len(result.failures) == 16
    assert [route.claim_id for route in result.routes] == [
        f"claim-{index:02d}" for index in range(17, 26)
    ]
    units = artifacts.list_identity_work_units()
    assert [unit.status for unit in units] == ["failed", "complete"]


@pytest.mark.asyncio
async def test_identity_retry_resumes_after_persisted_subject_census(tmp_path):
    dream, llm, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts,
        source,
        claim_id="claim-one",
        text="Atlas is a continuing accessibility project.",
        about="Atlas",
        claim_type="plan",
    )
    responses = split_scope_plan(new_scope("C001", "Atlas"))
    llm.call_structured.side_effect = [responses[0], {}]

    first = await dream.router.route([ClaimEvidence(claim, source)])

    assert len(first.failures) == 1
    failed = artifacts.list_identity_work_units()[0]
    assert failed.status == "failed"
    assert failed.stage == "identity_matching"
    assert failed.subject_nodes
    assert failed.identity_groups == []

    llm.call_structured.side_effect = responses[1:]
    second = await dream.router.route([ClaimEvidence(claim, source)])

    assert second.failures == []
    assert [route.claim_id for route in second.routes] == [claim.claim_id]
    completed = artifacts.list_identity_work_units()[0]
    assert completed.status == "complete"
    assert completed.attempt_count == 2
    assert completed.identity_groups
    assert llm.call_structured.call_count == 9


def test_entity_plan_contract_combines_identity_containment_and_participants():
    output_model = entity_plan_output_model(
        {"N001": "event", "N002": "person"},
        {"P001": "user"},
        {"you": "you", "project-cedar": "project", "person-rosa": "person"},
        matched_entity_ids={"N002": "person-rosa"},
        materialization_bases={"N002": ("direct_encounter",)},
    )
    valid = {"decisions": {
        "N001": {
            "entity_id": "",
            "scope": "occurrence",
            "parent_entity": "project-cedar",
            "adjudication": "accepted",
            "confidence": 0.9,
            "reason": "This is one review within the project.",
        },
        "N002": {
            "entity_id": "person-rosa",
            "scope": "materialized",
            "parent_entity": "",
            "continuity_basis": "direct_encounter",
            "adjudication": "accepted",
            "confidence": 0.9,
            "reason": "The evidence continues this person.",
        },
    }, "participants": {"P001": participant("you")}}

    parsed = output_model.model_validate(valid)
    assert parsed.decisions.N001.parent_entity == "project-cedar"
    assert parsed.participants.P001.entity == "you"
    with pytest.raises(ValidationError):
        output_model.model_validate({**valid, "participants": {}})
    with pytest.raises(ValidationError):
        output_model.model_validate({"decisions": {
            **valid["decisions"],
            "N002": {**valid["decisions"]["N002"], "entity_id": "project-cedar"},
        }, "participants": valid["participants"]})
    with pytest.raises(ValidationError):
        output_model.model_validate({"decisions": {
            **valid["decisions"],
            "N001": {
                **valid["decisions"]["N001"],
                "scope": "materialized",
                "parent_entity": "",
                "continuity_basis": "direct_encounter",
            },
        }, "participants": valid["participants"]})
    with pytest.raises(ValidationError):
        output_model.model_validate({"decisions": {
            **valid["decisions"],
            "N001": {
                **valid["decisions"]["N001"],
                "scope": "materialized",
                "parent_entity": "",
            },
        }, "participants": valid["participants"]})


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

    rendered = dream.router.formatter.format_evidence(
        {"C001": ClaimEvidence(item, source)}, {}
    )

    assert "'A relative'[role=subject]" in rendered
    assert "'Recurring endeavor'[role=owner]" in rendered
    assert "stable_entity_references=context:you" in rendered
    assert "source_title=none" in rendered
    assert f"[{source.segments[0].segment_id}]" in rendered
    assert source.segments[0].content in rendered


def build_dream(tmp_path, *, llm_response: dict):
    wiki = WikiStore(tmp_path / "wiki")
    logs = LogStore(tmp_path / "logs")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    llm = AsyncMock()
    if "assignments" in llm_response:
        set_scope_response(llm, llm_response)
    else:
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
    set_scope_response(llm, scope_plan({
        "C001": assignment(
            disposition="deferred",
            reason="More episodic context is required.",
        )
    }))

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
    plan = scope_plan(
        {"C001": assignment("N001", supporting=["C001"])},
        [scope_candidate(
            "N001",
            "Incidental Library",
            "topic",
            ["C001"],
        )],
    )
    plan["candidates"][0]["confidence"] = 0.6
    set_scope_response(dream.llm, plan)

    await dream.run()

    entity = artifacts.get_entity("topic-incidental-library")
    assert entity.materialization_state == "provisional"
    assert not wiki.exists(entity.slug)
    assert artifacts.get_placement(claim.claim_id).status == "deferred"


@pytest.mark.asyncio
async def test_evidence_maturity_is_separate_from_identity_confidence(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts,
        source,
        text="The user is considering an early archive effort.",
        claim_type="plan",
        about="Archive Effort",
    )
    responses = split_scope_plan(new_scope(
        "C001", "Archive Effort", "project"
    ))
    responses[4]["decisions"]["I001"] = {
        "admission": "provisional",
        "confidence": 0.9,
        "reason": "Continuity is not established yet.",
    }
    responses[5]["decisions"]["I001"]["verdict"] = "not_required"
    responses[6]["decisions"]["I001"]["scope"] = "provisional"
    responses[6]["decisions"]["I001"].pop("continuity_basis", None)
    responses[7]["decisions"]["C001"] = {
        "route_kind": "deferred",
        "confidence": 0.9,
        "reason": "The proposed owner is not materialized yet.",
    }
    llm.call_structured.side_effect = responses

    await dream.run()

    entity = artifacts.get_entity("project-archive-effort")
    assert entity.materialization_state == "provisional"
    assert not wiki.exists(entity.slug)
    assert artifacts.get_placement(claim.claim_id).status == "deferred"
    assessment = artifacts.list_identity_maturity_assessments()[0]
    assert assessment.proposal_admission == "provisional"
    assert assessment.verifier_verdict == "not_required"
    assert assessment.effective_admission == "provisional"
    assert assessment.supporting_claim_ids == [claim.claim_id]


@pytest.mark.asyncio
async def test_admitted_identity_stays_provisional_until_it_owns_a_claim(tmp_path):
    dream, _, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    add_claim(
        artifacts,
        source,
        text="The user noted a lasting organization as context.",
        claim_type="observation",
        about="Context Group",
    )
    set_scope_response(dream.llm, scope_plan(
        {"C001": assignment("you", supporting=["C001"])},
        [scope_candidate("N001", "Context Group", "organization", ["C001"])],
    ))

    await dream.run()

    entity = artifacts.get_entity("organization-context-group")
    assert entity.materialization_state == "provisional"
    assert not wiki.exists(entity.slug)


@pytest.mark.asyncio
async def test_later_distinct_source_can_promote_its_provisional_owner(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, first_source = add_source(logs, artifacts, suffix="first")
    add_claim(
        artifacts,
        first_source,
        text="An archive effort may continue.",
        claim_type="plan",
        about="Archive Effort",
    )
    first_responses = split_scope_plan(new_scope(
        "C001", "Archive Effort", "project"
    ))
    first_responses[4]["decisions"]["I001"] = {
        "admission": "provisional",
        "confidence": 0.9,
        "reason": "Continuity is not established yet.",
    }
    first_responses[5]["decisions"]["I001"]["verdict"] = "not_required"
    first_responses[6]["decisions"]["I001"]["scope"] = "provisional"
    first_responses[6]["decisions"]["I001"].pop("continuity_basis", None)
    llm.call_structured.side_effect = first_responses
    await dream.run()
    assert artifacts.get_entity(
        "project-archive-effort"
    ).materialization_state == "provisional"

    _, second_source = add_source(logs, artifacts, suffix="second")
    add_claim(
        artifacts,
        second_source,
        claim_id="claim-second",
        text="The archive effort now has continuing work.",
        claim_type="state",
        about="Archive Effort",
    )
    second_responses = split_scope_plan(scope_plan({
            "C001": assignment(
                disposition="deferred",
                supporting=["C001"],
            reason="The earlier claim remains deferred.",
        ),
        "C002": assignment(
                "project-archive-effort", supporting=["C002"]
            ),
        }, [scope_candidate(
            "N001", "Archive Effort", "project", ["C001", "C002"]
        )]))
    use_multiple_episode_maturity(second_responses, "N001")
    second_responses[1]["identities"][0].update({
        "resolution": "existing",
        "entity_id": "project-archive-effort",
    })
    second_responses[1]["identities"][0]["candidate_entity_ids"] = []
    second_responses[6]["decisions"]["I001"]["entity_id"] = (
        "project-archive-effort"
    )
    second_responses = [
        second_responses[0],
        second_responses[1],
        {"decision": {
            "verdict": "existing",
            "entity_id": "project-archive-effort",
            "candidate_entity_ids": [],
            "confidence": 0.95,
            "reason": "The continuing work confirms the same archive effort.",
        }},
        *second_responses[4:],
    ]
    llm.call_structured.side_effect = second_responses

    await dream.run()

    entity = artifacts.get_entity("project-archive-effort")
    assert entity.materialization_state == "materialized"
    assert wiki.exists(entity.slug)
    assert artifacts.get_placement("claim-second").owner_entity_id == entity.entity_id


@pytest.mark.asyncio
async def test_model_declared_project_role_projects_to_both_endpoint_pages(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    project = artifacts.create_entity("project", "Atlas")
    person = artifacts.create_entity("person", "Priya Raman")
    _, source = add_source(logs, artifacts)
    add_claim(
        artifacts,
        source,
        text="Priya will own pilot evaluation for Atlas.",
        claim_type="commitment",
        about="Priya Raman",
    )
    responses = split_scope_plan(scope_plan({
        "C001": assignment(
            person.entity_id,
            links=[project.entity_id],
            supporting=["C001"],
            relationship_kind="project_role",
        ),
    }))
    llm.call_structured.side_effect = responses

    await dream.run()

    assert "Priya will own pilot evaluation" in wiki.get(person.slug).content
    assert "Priya will own pilot evaluation" in wiki.get(project.slug).content
    placement = artifacts.get_placement("claim-one")
    assert placement.relationship_kind == "project_role"


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
    _, state_source = add_source(logs, artifacts, suffix="state")
    state = add_claim(
        artifacts,
        state_source,
        claim_id="claim-state",
        text="Atlas is a local desktop application.",
        claim_type="state",
        about="Atlas",
    )
    initial_support = ["C001", "C002"]
    revision_support = ["C001", "C002", "C003"]
    discovery_responses = split_scope_plan(scope_plan(
            {
                alias: assignment("N001", supporting=initial_support)
                for alias in initial_support
            },
            [
                    scope_candidate("N001", "Atlas", "project", initial_support),
                    scope_candidate("N002", "Supporting Concept", "topic", ["C002"]),
            ],
        ))
    use_multiple_episode_maturity(discovery_responses, "N001")
    revision_responses = split_scope_plan(scope_plan({
        alias: assignment("project-atlas", supporting=revision_support)
        for alias in revision_support
    }))
    dream.llm.call_structured.side_effect = [
        *discovery_responses,
        *revision_responses,
        *fact_resolution_plan({
            "early": (["C001"], early.text, "next_steps_deadlines"),
            "identity": (["C002"], identity.text, "overview"),
            "state": (["C003"], state.text, "current_status"),
        }, incoming_aliases=["C002", "C003"]),
    ]

    report = await dream.run()

    assert report.failures == []
    assert artifacts.get_placement(early.claim_id).owner_entity_id == "project-atlas"
    assert artifacts.get_placement(identity.claim_id).owner_entity_id == "project-atlas"
    assert artifacts.get_placement(state.claim_id).owner_entity_id == "project-atlas"
    assert wiki.exists("atlas")
    assert early.text not in wiki.get("you").content
    assert len(artifacts.list_scope_decisions(claim_id=early.claim_id)) == 2
    scope_calls = [
        call for call in dream.llm.call_structured.await_args_list
        if call.kwargs.get("debug_label") == "dream-claim-routing"
    ]
    revision_prompt = scope_calls[-1].args[1]
    assert "topic-supporting-concept" not in revision_prompt


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
    set_scope_response(llm, scope_plan({
        "C001": assignment(
            disposition="deferred",
            reason="One mention does not yet establish a continuing project.",
        )
    }))
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
    discovery_responses = split_scope_plan(scope_plan(
            {
                "C001": assignment("N001", supporting=support),
                "C002": assignment("N001", supporting=support),
            },
            [scope_candidate("N001", "Ava's Adoption", "project", support)],
        ))
    use_multiple_episode_maturity(discovery_responses, "N001")
    llm.call_structured.side_effect = [
        *discovery_responses,
        *fact_resolution_plan({
            "research": (["C001"], first.text, "timeline"),
            "interview": (["C002"], second.text, "next_steps_deadlines"),
        }, incoming_aliases=["C002"]),
    ]

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
async def test_deferred_owner_does_not_block_placed_sibling(tmp_path):
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

    set_scope_response(llm, scope_plan(
        {
            "C001": assignment(
                disposition="deferred", supporting=["C001"],
                reason="The completed registry has no supported owner.",
            ),
            "C002": assignment("N001", supporting=["C002"]),
        },
        [scope_candidate("N001", "Coffee", "topic", ["C002"])],
    ))
    report = await dream.run()

    assert report.pending_source_ids == []
    assert report.completed_source_ids == [first_entry.entry_id, second_entry.entry_id]
    assert logs.get(first_entry.entry_id).consolidated is True
    assert logs.get(second_entry.entry_id).consolidated is True
    assert wiki.exists("coffee")
    assert artifacts.get_claim("claim-first").dream_disposition == "deferred"
    assert llm.call_structured.await_count == 8


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
    assert llm.call_structured.await_count == 8


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
async def test_subject_graph_accepts_an_existing_person_participant(tmp_path):
    dream, _, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    ava = artifacts.create_entity("person", "Ava")
    _, source = add_source(
        logs,
        artifacts,
        source_type="meeting_transcript",
        participants=["Ava"],
    )
    claim = add_claim(artifacts, source, text="Ava adopted a dog.")
    responses = split_scope_plan(scope_plan(
        {"C001": assignment(ava.entity_id, supporting=["C001"])},
        participants={"P001": participant(ava.entity_id)},
    ))
    dream.llm.call_structured.side_effect = responses

    result = await dream.router.route([ClaimEvidence(claim, source)])

    assert result.failures == []
    assert result.routes[0].owner_entity_id == ava.entity_id
    assert len(result.encounters) == 1
    assert result.encounters[0].entity_id == ava.entity_id


@pytest.mark.asyncio
async def test_subject_graph_rejects_an_undeclared_participant_identity(tmp_path):
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
    assert len(report.failures) == 1
    assert "Entity plan response did not satisfy the contract" in report.failures[0][
        "reason"
    ]
    assert artifacts.list_entity_resolution_decisions() == []


@pytest.mark.asyncio
async def test_project_components_have_no_identity_creation_path(tmp_path):
    dream, llm, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    first = add_claim(
        artifacts, source, claim_id="claim-project",
        text="The archive is an ongoing effort.", claim_type="plan", about="Archive",
    )
    _, occurrence_source = add_source(logs, artifacts, suffix="occurrence")
    second = add_claim(
        artifacts, occurrence_source, claim_id="claim-session",
        text="Tuesday's recording was part of the archive.",
        claim_type="event", about="Tuesday Recording",
    )
    responses = split_scope_plan(scope_plan(
        {
            "C001": assignment("N001", supporting=["C001"]),
            "C002": assignment("N001", supporting=["C002"]),
        },
        [
            scope_candidate("N001", "Archive", "project", ["C001", "C002"]),
            scope_candidate("N002", "Tuesday Recording", "event", ["C002"]),
        ],
    ))
    use_multiple_episode_maturity(responses, "N001")
    responses[6]["decisions"]["I002"].update({
        "scope": "occurrence",
        "parent_entity": "I001",
        "reason": "Its memory value belongs to the Archive Project.",
    })
    responses[6]["decisions"]["I002"].pop("continuity_basis", None)
    llm.call_structured.side_effect = responses

    result = await dream.router.route([
        ClaimEvidence(first, source), ClaimEvidence(second, occurrence_source),
    ])

    assert result.failures == []
    assert [entity.title for entity in result.new_entities] == ["Archive"]
    component = next(
        decision for decision in result.entity_decisions
        if decision.proposed_title == "Tuesday Recording"
    )
    assert component.entity_id is None
    assert {route.owner_entity_id for route in result.routes} == {"project-archive"}


def test_subject_node_contract_defers_type_to_later_stage():
    output_model = subject_node_output_model(["C001"])

    parsed = output_model.model_validate({
        "nodes": [{
            "node_id": "N001",
            "title": "Archive",
            "supporting_evidence": ["C001"],
            "participant_evidence": [],
        }],
    })

    assert parsed.nodes[0].title == "Archive"


@pytest.mark.asyncio
async def test_ambiguous_subject_type_is_deferred_for_identity_review(tmp_path):
    dream, llm, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts,
        source,
        text="The salon has recurring sessions and is also producing a guide.",
        about="Neighborhood Salon",
        claim_type="plan",
    )
    responses = split_scope_plan(new_scope(
        "C001", "Neighborhood Salon", "project"
    ))
    responses[3]["decisions"]["I001"].update({
        "verdict": "ambiguous",
        "alternative_types": ["series"],
        "reason": "Project and Series are both materially plausible.",
    })
    responses[6]["decisions"]["I001"]["adjudication"] = "review_required"
    llm.call_structured.side_effect = responses[:7]

    result = await dream.router.route([ClaimEvidence(claim, source)])

    assert result.routes[0].disposition == "deferred"
    assert result.new_entities == []
    decision = result.entity_decisions[0]
    assert decision.review_state == "review_required"
    assert result.routes[0].identity_blocker_ids == (decision.decision_id,)
    assert decision.proposed_type_reason == (
        "Project and Series are both materially plausible."
    )
    assert result.maturity_assessments[0].effective_admission == "review_required"
    assert llm.call_structured.await_count == 7


@pytest.mark.asyncio
async def test_configured_user_routes_without_subject_identity_proposal(tmp_path):
    dream, llm, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    claim = add_claim(artifacts, source, text="The user prefers concise reports.")
    llm.call_structured.side_effect = split_scope_plan(you_scope())

    result = await dream.router.route([ClaimEvidence(claim, source)])

    assert result.failures == []
    assert result.routes[0].owner_entity_id == "you"
    assert all(entity.entity_id != "person-you" for entity in result.new_entities)
    assert llm.call_structured.await_count == 5


@pytest.mark.asyncio
async def test_shorter_person_name_resolves_to_existing_identity(tmp_path):
    dream, llm, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    person = artifacts.create_entity("person", "Priya Raman")
    _, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts,
        source,
        text="Priya shared a project update.",
        about="Priya",
        claim_type="state",
    )
    candidate = scope_candidate("N001", "Priya", "person", ["C001"])
    responses = split_scope_plan(scope_plan(
        {"C001": assignment(person.entity_id, supporting=["C001"])},
        [candidate],
    ))
    responses = use_existing_identity(
        responses, person.entity_id, title="Priya Raman", aliases=["Priya"]
    )
    llm.call_structured.side_effect = responses

    result = await dream.router.route([ClaimEvidence(claim, source)])

    assert [entity.entity_id for entity in result.new_entities] == [person.entity_id]
    assert result.new_entities[0].aliases == ["Priya"]
    assert result.routes[0].owner_entity_id == person.entity_id


@pytest.mark.asyncio
async def test_rejected_identity_match_cannot_mutate_existing_person(tmp_path):
    dream, llm, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    person = artifacts.create_entity("person", "Priya Raman")
    _, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts,
        source,
        text="Omar Haddad shared a project update.",
        about="Omar Haddad",
        claim_type="state",
    )
    candidate = scope_candidate("N001", "Omar Haddad", "person", ["C001"])
    responses = split_scope_plan(scope_plan(
        {"C001": assignment("N001", supporting=["C001"])},
        [candidate],
    ))
    responses.insert(4, {"decision": {
        "verdict": "distinct",
        "entity_id": "",
        "candidate_entity_ids": [],
        "confidence": 0.95,
        "reason": "The evidence establishes a different person.",
    }})
    llm.call_structured.side_effect = responses

    result = await dream.router.route([ClaimEvidence(claim, source)])

    assert [(entity.entity_id, entity.title) for entity in result.new_entities] == [
        ("person-omar-haddad", "Omar Haddad")
    ]
    assert artifacts.get_entity(person.entity_id).title == "Priya Raman"
    assert result.routes[0].owner_entity_id == "person-omar-haddad"


@pytest.mark.asyncio
async def test_existing_identity_match_is_verified_before_inheriting_shape(tmp_path):
    dream, llm, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    person = artifacts.create_entity("person", "Rosa Alvarez")
    _, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts,
        source,
        text="The selected appliance is a thirty-inch induction range.",
        about="thirty-inch induction range",
        claim_type="state",
    )
    responses = split_scope_plan(scope_plan(
        {"C001": assignment("N001", supporting=["C001"])},
        [scope_candidate(
            "N001", "thirty-inch induction range", "artifact", ["C001"]
        )],
    ))
    responses[1]["identities"][0].update({
        "resolution": "existing",
        "entity_id": person.entity_id,
        "candidate_entity_ids": [],
        "reason": "The initial matcher proposed the existing person.",
    })
    responses.insert(2, {"decision": {
        "verdict": "distinct",
        "entity_id": "",
        "candidate_entity_ids": [],
        "confidence": 1.0,
        "reason": "An appliance and a person are different identities.",
    }})
    llm.call_structured.side_effect = responses

    result = await dream.router.route([ClaimEvidence(claim, source)])

    assert result.failures == []
    assert [(entity.entity_type, entity.title) for entity in result.new_entities] == [
        ("artifact", "thirty-inch induction range")
    ]
    assert artifacts.get_entity(person.entity_id).title == "Rosa Alvarez"
    unit = artifacts.list_identity_work_units()[0]
    assert unit.existing_identity_verdicts["I001"]["verdict"] == "distinct"


@pytest.mark.asyncio
async def test_new_identity_verifier_matches_cross_run_duplicate_to_registry(tmp_path):
    dream, llm, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    existing = artifacts.create_entity("person", "Ada")
    _, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts,
        source,
        text="Ada scheduled another Bluebird accessibility test.",
        about="Ada",
        claim_type="plan",
    )
    responses = split_scope_plan(scope_plan(
        {"C001": assignment("N001", supporting=["C001"])},
        [scope_candidate("N001", "Ada", "person", ["C001"])],
    ))
    responses.insert(4, {"decision": {
        "verdict": "existing",
        "entity_id": existing.entity_id,
        "candidate_entity_ids": [],
        "confidence": 0.95,
        "reason": "The specific continuing history identifies canonical Ada.",
    }})
    responses[7]["decisions"]["I001"]["entity_id"] = existing.entity_id
    llm.call_structured.side_effect = responses

    result = await dream.router.route([ClaimEvidence(claim, source)])

    assert result.failures == []
    assert result.new_entities == []
    assert result.routes[0].owner_entity_id == existing.entity_id
    unit = artifacts.list_identity_work_units()[0]
    assert unit.new_identity_verdicts["I001"]["verdict"] == "existing"


def test_new_identity_verifier_contract_constrains_registry_ids():
    output_model = new_identity_verification_output_model(["person-ada"])
    valid = {
        "decision": {
            "verdict": "existing",
            "entity_id": "person-ada",
            "candidate_entity_ids": [],
            "confidence": 0.9,
            "reason": "Specific history establishes continuity.",
        }
    }

    assert output_model.model_validate(valid).decision.entity_id == "person-ada"
    valid["decision"]["entity_id"] = "person-unknown"
    with pytest.raises(ValidationError):
        output_model.model_validate(valid)


@pytest.mark.asyncio
async def test_later_project_name_updates_stable_identity_without_duplicate(tmp_path):
    dream, llm, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    project = artifacts.create_entity(
        "project", "Meeting Memory Assistant", aliases=["meeting assistant"]
    )
    _, source = add_source(logs, artifacts)
    claim = add_claim(
        artifacts,
        source,
        text="The meeting memory assistant is now named Lantern.",
        about="Lantern",
        claim_type="identity",
    )
    candidate = scope_candidate("N001", "Lantern", "project", ["C001"])
    responses = split_scope_plan(scope_plan(
        {"C001": assignment(project.entity_id, supporting=["C001"])},
        [candidate],
    ))
    responses = use_existing_identity(
        responses,
        project.entity_id,
        title="Lantern",
        aliases=["Meeting Memory Assistant"],
    )
    llm.call_structured.side_effect = responses

    result = await dream.router.route([ClaimEvidence(claim, source)])

    assert [entity.entity_id for entity in result.new_entities] == [project.entity_id]
    updated = result.new_entities[0]
    assert updated.title == "Lantern"
    assert "Meeting Memory Assistant" in updated.aliases
    assert [entity.entity_id for entity in artifacts.list_entities()].count(
        project.entity_id
    ) == 1
    assert result.routes[0].owner_entity_id == project.entity_id


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
        *split_scope_plan(scope_plan({
            "C001": assignment("topic-stable-page", supporting=["C001"])
        })),
        {"decisions": {"C001": {
            "candidate_fact_ids": ["X001"],
            "reason": "The preference facts may express the same durable state.",
        }}},
        *fact_resolution_plan({
            "tea": (["C001"], "Stable Page records a tea preference.", "why_it_matters"),
            "coffee": (["C002"], "Stable Page records a coffee preference.", "why_it_matters"),
        }, incoming_aliases=["C002"]),
    ]
    report = await dream.run()

    assert report.pages_updated == 1
    page = wiki.get("stable-page")
    assert "tea preference" in page.content
    assert "coffee preference" in page.content


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
    assert wiki.get("memory-design").page_type == "topic"

    second = await dream.run()

    page = wiki.get("memory-design")
    assert second.entries_consolidated == 0
    assert second.pages_updated == 0
    assert page.page_type == "topic"
    assert page.title == "Memory Design"
    assert "## Why It Matters" in page.content


@pytest.mark.asyncio
async def test_you_entity_is_typed_without_a_taxonomy_call(tmp_path):
    dream, llm, wiki, logs, artifacts = build_dream(
        tmp_path, llm_response=you_scope()
    )
    entry, source = add_source(logs, artifacts)
    add_claim(artifacts, source)

    report = await dream.run()

    assert report.completed_source_ids == [entry.entry_id]
    assert wiki.get("you").page_type == "you"
    assert wiki.get("you").title == "You"
    assert "## Preferences & Working Style" in wiki.get("you").content


@pytest.mark.asyncio
async def test_dream_preserves_accepted_fact_while_contradiction_is_pending(tmp_path):
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
        *split_scope_plan(you_scope()),
        {"decisions": {"C001": {
            "candidate_fact_ids": ["X001"],
            "reason": "The prior preference may express the same durable state.",
        }}},
        *fact_resolution_plan(
            {
                "new": (["C001"], "The user dislikes tea.", "preferences_working_style"),
                "old": (["C002"], "The user prefers tea.", "preferences_working_style"),
            },
            truth_changes=[{
                "relation": "contradicts",
                "incoming_claim_aliases": ["C001"],
                "target_claim_aliases": ["C002"],
                "explanation": "The new preference conflicts with the existing preference.",
                "confidence": 0.94,
            }],
        ),
    ]

    report = await dream.run()

    assert report.completed_source_ids == [second_entry.entry_id]
    assert len(report.reconsolidation_proposal_ids) == 1
    proposal = artifacts.get_reconsolidation_proposal(
        report.reconsolidation_proposal_ids[0]
    )
    assert proposal.status == "pending"
    assert proposal.incoming_claim_ids == ["claim-new"]
    assert proposal.target_claim_ids == ["claim-old"]
    assert proposal.proposed_relation == "contradicts"
    assert proposal.affected_entity_ids == ["you"]
    assert artifacts.get_claim("claim-old").status == "active"
    assert artifacts.get_claim("claim-new").status == "active"
    page = wiki.get("you")
    assert "prefers tea" in page.content
    assert "dislikes tea" not in page.content
    assert page.content.count("pending reconciliation") == 1


@pytest.mark.asyncio
async def test_invalid_fact_resolution_keeps_source_pending_and_page_unchanged(tmp_path):
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
        *split_scope_plan(you_scope()),
        {"decisions": {"C002": {
            "disposition": "no_change",
            "reason": "No accepted truth is changed.",
            "confidence": 0.9,
        }}},
        {"assignments": {}},
    ]

    report = await dream.run()

    assert report.completed_source_ids == []
    assert report.pending_source_ids == [second_entry.entry_id]
    assert report.failures[0]["stage"] == "fact_resolution"
    assert logs.get(second_entry.entry_id).consolidated is False
    assert artifacts.get_claim("claim-new").dream_disposition == "routing_failed"
    assert "no longer" not in wiki.get("you").content
    assert artifacts.list_reconsolidation_proposals() == []
