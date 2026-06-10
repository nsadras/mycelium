from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from benchmarks.mycelium_bench.adapters import BenchmarkMessage, MemorySystem
from benchmarks.mycelium_bench.scoring import locomo_score, summarize_scores


async def run_locomo(
    *,
    data_path: Path,
    output_dir: Path,
    system: MemorySystem,
    prediction_key: str,
    max_samples: int | None = None,
    max_questions: int | None = None,
    sample_index: int | None = None,
) -> dict[str, Any]:
    samples = json.loads(data_path.read_text(encoding="utf-8"))
    if sample_index is not None:
        if sample_index < 1 or sample_index > len(samples):
            raise ValueError(f"--sample-index must be between 1 and {len(samples)}")
        samples = [samples[sample_index - 1]]
    elif max_samples is not None:
        samples = samples[:max_samples]

    output_dir.mkdir(parents=True, exist_ok=True)
    predictions = read_json_if_exists(output_dir / "predictions.json", default=[])
    flat_rows = read_jsonl_if_exists(output_dir / "predictions.jsonl")
    completed_sample_ids = {str(sample.get("sample_id")) for sample in predictions}
    started = time.time()

    for sample_index, sample in enumerate(samples):
        sample_id = str(sample.get("sample_id") or f"sample-{sample_index}")
        if sample_id in completed_sample_ids:
            print(f"[locomo] sample {sample_index + 1}/{len(samples)} skip completed: {sample_id}", flush=True)
            continue
        print(f"[locomo] sample {sample_index + 1}/{len(samples)} reset: {sample_id}", flush=True)
        await system.reset(sample_id)
        sessions = iter_locomo_sessions(sample)
        for session_index, (session_id, timestamp, messages) in enumerate(sessions):
            print(
                f"[locomo] sample {sample_id} memorize session {session_index + 1}/{len(sessions)}: {session_id}",
                flush=True,
            )
            await system.memorize(
                messages,
                {
                    "sample_id": sample_id,
                    "session_id": session_id,
                    "timestamp": timestamp,
                },
            )
        print(f"[locomo] sample {sample_id} finalize memory", flush=True)
        await system.finalize_case()

        output_sample = {"sample_id": sample_id, "qa": deepcopy(sample.get("qa", [])), "system_stats": system.stats()}
        qas = output_sample["qa"]
        if max_questions is not None:
            qas = qas[:max_questions]
            output_sample["qa"] = qas

        for question_index, qa in enumerate(qas):
            question = str(qa.get("question", ""))
            print(
                f"[locomo] sample {sample_id} answer question {question_index + 1}/{len(qas)}",
                flush=True,
            )
            answer = await system.answer(
                question,
                {
                    "sample_id": sample_id,
                    "query_id": f"{sample_id}-q{question_index}",
                    "category": qa.get("category"),
                },
            )
            score = locomo_score(answer.output, qa.get("answer", ""), int(qa.get("category", 0)))
            qa[prediction_key] = answer.output
            qa[f"{prediction_key}_score"] = round(score, 4)
            qa[f"{prediction_key}_metadata"] = answer.metadata
            flat_rows.append(
                {
                    "sample_id": sample_id,
                    "question_index": question_index,
                    "question": question,
                    "answer": qa.get("answer"),
                    "prediction": answer.output,
                    "category": qa.get("category"),
                    "score": score,
                    "input_len": answer.input_len,
                    "output_len": answer.output_len,
                    "memory_construction_time": answer.memory_construction_time,
                    "query_time_len": answer.query_time_len,
                    "metadata": answer.metadata,
                }
            )

        predictions.append(output_sample)
        completed_sample_ids.add(sample_id)
        write_json(output_dir / "predictions.json", predictions)
        write_jsonl(output_dir / "predictions.jsonl", flat_rows)
        write_json(output_dir / "summary.json", summarize_locomo_run(flat_rows, started, prediction_key))

    summary = summarize_locomo_run(flat_rows, started, prediction_key)
    write_json(output_dir / "predictions.json", predictions)
    write_jsonl(output_dir / "predictions.jsonl", flat_rows)
    write_json(output_dir / "summary.json", summary)
    return summary


def iter_locomo_sessions(sample: dict[str, Any]) -> list[tuple[str, str | None, list[BenchmarkMessage]]]:
    conversation = sample.get("conversation", {})
    sessions = []
    for key in sorted(conversation, key=session_sort_key):
        if not key.startswith("session_") or key.endswith("_date_time"):
            continue
        session_turns = conversation.get(key) or []
        timestamp = conversation.get(f"{key}_date_time")
        messages = [locomo_turn_to_message(turn, timestamp) for turn in session_turns]
        sessions.append((key, timestamp, messages))
    return sessions


def locomo_turn_to_message(turn: dict[str, Any], timestamp: str | None) -> BenchmarkMessage:
    text = str(turn.get("text", "")).strip()
    if turn.get("blip_caption"):
        text = f"{text}\nImage caption: {turn['blip_caption']}"
    if turn.get("img_url"):
        text = f"{text}\nImage URL: {turn['img_url']}"
    return BenchmarkMessage(
        role="user",
        speaker=str(turn.get("speaker", "speaker")),
        content=text.strip(),
        timestamp=timestamp,
        message_id=str(turn.get("dia_id", "")) or None,
        metadata={k: v for k, v in turn.items() if k not in {"text", "speaker", "dia_id"}},
    )


def session_sort_key(key: str) -> tuple[int, str]:
    if not key.startswith("session_") or key.endswith("_date_time"):
        return (10**9, key)
    try:
        return (int(key.split("_")[1]), key)
    except (IndexError, ValueError):
        return (10**9, key)


def summarize_locomo_run(rows: list[dict[str, Any]], started: float, prediction_key: str) -> dict[str, Any]:
    summary = summarize_scores(rows)
    summary.update(
        {
            "benchmark": "locomo",
            "prediction_key": prediction_key,
            "elapsed_seconds": time.time() - started,
            "mean_input_len": mean(row["input_len"] for row in rows),
            "mean_output_len": mean(row["output_len"] for row in rows),
            "mean_memory_construction_time": mean(row["memory_construction_time"] for row in rows),
            "mean_query_time": mean(row["query_time_len"] for row in rows),
        }
    )
    return summary


def mean(values: Any) -> float:
    numbers = list(values)
    return sum(numbers) / len(numbers) if numbers else 0.0


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def read_json_if_exists(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
