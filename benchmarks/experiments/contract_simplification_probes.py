"""Re-run compact production contracts against host Gemma.

Historical pre-integration requests remain in their dated artifact directories.
Each invocation uses a fresh output directory and prints its path.
"""

import asyncio
import json
import os
import sys
from jinja2 import Template
from mycelium.artifacts import SourceSegment
from mycelium.encoder import Encoder
from pathlib import Path

from mycelium import structured_outputs as contracts
from benchmarks.experiments.probe_support import RecordedSdk, fresh_run_root, write
from mycelium import prompts
from mycelium.ollama import OllamaClient

ROOT = fresh_run_root("contract-simplification")
PROMPTS = Path("mycelium/prompt_templates/memory")


async def call(name, system, user, schema, think=False):
    root = ROOT / "probes" / name
    if root.exists():
        raise ValueError(f"Use a fresh probe output directory: {root}")
    print(f"Output: {root}", flush=True)
    client = OllamaClient(
        "http://localhost:11434",
        "gemma4:12b",
        timeout=900,
        context_window_tokens=65536,
        reasoning_output_tokens=32768,
    )
    await client.client._client.aclose()
    sdk = RecordedSdk("gemma4:12b", root / "requests")
    client.client = sdk
    os.environ["MYCELIUM_LLM_DEBUG_DIR"] = str(root / "debug")
    try:
        result = await client.call_structured(
            system, user, schema, think=think, num_predict=8192, debug_label=name
        )
        result = schema.model_validate(result).model_dump()
        outcome = {"valid": True, "result": result}
    except Exception as exc:
        outcome = {"valid": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await sdk.close()
    write(root / "result.json", outcome)
    print(name, outcome, flush=True)


async def reason():
    for name, old, new in [
        (
            "changed",
            "Lena's bicycle is blue.",
            "Lena repainted that bicycle green yesterday; it is now green.",
        ),
        (
            "distinct",
            "Lena's touring bicycle is blue.",
            "Lena bought a second, green folding bicycle yesterday.",
        ),
        (
            "unclear",
            "A resident owns a blue bicycle.",
            "A visitor owns a green bicycle.",
        ),
    ]:
        _, user = prompts.fact_truth_prompt(
            "Lena (person)",
            json.dumps({"C001": {"text": old}}),
            "[]",
            "[]",
            json.dumps({"C002": {"text": new}}),
            "[]",
        )
        await call(
            "truth-" + name,
            (PROMPTS / "fact_truth.system.jinja").read_text(),
            user,
            contracts.fact_truth_output_model(["C001"]),
            True,
        )
    claims = {
        f"C{i:03d}": t
        for i, t in enumerate(
            [
                "Lena attended a workshop on May 3.",
                "That May 3 workshop began at 9 a.m.",
                "Lena attended a workshop on June 4.",
                "That June 4 workshop had twelve participants.",
                "Lena is considering learning sailing.",
                "Lena has not decided whether to learn sailing.",
                "Lena prefers written directions.",
            ],
            1,
        )
    }
    _, user = prompts.fact_synthesis_prompt(
        "Lena (person)",
        json.dumps({k: {"text": v} for k, v in claims.items()}),
        "[]",
        "[]",
        "history: completed events\nplans: future possibilities\npreferences: preferences",
    )
    await call(
        "synthesis",
        (PROMPTS / "fact_synthesis.system.jinja").read_text(),
        user,
        contracts.fact_synthesis_output_model(
            claims, ["history", "plans", "preferences"]
        ),
        True,
    )


async def extraction():
    async def extract(name, kind, ids, text, context="", context_ids=()):
        _, user = prompts.claim_extraction_prompt(
            kind, "source-1", ["Lena"], text, context
        )
        system = Template((PROMPTS / "extraction.system.jinja").read_text()).render(
            source_policy=prompts.render_prompt(
                prompts._EXTRACTION_POLICY_TEMPLATES[kind]
            )
        )
        await call(
            name,
            system,
            user,
            contracts.extraction_output_model(ids, context_ids),
            think=bool(context_ids) and "--context-reasoning" in sys.argv,
        )

    await extract(
        "extract-neutral",
        "agent_conversation",
        ["S1", "S2", "S3"],
        "[S1] speaker=Lena; role=user\nI joined a choir in April.\n\n[S2] speaker=Lena; role=user\nI prefer written updates.\n\n[S3] speaker=Lena; role=user\nI am considering a pottery class, but have not decided.",
    )
    for name, reply in [
        ("accept", "Yes, I will do that next Saturday."),
        ("refuse", "I might try it eventually, but I will not do that next Saturday."),
    ]:
        await extract(
            "extract-" + name,
            "agent_conversation",
            ["S1"],
            "[S1] speaker=Lena; role=user\n" + reply,
            "[P1] role=assistant\nYou could repair the garden gate with cedar boards next Saturday.",
            ["P1"],
        )
    source = json.loads(
        Path(
            "benchmark_runs/reasoning-policy-20260909-locomo/stores/conv-26/artifacts/sources/source-ed6698b588b14e40.json"
        ).read_text()
    )
    segments = [SourceSegment(**s) for s in source["segments"][:48]]
    _, user = prompts.claim_extraction_prompt(
        source["source_type"],
        source["source_id"],
        source["participants"],
        Encoder._render_claim_segments(segments),
    )
    system = Template((PROMPTS / "extraction.system.jinja").read_text()).render(
        source_policy=prompts.render_prompt(
            prompts._EXTRACTION_POLICY_TEMPLATES[source["source_type"]]
        )
    )
    await call(
        "extract-natural",
        system,
        user,
        contracts.extraction_output_model([s.segment_id for s in segments]),
    )

    # Current attribution/presentation probes live in attribution_contract_probes.


async def context_selection():
    records = "\n".join(
        [
            'M001: {"content":"Lena prefers written directions."}',
            'M002: {"content":"Lena owns a bicycle."}',
            'M003: {"content":"Lena grows tomatoes."}',
        ]
    )
    for name, query in [
        ("relevant", "How should I give Lena directions?"),
        ("unrelated", "What is the height of the tallest mountain?"),
    ]:
        system, user = prompts.assistant_context_selection_prompt(query, records)
        await call(
            "context-" + name,
            system,
            user,
            contracts.complementary_selection_model(["M001", "M002", "M003"]),
        )


if __name__ == "__main__":
    asyncio.run(
        context_selection()
        if "--context" in sys.argv
        else extraction()
        if "--extraction" in sys.argv
        else reason()
    )
