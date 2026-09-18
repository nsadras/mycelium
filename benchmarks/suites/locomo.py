from __future__ import annotations

from mycelium.snapshots import snapshot_store

import json
import os
import tempfile
import re
import time
import hashlib
import subprocess
from dataclasses import asdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from benchmarks.shared.adapters import (
    BenchmarkMessage,
    MemorySystem,
    MyceliumMemorySystem,
)
from benchmarks.shared.scoring import locomo_score, summarize_scores
from benchmarks.shared.semantic_scoring import SemanticScorer, summarize_judgments
from mycelium.telemetry import trace_operation
from benchmarks.shared.provenance import effective_configuration, model_inventory, validate_model_resume
from benchmarks.shared.run_tracking import recorded_run, prior_elapsed, environment_manifest, begin_invocation, invocation_started


@recorded_run
async def run_locomo(
    *,
    data_path: Path,
    output_dir: Path,
    system: MemorySystem,
    prediction_key: str,
    max_samples: int | None = None,
    max_questions: int | None = None,
    max_sessions: int | None = None,
    questions_per_category: int | None = None,
    sample_index: int | None = None,
    snapshot_sessions: bool = False,
    allow_incomplete_encoding: bool = False,
    semantic_scorer: SemanticScorer | None = None,
) -> dict[str, Any]:
    if snapshot_sessions and not isinstance(system, MyceliumMemorySystem):
        raise ValueError("--snapshot-sessions requires a Mycelium-backed system")
    if snapshot_sessions and system.frozen_store is not None:
        raise ValueError(
            "--snapshot-sessions requires session ingestion, not --frozen-store"
        )
    samples = json.loads(data_path.read_text(encoding="utf-8"))
    if sample_index is not None:
        if sample_index < 1 or sample_index > len(samples):
            raise ValueError(f"--sample-index must be between 1 and {len(samples)}")
        samples = [samples[sample_index - 1]]
    elif max_samples is not None:
        samples = samples[:max_samples]

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "run_manifest.json"
    settings = {
        "protocol_version": 6,
        "semantic_scorer": semantic_scorer.specification if semantic_scorer else None,
        "allow_incomplete_encoding": allow_incomplete_encoding,
        "dataset_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "system": system.name,
        "prediction_key": prediction_key,
        "max_samples": max_samples,
        "max_questions": max_questions,
        "max_sessions": max_sessions,
        "questions_per_category": questions_per_category,
        "sample_index": sample_index,
        **({"snapshot_sessions": True} if snapshot_sessions else {}),
        "qa_model": getattr(getattr(system, "qa_client", None), "model", None),
        **{
            key: str(getattr(system, key, None))
            for key in (
                "memory_model",
                "context_budget_tokens",
                "dream_policy",
                "memory_profile",
                "replay_store",
                "frozen_store",
            )
        },
        "effective_config": effective_configuration(system),
    }
    manifest = read_json_if_exists(manifest_path, default=None)
    if manifest is not None and manifest["settings"] != settings:
        raise ValueError(
            "Run settings differ from the checkpoint; use a fresh output directory"
        )
    inventory = await model_inventory(system, semantic_scorer=semantic_scorer)
    if manifest is not None:
        validate_model_resume(manifest.get('model_inventory', {}), inventory)
    if manifest is None:
        if (output_dir / "predictions.json").exists():
            raise ValueError(
                "Existing predictions have no run manifest; use a fresh output directory"
            )
        manifest = {"settings": settings, "status": "running", "execution_status": "running", "encoding_status": "pending", "qa_status": "pending", "environment": environment_manifest(), "cases": {}}
    manifest['model_inventory'] = inventory
    manifest['scoring_status'] = 'pending' if semantic_scorer else 'disabled'
    manifest['model_provenance_complete'] = all(not value['error'] for value in inventory.values())
    begin_invocation(output_dir)
    manifest.update(status="running", execution_status="running")
    manifest.pop("execution_error", None)
    write_json(manifest_path, manifest)
    checkpoint_dir = output_dir / "questions"
    checkpoint_dir.mkdir(exist_ok=True)
    checkpoints = [
        json.loads(path.read_text()) for path in sorted(checkpoint_dir.glob("*.json"))
    ]
    completed_questions = {
        (row["sample_id"], row["question_index"]): row for row in checkpoints
    }
    predictions = read_json_if_exists(output_dir / "predictions.json", default=[])
    flat_rows = checkpoints.copy()
    completed_sample_ids = {str(sample.get("sample_id")) for sample in predictions}
    started = invocation_started() - prior_elapsed(output_dir)

    for sample_index, sample in enumerate(samples):
        sample_id = str(sample.get("sample_id") or f"sample-{sample_index}")
        if sample_id in completed_sample_ids:
            print(
                f"[locomo] sample {sample_index + 1}/{len(samples)} skip completed: {sample_id}",
                flush=True,
            )
            continue
        print(
            f"[locomo] sample {sample_index + 1}/{len(samples)} reset: {sample_id}",
            flush=True,
        )
        with trace_operation('reset', sample_id=sample_id):
            await system.reset(sample_id)
        sessions = iter_locomo_sessions(sample)
        if max_sessions is not None:
            if max_sessions <= 0:
                raise ValueError("--max-sessions must be positive")
            sessions = sessions[:max_sessions]
        for session_index, (session_id, timestamp, messages) in enumerate(sessions):
            print(
                f"[locomo] sample {sample_id} memorize session {session_index + 1}/{len(sessions)}: {session_id}",
                flush=True,
            )
            session_started = time.perf_counter()
            with trace_operation('memorize', sample_id=sample_id, session_id=session_id):
                await system.memorize(
                    messages,
                    {
                        "sample_id": sample_id,
                        "session_id": session_id,
                        "timestamp": timestamp,
                    },
                )
            print(
                f"[locomo] sample {sample_id} memorize session {session_index + 1}/{len(sessions)}: "
                f"{session_id} finished in {time.perf_counter() - session_started:.1f}s",
                flush=True,
            )
            if snapshot_sessions:
                snapshot = output_dir / "snapshots" / system.case_id / session_id
                # Resume revisits ingestion against an advanced store. Preserve
                # already published snapshots rather than replacing their history.
                if not snapshot.exists():
                    snapshot.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory(
                        dir=snapshot.parent, prefix=".snapshot-"
                    ) as staging:
                        staged_store = Path(staging) / "store"
                        snapshot_store(system._require_mem().store_path, staged_store)
                        staged_store.rename(snapshot)
                print(f"[locomo] sample {sample_id} snapshot: {snapshot}", flush=True)
        print(f"[locomo] sample {sample_id} finalize memory", flush=True)
        with trace_operation('finalize', sample_id=sample_id):
            await system.finalize_case()
        case_stats = system.stats()
        encoding_status = case_stats.get("encoding_status", "complete")
        manifest["cases"][sample_id] = case_stats
        manifest["encoding_status"] = "incomplete" if any(case.get("encoding_status") == "incomplete" for case in manifest["cases"].values()) else "complete"
        if encoding_status == "incomplete" and not allow_incomplete_encoding:
            manifest.update(status="failed", execution_status="blocked", qa_status="not_run")
            write_json(manifest_path, manifest)
            raise RuntimeError("Encoding is incomplete; inspect the run manifest or explicitly enable diagnostic QA")
        write_json(manifest_path, manifest)

        all_qas = deepcopy(sample.get("qa", []))
        indexed_qas = list(enumerate(all_qas))
        if questions_per_category is not None:
            indexed_qas = select_questions_per_category(
                indexed_qas, questions_per_category
            )
        if max_questions is not None:
            indexed_qas = indexed_qas[:max_questions]
        manifest["qa_status"] = "running" if indexed_qas else "not_run"
        write_json(manifest_path, manifest)
        output_sample = {
            "sample_id": sample_id,
            "qa": [qa for _, qa in indexed_qas],
            "system_stats": system.stats(),
        }

        for panel_index, (question_index, qa) in enumerate(indexed_qas):
            question = str(qa.get("question", ""))
            print(
                f"[locomo] sample {sample_id} answer question {panel_index + 1}/{len(indexed_qas)} "
                + f"(source index {question_index})",
                flush=True,
            )
            answer_metadata = {
                "sample_id": sample_id,
                "query_id": f"{sample_id}-q{question_index}",
                "category": qa.get("category"),
            }
            if system.name == "gold_evidence":
                answer_metadata["gold_evidence"] = qa.get("evidence") or []
            prior = completed_questions.get((sample_id, question_index))
            if prior is not None:
                qa[prediction_key] = prior["prediction"]
                qa[f"{prediction_key}_score"] = round(prior["score"], 4)
                qa[f"{prediction_key}_metadata"] = prior["metadata"]
                continue
            with trace_operation('answer', sample_id=sample_id, query_id=answer_metadata['query_id']) as linkage:
                answer = await system.answer(
                    question,
                    answer_metadata,
                )
            answer.metadata['trace'] = linkage
            answer.metadata["encoding_status"] = encoding_status
            _record_evidence_survival(answer, qa.get("evidence"))
            _record_retrieval_evidence(answer, qa.get("evidence"))
            score = locomo_score(
                answer.output, qa.get("answer", ""), int(qa.get("category", 0))
            )
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
                    "retrieval_seconds": answer.retrieval_seconds,
                    "query_time_len": answer.query_time_len,
                    "metadata": answer.metadata,
                }
            )

            row = flat_rows[-1]
            checkpoint_id = hashlib.sha256(
                f"{sample_id}:{question_index}".encode()
            ).hexdigest()
            write_json(checkpoint_dir / f"{checkpoint_id}.json", row)
            completed_questions[(sample_id, question_index)] = row
            manifest.update(
                sample_id=sample_id,
                phase="qa",
                completed_questions=len(completed_questions),
            )
            write_json(manifest_path, manifest)

        predictions.append(output_sample)
        completed_sample_ids.add(sample_id)
        write_json(output_dir / "predictions.json", predictions)
        write_jsonl(output_dir / "predictions.jsonl", flat_rows)
        write_json(
            output_dir / "summary.json",
            summarize_locomo_run(flat_rows, started, prediction_key),
        )

    manifest['qa_status'] = 'complete' if completed_questions else 'not_run'
    if semantic_scorer is not None:
        manifest['scoring_status'] = 'running'
        write_json(manifest_path, manifest)
        for row in flat_rows:
            if row.get('semantic_judgment', {}).get('status') == 'complete':
                continue
            checkpoint_id = hashlib.sha256(f"{row['sample_id']}:{row['question_index']}".encode()).hexdigest()
            checkpoint_path = checkpoint_dir / f"{checkpoint_id}.json"
            row['semantic_judgment'] = {'status': 'running'}
            write_json(checkpoint_path, row)
            with trace_operation('semantic_judgment', sample_id=row['sample_id'],
                                 query_id=f"{row['sample_id']}-q{row['question_index']}") as linkage:
                scoring_started = time.perf_counter()
                try:
                    judgment = await semantic_scorer.judge(
                        question=row['question'], reference=row['answer'],
                        prediction=row['prediction'], answerable=int(row['category']) != 5,
                    )
                    result = {'status': 'complete', 'judgment': judgment}
                except Exception as exc:
                    result = {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
                row['semantic_judgment'] = {
                    **result, 'trace': linkage, 'seconds': time.perf_counter() - scoring_started,
                }
            write_json(checkpoint_path, row)
            manifest['scoring_status'] = summarize_judgments(flat_rows, enabled=True)['status']
            write_json(manifest_path, manifest)

    summary = summarize_locomo_run(flat_rows, started, prediction_key)
    summary['semantic_scoring'] = summarize_judgments(flat_rows, enabled=semantic_scorer is not None)
    write_json(output_dir / "predictions.json", predictions)
    write_jsonl(output_dir / "predictions.jsonl", flat_rows)
    write_json(output_dir / "summary.json", summary)
    manifest.update(status="complete", execution_status="complete", qa_status="complete" if completed_questions else "not_run", completed_questions=len(completed_questions))
    manifest['scoring_status'] = summary['semantic_scoring']['status']
    write_json(manifest_path, manifest)
    return summary


async def run_locomo_wiki_baseline(
    *,
    data_path: Path,
    output_dir: Path,
    system: MyceliumMemorySystem,
    sample_index: int = 1,
    max_sessions: int = 2,
    user_speaker: str | None = None,
) -> dict[str, Any]:
    """Fresh, sequential build snapshots for human wiki review; no QA or gold input."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Wiki baseline requires a fresh output directory")
    if system.replay_store or system.frozen_store:
        raise ValueError(
            "Wiki baseline must build from source, not derived replay artifacts"
        )
    samples = json.loads(data_path.read_text(encoding="utf-8"))
    if not 1 <= sample_index <= len(samples) or max_sessions < 1:
        raise ValueError("Invalid sample index or session count")
    sample = samples[sample_index - 1]
    selected = iter_locomo_sessions(sample, user_speaker=user_speaker)[:max_sessions]
    speakers = {m.speaker for _, _, messages in selected for m in messages}
    if user_speaker is not None and user_speaker not in speakers:
        raise ValueError("Configured user speaker must appear in the selected sessions")
    output_dir.mkdir(parents=True, exist_ok=True)
    system.memory_profile = "user"
    system.dream_policy = "per-batch"
    await system.reset(str(sample["sample_id"]))
    memory = system._require_mem()
    keys = {key for sid, _, _ in selected for key in (sid, f"{sid}_date_time")}
    write_json(
        output_dir / "input.json",
        {
            "sample_id": sample["sample_id"],
            "conversation": {
                k: v
                for k, v in sample["conversation"].items()
                if k in keys or k in {"speaker_a", "speaker_b"}
            },
        },
    )
    write_json(
        output_dir / "messages.json",
        [
            {
                "session_id": sid,
                "timestamp": timestamp,
                "messages": [asdict(m) for m in messages],
            }
            for sid, timestamp, messages in selected
        ],
    )
    manifest = {
        "sample_id": sample["sample_id"],
        "sample_index": sample_index,
        "session_ids": [sid for sid, _, _ in selected],
        "user_speaker": user_speaker,
        "dataset_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "input_sha256": hashlib.sha256(
            (output_dir / "input.json").read_bytes()
        ).hexdigest(),
        "config": asdict(memory.config),
        "build_policy": "after_each_session",
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "checkpoints": [],
    }
    (output_dir / "working_tree.patch").write_text(
        subprocess.check_output(["git", "diff", "HEAD"], text=True)
    )
    write_json(output_dir / "manifest.json", manifest)
    snapshot_store(memory.store_path, output_dir / "snapshots" / "initial")
    for sid, timestamp, messages in selected:
        print(
            f"[wiki-baseline] {sample['sample_id']} user={user_speaker!r}: capture/build {sid}",
            flush=True,
        )
        started = time.perf_counter()
        await system.memorize(
            messages,
            {
                "session_id": sid,
                "timestamp": timestamp,
                "sample_id": sample["sample_id"],
            },
        )
        snapshot = output_dir / "snapshots" / sid
        snapshot_store(memory.store_path, snapshot)
        checkpoint = {
            "session_id": sid,
            "elapsed_seconds": time.perf_counter() - started,
            "stats": system.stats(),
            "coverage": memory.artifacts.coverage_report(),
            "pages": [
                {"slug": p.slug, "title": p.title, "entity_id": p.entity_id}
                for p in memory.wiki.list()
            ],
            "pending_sources": memory.consolidation_status().pending_sources,
        }
        manifest["checkpoints"].append(checkpoint)
        write_json(output_dir / "manifest.json", manifest)
        print(
            f"[wiki-baseline] saved {snapshot}: {len(checkpoint['pages'])} pages "
            f"in {checkpoint['elapsed_seconds']:.1f}s",
            flush=True,
        )
    return manifest


def iter_locomo_sessions(
    sample: dict[str, Any],
    *,
    user_speaker: str | None = None,
) -> list[tuple[str, str | None, list[BenchmarkMessage]]]:
    conversation = sample.get("conversation", {})
    sessions = []
    for key in sorted(conversation, key=session_sort_key):
        if not key.startswith("session_") or key.endswith("_date_time"):
            continue
        session_turns = conversation.get(key) or []
        timestamp = conversation.get(f"{key}_date_time")
        messages = [
            locomo_turn_to_message(turn, timestamp, user_speaker=user_speaker)
            for turn in session_turns
        ]
        sessions.append((key, timestamp, messages))
    return sessions


def locomo_turn_to_message(
    turn: dict[str, Any],
    timestamp: str | None,
    *,
    user_speaker: str | None = None,
) -> BenchmarkMessage:
    text = str(turn.get("text", "")).strip()
    if turn.get("blip_caption"):
        text = f"{text}\nImage caption: {turn['blip_caption']}"
    if turn.get("img_url"):
        text = f"{text}\nImage URL: {turn['img_url']}"
    return BenchmarkMessage(
        role="user"
        if user_speaker is not None and turn.get("speaker") == user_speaker
        else "participant",
        speaker=str(turn.get("speaker", "speaker")),
        content=text.strip(),
        timestamp=timestamp,
        message_id=str(turn.get("dia_id", "")) or None,
        metadata={
            k: v for k, v in turn.items() if k not in {"text", "speaker", "dia_id"}
        },
    )


def session_sort_key(key: str) -> tuple[int, str]:
    if not key.startswith("session_") or key.endswith("_date_time"):
        return (10**9, key)
    try:
        return (int(key.split("_")[1]), key)
    except (IndexError, ValueError):
        return (10**9, key)


def select_questions_per_category(
    indexed_qas: list[tuple[int, dict[str, Any]]], limit: int
) -> list[tuple[int, dict[str, Any]]]:
    if limit <= 0:
        raise ValueError("--questions-per-category must be positive")
    counts: dict[str, int] = {}
    selected = []
    for question_index, qa in indexed_qas:
        category = str(qa.get("category"))
        count = counts.get(category, 0)
        if count >= limit:
            continue
        selected.append((question_index, qa))
        counts[category] = count + 1
    return selected


def summarize_locomo_run(
    rows: list[dict[str, Any]], started: float, prediction_key: str
) -> dict[str, Any]:
    summary = summarize_scores(rows)
    summary.update(
        {
            "benchmark": "locomo",
            "prediction_key": prediction_key,
            "elapsed_seconds": time.perf_counter() - started,
            "mean_input_len": mean(row["input_len"] for row in rows),
            "mean_output_len": mean(row["output_len"] for row in rows),
            "mean_retrieval_seconds": mean(
                row["retrieval_seconds"] for row in rows
            ),
            "mean_query_time": mean(row["query_time_len"] for row in rows),
        }
    )
    evidence_metrics = [
        row.get("metadata", {}).get("retrieval_evidence") for row in rows
    ]
    measured = [metric for metric in evidence_metrics if isinstance(metric, dict)]
    if measured:
        summary["retrieval_evidence"] = {
            "question_count": len(measured),
            "mean_recall": mean(metric["recall"] for metric in measured),
            "all_evidence_question_rate": mean(
                1.0 if metric["all_evidence_present"] else 0.0 for metric in measured
            ),
        }
    survival_reports = [
        row.get("metadata", {}).get("evidence_survival") for row in rows
    ]
    measured_survival = [
        report for report in survival_reports if isinstance(report, dict)
    ]
    if measured_survival:
        stages = sorted({stage for report in measured_survival for stage in report})
        summary["evidence_survival"] = {
            stage: {
                "question_count": len(stage_reports),
                "mean_recall": mean(item["recall"] for item in stage_reports),
                "all_evidence_question_rate": mean(
                    1.0 if item["all_evidence_present"] else 0.0
                    for item in stage_reports
                ),
            }
            for stage in stages
            if (
                stage_reports := [
                    report[stage]
                    for report in measured_survival
                    if isinstance(report.get(stage), dict)
                ]
            )
        }
    return summary


def _record_retrieval_evidence(answer: Any, evidence: Any) -> None:
    """Measure labeled-source recall when a synthetic benchmark context is retained."""
    exact_context_report = answer.metadata.get("evidence_survival", {}).get("context")
    if isinstance(exact_context_report, dict):
        answer.metadata["retrieval_evidence"] = dict(exact_context_report)
        return
    context = answer.metadata.get("retrieval_context")
    if not isinstance(context, str):
        return
    required = [str(label) for label in evidence or [] if str(label)]
    if not required:
        return
    present = [
        label
        for label in required
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(label)}(?![A-Za-z0-9])", context)
    ]
    answer.metadata["retrieval_evidence"] = {
        "required": required,
        "present": present,
        "recall": len(present) / len(required),
        "all_evidence_present": len(present) == len(required),
    }


def _record_evidence_survival(answer: Any, evidence: Any) -> None:
    evidence_segments = answer.metadata.pop("_evidence_stage_segments", None)
    if not isinstance(evidence_segments, dict):
        return
    required = [str(label) for label in evidence or [] if str(label)]
    if not required:
        return
    raw_segments_by_label = evidence_segments.get("segments_by_label")
    raw_stages = evidence_segments.get("stages")
    if not isinstance(raw_segments_by_label, dict) or not isinstance(raw_stages, dict):
        return
    segments_by_label = {
        str(label): {str(segment_id) for segment_id in segment_ids or []}
        for label, segment_ids in raw_segments_by_label.items()
    }
    report = {}
    for stage, raw_segment_ids in raw_stages.items():
        represented = {str(segment_id) for segment_id in raw_segment_ids or []}
        label_coverage = {
            label: (
                len(segments_by_label.get(label, set()) & represented)
                / len(segments_by_label[label])
                if segments_by_label.get(label)
                else 0.0
            )
            for label in required
        }
        present = [label for label in required if label_coverage[label] == 1.0]
        partially_present = [
            label for label in required if 0.0 < label_coverage[label] < 1.0
        ]
        missing = [label for label in required if label_coverage[label] == 0.0]
        report[str(stage)] = {
            "required": required,
            "present": present,
            "partially_present": partially_present,
            "missing": missing,
            "label_coverage": label_coverage,
            "recall": mean(label_coverage.values()),
            "all_evidence_present": len(present) == len(required),
        }
    answer.metadata["evidence_survival"] = report


def mean(values: Any) -> float:
    numbers = list(values)
    return sum(numbers) / len(numbers) if numbers else 0.0


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_text(path, json.dumps(data, indent=2, ensure_ascii=False))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_text(
        path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    )


def _atomic_text(path: Path, text: str) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".checkpoint-",
            delete=False,
        ) as stream:
            temporary = stream.name
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def read_json_if_exists(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))
