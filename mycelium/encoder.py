import datetime
import re
from typing import Any, List
import uuid

from mycelium.models import LogEntry
from mycelium.store import LogStore
from mycelium.ollama import OllamaClient
from mycelium.config import Config
from mycelium import prompts
from mycelium.structured_outputs import (
    claim_extraction_output_model,
    extraction_coverage_output_model,
)
from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    EpisodeManifest,
    ExtractionSegmentDisposition,
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

    async def encode_session(
        self,
        transcript: str,
        session_id: str,
        *,
        source_type: str = "agent_conversation",
        occurred_at: str | datetime.datetime | None = None,
        participants: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        segments: list[SourceSegment | dict[str, Any]] | None = None,
    ) -> List[LogEntry]:
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        short_id = str(uuid.uuid4())[:8]
        entry_id = f"{date_str}#session-{short_id}"
        content = transcript.strip()
        if not content:
            return []

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
        source_id = f"source-{short_id}"
        normalized_segments = self._normalize_segments(
            segments, content, source_id, source_type
        )
        participant_names = participants or list(dict.fromkeys(
            segment.speaker for segment in normalized_segments if segment.speaker
        ))
        occurred = occurred_at.isoformat() if isinstance(occurred_at, datetime.datetime) else occurred_at
        source = SourceDocument(
            source_id=source_id,
            source_type=source_type,
            session_id=session_id,
            recorded_at=now.isoformat(),
            occurred_at=occurred,
            participants=participant_names,
            segments=normalized_segments,
            raw_log_entry_id=entry_id,
            metadata=metadata or {},
        )
        episode = EpisodeManifest(
            episode_id=f"episode-{short_id}", source_id=source_id, source_type=source_type,
            occurred_at=occurred, participants=participant_names,
            segment_ids=[segment.segment_id for segment in normalized_segments],
        )
        self.artifacts.save_source(source)
        self.artifacts.save_episode(episode)
        await self._extract_claims(source, episode)
        return [entry]

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

    async def _extract_claims(self, source: SourceDocument, episode: EpisodeManifest) -> None:
        try:
            allowed_ids = {segment.segment_id for segment in source.segments}
            claim_ids: list[str] = []
            dispositions: dict[str, ExtractionSegmentDisposition] = {}
            extraction_errors: list[str] = []

            for batch_index, batch in enumerate(
                self._segment_batches(source.segments), start=1
            ):
                batch_ids = {segment.segment_id for segment in batch}
                coverage_model = extraction_coverage_output_model(batch_ids)
                system, user = prompts.extraction_coverage_prompt(
                    source.source_type,
                    source.source_id,
                    source.occurred_at,
                    self._render_segments(batch),
                )
                try:
                    coverage = await self.llm.call_structured(
                        system,
                        user,
                        coverage_model,
                        num_predict=4096,
                        debug_label=(
                            f"extraction-coverage-{source.source_id}-batch-{batch_index}"
                        ),
                    )
                    if not isinstance(coverage, dict):
                        raise ValueError("extraction coverage did not return an object")
                    coverage = coverage_model.model_validate(coverage).model_dump(
                        exclude_none=True
                    )
                    coverage_by_id = {
                        item["segment_id"]: item
                        for item in coverage["segment_dispositions"]
                    }
                    claim_bearing = [
                        segment for segment in batch
                        if coverage_by_id[segment.segment_id]["disposition"]
                        == "claim_bearing"
                    ]
                    for item in coverage["segment_dispositions"]:
                        if item["disposition"] == "source_only":
                            dispositions[item["segment_id"]] = (
                                ExtractionSegmentDisposition(
                                    segment_id=item["segment_id"],
                                    disposition="source_only",
                                    reason=item["reason"],
                                )
                            )
                    if not claim_bearing:
                        continue

                    admitted_ids = {
                        segment.segment_id for segment in claim_bearing
                    }
                    claim_model = claim_extraction_output_model(admitted_ids)
                    system, user = prompts.claim_extraction_prompt(
                        source.source_type,
                        source.source_id,
                        source.occurred_at,
                        self._render_segments(claim_bearing),
                    )
                    response = await self.llm.call_structured(
                        system,
                        user,
                        claim_model,
                        num_predict=8192,
                        debug_label=(
                            f"claim-extraction-{source.source_id}-batch-{batch_index}"
                        )
                    )
                    if not isinstance(response, dict):
                        raise ValueError("claim extraction did not return an object")
                    response = claim_model.model_validate(response).model_dump(
                        exclude_none=True
                    )
                    staged_claims = self._build_extracted_claims(source, response)
                    for claim in staged_claims:
                        self.artifacts.save_claim(claim)
                        claim_ids.append(claim.claim_id)
                    claims_by_segment = {
                        segment_id: [
                            claim.claim_id for claim in staged_claims
                            if segment_id in claim.provenance[0].segment_ids
                        ]
                        for segment_id in admitted_ids
                    }
                    for segment_id, linked_claim_ids in claims_by_segment.items():
                        dispositions[segment_id] = ExtractionSegmentDisposition(
                            segment_id=segment_id,
                            disposition="claimed",
                            claim_ids=linked_claim_ids,
                            reason=coverage_by_id[segment_id]["reason"],
                        )
                except Exception as exc:
                    extraction_errors.append(f"batch {batch_index}: {exc}")

            episode.claim_ids = claim_ids
            accounted_ids = set(dispositions)
            substantive_remaining = allowed_ids - accounted_ids
            episode.segment_dispositions = [
                dispositions[segment_id] for segment_id in sorted(dispositions)
            ]
            episode.extraction_status = "partial" if substantive_remaining else "complete"
            if substantive_remaining:
                episode.extraction_error = "; ".join(extraction_errors) or (
                    f"{len(substantive_remaining)} substantive segments remain unclaimed"
                )
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
    def _segment_batches(
        segments: list[SourceSegment], batch_size: int = 48
    ) -> list[list[SourceSegment]]:
        return [
            segments[index:index + batch_size]
            for index in range(0, len(segments), batch_size)
        ]

    def _build_extracted_claims(
        self,
        source: SourceDocument,
        response: dict[str, Any],
    ) -> list[MemoryClaim]:
        """Build a validated batch before any claim in it is persisted."""
        claims: list[MemoryClaim] = []
        for raw in response["claims"]:
            claim_text = str(raw["text"]).strip()
            segment_ids = list(dict.fromkeys(raw["segment_ids"]))
            source_speakers = list(dict.fromkeys(
                segment.speaker for segment in source.segments
                if segment.segment_id in segment_ids and segment.speaker
            ))
            about = list(raw["about"])
            raw_modality = str(raw.get("evidence_modality") or "unknown").strip().lower()
            facets = dict(raw.get("facets", {}) or {})
            is_inferred = (
                raw.get("evidence_type") == "inferred"
                and bool(str(facets.get("inference_basis") or "").strip())
            )
            cited_segments = [
                segment for segment in source.segments
                if segment.segment_id in segment_ids
            ]
            timestamped_segments = [
                segment for segment in cited_segments if segment.timestamp
            ]
            anchor_segment_id = str(
                raw.get("temporal_anchor_segment_id") or ""
            ).strip()
            anchor_segment = next(
                (
                    segment for segment in timestamped_segments
                    if segment.segment_id == anchor_segment_id
                ),
                None,
            )
            temporal_anchor = (
                anchor_segment.timestamp
                if anchor_segment is not None
                else None if timestamped_segments else source.occurred_at
            )
            claims.append(MemoryClaim(
                claim_id=f"claim-{uuid.uuid4().hex[:12]}",
                text=claim_text,
                about=about,
                provenance=[ClaimProvenance(
                    source_id=source.source_id,
                    segment_ids=segment_ids,
                    raw_log_entry_id=source.raw_log_entry_id,
                    speaker=source_speakers[0] if len(source_speakers) == 1 else raw.get("speaker"),
                    evidence_type="inferred" if is_inferred else "explicit",
                )],
                recorded_at=source.recorded_at,
                confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.8)))),
                slot=str(raw["slot"]).strip() if raw.get("slot") else None,
                facets=normalize_temporal_facets(
                    facets, temporal_anchor, claim_text
                ),
                claim_type=str(raw.get("claim_type") or "unknown"),
                predicate=str(raw["predicate"]) if raw.get("predicate") else None,
                evidence_modality=raw_modality,
                temporal_status=str(raw.get("temporal_status") or "unknown"),
            ))
        return claims
