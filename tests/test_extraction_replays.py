"""Real-model extraction probes and public capture/build/retrieval replays.

MYCELIUM_RUN_EXTRACTION_REPLAYS=1 .venv/bin/pytest -q -s tests/test_extraction_replays.py
"""
import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from mycelium import Mycelium, SourceInput
from mycelium import prompts
from mycelium.structured_outputs import extraction_output_model
from tests.model_probe_helpers import capture, check_meaning

CASES = json.loads((Path(__file__).parent / "fixtures/extraction_replays.json").read_text())
CONFIG = Path(__file__).resolve().parents[1] / "mycelium.toml"
pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.skipif(
    os.getenv("MYCELIUM_RUN_EXTRACTION_REPLAYS") != "1",
    reason="Set MYCELIUM_RUN_EXTRACTION_REPLAYS=1 for real Ollama probes/replays",
)]


async def test_meaning_judge_rejects_strengthened_intention(tmp_path):
    memory = Mycelium(tmp_path / "store", config_path=CONFIG)
    with pytest.raises(AssertionError):
        await check_meaning(memory, {
            "expected": "The user is considering learning to sail.",
            "forbidden": "The user has decided to learn to sail.",
        }, ["The user plans to learn to sail."], tmp_path / "meaning.json")


async def test_large_extraction_partition(tmp_path, monkeypatch):
    """Exercise a full-size batch; tiny turns alone missed accounting overlap."""
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm-errors"))
    memory = Mycelium(tmp_path / "store", config_path=CONFIG)
    assertions = [
        "I work as a librarian.", "I enjoy landscape painting.",
        "My sister lives in Oslo.", "I own a blue bicycle.",
        "I am learning Spanish.", "I volunteer at an animal shelter.",
        "I prefer written directions.", "I joined a choir last month.",
        "I am considering a trip in October.", "I dislike crowded concerts.",
        "I have two cats.", "I grow tomatoes on my balcony.",
    ]
    messages = [message for assertion in assertions for message in (
        {"role": "user", "content": assertion},
        {"role": "assistant", "content": "Thanks for sharing."},
        {"role": "user", "content": "You're welcome."},
        {"role": "assistant", "content": "Is there anything else?"},
    )]
    captured = await capture(memory, messages, "large")
    source = memory.artifacts.get_source(captured.source_ids[0])
    schema = extraction_output_model([s.segment_id for s in source.segments])
    system, user = prompts.claim_extraction_prompt(
        source.source_type, source.source_id, source.participants,
        memory.encoder._render_claim_segments(source.segments),
    )
    result = schema.model_validate(await memory.llm.call_structured(
        system, user, schema, num_predict=8192, debug_label="large-partition",
    )).model_dump()
    (tmp_path / "response.json").write_text(json.dumps(result, indent=2))
    assert result["claims"] and result["source_only"]
    await check_meaning(memory, {
        "expected": "The user works as a librarian and grows tomatoes on their balcony.",
        "forbidden": "The user has committed to an October trip.",
    }, result["claims"], tmp_path / "meaning.json")


async def test_long_multiparty_concrete_admission(tmp_path, monkeypatch):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm-errors"))
    memory = Mycelium(tmp_path / "store", config_path=CONFIG)
    statements = [
        "Last weekend I stayed in a small cabin near the coast.",
        "I made lentil soup with roasted peppers on Sunday evening.",
        "I saw my doctor yesterday about my wrist.",
        "My wrist is still sore but improving; the doctor said it wasn't fractured.",
        "I practiced landscape painting at the community studio on Monday.",
        "I have been keeping a journal to manage stress.",
        "I took my daughter to her dentist appointment on Tuesday.",
        "My daughter needs another dentist appointment next month.",
    ]
    segments = [segment for statement in statements for segment in (
        {"speaker": "Mira", "content": statement},
        {"speaker": "Noah", "content": "Thanks for sharing. Keep going, you've got this!"},
        {"speaker": "Mira", "content": "Thanks for listening."},
        {"speaker": "Noah", "content": "Of course. What else is new?"},
    )]
    captured = await memory.ingest_source(SourceInput(
        transcript="\n".join(f"{s['speaker']}: {s['content']}" for s in segments),
        source_type="multi_party_conversation", participants=("Mira", "Noah"),
        session_id="neutral-long", idempotency_key="neutral-long",
        segments=tuple({**s, "segment_id": "", "index": i,
                        "metadata": {"fixture_assertion": i % 4 == 0}}
                       for i, s in enumerate(segments)),
    ))
    source = memory.artifacts.get_source(captured.source_ids[0])
    schema = extraction_output_model([s.segment_id for s in source.segments])
    system, user = prompts.claim_extraction_prompt(
        source.source_type, source.source_id, source.participants,
        memory.encoder._render_claim_segments(source.segments),
    )
    result = schema.model_validate(await memory.llm.call_structured(
        system, user, schema, num_predict=8192, debug_label="multiparty-admission",
    )).model_dump()
    (tmp_path / "response.json").write_text(json.dumps(result, indent=2))
    cited = {sid for c in result["claims"] for sid in c["segment_ids"]}
    assert {s.segment_id for s in source.segments if s.metadata["fixture_assertion"]} <= cited
    assert {s.segment_id for s in source.segments if not s.metadata["fixture_assertion"]}.isdisjoint(cited)
    await check_meaning(memory, {
        "expected": "Mira stayed in a coastal cabin last weekend, made lentil soup with roasted peppers on "
                    "Sunday evening, and has a sore but improving wrist that the doctor said was not fractured.",
        "forbidden": "Mira's wrist is fully healed.",
    }, result["claims"], tmp_path / "meaning.json")


