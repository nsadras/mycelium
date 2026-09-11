"""Opt-in host-model comparison using production contracts and isolated stores."""
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from ollama import AsyncClient

from benchmarks.experiments import reasoning_contract_probes as probes
from benchmarks.experiments.probe_support import RecordedSdk, fresh_run_root, write
from mycelium import Mycelium, SourceInput
from mycelium.artifacts import SourceSegment
from mycelium.encoder import Encoder
from mycelium.ollama import OllamaClient
from mycelium.structured_outputs import extraction_output_model

ROOT = fresh_run_root("model-contract-comparison")
MODELS = ("gemma4:12b", "qwen3.5:9b")


async def contracts(model, root):
    catalog = {}

    async def collect(name, system, user, schema, **kwargs):
        catalog[name] = (system, user, schema, kwargs)

    await probes.run_contracts(collect)
    for name in ("extraction-native-False", "truth-changed", "truth-distinct", "synthesis"):
        target = root / name
        if target.exists():
            raise ValueError(f"Use a fresh contract output directory: {target}")
        system, user, schema, _ = catalog[name]
        think = name != "extraction-native-False"
        client = OllamaClient("http://localhost:11434", model, timeout=900,
                              context_window_tokens=65536, reasoning_output_tokens=32768)
        await client.client._client.aclose()
        transport = RecordedSdk(model, target / "requests")
        client.client = transport
        os.environ["MYCELIUM_LLM_DEBUG_DIR"] = str(target / "debug")
        started = time.monotonic()
        try:
            result = await client.call_structured(system, user, schema, think=think,
                                                  num_predict=8192, debug_label=name)
            outcome = {"valid": True, "result": result}
        except Exception as exc:
            outcome = {"valid": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            await transport.close()
        outcome["seconds"] = time.monotonic() - started
        write(target / "result.json", outcome)
        print(model, name, outcome, flush=True)


async def cumulative(model, root):
    if root.exists():
        raise ValueError(f"Use a fresh cumulative output directory: {root}")
    batches = [
        ["I work as a librarian.", "I own a blue bicycle.", "I enjoy watercolor painting."],
        ["I have worked as a librarian for ten years.", "My bicycle has a wicker basket.",
         "I prefer painting landscapes in watercolor."],
        ["I still enjoy watercolor painting.", "I am considering taking a pottery class, but have not decided.",
         "I prefer written directions."],
    ]
    started = time.monotonic()
    outcome = {"builds": []}
    try:
        for index, statements in enumerate(batches, 1):
            memory = Mycelium(root / "store", config_path=Path("mycelium.toml"))
            memory.config.llm.model = model
            memory.llm.model = model
            await memory.llm.client._client.aclose()
            transport = RecordedSdk(model, root / "requests")
            memory.llm.client = transport
            os.environ["MYCELIUM_LLM_DEBUG_DIR"] = str(root / "debug")
            try:
                await memory.ingest_source(SourceInput(
                    transcript="\n".join(statements), session_id=f"batch-{index}",
                    idempotency_key=f"batch-{index}",
                    segments=tuple({"role": "user", "speaker": "user", "content": text,
                                    "segment_id": "", "index": i,
                                    "timestamp": "2026-09-04T12:00:00+00:00"}
                                   for i, text in enumerate(statements))))
                build = await memory.consolidate()
                outcome["builds"].append(asdict(build))
                write(root / f"build-{index}.json", asdict(build))
                if build.report.failures:
                    raise ValueError(str(build.report.failures))
                facts = memory.artifacts.list_consolidated_facts()
                outcome["facts"] = [asdict(f) for f in facts]
                outcome["claim_count"] = len(memory.artifacts.list_claims())
                if index == len(batches):
                    represented = {cid for fact in facts for cid in fact.member_claim_ids}
                    claim_ids = {claim.claim_id for claim in memory.artifacts.list_claims()}
                    outcome["quality"] = {
                        "represented_claim_count": len(represented),
                        "unrepresented_claim_ids": sorted(claim_ids - represented),
                        "unknown_member_ids": sorted(represented - claim_ids),
                    }
                    async with memory.session("What do you remember about my bicycle?") as session:
                        outcome["retrieval"] = asdict(session.memory_evidence)
            finally:
                await transport.close()
        outcome["completed"] = True
    except Exception as exc:
        outcome.update(completed=False, error=f"{type(exc).__name__}: {exc}")
    outcome["seconds"] = time.monotonic() - started
    write(root / "result.json", outcome)
    print(model, "cumulative", outcome.get("completed"), outcome["seconds"], flush=True)


async def main():
    print(f"Output: {ROOT}", flush=True)
    for model in MODELS:
        root = ROOT / model.replace(":", "-")
        sdk = AsyncClient(host="http://localhost:11434", timeout=900)
        try:
            warmup = await sdk.chat(model=model, messages=[{"role": "user", "content": "Reply with OK."}],
                                    think=False, options={"num_ctx": 65536, "num_predict": 64})
            write(root / "warmup.json", warmup.model_dump(mode="json", exclude_none=True))
        finally:
            await sdk._client.aclose()
        await contracts(model, root / "contracts")
        await cumulative(model, root / "cumulative")


async def natural():
    print(f"Output: {ROOT}", flush=True)
    source_path = Path("benchmark_runs/reasoning-policy-20260909-locomo/stores/conv-26/artifacts/sources/source-ed6698b588b14e40.json")
    source = json.loads(source_path.read_text())
    segments = [SourceSegment(**s) for s in source["segments"][:48]]
    system, user = probes.prompts.claim_extraction_prompt(
        source["source_type"], source["source_id"], source["participants"],
        Encoder._render_claim_segments(segments))
    schema = extraction_output_model([s.segment_id for s in segments])
    for model in MODELS:
        root = ROOT / model.replace(":", "-") / "natural-extraction"
        if root.exists():
            raise ValueError(f"Use a fresh extraction output directory: {root}")
        client = OllamaClient("http://localhost:11434", model, timeout=900,
                              context_window_tokens=65536, reasoning_output_tokens=32768)
        warmup = await client.client.chat(model=model,
            messages=[{"role": "user", "content": "Reply with OK."}], think=False,
            options={"num_ctx":65536, "num_predict":64})
        write(root / "warmup.json", warmup.model_dump(mode="json", exclude_none=True))
        await client.client._client.aclose()
        transport = RecordedSdk(model, root / "requests")
        client.client = transport
        os.environ["MYCELIUM_LLM_DEBUG_DIR"] = str(root / "debug")
        started = time.monotonic()
        try:
            result = await client.call_structured(system, user, schema, think=False,
                                                  num_predict=8192, debug_label="natural-extraction")
            outcome = {"valid":True, "result":result}
        except Exception as exc:
            outcome = {"valid":False, "error":f"{type(exc).__name__}: {exc}"}
        finally:
            await transport.close()
        outcome["seconds"] = time.monotonic() - started
        write(root / "result.json", outcome)
        print(model, "natural-extraction", outcome["valid"], outcome["seconds"], flush=True)


if __name__ == "__main__":
    asyncio.run(natural() if "--natural-only" in sys.argv else main())
