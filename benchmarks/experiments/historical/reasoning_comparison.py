"""Historical 2026-09-09 reasoning experiment; see benchmarks/README.md."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from ollama import AsyncClient

from mycelium import Mycelium, SourceInput, prompts
from mycelium.budget import count_tokens, require_request_budget
from mycelium.structured_outputs import extraction_output_model
from benchmarks.suites.locomo import iter_locomo_sessions
from benchmarks.experiments.probe_support import write

ROOT = Path("benchmark_runs/reasoning-comparison-20260909")
OUTPUT_TOKENS = 16384
CONTEXT_TOKENS = 32768
TEMPERATURE = 0.0


class RecordedTransport:
    def __init__(self, llm, root, think, temperature=0.0):
        self.client = AsyncClient(host=llm.url, timeout=900)
        self.root = root
        self.think = think
        self.calls = 0
        self.temperature = temperature

    async def chat(self, **kwargs):
        self.calls += 1
        if getattr(self, "omit_format", False):
            kwargs.pop("format", None)
        kwargs["think"] = self.think
        kwargs["options"] = {**kwargs["options"], "num_ctx": CONTEXT_TOKENS,
                             "num_predict": OUTPUT_TOKENS, "seed": 17,
                             "temperature": self.temperature, "top_k": 64, "top_p": 0.95}
        estimated = require_request_budget(kwargs["messages"], context_window=CONTEXT_TOKENS,
                                           output_tokens=OUTPUT_TOKENS, schema=kwargs.get("format"),
                                           tools=kwargs.get("tools"))
        path = self.root / "requests" / f"{self.calls:04d}.json"
        record = {"request": kwargs, "estimated_input_tokens": estimated,
                  "input_sha256": hashlib.sha256(json.dumps(kwargs["messages"], sort_keys=True).encode()).hexdigest()}
        write(path, record)
        start = time.perf_counter()
        try:
            result = await self.client.chat(**kwargs)
            response = result.model_dump(mode="json", exclude_none=True)
            record["response"] = response
            record["thinking_chars"] = len(result.message.thinking or "")
            record["thinking_estimated_tokens"] = count_tokens(result.message.thinking or "")
            record["content_estimated_tokens"] = count_tokens(result.message.content or "")
            record["truncated"] = result.done_reason == "length"
            return result
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            record["elapsed_seconds"] = time.perf_counter() - start
            write(path, record)


def instrument(memory, root, think):
    llm = memory.llm
    llm.context_window_tokens = CONTEXT_TOKENS
    memory.config.llm.context_window_tokens = CONTEXT_TOKENS
    llm.client = RecordedTransport(llm, root, think, temperature=TEMPERATURE)
    original = llm.call_structured

    async def call(system, user, schema, **kwargs):
        kwargs["num_predict"] = OUTPUT_TOKENS
        return await original(system, user, schema, **kwargs)

    llm.call_structured = call
    os.environ["MYCELIUM_LLM_DEBUG_DIR"] = str(root / "failures")
    return memory


def memory_at(root, think, profile="user"):
    memory = Mycelium(root / "store", config_path=Path("mycelium.toml"), memory_profile=profile)
    return instrument(memory, root, think)


def call_statistics(root):
    records = [json.loads(p.read_text()) for p in sorted((root / "requests").glob("*.json"))]
    return {
        "attempts": len(records),
        "request_seconds": sum(r["elapsed_seconds"] for r in records),
        "nonempty_thinking_calls": sum(r.get("thinking_chars", 0) > 0 for r in records),
        "thinking_estimated_tokens": sum(r.get("thinking_estimated_tokens", 0) for r in records),
        "content_estimated_tokens": sum(r.get("content_estimated_tokens", 0) for r in records),
        "native_eval_tokens": sum(r.get("response", {}).get("eval_count", 0) for r in records),
        "max_native_eval_tokens": max((r.get("response", {}).get("eval_count", 0) for r in records), default=0),
        "max_native_prompt_tokens": max((r.get("response", {}).get("prompt_eval_count", 0) for r in records), default=0),
        "truncated_calls": sum(r.get("truncated", False) for r in records),
        "transport_errors": sum("error" in r for r in records),
    }


async def probes():
    for case, reply in [("accept", "Yes, I will do that next Saturday."),
                        ("decline", "I might try it eventually, but I will not do that next Saturday.")]:
        for think in ([False, True] if case == "accept" else [True, False]):
            root = ROOT / "probes" / case / ("on" if think else "off")
            if (root / "result.json").exists():
                continue
            memory = memory_at(root, think)
            schema = extraction_output_model(["new-1"], ["prior-1"])
            system, user = prompts.claim_extraction_prompt(
                "agent_conversation", "source-1", ["Mira"],
                f"[new-1] role=user speaker=Mira: {reply}",
                context="[prior-1] role=assistant: You could repair the garden gate with cedar boards.",
            )
            result = await memory.llm.call_structured(system, user, schema, debug_label="reasoning-probe")
            write(root / "result.json", result)
            write(root / "stats.json", call_statistics(root))
            print("PROBE", case, think, call_statistics(root), flush=True)


async def diagnose(recommended=False, grounded=False):
    """Preserve single-attempt budget/sampling controls after the initial loop."""
    global OUTPUT_TOKENS, CONTEXT_TOKENS
    controls = [
        ("larger-budget", 32768, 49152, 0.0, [("accept", False), ("accept", True)]),
        ("temperature-02", 16384, 32768, 0.2,
         [("accept", False), ("accept", True), ("decline", True), ("decline", False)]),
    ]
    if recommended:
        controls = [("temperature-10-grounded" if grounded else "temperature-10", 16384, 32768, 1.0,
                     [("accept", False), ("accept", True), ("decline", True), ("decline", False)])]
    for label, budget, context, temperature, cases in controls:
        OUTPUT_TOKENS, CONTEXT_TOKENS = budget, context
        for case, think in cases:
            root = ROOT / "diagnostics" / label / case / ("on" if think else "off")
            if (root / "outcome.json").exists():
                continue
            memory = memory_at(root, think)
            memory.llm.client.temperature = temperature
            reply = ("Yes, I will do that next Saturday." if case == "accept" else
                     "I might try it eventually, but I will not do that next Saturday.")
            system, user = prompts.claim_extraction_prompt(
                "agent_conversation", "source-1", ["Mira"],
                f"[new-1] role=user speaker=Mira: {reply}",
                context="[prior-1] role=assistant: You could repair the garden gate with cedar boards.",
            )
            schema = extraction_output_model(["new-1"], ["prior-1"])
            if grounded:
                user += "\n\nOUTPUT JSON SCHEMA:\n" + json.dumps(schema.model_json_schema(), ensure_ascii=False)
            print("DIAGNOSTIC", label, case, think, flush=True)
            try:
                result = await memory.llm.call_structured(
                    system, user, schema,
                    max_retries=1, debug_label="reasoning-diagnostic",
                )
                outcome = {"success": True, "result": result}
            except Exception as exc:
                outcome = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
            outcome["calls"] = call_statistics(root)
            write(root / "outcome.json", outcome)
            print("OUTCOME", label, case, think, outcome, flush=True)
            await memory.llm.client.client._client.aclose()


async def natural_grounding(unconstrained=False):
    """Replay the failed natural-dialogue batch with exact schema grounding."""
    original_path = ROOT / "pipeline-temperature-10/locomo9/on/requests/0001.json"
    request = json.loads(original_path.read_text())["request"]
    ids = request["format"]["$defs"]["EvidenceFirstStatement"]["properties"]["segment_ids"]["items"]["enum"]
    schema = extraction_output_model(ids)
    assert schema.model_json_schema() == request["format"], "Replay schema changed"
    conditions = [(True, True)] if unconstrained else [(False, False), (True, True), (True, False)]
    for grounded, think in conditions:
        root = ROOT / "diagnostics/natural-grounding" / ("grounded" if grounded else "original") / ("on" if think else "off")
        if unconstrained:
            root = ROOT / "diagnostics/natural-grounding/unconstrained/on"
        if (root / "outcome.json").exists():
            continue
        memory = memory_at(root, think, "none")
        memory.llm.client.temperature = 1.0
        memory.llm.client.omit_format = unconstrained
        system, user = [m["content"] for m in request["messages"]]
        if grounded:
            user += "\n\nOUTPUT JSON SCHEMA:\n" + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        print("NATURAL", grounded, think, flush=True)
        try:
            result = await memory.llm.call_structured(system, user, schema, max_retries=1,
                                                      debug_label="natural-grounding")
            outcome = {"success": True, "result": result}
        except Exception as exc:
            outcome = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
        outcome["calls"] = call_statistics(root)
        write(root / "outcome.json", outcome)
        print("OUTCOME", grounded, think, outcome, flush=True)
        await memory.llm.client.client._client.aclose()


NEUTRAL = [
    ["I work as a librarian.", "I enjoy watercolor painting.", "I own a blue bicycle.",
     "I am learning Spanish.", "I grow tomatoes on my balcony.", "I joined a choir last month."],
    ["I have worked as a librarian for ten years.", "I prefer painting landscapes in watercolor.",
     "My bicycle has a wicker basket.", "I practice Spanish on Tuesday evenings.",
     "My balcony tomatoes are cherry tomatoes.", "My choir rehearses on Wednesdays."],
    ["I still enjoy watercolor painting.", "I plan to take a pottery class in November.",
     "I bought a red raincoat yesterday.", "I volunteer at an animal shelter on Saturdays.",
     "I prefer written directions.", "I have two cats."],
]


def experiment_inputs(case):
    if case == "neutral":
        return [dict(session_id=f"session-{i}", occurred_at="2026-09-04T12:00:00+00:00",
                     source_type="agent_conversation", participants=["user"],
                     messages=[dict(role="user", speaker="user", content=text,
                                    timestamp="2026-09-04T12:00:00+00:00") for text in batch])
                for i, batch in enumerate(NEUTRAL, 1)]
    sample_index = 9 if case == "locomo9" else 1
    samples = json.loads(Path("../locomo/data/locomo10.json").read_text())
    sample = samples[sample_index - 1]
    return [dict(session_id=sid, occurred_at=stamp, source_type="multi_party_conversation",
                 participants=list(dict.fromkeys(m.speaker for m in messages)),
                 messages=[asdict(m) for m in messages])
            for sid, stamp, messages in iter_locomo_sessions(sample)[:2 if case == "locomo9" else 1]]


async def build_case(case, think):
    root = ROOT / case / ("on" if think else "off")
    if (root / "summary.json").exists():
        print("SKIP completed", case, think, flush=True)
        return
    if (root / "store").exists():
        raise ValueError(f"Incomplete experiment at {root}; inspect before rerunning")
    root.mkdir(parents=True, exist_ok=True)
    inputs = experiment_inputs(case)
    write(root / "inputs.json", inputs)
    memory = memory_at(root, think, "user" if case == "neutral" else "none")
    reports = []
    total_started = time.perf_counter()
    for i, batch in enumerate(inputs, 1):
        print("BUILD", case, "on" if think else "off", i, flush=True)
        started = time.perf_counter()
        source = SourceInput(
            transcript="\n".join(f"{m['speaker']}: {m['content']}" for m in batch["messages"]),
            session_id=batch["session_id"], idempotency_key=f"reasoning-comparison:{case}:{i}",
            occurred_at=batch["occurred_at"], source_type=batch["source_type"],
            participants=tuple(batch["participants"]),
            segments=tuple(dict(segment_id="", index=j, content=m["content"], role=m["role"],
                                speaker=m["speaker"], timestamp=m.get("timestamp"),
                                metadata={**m.get("metadata", {}), "source_label": m.get("message_id")})
                           for j, m in enumerate(batch["messages"])),
        )
        await memory.ingest_source(source)
        build = await memory.consolidate()
        report = {"session": i, "elapsed_seconds": time.perf_counter() - started,
                  "build": asdict(build), "coverage": memory.artifacts.coverage_report()}
        reports.append(report)
        write(root / f"build-{i}.json", report)
        shutil.copytree(memory.store_path / "wiki", root / "snapshots" / str(i) / "wiki")
        write(root / "snapshots" / str(i) / "claims.json", [asdict(c) for c in memory.artifacts.list_claims()])
        write(root / "snapshots" / str(i) / "facts.json", [asdict(f) for f in memory.artifacts.list_consolidated_facts()])
        print("DONE", case, think, i, round(report["elapsed_seconds"], 1),
              "failures", build.report.failures, flush=True)
        # Check durable state with the same experimental transport after every build.
        transport = memory.llm.client
        await transport.client._client.aclose()
        memory = memory_at(root, think, "user" if case == "neutral" else "none")
        memory.llm.client.calls = transport.calls
    summary = {"case": case, "thinking": think, "elapsed_seconds": time.perf_counter() - total_started,
               "coverage": memory.artifacts.coverage_report(), "calls": call_statistics(root),
               "build_failures": [failure for r in reports for failure in r["build"]["report"]["failures"]]}
    write(root / "summary.json", summary)
    print("COMPLETE", case, think, summary["calls"], flush=True)


async def main():
    global ROOT, TEMPERATURE
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["probes", "diagnose", "recommended", "grounded", "natural", "unconstrained", "builds"])
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()
    TEMPERATURE = args.temperature
    if args.mode == "builds":
        ROOT = ROOT / f"pipeline-temperature-{round(TEMPERATURE * 10):02d}"
    ROOT.mkdir(parents=True, exist_ok=True)
    if args.mode == "probes":
        await probes()
        return
    if args.mode in {"diagnose", "recommended", "grounded"}:
        await diagnose(recommended=args.mode != "diagnose", grounded=args.mode == "grounded")
        return
    if args.mode in {"natural", "unconstrained"}:
        await natural_grounding(unconstrained=args.mode == "unconstrained")
        return
    write(ROOT / "manifest.json", {
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "model": "gemma4:12b", "context_tokens": CONTEXT_TOKENS, "output_tokens": OUTPUT_TOKENS,
        "timeout_seconds": 900, "temperature": TEMPERATURE, "seed": 17,
        "order": [["neutral", False], ["neutral", True], ["locomo9", True], ["locomo9", False],
                  ["locomo1", False], ["locomo1", True]],
        "dataset_sha256": hashlib.sha256(Path("../locomo/data/locomo10.json").read_bytes()).hexdigest(),
    })
    for case, think in [("neutral", False), ("neutral", True), ("locomo9", True), ("locomo9", False),
                        ("locomo1", False), ("locomo1", True)]:
        await build_case(case, think)


if __name__ == "__main__":
    asyncio.run(main())
