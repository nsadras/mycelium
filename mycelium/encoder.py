import datetime
import re
from typing import Any, List
import uuid

from mycelium.models import LogEntry
from mycelium.store import LogStore
from mycelium.ollama import OllamaClient
from mycelium.config import Config
from mycelium import prompts
from mycelium.structured_outputs import extraction_output_model
from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    EpisodeManifest,
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
            importance=0.8,
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
        programmatic_ignored_ids = {
            segment.segment_id for segment in source.segments
            if self._is_source_furniture(segment.content)
        }
        extractable_segments = [
            segment for segment in source.segments
            if segment.segment_id not in programmatic_ignored_ids
        ]
        try:
            allowed_ids = {segment.segment_id for segment in source.segments}
            claim_ids: list[str] = []
            covered_ids: set[str] = set()
            ignored_ids = set(programmatic_ignored_ids)
            extraction_errors: list[str] = []

            for batch_index, batch in enumerate(
                self._segment_batches(extractable_segments), start=1
            ):
                batch_ids = {segment.segment_id for segment in batch}
                output_model = extraction_output_model(batch_ids)
                system, user = prompts.claim_extraction_prompt(
                    source.source_type,
                    source.source_id,
                    source.occurred_at,
                    self._render_segments(batch),
                )
                try:
                    response = await self.llm.call_structured(
                        system,
                        user,
                        output_model,
                        num_predict=8192,
                        debug_label=(
                            f"claim-extraction-{source.source_id}-batch-{batch_index}"
                        ),
                    )
                    if not isinstance(response, dict):
                        raise ValueError("claim extraction did not return an object")
                    response = output_model.model_validate(response).model_dump(
                        exclude_none=True
                    )
                    self._validate_batch_accounting(response, batch_ids)
                    covered_ids.update(self._persist_extracted_claims(
                        source, response, batch_ids, claim_ids
                    ))
                    ignored_ids.update(
                        value for value in response.get("ignored_segment_ids", [])
                        if value in batch_ids
                    )
                except Exception as exc:
                    extraction_errors.append(f"batch {batch_index}: {exc}")

            episode.claim_ids = claim_ids
            remaining_ids = allowed_ids - covered_ids
            substantive_remaining = remaining_ids - ignored_ids
            episode.ignored_segment_ids = sorted((ignored_ids & allowed_ids) - covered_ids)
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
    def _is_source_furniture(content: str) -> bool:
        return bool(re.match(r"^image url:\s*", content.strip(), re.IGNORECASE))

    @staticmethod
    def _segment_batches(
        segments: list[SourceSegment], batch_size: int = 48
    ) -> list[list[SourceSegment]]:
        return [
            segments[index:index + batch_size]
            for index in range(0, len(segments), batch_size)
        ]

    @staticmethod
    def _validate_batch_accounting(
        response: dict[str, Any], allowed_ids: set[str]
    ) -> None:
        claimed_ids = {
            segment_id
            for claim in response.get("claims", [])
            for segment_id in claim.get("segment_ids", [])
        }
        ignored_ids = set(response.get("ignored_segment_ids", []))
        invalid_ids = (claimed_ids | ignored_ids) - allowed_ids
        if invalid_ids:
            raise ValueError(
                "Extraction referenced unknown segment IDs: "
                + ", ".join(sorted(invalid_ids))
            )
        overlap = claimed_ids & ignored_ids
        if overlap:
            raise ValueError(
                "Extraction marked segments as both claimed and ignored: "
                + ", ".join(sorted(overlap))
            )

    @staticmethod
    def _is_direct_atomic_claim(text: str) -> bool:
        """Reject dialogue-shaped output instead of storing conversational debris."""
        normalized = " ".join(text.split()).strip()
        if not normalized:
            return False
        dialogue_pronoun = re.compile(
            r"(?:^|\W)(?:i|i'm|i've|i'd|my|mine|we|we're|we've|we'll|our|ours|"
            r"you|you're|you've|you'll|your|yours|let's)(?:\W|$)",
            re.IGNORECASE,
        )
        reporting_wrapper = re.compile(
            r"^[A-Z][\w'-]+\s+(?:stated|said|mentioned|reported|informed|"
            r"acknowledged|expressed|confirmed|affirmed)\s+that\b",
            re.IGNORECASE,
        )
        deictic_fragment = re.compile(
            r"^(?:it is|it's|that is|that's|this is)\b",
            re.IGNORECASE,
        )
        return (
            not dialogue_pronoun.search(normalized)
            and not reporting_wrapper.search(normalized)
            and not deictic_fragment.search(normalized)
        )

    def _persist_extracted_claims(
        self,
        source: SourceDocument,
        response: dict[str, Any],
        allowed_ids: set[str],
        claim_ids: list[str],
    ) -> set[str]:
        covered_ids: set[str] = set()
        for raw in response.get("claims", []):
            if not isinstance(raw, dict) or not str(raw.get("text", "")).strip():
                continue
            claim_text = str(raw["text"]).strip()
            if not self._is_direct_atomic_claim(claim_text):
                continue
            segment_ids = list(dict.fromkeys(
                segment_id for segment_id in raw.get("segment_ids", [])
                if segment_id in allowed_ids
            ))
            if not segment_ids:
                continue
            source_speakers = list(dict.fromkeys(
                segment.speaker for segment in source.segments
                if segment.segment_id in segment_ids and segment.speaker
            ))
            about = [item for item in raw.get("about", []) if isinstance(item, dict)]
            if not any(item.get("entity") for item in about) and len(source_speakers) == 1:
                about = [{"entity": source_speakers[0], "role": "speaker"}]
            raw_modality = str(raw.get("evidence_modality") or "unknown").strip().lower()
            if not self._has_explicit_subject(claim_text, about):
                attributed = self._attribute_subjectless_claim(
                    claim_text, source_speakers, about, raw_modality
                )
                if attributed is None:
                    continue
                claim_text, about = attributed
            covered_ids.update(segment_ids)
            facets = dict(raw.get("facets", {}) or {})
            if claim_text != str(raw["text"]).strip():
                facets["attribution_normalized"] = True
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
            claim = MemoryClaim(
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
            )
            self.artifacts.save_claim(claim)
            claim_ids.append(claim.claim_id)
        return covered_ids

    @staticmethod
    def _has_explicit_subject(text: str, about: list[dict[str, Any]]) -> bool:
        """Require standalone claims to name at least one entity they are about."""
        normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        entities = [
            re.sub(r"[^a-z0-9]+", " ", str(item.get("entity", "")).lower()).strip()
            for item in about
            if item.get("entity")
        ]
        return bool(entities) and any(
            re.search(rf"(?:^|\s){re.escape(entity)}(?:\s|$)", normalized)
            for entity in entities if entity
        )

    @classmethod
    def _attribute_subjectless_claim(
        cls,
        text: str,
        source_speakers: list[str],
        about: list[dict[str, Any]],
        evidence_modality: str = "unknown",
    ) -> tuple[str, list[dict[str, Any]]] | None:
        """Make an otherwise useful model paraphrase standalone without guessing its subject."""
        if len(source_speakers) != 1:
            return None
        speaker = source_speakers[0].strip()
        if not speaker:
            return None
        normalized_about = list(about)
        if not any(
            str(item.get("entity", "")).strip().lower() == speaker.lower()
            for item in normalized_about
        ):
            normalized_about.append({"entity": speaker, "role": "speaker"})
        stripped = " ".join(text.split()).strip()
        stripped = re.sub(
            r",?\s+according to (?:the )?image caption(?:\s+for\s+source-[a-z0-9]+#seg-\d+)?\.?$",
            ".",
            stripped,
            flags=re.I,
        )
        stripped = re.sub(
            r"\s+for\s+source-[a-z0-9]+#seg-\d+\b", "", stripped, flags=re.I
        )
        if evidence_modality == "visual":
            visual = re.match(
                r"^(?:a|the)\s+(photo|image|image caption)\s+(shows|describes)\s+(.+)$",
                stripped,
                re.I,
            )
            visual_of = re.match(
                r"^(?:a|the)\s+(photo|image)\s+of\s+(.+?)(?:\s+is present)?\.?$",
                stripped,
                re.I,
            )
            if visual:
                medium = visual.group(1).lower()
                article = "an" if medium.startswith("image") else "a"
                verb = "showing" if visual.group(2).lower() == "shows" else "describing"
                attributed = f"{speaker} shared {article} {medium} {verb} {visual.group(3)}"
            elif visual_of:
                medium = visual_of.group(1).lower()
                article = "an" if medium == "image" else "a"
                subject = re.sub(
                    r"\s+contains\s+", " containing ", visual_of.group(2), flags=re.I
                )
                attributed = f"{speaker} shared {article} {medium} of {subject}"
            else:
                attributed = f"{speaker} shared visual evidence describing {stripped[0].lower()}{stripped[1:]}"
        else:
            attributed = f"{speaker} reported that {stripped[0].lower()}{stripped[1:]}"
        if text.rstrip().endswith((".", "!", "?")) and not attributed.endswith((".", "!", "?")):
            attributed += text.rstrip()[-1]
        if not cls._has_explicit_subject(attributed, normalized_about):
            return None
        return attributed, normalized_about
