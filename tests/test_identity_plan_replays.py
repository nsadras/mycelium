"""Opt-in direct probes of the production identity/page contract."""
import json
import os
from pathlib import Path

import pytest

from mycelium import Mycelium
from mycelium.artifacts import ClaimProvenance, EntityRecord, MemoryClaim, SourceDocument, SourceSegment
from mycelium.consolidation_models import ClaimEvidence
from mycelium.consolidation import ClaimRouter
from mycelium.consolidation_formatting import RoutingFormatter
from mycelium.identity_plan import identity_plan_model, identity_plan_prompt, planned_subjects, declared_user_bindings


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("MYCELIUM_RUN_IDENTITY_REPLAYS") != "1", reason="Opt-in host model probes")
@pytest.mark.parametrize("mode,case", [
    ("probe", case) for case in ["user", "namesakes", "project", "two_speakers", "tool", "existing",
                                "ambiguous", "ambiguous_rephrased", "distinct_ambiguous"]
] + [("replay", case) for case in ["ambiguous", "ambiguous_rephrased", "distinct_ambiguous"]])
async def test_identity_plan_real_model(tmp_path, monkeypatch, mode, case):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm-errors"))
    memory = Mycelium(tmp_path / "store", config_path=Path(__file__).resolve().parents[1] / "mycelium.toml")
    cases = {
        "user": [("Nora", "user", "I enjoy restoring old radios.")],
        "namesakes": [("Lee", "participant", "My colleague Morgan repairs bicycles. My neighbor Morgan is a different person and teaches pottery.")],
        "project": [("user", "user", "I started a garden irrigation project today. The moisture sensor is one component of the project.")],
        "two_speakers": [("Nora", "user", "I enjoy restoring old radios."),
                         ("Amir", "participant", "I grow herbs on my balcony."),
                         ("Nora", "user", "I plan to study electronics."),
                         ("Amir", "participant", "I donated vegetables to the food bank last week.")],
        "tool": [("catalog", "tool", "Harbor Workshop is a bicycle repair business at 42 Wharf Road, founded by Elena Ruiz."),
                 ("catalog", "tool", "Elena Ruiz founded Harbor Workshop in 2019 and teaches its repair classes.")],
        "existing": [("catalog", "tool", "Harbor Workshop, the bicycle repair business at 42 Wharf Road, now offers wheel-building classes.")],
        "ambiguous": [("Lee", "participant", "Morgan offered to help. I cannot tell whether the message came from my colleague or my neighbor; both are named Morgan.")],
        "ambiguous_rephrased": [("Lee", "participant", "An unsigned offer to help came from one of the two Morgans I know. It could be my neighbor or my colleague; I do not know which sent it.")],
        "distinct_ambiguous": [("Lee", "participant", "Two different people named Morgan sent separate offers to help. One offered transport, the other offered equipment. They are my colleague and neighbor, but I cannot tell which made which offer.")],
    }
    registry = []
    if case == "existing":
        registry = [("entity-73", "organization", "Harbor Workshop", ["Bicycle repair business at 42 Wharf Road"])]
    elif case in {"ambiguous", "ambiguous_rephrased", "distinct_ambiguous"}:
        registry = [("entity-18", "person", "Morgan (Lee's colleague)", ["Morgan"]),
                    ("entity-29", "person", "Morgan (Lee's neighbor)", ["Morgan"])]
    for entity_id, kind, title, names in registry:
        memory.artifacts.save_entity(EntityRecord(entity_id, kind, title, entity_id, names,
                                                  "active", "2026-09-04", "2026-09-04"))
    turns = cases[case]
    source = SourceDocument("s1", "tool_observation" if case in {"tool", "existing"} else "multi_party_conversation", "s", "2026-09-04", None,
                            [t[0] for t in turns], [SourceSegment(f"s1#{i}", i, text, speaker=name, role=role)
                            for i, (name, role, text) in enumerate(turns)])
    aliases = {f"C{i+1:03d}": ClaimEvidence(MemoryClaim(f"c{i+1}", text, [],
               [ClaimProvenance("s1", [f"s1#{i}"])], "2026-09-04"), source)
               for i, (_, _, text) in enumerate(turns)}
    speakers = list(dict.fromkeys((name, role) for name, role, _ in turns))
    participants = {f"P{i+1:03d}": (source, name, role) for i, (name, role) in enumerate(speakers)}
    formatter = RoutingFormatter(memory.artifacts)
    schema = identity_plan_model(aliases, {p: role for p, (_, _, role) in participants.items()},
                                         {e.entity_id: e.entity_type for e in memory.artifacts.list_entities()})
    system, user = identity_plan_prompt(formatter.entity_planning_catalog(memory.artifacts.list_entities()),
                                       formatter.format_evidence(aliases, participants), "none", "none",
                                       declared_user_bindings(participants))
    try:
        if mode == "probe":
            response = schema.model_validate(await memory.llm.call_structured(system, user, schema, num_predict=8192)).model_dump()
        else:
            memory.artifacts.save_source(source)
            for item in aliases.values():
                memory.artifacts.save_claim(item.claim)
            routed = await ClaimRouter(memory.llm, memory.artifacts).route(list(aliases.values()))
            assert not routed.failures
            assert not routed.new_entities
            assert all(r.disposition == "deferred" and r.identity_blocker_ids for r in routed.routes)
            assert len(routed.routes) == len(aliases)
            for decision in routed.entity_decisions:
                memory.artifacts.save_entity_resolution_decision(decision)
            restarted = Mycelium(tmp_path / "store", config_path=Path(__file__).resolve().parents[1] / "mycelium.toml")
            pending = restarted.artifacts.list_entity_resolution_decisions(review_state="review_required")
            assert len(pending) == (2 if case == "distinct_ambiguous" else 1)
            for decision in pending:
                assert set(decision.candidate_entity_ids) == {"entity-18", "entity-29"}
                assert decision.supporting_claim_ids == ["c1"]
                assert decision.supporting_segment_ids == ["s1#0"]
            catalog = RoutingFormatter(restarted.artifacts).format_pending_identity_proposals(pending)
            assert "entity-18" in catalog and "entity-29" in catalog
            assert {e.entity_id for e in memory.artifacts.list_entities()} == {"you", "entity-18", "entity-29"}
            return
    finally:
        (tmp_path / "calls.json").write_text(json.dumps(list(memory.llm._call_log), indent=2, default=str))
    (tmp_path / "response.json").write_text(json.dumps(response, indent=2))
    print(case, tmp_path, json.dumps(response), flush=True)
    nodes = {n["node_id"]: n for n in planned_subjects(response, {e.entity_id: e for e in memory.artifacts.list_entities()})}
    participants = {p: n["node_id"] for n in nodes.values() for p in n["participant_evidence"]}
    if case in {"user", "project"}:
        assert nodes[participants["P001"]]["entity_id"] == "you"
        assert all(n["entity_type"] != "person" for n in nodes.values())
    if case == "namesakes":
        # Distinct identities in this evaluation input, not a production name rule.
        assert len([n for n in nodes.values() if n["entity_type"] == "person" and not n["participant_evidence"]]) == 2
        assert all(n["entity_id"] != "you" for n in nodes.values())
    if case == "project":
        assert len([n for n in nodes.values() if n["entity_type"] == "project"]) == 1
    if case == "two_speakers":
        assert nodes[participants["P001"]]["entity_id"] == "you"
        assert nodes[participants["P002"]]["entity_type"] == "person"
        assert len(nodes) == 2
        assert set(nodes[participants["P001"]]["supporting_evidence"]) & set(aliases) == {"C001", "C003"}
        assert set(nodes[participants["P002"]]["supporting_evidence"]) & set(aliases) == {"C002", "C004"}
    if case == "tool":
        assert len(nodes) == 2
        assert {n["entity_type"] for n in nodes.values()} == {"organization", "person"}
        assert all(n["resolution"] == "new" for n in nodes.values())
    if case == "existing":
        assert len(nodes) == 1
        assert next(iter(nodes.values()))["entity_id"] == "entity-73"
    if case in {"ambiguous", "ambiguous_rephrased", "distinct_ambiguous"}:
        unresolved = [n for n in nodes.values() if n["resolution"] == "review_required"]
        assert len(unresolved) == (2 if case == "distinct_ambiguous" else 1)
        for node in unresolved:
            assert set(node["candidate_entity_ids"]) == {"entity-18", "entity-29"}


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("MYCELIUM_RUN_IDENTITY_REPLAYS") != "1", reason="Opt-in host model probes")
async def test_staged_unnamed_identity_survives_revisit(tmp_path, monkeypatch):
    from dataclasses import asdict
    from mycelium.artifacts import EntityResolutionDecision
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(tmp_path / "store", config_path=Path(__file__).resolve().parents[1] / "mycelium.toml")
    entity = EntityRecord("person-traveler", "person", "The traveler", "traveler", [], "active",
                          "2026-09-08", "2026-09-08")
    source = SourceDocument("s1", "tool_observation", "s", "2026-09-08", None, [], [
        SourceSegment("s1#1", 0, "A traveler at the station repaired a radio on Monday.", role="tool"),
        SourceSegment("s1#2", 1, "That traveler also explained how the radio antenna works.", role="tool"),
    ])
    claims = [MemoryClaim(f"c{i}", seg.content, [], [ClaimProvenance("s1", [seg.segment_id])], "2026-09-08")
              for i, seg in enumerate(source.segments, 1)]
    memory.artifacts.save_source(source)
    for claim in claims:
        memory.artifacts.save_claim(claim)
    decision = EntityResolutionDecision("d1", "entity_creation", entity.entity_id, "person", entity.title,
        ["s1"], [c.claim_id for c in claims], [s.segment_id for s in source.segments], 0.9,
        "A particular traveler who repaired and explained a radio at the station.", "accepted", "first", "2026-09-08",
        identity_evidence_claim_ids=[c.claim_id for c in claims])
    router = ClaimRouter(memory.llm, memory.artifacts)
    result = await router.route([ClaimEvidence(claims[1], source)], dream_run_id="revisit",
                                 seed_entities=[entity], seed_identity_decisions=[decision])
    (tmp_path / "routing.json").write_text(json.dumps(asdict(result), indent=2, default=str))
    assert not result.failures
    assert {e.entity_id for e in result.new_entities} <= {entity.entity_id}
    assert result.routes[0].owner_entity_id == entity.entity_id
    assert result.routes[0].placed
    assert all(d.entity_id == entity.entity_id for d in result.entity_decisions)
