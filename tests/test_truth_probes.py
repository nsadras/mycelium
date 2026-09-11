"""Direct production truth-review probes; fixtures never enter product prompts."""
import json
import os
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock

import pytest

from mycelium import Mycelium, prompts
from mycelium.structured_outputs import fact_truth_output_model
from tests.model_probe_helpers import capture


CASES = [
    ("same_domain_plans", "Mira plans to take her children skating.",
     "Mira plans to take her children hiking next month.", "no_change", None),
    ("independent_plans", "Mira plans to learn pottery.", "Mira plans to join a choir.", "no_change", None),
    ("additional_detail", "Mira's workshop is on Tuesday.", "Mira's workshop has eight seats.", "no_change", None),
    ("uncertain_alternative", "Mira lives in Oslo.", "Mira is considering moving to Lisbon.", "no_change", None),
    ("separate_events", "Mira visited Oslo in May.", "Mira visited Lisbon in June.", "no_change", None),
    ("replacement", "Mira's sole mailing address is in Oslo.",
     "Mira has moved her sole mailing address to Lisbon, replacing the Oslo address.", "truth_change", "supersedes"),
    ("contradiction", "Mira's only bicycle was blue on August 1, 2026.",
     "Mira's only bicycle was red, not blue, on August 1, 2026.", "truth_change", "contradicts"),
    ("cancellation", "Mira plans to attend the September workshop.",
     "Mira has cancelled her plan to attend the September workshop.", "truth_change", "supersedes"),
]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("MYCELIUM_RUN_TRUTH_PROBES") != "1", reason="Opt-in host Ollama probes")
@pytest.mark.parametrize("name,prior,incoming,disposition,relation", CASES, ids=[c[0] for c in CASES])
async def test_truth_review(tmp_path, monkeypatch, name, prior, incoming, disposition, relation):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm-errors"))
    memory = Mycelium(tmp_path / "store", config_path=Path(__file__).resolve().parents[1] / "mycelium.toml")
    schema = fact_truth_output_model(["C001"])
    system, user = prompts.fact_truth_prompt(
        "Mira (person)", json.dumps({"C001": prior}), "none", "none",
        json.dumps({"C002": incoming}), "[]",
    )
    result = schema.model_validate(await memory.llm.call_structured(
        system, user, schema, num_predict=2048, debug_label="truth-probe", think=True,
    )).model_dump()
    (tmp_path / "response.json").write_text(json.dumps(result, indent=2))
    print(name, tmp_path, json.dumps(result), flush=True)
    decision = result
    assert (decision["relation"] == "no_change") == (disposition == "no_change")
    if relation:
        assert decision["relation"] == relation
        assert decision["changed_targets"] == ["C001"]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("MYCELIUM_RUN_TRUTH_PROBES") != "1", reason="Opt-in host Ollama replays")
@pytest.mark.parametrize("prior,incoming,relation", [
    ("I plan to take my children skating.", "I plan to take my children hiking next month.", None),
    ("My sole mailing address is in Oslo.",
     "I have moved my sole mailing address to Lisbon, replacing my Oslo address.", "supersedes"),
    ("My only bicycle was blue on August 1, 2026.",
     "My only bicycle was red, not blue, on August 1, 2026.", "contradicts"),
], ids=["compatible_plans", "replacement", "contradiction"])
async def test_truth_review_two_builds(tmp_path, monkeypatch, prior, incoming, relation):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm-errors"))
    memory = Mycelium(tmp_path / "store", config_path=Path(__file__).resolve().parents[1] / "mycelium.toml")
    await capture(memory, [{"role": "user", "content": prior}], "prior")
    first = await memory.consolidate()
    assert not first.report.failures
    accepted = {c.claim_id: c.text for c in memory.artifacts.list_claims()}
    assert accepted
    prior_states = {e.entity_id: e.materialization_state for e in memory.artifacts.list_entities()}
    revision = Mock(wraps=memory.consolidator.policy.scope_revision_claims)
    monkeypatch.setattr(memory.consolidator.policy, "scope_revision_claims", revision)
    await capture(memory, [{"role": "user", "content": incoming}], "incoming")
    second = await memory.consolidate()
    (tmp_path / "build.json").write_text(json.dumps(asdict(second), indent=2, default=str))
    (tmp_path / "calls.json").write_text(json.dumps(list(memory.llm._call_log), indent=2, default=str))
    assert not second.report.failures
    for call in revision.call_args_list:
        assert call.args[1]
        assert all(prior_states.get(e.entity_id) != "materialized" for e in call.args[1])
    proposals = memory.artifacts.list_reconsolidation_proposals()
    (tmp_path / "proposals.json").write_text(json.dumps([asdict(p) for p in proposals], indent=2))
    if relation:
        assert len(proposals) == 1
        assert proposals[0].proposed_relation == relation
        assert proposals[0].status == "pending"
        assert set(proposals[0].target_claim_ids).issubset(accepted)
    else:
        assert proposals == []
    for claim_id, text in accepted.items():
        claim = memory.artifacts.get_claim(claim_id)
        assert claim.status == "active" and claim.text == text
    if relation:
        await capture(memory, [{"role": "user", "content": "I joined a choir last month."}], "unrelated")
        third = await memory.consolidate()
        assert not third.report.failures
        held = {cid for p in memory.artifacts.list_reconsolidation_proposals(status="pending")
                for cid in p.incoming_claim_ids}
        represented = {cid for fact in memory.artifacts.list_consolidated_facts()
                       for cid in fact.member_claim_ids}
        eligible = {p.claim_id for p in memory.artifacts.list_placements() if p.status == "placed"} - held
        assert eligible <= represented
        assert not held & represented
        (tmp_path / "third-build.json").write_text(json.dumps(asdict(third), indent=2, default=str))
