import datetime
import hashlib
import json
import re
from typing import Any, List
import uuid
from dataclasses import asdict, replace

from mycelium.budget import count_tokens, require_request_budget, ContextBudgetError
from mycelium.models import LogEntry
from mycelium.operations import IngestionResult, SourceInput
from mycelium.store import LogStore
from mycelium.ollama import OllamaClient
from mycelium.config import Config
from mycelium import prompts
from mycelium.structured_outputs import extraction_output_model, extraction_records
from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    EpisodeManifest,
    ExtractionBatchState,
    ExtractionSegmentDisposition,
    IngestionOperation,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
    normalize_temporal_facets,
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
                None
                if source_input.segments is None
                else list(source_input.segments)
            ),
            idempotency_key=source_input.idempotency_key,
        )
        if not entries:
            return IngestionResult(status="empty")

        entry_ids = {entry.entry_id for entry in entries}
        sources = [
            source for source in self.artifacts.list_sources()
            if source.raw_log_entry_id in entry_ids
        ]
        source_ids = {source.source_id for source in sources}
        episodes = [
            episode for episode in self.artifacts.list_episodes()
            if episode.source_id in source_ids
        ]
        claim_ids = tuple(dict.fromkeys(
            claim_id for episode in episodes for claim_id in episode.claim_ids
        ))
        operation_ids = tuple(dict.fromkeys(
            str(source.metadata["ingestion_operation_id"])
            for source in sources
            if source.metadata.get("ingestion_operation_id")
        ))
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
                error = (
                    "A non-empty source transcript must produce at least one segment"
                )
                operation.status = "failed"
                operation.error = f"ValueError: {error}"
                operation.updated_at = datetime.datetime.now().astimezone().isoformat()
                self.artifacts.save_ingestion_operation(operation)
                raise ValueError(error)
            participant_names = participants or list(dict.fromkeys(
                segment.speaker
                for segment in normalized_segments
                if segment.speaker
            ))
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
                metadata={**(metadata or {}), "ingestion_operation_id": operation_id},
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
        return [entry]

    def _sync_ingestion_operation(
        self,
        episode: EpisodeManifest,
        *,
        operation: IngestionOperation | None = None,
    ) -> None:
        if operation is None:
            operation = next((
                candidate
                for candidate in self.artifacts.list_ingestion_operations()
                if candidate.episode_id == episode.episode_id
            ), None)
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
        split_turns = source_type in {"multi_party_conversation", "meeting_transcript"}
        expanded: list[SourceSegment] = []
        for source_index, segment in enumerate(base):
            parts = self._sentence_parts(segment.content) if split_turns else [segment.content]
            for part_index, part in enumerate(parts):
                metadata = dict(segment.metadata)
                if len(parts) > 1:
                    metadata.update({
                        "parent_segment_index": source_index,
                        "sentence_index": part_index,
                    })
                expanded.append(SourceSegment(
                    segment_id="",
                    index=0,
                    content=part,
                    speaker=segment.speaker,
                    role=segment.role,
                    timestamp=segment.timestamp,
                    start_seconds=segment.start_seconds,
                    end_seconds=segment.end_seconds,
                    metadata=metadata,
                ))
        normalized = []
        for index, segment in enumerate(expanded):
            segment.index = index
            segment.segment_id = f"{source_id}#seg-{index + 1:04d}"
            normalized.append(segment)
        return normalized

    @staticmethod
    def _sentence_parts(content: str) -> list[str]:
        """Split prose turns for fact coverage while preserving non-prose lines."""
        parts: list[str] = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if re.match(r"^(?:image caption|image url):", line, re.IGNORECASE):
                parts.append(line)
                continue
            sentences = re.split(
                r"(?<=[.!?])\s+(?=(?:[\"'(]*[A-Z0-9]))",
                line,
            )
            parts.extend(sentence.strip() for sentence in sentences if sentence.strip())
        return parts or [content.strip()]

    async def extract_pending(self, source_ids: set[str] | None = None) -> list[str]:
        """Extract unfinished sources in the explicit build snapshot."""
        completed: list[str] = []
        sources = {source.source_id: source for source in self.artifacts.list_sources()}
        for episode in self.artifacts.list_episodes():
            if source_ids is not None and episode.source_id not in source_ids:
                continue
            if episode.extraction_status == "complete":
                continue
            source = sources.get(episode.source_id)
            if source is None or source.status != "active":
                continue
            await self._extract_claims(source, episode)
            self._sync_ingestion_operation(episode)
            if episode.extraction_status == "complete":
                completed.append(episode.episode_id)
        return completed

    async def _extract_claims(self, source: SourceDocument, episode: EpisodeManifest) -> None:
        try:
            context_sources = [
                self.artifacts.get_source(source_id)
                for source_id in source.metadata.get("context_source_ids", [])
            ]
            # Bound earlier context independently; never truncate a cited segment.
            selected_context = []
            context_tokens = 0
            for prior in reversed(context_sources):
                cost = count_tokens(self._render_segments(prior.segments))
                if prior.status == "active" and context_tokens + cost <= self.config.llm.context_window_tokens // 4:
                    selected_context.insert(0, prior)
                    context_tokens += cost
            context_sources = selected_context
            context_segments = [seg for prior in context_sources for seg in prior.segments]
            claim_ids: list[str] = list(episode.claim_ids)
            dispositions = {
                item.segment_id: item for item in episode.segment_dispositions
            }
            extraction_errors: list[str] = []
            def request_for(batch):
                start = next(i for i, seg in enumerate(source.segments) if seg.segment_id == batch[0].segment_id)
                # Complete adjacent segments resolve replies across extraction boundaries.
                neighbors = []
                context_limit = self.config.llm.context_window_tokens // 4
                for segment in reversed(source.segments[:start]):
                    trial = [segment, *neighbors]
                    if count_tokens(self._render_segments(trial)) > context_limit:
                        break
                    neighbors = trial
                # The adjacent same-source context has priority over older sources.
                supplied_context = list(neighbors)
                for segment in reversed(context_segments):
                    trial = [segment, *supplied_context]
                    if count_tokens(self._render_segments(trial)) > context_limit:
                        break
                    supplied_context = trial
                schema = extraction_output_model(
                    [seg.segment_id for seg in batch], [seg.segment_id for seg in supplied_context],
                )
                system, user = prompts.claim_extraction_prompt(
                    source.source_type, source.source_id, list(source.participants),
                    self._render_claim_segments(batch), context=self._render_segments(supplied_context),
                )
                return system, user, schema, neighbors, bool(supplied_context)

            def fits(batch):
                system, user, schema, _, think = request_for(batch)
                output_tokens = (max(8192, self.config.llm.reasoning_output_tokens)
                                 if think and self.config.llm.reasoning_enabled else 8192)
                try:
                    require_request_budget(
                        [{"role": "system", "content": system}, {"role": "user", "content": user}],
                        context_window=self.config.llm.context_window_tokens, output_tokens=output_tokens,
                        schema=schema.model_json_schema(),
                    )
                    return True
                except ContextBudgetError:
                    return False

            if not episode.extraction_batches:
                batches = self._segment_batches(source.segments, fits=fits)
                episode.extraction_batches = [
                    ExtractionBatchState(
                        batch_id=f"{episode.episode_id}-batch-{batch_index}",
                        batch_index=batch_index,
                        segment_ids=[segment.segment_id for segment in batch],
                    )
                    for batch_index, batch in enumerate(batches, start=1)
                ]
                self.artifacts.save_episode(episode)
            segments_by_id = {seg.segment_id: seg for seg in source.segments}
            # Persisted segment boundaries are the resume contract, even if budgets change.
            for state in episode.extraction_batches:
                batch_index = state.batch_index
                batch = [segments_by_id[sid] for sid in state.segment_ids]
                if state.status == "complete":
                    continue
                state.attempt_count += 1
                state.last_error = None
                batch_ids = {segment.segment_id for segment in batch}
                try:
                    system, user, claim_model, neighbors, think = request_for(batch)
                    if state.response is None:
                        response = await self.llm.call_structured(
                            system, user, claim_model, num_predict=8192, think=think,
                            debug_label=f"claim-extraction-{source.source_id}-batch-{batch_index}",
                        )
                    else:
                        response = state.response
                    response = claim_model.model_validate(response).model_dump()
                    records = extraction_records(response)
                    staged_claims = self._build_extracted_claims(
                        source, records, state.batch_id,
                        context_sources=[*context_sources, replace(source, segments=neighbors)]
                    )
                    # Persist validated output before publishing claims so a write
                    # interruption replays the same decision without a new model call.
                    state.response = response
                    self.artifacts.save_episode(episode)
                    for claim in staged_claims:
                        # Stable batch IDs make publication insert-only. Retrying
                        # must not overwrite a user correction to a published claim.
                        try:
                            self.artifacts.get_claim(claim.claim_id)
                        except FileNotFoundError:
                            self.artifacts.save_claim(claim)
                        claim_ids.append(claim.claim_id)
                    source_only = {
                        item["segment_id"]: item["reason"] for item in records["source_only"]
                    }
                    for segment_id in batch_ids:
                        supporting_ids = [
                            claim.claim_id for claim in staged_claims
                            if segment_id in claim.provenance[0].segment_ids
                        ]
                        dispositions[segment_id] = ExtractionSegmentDisposition(
                            segment_id=segment_id,
                            disposition="claimed" if supporting_ids else "source_only",
                            reason=(
                                "Cited by extracted statements." if supporting_ids
                                else source_only[segment_id]
                            ),
                            claim_ids=supporting_ids,
                        )
                    state.status = "complete"
                    state.last_error = None
                except Exception as exc:
                    state.status = "failed"
                    state.last_error = str(exc)
                    extraction_errors.append(f"batch {batch_index}: {exc}")
                finally:
                    episode.claim_ids = list(dict.fromkeys(claim_ids))
                    episode.segment_dispositions = [
                        dispositions[segment_id] for segment_id in sorted(dispositions)
                    ]
                    self.artifacts.save_episode(episode)

            episode.claim_ids = list(dict.fromkeys(claim_ids))
            for state in episode.extraction_batches:
                if state.status == "complete":
                    state.response = None
            terminal_batches = {
                state.batch_id for state in episode.extraction_batches
                if state.status == "complete"
            }
            incomplete = len(terminal_batches) != len(episode.extraction_batches)
            episode.segment_dispositions = [
                dispositions[segment_id] for segment_id in sorted(dispositions)
            ]
            episode.extraction_status = "partial" if incomplete else "complete"
            if incomplete:
                persisted_errors = [
                    f"batch {state.batch_index}: {state.last_error}"
                    for state in episode.extraction_batches if state.last_error
                ]
                episode.extraction_error = "; ".join(
                    extraction_errors or persisted_errors
                ) or "Extraction has retryable incomplete batches"
            else:
                episode.extraction_error = None
        except Exception as exc:
            episode.extraction_status = "failed"
            episode.extraction_error = str(exc)
        self.artifacts.save_episode(episode)

    @staticmethod
    def _render_segments(segments: list[SourceSegment]) -> str:
        return "\n\n".join(
            f"[{segment.segment_id}] speaker={segment.speaker or 'unknown'}; role={segment.role or 'unknown'}; "
            f"time={segment.timestamp or 'unknown'}\n{segment.content}"
            for segment in segments
        )

    @staticmethod
    def _render_claim_segments(segments: list[SourceSegment]) -> str:
        """Render semantic evidence without exposing recording-time metadata."""
        return "\n\n".join(
            f"[{segment.segment_id}] speaker={segment.speaker or 'unknown'}; "
            f"role={segment.role or 'unknown'}\n{segment.content}"
            for segment in segments
        )

    @staticmethod
    def _segment_batches(
        segments: list[SourceSegment], batch_size: int = 48, *, fits=None,
    ) -> list[list[SourceSegment]]:
        batches = []
        current = []
        for segment in segments:
            trial = [*current, segment]
            if current and (len(trial) > batch_size or (fits and not fits(trial))):
                batches.append(current)
                current = []
            current.append(segment)
            if fits and not fits(current):
                raise ContextBudgetError("A complete source segment exceeds the extraction budget")
        if current:
            batches.append(current)
        return batches

    def _build_extracted_claims(
        self,
        source: SourceDocument,
        response: dict[str, Any],
        batch_id: str,
        *, context_sources: list[SourceDocument] | None = None,
    ) -> list[MemoryClaim]:
        """Build a validated batch before any claim in it is persisted."""
        claims: list[MemoryClaim] = []
        for claim_index, raw in enumerate(response["claims"], start=1):
            claim_text = str(raw["text"]).strip()
            segment_ids = list(dict.fromkeys(raw["segment_ids"]))
            source_speakers = list(dict.fromkeys(
                segment.speaker for segment in source.segments
                if segment.segment_id in segment_ids and segment.speaker
            ))
            about = list(raw["about"])
            raw_modality = str(raw.get("evidence_modality") or "unknown").strip().lower()
            facets = dict(raw.get("facets", {}) or {})
            # The model declares an inference by supplying its evidence basis.
            is_inferred = facets.get("inference_basis") is not None
            cited_segments = [
                segment for segment in source.segments
                if segment.segment_id in segment_ids
            ]
            anchor_segment_id = str(
                raw.get("temporal_anchor_segment_id") or ""
            ).strip()
            cited_context_ids = set(raw.get("context_segment_ids", []))
            anchor_candidates = [
                *cited_segments,
                *(segment for prior in context_sources or [] for segment in prior.segments
                  if segment.segment_id in cited_context_ids),
            ]
            anchor_segment = next(
                (
                    segment for segment in anchor_candidates
                    if segment.segment_id == anchor_segment_id
                ),
                None,
            )
            timestamped_evidence = [segment for segment in anchor_candidates if segment.timestamp]
            unambiguous_timestamp = None
            if not anchor_segment_id:
                cited_timestamps = {
                    segment.timestamp for segment in timestamped_evidence
                }
                if len(cited_timestamps) == 1:
                    unambiguous_timestamp = next(iter(cited_timestamps))
            if anchor_segment is not None:
                temporal_anchor = anchor_segment.timestamp
            elif unambiguous_timestamp is not None:
                temporal_anchor = unambiguous_timestamp
            elif timestamped_evidence:
                temporal_anchor = None
            else:
                temporal_anchor = source.occurred_at
            context_provenance = []
            for prior in context_sources or []:
                cited = [seg.segment_id for seg in prior.segments if seg.segment_id in cited_context_ids]
                if cited:
                    context_provenance.append(ClaimProvenance(
                        source_id=prior.source_id, segment_ids=cited,
                        raw_log_entry_id=prior.raw_log_entry_id, evidence_type="explicit",
                    ))
            claims.append(MemoryClaim(
                claim_id=(
                    "claim-"
                    + hashlib.sha256(
                        f"{source.source_id}:{batch_id}:{claim_index}".encode("utf-8")
                    ).hexdigest()[:16]
                ),
                text=claim_text,
                about=about,
                provenance=[ClaimProvenance(
                    source_id=source.source_id,
                    segment_ids=segment_ids,
                    raw_log_entry_id=source.raw_log_entry_id,
                    speaker=source_speakers[0] if len(source_speakers) == 1 else None,
                    evidence_type="inferred" if is_inferred else "explicit",
                ), *context_provenance],
                recorded_at=source.recorded_at,
                confidence=0.8,
                facets=normalize_temporal_facets(
                    facets, temporal_anchor
                ),
                claim_type=str(raw.get("claim_type") or "unknown"),
                predicate=str(raw["predicate"]) if raw.get("predicate") else None,
                evidence_modality=raw_modality,
                temporal_status=str(raw.get("temporal_status") or "unknown"),
            ))
        return claims