async def test_tool_admission_preserves_business_facts_not_transport_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm-errors"))
    memory = Mycelium(tmp_path / "store", config_path=CONFIG)
    payload = json.dumps({
        "result": "Harbor Workshop is a bicycle repair business at 42 Wharf Road, founded by Elena Ruiz in 2019.",
        "transport_metadata": {"operator": "Noah", "request_id": "request-7", "elapsed_ms": 41},
    })
    captured = await memory.ingest_source(SourceInput(
        transcript=payload, source_type="tool_observation", session_id="tool-probe",
        idempotency_key="tool-probe", segments=({"segment_id": "", "index": 0, "content": payload, "role": "tool"},),
    ))
    source = memory.artifacts.get_source(captured.source_ids[0])
    schema = extraction_output_model([s.segment_id for s in source.segments])
    system, user = prompts.claim_extraction_prompt(
        source.source_type, source.source_id, source.participants,
        memory.encoder._render_claim_segments(source.segments),
    )
    result = schema.model_validate(await memory.llm.call_structured(system, user, schema, num_predict=8192)).model_dump()
    (tmp_path / "response.json").write_text(json.dumps(result, indent=2))
    await check_meaning(memory, {
        "expected": "Harbor Workshop is a bicycle repair business at 42 Wharf Road, founded by Elena Ruiz in 2019.",
        "forbidden": "Noah operates Harbor Workshop.",
    }, result["claims"], tmp_path / "meaning.json")


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
@pytest.mark.parametrize("mode", ["probe", "replay"])
async def test_extraction_contract_in_real_system(tmp_path, monkeypatch, case, mode):
    print(f"{mode} {case['name']}: {tmp_path}", flush=True)
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm-errors"))
    memory = Mycelium(tmp_path / "store", config_path=CONFIG)
    prior_ids = ()
    if case["context"]:
        prior_ids = (await capture(memory, case["context"], "prior")).source_ids
    result = await capture(memory, case["messages"], "current", prior_ids)
    source = memory.artifacts.get_source(result.source_ids[0])
    context = [memory.artifacts.get_source(s) for s in prior_ids]
    assert memory.artifacts.list_claims() == []
    if mode == "probe":
        schema = extraction_output_model(
            [s.segment_id for s in source.segments],
            [s.segment_id for p in context for s in p.segments],
        )
        system, user = prompts.claim_extraction_prompt(
            source.source_type, source.source_id, source.participants,
            memory.encoder._render_claim_segments(source.segments),
            context=memory.encoder._render_segments([s for p in context for s in p.segments]),
        )
        response = schema.model_validate(await memory.llm.call_structured(
            system, user, schema, num_predict=8192, think=any(p.segments for p in context),
        )).model_dump()
        (tmp_path / "response.json").write_text(json.dumps(response, indent=2))
        if not case["expected"]:
            assert response["claims"] == []
        else:
            if case["context"]:
                assert any(c["context_segment_ids"] for c in response["claims"])
            await check_meaning(memory, case, response["claims"], tmp_path / "meaning.json")
        return

    build = await memory.consolidate()
    (tmp_path / "build.json").write_text(json.dumps(asdict(build), indent=2, default=str))
    assert build.report.failures == []
    episodes = memory.artifacts.list_episodes()
    assert all(e.extraction_status == "complete" for e in episodes)
    assert all(b.attempt_count == 1 for e in episodes for b in e.extraction_batches)
    claims = memory.artifacts.list_claims()
    if not case["expected"]:
        assert claims == []
        assert all(d.disposition == "source_only" and d.reason for e in episodes for d in e.segment_dispositions)
    else:
        current_claims = [c for c in claims if c.provenance[0].source_id == source.source_id]
        assert current_claims
        if prior_ids:
            assert any(p.source_id in prior_ids for c in current_claims for p in c.provenance)
        await check_meaning(memory, case, [asdict(c) for c in current_claims], tmp_path / "extracted_meaning.json")
        current_ids = {c.claim_id for c in current_claims}
        rendered = [item["text"] for page in memory.wiki.list()
                    for section in page.sections for item in section["items"]
                    if item["kind"] == "fact" and current_ids.intersection(item["claim_ids"])]
        (tmp_path / "wiki_statements.json").write_text(json.dumps(rendered, indent=2))
        await check_meaning(memory, case, rendered, tmp_path / "wiki_meaning.json")

    # Restart and no-work Build must neither re-extract nor duplicate sources/claims.
    def extracted_snapshot(claims):
        return {c.claim_id: {k: v for k, v in asdict(c).items() if not k.startswith("dream_")} for c in claims}

    before = extracted_snapshot(claims)
    memory = Mycelium(tmp_path / "store", config_path=CONFIG)
    assert (await memory.consolidate()).processed_episode_ids == ()
    assert extracted_snapshot(memory.artifacts.list_claims()) == before
    async with memory.session(case["query"]) as session:
        assert session.transcript == []
        evidence = session.memory_evidence
        (tmp_path / "retrieved.json").write_text(json.dumps(asdict(evidence), indent=2))
        if not case["expected"]:
            assert evidence.records == ()
        else:
            assert any(c.source_id == source.source_id for r in evidence.records for c in r.citations)
            await check_meaning(memory, case, [r.statement for r in evidence.records], tmp_path / "retrieved_meaning.json")
