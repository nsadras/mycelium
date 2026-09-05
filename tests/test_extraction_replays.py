"""Real-model extraction probes and public capture/build/retrieval replays.

MYCELIUM_RUN_EXTRACTION_REPLAYS=1 .venv/bin/pytest -q -s tests/test_extraction_replays.py
"""
import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from mycelium import Mycelium, SourceInput
from mycelium import prompts
from mycelium.structured_outputs import extraction_output_model

CASES = json.loads((Path(__file__).parent / "fixtures/extraction_replays.json").read_text())
CONFIG = Path(__file__).resolve().parents[1] / "mycelium.toml"
pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.skipif(
    os.getenv("MYCELIUM_RUN_EXTRACTION_REPLAYS") != "1",
    reason="Set MYCELIUM_RUN_EXTRACTION_REPLAYS=1 for real Ollama probes/replays",
)]


class MeaningVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_supported: bool
    forbidden_asserted: bool
    reason: str


async def check_meaning(memory, case, statements, path):
    # A model judge handles paraphrases; exact source IDs and batch accounting
    # are checked separately. This judge is evaluation-only, not product logic.
    verdict = await memory.llm.call_structured(
        "Evaluate whether the supplied stored assertions entail the expected assertion and "
        "whether they assert the forbidden assertion. Mere mention or explicit negation is "
        "not assertion. Do not infer agreement from a proposal, consideration, or refusal. "
        "Return schema-valid JSON and explain the evidence.",
        json.dumps({"statements": statements, "expected": case["expected"], "forbidden": case["forbidden"]}),
        MeaningVerdict, num_predict=2048,
    )
    path.write_text(json.dumps(verdict, indent=2))
    assert verdict["expected_supported"], verdict
    assert not verdict["forbidden_asserted"], verdict


async def capture(memory, messages, key, context_ids=()):
    return await memory.ingest_source(SourceInput(
        transcript="\n".join(f"{m['role']}: {m['content']}" for m in messages),
        session_id="conversation", idempotency_key=key,
        segments=tuple({**m, "segment_id": "", "index": i, "speaker": m["role"],
                        "timestamp": "2026-09-04T12:00:00+00:00"} for i, m in enumerate(messages)),
        metadata={"context_source_ids": list(context_ids)},
    ))


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
            system, user, schema, num_predict=8192,
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
