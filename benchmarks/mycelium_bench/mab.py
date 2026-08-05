from __future__ import annotations

import json
import sys
import time
import types
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from benchmarks.mycelium_bench.adapters import BenchmarkMessage, MemorySystem


class MyceliumMABAgent:
    def __init__(self, system: MemorySystem) -> None:
        self.system = system
        self.agent_start_time = time.perf_counter()

    async def memorize_context(self, context_chunks: list[str], context_id: int) -> None:
        await self.system.reset(f"context-{context_id}")
        for chunk_index, chunk in enumerate(context_chunks):
            await self.system.memorize(
                [BenchmarkMessage(role="user", content=chunk, message_id=f"chunk-{chunk_index}")],
                {"session_id": f"context-{context_id}-chunk-{chunk_index}", "context_id": context_id},
            )
        await self.system.finalize_case()

    async def answer(self, query: str, query_id: int, context_id: int) -> dict[str, Any]:
        answer = await self.system.answer(
            query,
            {"query_id": f"context-{context_id}-query-{query_id}", "context_id": context_id},
        )
        return {
            "output": answer.output,
            "input_len": answer.input_len,
            "output_len": answer.output_len,
            "memory_construction_time": answer.memory_construction_time,
            "query_time_len": answer.query_time_len,
            "mycelium_metadata": answer.metadata,
        }


async def run_memoryagentbench(
    *,
    mab_root: Path,
    dataset_config_path: Path,
    output_dir: Path,
    system: MemorySystem,
    max_contexts: int | None = None,
    max_queries: int | None = None,
) -> dict[str, Any]:
    mab_root = mab_root.resolve()
    if str(mab_root) not in sys.path:
        sys.path.insert(0, str(mab_root))
    install_editdistance_shim()
    ensure_nltk_tokenizers()

    from conversation_creator import ConversationCreator
    from utils.eval_other_utils import metrics_summarization

    dataset_config = load_yaml(dataset_config_path)
    agent_config = {
        "agent_name": "Simple_rag_bm25",
        "model": "mycelium",
        "input_length_limit": 10_000_000,
        "buffer_length": 0,
        "output_dir": str(output_dir),
    }
    dataset_config.setdefault("debug", False)
    dataset_config.setdefault("max_test_samples", max_contexts or 1)
    dataset_config.setdefault("seed", 42)

    creator = ConversationCreator(agent_config, dataset_config)
    all_context_chunks = creator.get_chunks()
    all_query_answer_pairs = creator.get_query_and_answers()
    if max_contexts is not None:
        all_context_chunks = all_context_chunks[:max_contexts]
        all_query_answer_pairs = all_query_answer_pairs[:max_contexts]

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "results.json"
    metrics: dict[str, list[Any]] = defaultdict(list)
    results: list[dict[str, Any]] = []
    started = time.perf_counter()
    query_index = 0
    agent = MyceliumMABAgent(system)

    for context_index, (context_chunks, query_answer_pairs) in enumerate(zip(all_context_chunks, all_query_answer_pairs)):
        print(
            f"[mab] context {context_index + 1}/{len(all_context_chunks)} memorize {len(context_chunks)} chunks",
            flush=True,
        )
        await agent.memorize_context(context_chunks, context_index)
        for query, answer, qa_pair_id in normalize_query_pairs(query_answer_pairs):
            if max_queries is not None and query_index >= max_queries:
                break
            print(f"[mab] context {context_index} answer query {query_index}", flush=True)
            output = await agent.answer(query, query_index, context_index)
            metrics, results = metrics_summarization(
                output,
                query,
                answer,
                dataset_config,
                metrics,
                results,
                query_index,
                qa_pair_id,
            )
            query_index += 1
            write_mab_results(output_path, dataset_config, metrics, results, started)
        if max_queries is not None and query_index >= max_queries:
            break

    summary = write_mab_results(output_path, dataset_config, metrics, results, started)
    return summary


def normalize_query_pairs(query_answer_pairs: list[Any]) -> list[tuple[str, Any, Any]]:
    normalized = []
    for item in query_answer_pairs:
        if len(item) == 3:
            normalized.append((item[0], item[1], item[2]))
        else:
            normalized.append((item[0], item[1], None))
    return normalized


def write_mab_results(
    output_path: Path,
    dataset_config: dict[str, Any],
    metrics: dict[str, list[Any]],
    results: list[dict[str, Any]],
    started: float,
) -> dict[str, Any]:
    averaged_metrics = {
        key: mean(values) * (1 if ("_len" in key or "_time" in key) else 100)
        for key, values in metrics.items()
    }
    data = {
        "dataset_config": dataset_config,
        "data": results,
        "metrics": metrics,
        "averaged_metrics": averaged_metrics,
        "time_cost": time.perf_counter() - started,
    }
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "benchmark": "memoryagentbench",
        "output_path": str(output_path),
        "queries": len(results),
        "averaged_metrics": averaged_metrics,
        "elapsed_seconds": time.perf_counter() - started,
    }


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def mean(values: list[Any]) -> float:
    numbers = [float(value) for value in values]
    return sum(numbers) / len(numbers) if numbers else 0.0


def install_editdistance_shim() -> None:
    if "editdistance" in sys.modules:
        return
    module = types.ModuleType("editdistance")
    module.eval = levenshtein_distance
    sys.modules["editdistance"] = module


def levenshtein_distance(left: Any, right: Any) -> int:
    a = str(left)
    b = str(right)
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            replace = previous[j - 1] + (ca != cb)
            current.append(min(insert, delete, replace))
        previous = current
    return previous[-1]


def ensure_nltk_tokenizers() -> None:
    try:
        import nltk

        for resource, download_name in (
            ("tokenizers/punkt", "punkt"),
            ("tokenizers/punkt_tab/english", "punkt_tab"),
        ):
            try:
                nltk.data.find(resource)
            except LookupError:
                nltk.download(download_name, quiet=True)
    except Exception:
        return
