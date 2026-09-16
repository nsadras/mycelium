"""Neutral direct contract probes for the optional reference answer scorer."""

import asyncio
from pathlib import Path

import httpx

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.semantic_scoring import SemanticScorer
from mycelium.config import Config


CASES = [
    ("paraphrase", "How does Remy travel to work?", "By bicycle", "Remy cycles to work.", True, "correct"),
    ("negation", "Does Remy drink coffee?", "Remy avoids coffee.", "Remy drinks coffee.", True, "incorrect"),
    ("partial", "What should attendees bring?", "A notebook and a pencil", "A notebook.", True, "partial"),
    ("wrong_number", "When does the meeting begin?", "At 14:00", "At 15:00", True, "incorrect"),
    ("refusal", "What is Remy's middle name?", None, "The information provided does not establish a middle name.", False, "correct"),
    ("refusal_then_guess", "What is Remy's middle name?", None, "I have no information, but Remy's middle name is James.", False, "incorrect"),
    ("missing_reference", "Where does Remy work?", None, "At the library.", True, "ungradable"),
]


async def main():
    root = fresh_run_root("reference-judgment")
    config = Config.from_toml(Path("mycelium.toml")).llm
    scorer = SemanticScorer(config, root / "calls.jsonl")
    write(root / "scorer.json", scorer.specification)
    async with httpx.AsyncClient(timeout=10) as client:
        tags = await client.get(config.url.rstrip("/") + "/api/tags")
        tags.raise_for_status()
        write(root / "models.json", tags.json())
    results = []
    for trial in range(3):
        for name, question, reference, prediction, answerable, expected in CASES:
            request = dict(question=question, reference=reference, prediction=prediction, answerable=answerable)
            record = {"trial": trial, "case": name, "request": request, "expected": expected}
            results.append(record)
            write(root / "results.json", results)
            record["judgment"] = await scorer.judge(**request)
            record["passed"] = record["judgment"]["verdict"] == expected
            write(root / "results.json", results)
            print(name, trial, record["judgment"], record["passed"], flush=True)
    print("OUTPUT", root, flush=True)
    if not all(row["passed"] for row in results):
        raise SystemExit("Reference judgment contract did not pass every trial")


if __name__ == "__main__":
    asyncio.run(main())
