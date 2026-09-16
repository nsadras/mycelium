"""Native proof of daily-driver judgment ID domains and positive/negative cases."""

import asyncio
from dataclasses import asdict

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from benchmarks.suites.daily_driver.eval import judge_probe_answer
from mycelium import Mycelium


CASES = [
    (
        "supported",
        "At what time does the call start?",
        "14:00 UTC",
        True,
        {"time": {"text": "The call starts at 14:00 UTC."}},
        ["time"],
        [],
        True,
    ),
    (
        "forbidden",
        "Where should the recording be stored?",
        "Upload it to the public archive.",
        True,
        {
            "local": {"text": "The recording must remain on the user's computer."},
            "public": {"text": "Upload the recording to the public archive."},
        },
        ["local"],
        ["public"],
        False,
    ),
    (
        "unknown",
        "What is the delivery address?",
        "I do not have enough information to answer this question.",
        False,
        {},
        [],
        [],
        True,
    ),
]


async def main():
    root = fresh_run_root("daily-judgment-contract")
    print("OUTPUT", root, flush=True)
    with Mycelium(root / "store", config_path="mycelium.toml") as memory:
        memory.llm.client = RecordingClient(memory.llm.client, root / "requests")
        memory.llm.trace_path = root / "calls.jsonl"
        write(root / "config.json", asdict(memory.config))
        write(root / "models.json", (await memory.llm.client.list()).model_dump())
        results = []
        for trial in range(3):
            for (
                name,
                question,
                answer,
                answerable,
                facts,
                required,
                forbidden,
                expected,
            ) in CASES:
                probe = {
                    "question": question,
                    "answerable": answerable,
                    "required_facts": required,
                    "forbidden_facts": forbidden,
                }
                judgment = await judge_probe_answer(
                    llm=memory.llm, probe=probe, answer=answer, gold_facts=facts
                )
                record = {
                    "trial": trial,
                    "case": name,
                    "probe": probe,
                    "answer": answer,
                    "facts": facts,
                    "judgment": judgment,
                    "passed": judgment["passed"] == expected,
                }
                if name == "forbidden":
                    record["passed"] = record["passed"] and judgment[
                        "present_forbidden_fact_ids"
                    ] == ["public"]
                results.append(record)
                write(root / "results.json", results)
                print(trial, name, record["passed"], judgment, flush=True)
        if not all(r["passed"] for r in results):
            raise SystemExit("Daily-driver judgment contract failed")


if __name__ == "__main__":
    asyncio.run(main())
