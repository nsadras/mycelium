import datetime
import hashlib
import json
from typing import Any, List
import uuid
from dataclasses import asdict

from mycelium.batching import split_text_by_tokens
from mycelium.models import LogEntry
from mycelium.operations import IngestionResult, SourceInput
from mycelium.store import LogStore
from mycelium.ollama import OllamaClient
from mycelium.config import Config
from mycelium.artifacts import (
    ArtifactStore,
    EpisodeManifest,
    IngestionOperation,
    SourceDocument,
    SourceSegment,
    segment_transcript,
)


class Encoder:
    def __init__(
        self,
        llm: OllamaClient,
        log_store: LogStore,
        config: Config,
        artifacts: ArtifactStore,
    ):
        self.llm = llm
        self.log_store = log_store
        self.config = config
        self.artifacts = artifacts

    async def ingest_source(self, source_input: SourceInput) -> IngestionResult:
        entries = await self.capture_session(
            source_input.transcript,
            source_input.session_id,
            source_type=source_input.source_type,
            occurred_at=source_input.occurred_at,
            participants=list(source_input.participants),
            metadata=dict(source_input.metadata),
            segments=(
                None if source_input.segments is None else list(source_input.segments)
            ),
            idempotency_key=source_input.idempotency_key,
        )
        if not entries:
            return IngestionResult(status="empty")

        entry_ids = {entry.entry_id for entry in entries}
        sources = [
            source
            for source in self.artifacts.list_sources()
            if source.raw_log_entry_id in entry_ids
        ]
        source_ids = {source.source_id for source in sources}
        episodes = [
            episode
            for episode in self.artifacts.list_episodes()
            if episode.source_id in source_ids
        ]
        claim_ids = tuple(
            dict.fromkeys(
                claim_id for episode in episodes for claim_id in episode.claim_ids
            )
        )
        operation_ids = tuple(
            dict.fromkeys(
                str(source.metadata["ingestion_operation_id"])
                for source in sources
                if source.metadata.get("ingestion_operation_id")
            )
        )
        status = "captured"
        return IngestionResult(
            status=status,
            log_entries=tuple(entries),
            source_ids=tuple(source.source_id for source in sources),
            episode_ids=tuple(episode.episode_id for episode in episodes),
            claim_ids=claim_ids,
            operation_ids=operation_ids,
        )

    async def capture_session(
        self,
        transcript: str,
        session_id: str,
        *,
        source_type: str = "agent_conversation",
        occurred_at: str | datetime.datetime | None = None,
        participants: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        segments: list[SourceSegment | dict[str, Any]] | None = None,
        idempotency_key: str | None = None,
    ) -> List[LogEntry]:
        with self.artifacts.db.transaction():
            content = transcript.strip()
            if not content:
                return []

            input_digest = self._input_digest(
                content,
                session_id,
                source_type,
                occurred_at,
                participants,
                metadata,
                segments,
            )
            ingestion_key = idempotency_key or f"generated:{uuid.uuid4()}"
            operation_suffix = hashlib.sha256(
                ingestion_key.encode("utf-8")
            ).hexdigest()[:16]
            operation_id = f"ingest-{operation_suffix}"
            try:
                operation = self.artifacts.get_ingestion_operation(operation_id)
            except FileNotFoundError:
                now = datetime.datetime.now().astimezone()
                operation = IngestionOperation(
                    operation_id=operation_id,
                    idempotency_key=ingestion_key,
                    input_digest=input_digest,
                    entry_id=f"{now:%Y-%m-%d}#session-{operation_suffix}",
                    source_id=f"source-{operation_suffix}",
                    episode_id=f"episode-{operation_suffix}",
                    status="planned",
                    created_at=now.isoformat(),
                    updated_at=now.isoformat(),
                )
                self.artifacts.save_ingestion_operation(operation)
            if operation.idempotency_key != ingestion_key:
                raise ValueError("Ingestion operation ID collision")
            if operation.input_digest != input_digest:
                raise ValueError(
                    "An ingestion idempotency key cannot be reused for different input"
                )

            now = datetime.datetime.fromisoformat(operation.created_at)
            entry_id = operation.entry_id

            entry = LogEntry(
                entry_id=entry_id,
                session_id=session_id,
                timestamp=now,
                content=(
                    "Raw conversation transcript. Treat this as canonical source evidence during dream "
                    "consolidation and retrieval.\n\n"
                    f"{content}"
                ),
                durability="durable",
                consolidated=False,
            )

            self.log_store.append(entry)
            try:
                source = self.artifacts.get_source(operation.source_id)
            except FileNotFoundError:
                normalized_segments = self._normalize_segments(
                    segments, content, operation.source_id, source_type
                )
                if not normalized_segments:
                    error = "A non-empty source transcript must produce at least one segment"
                    operation.status = "failed"
                    operation.error = f"ValueError: {error}"
                    operation.updated_at = (
                        datetime.datetime.now().astimezone().isoformat()
                    )
                    self.artifacts.save_ingestion_operation(operation)
                    raise ValueError(error)
                participant_names = participants or list(
                    dict.fromkeys(
                        segment.speaker
                        for segment in normalized_segments
                        if segment.speaker
                    )
                )
                occurred = (
                    occurred_at.isoformat()
                    if isinstance(occurred_at, datetime.datetime)
                    else occurred_at
                )
                source = SourceDocument(
                    source_id=operation.source_id,
                    source_type=source_type,
                    session_id=session_id,
                    recorded_at=now.isoformat(),
                    occurred_at=occurred,
                    participants=participant_names,
                    segments=normalized_segments,
                    raw_log_entry_id=entry_id,
                    metadata={
                        **(metadata or {}),
                        "ingestion_operation_id": operation_id,
                    },
                )
                self.artifacts.save_source(source)
            try:
                episode = self.artifacts.get_episode(operation.episode_id)
            except FileNotFoundError:
                episode = EpisodeManifest(
                    episode_id=operation.episode_id,
                    source_id=source.source_id,
                    source_type=source.source_type,
                    occurred_at=source.occurred_at,
                    participants=list(source.participants),
                    segment_ids=[segment.segment_id for segment in source.segments],
                )
                self.artifacts.save_episode(episode)

            if operation.status != "complete":
                operation.status = "captured"
                operation.error = None
                operation.updated_at = datetime.datetime.now().astimezone().isoformat()
                self.artifacts.save_ingestion_operation(operation)
            result = [entry]

        self.artifacts.db.publish()
        return result

    def sync_ingestion_status(
        self,
        episode: EpisodeManifest,
        *,
        operation: IngestionOperation | None = None,
    ) -> None:
        if operation is None:
            operation = next(
                (
                    candidate
                    for candidate in self.artifacts.list_ingestion_operations()
                    if candidate.episode_id == episode.episode_id
                ),
                None,
            )
        if operation is None:
            return
        operation.status = (
            "complete" if episode.extraction_status == "complete" else "failed"
        )
        operation.error = episode.extraction_error
        operation.updated_at = datetime.datetime.now().astimezone().isoformat()
        self.artifacts.save_ingestion_operation(operation)

    @staticmethod
    def _input_digest(
        transcript: str,
        session_id: str,
        source_type: str,
        occurred_at: str | datetime.datetime | None,
        participants: list[str] | None,
        metadata: dict[str, Any] | None,
        segments: list[SourceSegment | dict[str, Any]] | None,
    ) -> str:
        serialized_segments = None
        if segments is not None:
            serialized_segments = []
            for item in segments:
                value = asdict(item) if isinstance(item, SourceSegment) else dict(item)
                value.pop("segment_id", None)
                value.pop("index", None)
                serialized_segments.append(value)
        payload = {
            "transcript": transcript,
            "session_id": session_id,
            "source_type": source_type,
            "occurred_at": (
                occurred_at.isoformat()
                if isinstance(occurred_at, datetime.datetime)
                else occurred_at
            ),
            "participants": participants or [],
            "metadata": metadata or {},
            "segments": serialized_segments,
        }
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _normalize_segments(
        self,
        segments: list[SourceSegment | dict[str, Any]] | None,
        transcript: str,
        source_id: str,
        source_type: str,
    ) -> list[SourceSegment]:
        base = (
            segment_transcript(transcript, source_id)
            if segments is None
            else [
                item if isinstance(item, SourceSegment) else SourceSegment(**item)
                for item in segments
            ]
        )
        expanded: list[SourceSegment] = []
        for source_index, segment in enumerate(base):
            # Mechanical token boundaries preserve complete original text and role
            # metadata. Sentence-level exhaustive extraction is no longer a stage.
            parts = split_text_by_tokens(segment.content, max(256, self.config.llm.context_window_tokens // 16)) or [""]
            for part_index, part in enumerate(parts):
                metadata = dict(segment.metadata)
                if len(parts) > 1:
                    metadata.update(
                        {
                            "parent_segment_index": source_index,
                            "chunk_index": part_index,
                        }
                    )
                expanded.append(
                    SourceSegment(
                        segment_id="",
                        index=0,
                        content=part,
                        speaker=segment.speaker,
                        role=segment.role,
                        timestamp=segment.timestamp,
                        start_seconds=segment.start_seconds,
                        end_seconds=segment.end_seconds,
                        metadata=metadata,
                        participant_id=segment.participant_id,
                    )
                )
        normalized = []
        for index, segment in enumerate(expanded):
            segment.index = index
            segment.segment_id = f"{source_id}#seg-{index + 1:04d}"
            normalized.append(segment)
        return normalized
