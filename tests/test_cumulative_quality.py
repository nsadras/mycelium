"""Neutral cumulative-memory contracts and opt-in host-model checks."""

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from mycelium import Mycelium, prompts
from mycelium.structured_outputs import extraction_records
from mycelium.truth_review import TruthReviewer


TEMPORAL_CASES = [
    (
        "separate_occurrences",
        "2026-02-12",
        "Rina injured her wrist skating last Saturday.",
        "2026-07-19",
        "Rina injured her wrist after falling from a ladder last Tuesday.",
        "no_change",
    ),
    (
        "different_objects",
        "2026-02-12",
        "Rina sold her old laptop.",
        "2026-07-19",
        "Rina's new laptop stopped charging.",
        "no_change",
    ),
    (
        "same_occurrence",
        "2026-07-19",
        "Rina's wrist injury happened on July 14 while skating.",
        "2026-07-20",
        "The July 14 wrist injury was from falling from a ladder, not skating.",
        "truth_change",
    ),
    (
        "explicit_transition",
        "2026-02-12",
        "Rina's sole mailing address is in Oslo.",
        "2026-07-19",
        "Rina moved her sole mailing address to Lisbon, replacing Oslo.",
        "truth_change",
    ),
]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("MYCELIUM_RUN_CUMULATIVE_PROBES") != "1",
    reason="Opt-in host-model contracts",
)
@pytest.mark.parametrize(
    "name,oldtime,old,newtime,new,expected",
    TEMPORAL_CASES,
    ids=[c[0] for c in TEMPORAL_CASES],
)
async def test_temporal_scope_contract(
    tmp_path, monkeypatch, name, oldtime, old, newtime, new, expected
):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(
        tmp_path / "store",
        config_path=Path(__file__).resolve().parents[1] / "mycelium.toml",
    )

    def record(text, date):
        return {
            "text": text,
            "temporal_status": "unknown",
            "temporal": [],
            "source_times": [
                {
                    "source_id": "s" + date,
                    "occurred_at": date,
                    "segments": [{"segment_id": "seg" + date, "timestamp": date}],
                }
            ],
        }

    result = (await TruthReviewer(memory.llm, memory.artifacts)._compare_pairs(
        [("older", "newer")],
        {"older": record(old, oldtime), "newer": record(new, newtime)},
    ))[("older", "newer")]
    (tmp_path / "response.json").write_text(json.dumps(result, indent=2))
    assert ("truth_change" if result["relation"] != "no_change" else "no_change") == expected


def test_extraction_requires_explicit_temporal_classification():
    from mycelium.structured_outputs import extraction_output_model
    schema = extraction_output_model(["s1"])
    claim = {'text': 'A stored assertion.', 'about': [{'entity': 'user', 'role': 'subject'}], 'segment_ids': ['s1'], 'claim_type': 'unknown', 'evidence_modality': 'unknown', 'facets': {'times': [], 'inference_basis': None}}
    with pytest.raises(ValidationError, match="temporal_status"):
        schema.model_validate({"segments": {"s1": {"claims": [claim]}}})
    claim["temporal_status"] = "unknown"
    schema.model_validate({"segments": {"s1": {"claims": [claim]}}})


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("MYCELIUM_RUN_CUMULATIVE_PROBES") != "1", reason="Opt-in host-model contracts")
async def test_extraction_temporal_and_fidelity_contract(tmp_path, monkeypatch):
    from mycelium.structured_outputs import extraction_output_model
    from tests.model_probe_helpers import check_meaning
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(tmp_path / "store", config_path=Path(__file__).resolve().parents[1] / "mycelium.toml")
    texts = [
        "I decided to repair my old camera and donate it.",
        "I donated the repaired camera yesterday.",
        "The breathing exercises have helped me sleep.",
        "I slipped while returning from the market last Thursday.",
        "During the retreat last month, we stayed in a quiet guesthouse beside the harbor.",
        "I practice the flute every morning.",
    ]
    ids = [f"S{i}" for i in range(1, 7)]
    system, user = prompts.claim_extraction_prompt("agent_conversation", "s", ["user"],
        "\n".join(f"[{sid}] speaker=user; role=user\n{text}" for sid, text in zip(ids, texts)))
    response = await memory.llm.call_structured(system, user, extraction_output_model(ids),
                                               num_predict=8192, dump_success=True)
    (tmp_path / "response.json").write_text(json.dumps(response, indent=2))
    claims = extraction_records(response)["claims"]
    assert {sid for c in claims for sid in c["segment_ids"]} == set(ids)
    for sid, state in {"S2": "past", "S4": "past", "S5": "past", "S6": "recurring"}.items():
        assert all(c["temporal_status"] == state for c in claims if sid in c["segment_ids"])
    for sid, expected, forbidden in [
        ("S1", "The user decided to repair and donate their old camera.", "The user already donated the camera."),
        ("S4", "The user slipped on the return journey from the market.", "The user slipped on the journey to the market."),
    ]:
        await check_meaning(memory, {"expected": expected, "forbidden": forbidden},
                            [c for c in claims if sid in c["segment_ids"]], tmp_path / f"meaning-{sid}.json")
