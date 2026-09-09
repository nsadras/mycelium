"""Neutral cumulative-memory contracts and opt-in host-model checks."""

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from mycelium import Mycelium, prompts
from mycelium.structured_outputs import fact_truth_output_model


def scope_record(relation="same"):
    return {
        "prior_referent": "The existing occurrence",
        "incoming_referent": "The reported occurrence",
        "reason": "The evidence establishes the declared scope.",
        "relation": relation,
    }


def test_truth_change_requires_same_scope():
    schema = fact_truth_output_model(["C003"], ["C001", "C002"])
    decision = {
        "disposition": "truth_change",
        "relation": "contradicts",
        "target_claim_aliases": ["C001"],
        "durable_field": "color",
        "prior_state": "blue",
        "incoming_state": "green",
        "transition_evidence": "An explicit correction",
        "explanation": "Same object and time",
        "confidence": 0.9,
        "scope": {"C001": scope_record(), "C002": scope_record("distinct")},
    }
    schema.model_validate({"decisions": {"C003": decision}})
    decision["target_claim_aliases"] = ["C002"]
    with pytest.raises(ValidationError, match="same scope"):
        schema.model_validate({"decisions": {"C003": decision}})


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
            "temporal": None,
            "source_times": [
                {
                    "source_id": "s" + date,
                    "occurred_at": date,
                    "segments": [{"segment_id": "seg" + date, "timestamp": date}],
                }
            ],
        }

    system, user = prompts.fact_truth_prompt(
        "Rina (person)",
        json.dumps({"C001": record(old, oldtime)}),
        "none",
        "none",
        json.dumps({"C002": record(new, newtime)}),
        "[]",
    )
    schema = fact_truth_output_model(["C002"], ["C001"])
    result = await memory.llm.call_structured(
        system, user, schema, num_predict=2048, dump_success=True
    )
    (tmp_path / "response.json").write_text(json.dumps(result, indent=2))
    assert result["decisions"]["C002"]["disposition"] == expected
