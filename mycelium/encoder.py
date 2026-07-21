import datetime
from typing import Any, List, Optional
import uuid

from mycelium.models import LogEntry
from mycelium.store import WikiStore, LogStore
from mycelium.ollama import OllamaClient
from mycelium.config import Config
from mycelium import prompts
from mycelium.structured_outputs import ImportanceRatingOutput
from mycelium.structured_outputs import ExtractedEpisodeOutput
from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    ClaimReconciler,
    EpisodeManifest,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
    normalize_temporal_facets,
    segment_transcript,
)

IMPORTANCE_LABELS = {
    "low": 0.25,
    "medium": 0.6,
    "high": 0.9,
}


def normalize_importance(value, default: float = 0.5) -> float:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in IMPORTANCE_LABELS:
            return IMPORTANCE_LABELS[normalized]
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class Encoder:
    def __init__(self, llm: OllamaClient, wiki_store: WikiStore, log_store: LogStore, config: Config, artifacts: ArtifactStore | None = None):
        self.llm = llm
        self.wiki_store = wiki_store
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
            importance=0.8,
            status="raw",
            durability="durable",
            consolidated=False,
            decay_score=1.0,
        )

        self.log_store.append(entry)
        if self.artifacts is not None:
            source_id = f"source-{short_id}"
            normalized_segments = self._normalize_segments(segments, content, source_id)
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
            if self.config.dream.evidence_mode != "raw":
                await self._extract_claims(source, episode)
        return [entry]

    def _normalize_segments(
        self,
        segments: list[SourceSegment | dict[str, Any]] | None,
        transcript: str,
        source_id: str,
    ) -> list[SourceSegment]:
        if segments is None:
            return segment_transcript(transcript, source_id)
        normalized = []
        for index, item in enumerate(segments):
            segment = item if isinstance(item, SourceSegment) else SourceSegment(**item)
            segment.index = index
            segment.segment_id = f"{source_id}#seg-{index + 1:04d}"
            normalized.append(segment)
        return normalized

    async def _extract_claims(self, source: SourceDocument, episode: EpisodeManifest) -> None:
        rendered = "\n\n".join(
            f"[{segment.segment_id}] speaker={segment.speaker or 'unknown'}; role={segment.role or 'unknown'}; "
            f"time={segment.timestamp or 'unknown'}\n{segment.content}"
            for segment in source.segments
        )
        system, user = prompts.claim_extraction_prompt(
            source.source_type, source.source_id, source.occurred_at, rendered
        )
        try:
            response = await self.llm.call_structured(
                system, user, ExtractedEpisodeOutput, num_predict=8192,
                debug_label=f"claim-extraction-{source.source_id}",
            )
            if not isinstance(response, dict):
                raise ValueError("claim extraction did not return an object")
            allowed_ids = {segment.segment_id for segment in source.segments}
            reconciler = ClaimReconciler(self.artifacts)
            claim_ids: list[str] = []
            for raw in response.get("claims", []):
                if not isinstance(raw, dict) or not str(raw.get("text", "")).strip():
                    continue
                segment_ids = list(dict.fromkeys(
                    segment_id for segment_id in raw.get("segment_ids", []) if segment_id in allowed_ids
                ))
                if not segment_ids:
                    continue
                source_speakers = list(dict.fromkeys(
                    segment.speaker for segment in source.segments
                    if segment.segment_id in segment_ids and segment.speaker
                ))
                claim = MemoryClaim(
                    claim_id=f"claim-{uuid.uuid4().hex[:12]}",
                    text=str(raw["text"]).strip(),
                    kind=str(raw.get("kind") or "fact").strip().lower(),
                    about=[item for item in raw.get("about", []) if isinstance(item, dict)],
                    provenance=[ClaimProvenance(
                        source_id=source.source_id, segment_ids=segment_ids,
                        raw_log_entry_id=source.raw_log_entry_id,
                        speaker=source_speakers[0] if len(source_speakers) == 1 else raw.get("speaker"),
                        evidence_type=str(raw.get("evidence_type", "explicit")),
                    )],
                    recorded_at=source.recorded_at,
                    confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.8)))),
                    inferred=raw.get("evidence_type") == "inferred",
                    slot=str(raw["slot"]).strip() if raw.get("slot") else None,
                    facets=normalize_temporal_facets(raw.get("facets", {}), source.occurred_at),
                )
                canonical = reconciler.reconcile(claim)
                if canonical.claim_id not in claim_ids:
                    claim_ids.append(canonical.claim_id)
            episode.claim_ids = claim_ids
            episode.summary = str(response.get("summary", "")).strip()
            episode.extraction_status = "complete"
        except Exception as exc:
            episode.extraction_status = "failed"
            episode.extraction_error = str(exc)
        self.artifacts.save_episode(episode)

    async def encode(
        self,
        content: str,
        session_id: str,
        importance: Optional[float] = None,
        durability: str = "durable",
    ) -> LogEntry:
        
        final_importance = importance
        
        if importance is None:
            system, user = prompts.importance_rating_prompt(content)
            response = await self.llm.call_structured(system, user, ImportanceRatingOutput)
            
            if isinstance(response, dict):
                final_importance = float(response.get("importance", 0.5))
            else:
                final_importance = 0.5
                
        if final_importance is None:
            final_importance = 0.5
            
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        short_id = str(uuid.uuid4())[:8]
        entry_id = f"{date_str}#entry-{short_id}"
        
        entry = LogEntry(
            entry_id=entry_id,
            session_id=session_id,
            timestamp=now,
            content=content,
            importance=final_importance,
            status="raw",
            durability=durability,  # type: ignore[arg-type]
            consolidated=False,
            decay_score=1.0
        )
        
        self.log_store.append(entry)
        return entry
