"""Durable source, episode, and claim artifacts for the memory pipeline.

The JSON representation is intentionally boring and inspectable.  Raw source text is
never replaced by an LLM summary; claims point back to exact source segment ids.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


CLAIM_TYPES = {
    "identity", "state", "event", "preference", "plan", "belief",
    "relationship", "decision", "commitment", "interaction", "observation",
    "unknown",
}
EVIDENCE_MODALITIES = {"speech", "visual", "tool", "inference", "mixed", "unknown"}
TEMPORAL_STATUSES = {"past", "current", "future", "recurring", "atemporal", "unknown"}
DERIVATION_OPERATIONS = {
    "temporal_arithmetic", "event_count", "recurring_pattern",
    "cross_fact_relationship",
}

def _normalized_label(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


@dataclass
class SourceSegment:
    segment_id: str
    index: int
    content: str
    speaker: str | None = None
    role: str | None = None
    timestamp: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceDocument:
    source_id: str
    source_type: str
    session_id: str
    recorded_at: str
    occurred_at: str | None
    participants: list[str]
    segments: list[SourceSegment]
    raw_log_entry_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClaimProvenance:
    source_id: str
    segment_ids: list[str]
    raw_log_entry_id: str | None = None
    speaker: str | None = None
    evidence_type: str = "explicit"


@dataclass
class MemoryClaim:
    claim_id: str
    text: str
    kind: str
    about: list[dict[str, str]]
    provenance: list[ClaimProvenance]
    recorded_at: str
    status: str = "active"
    confidence: float = 0.8
    inferred: bool = False
    slot: str | None = None
    facets: dict[str, Any] = field(default_factory=dict)
    links: list[dict[str, str]] = field(default_factory=list)
    page_slugs: list[str] = field(default_factory=list)
    salience: float = 0.5
    claim_type: str = "unknown"
    predicate: str | None = None
    evidence_modality: str = "unknown"
    temporal_status: str = "unknown"
    derivation_operation: str | None = None

    def __post_init__(self) -> None:
        """Normalize the compact semantic envelope without inferring it from prose or labels."""
        normalized_type = _normalized_label(self.claim_type)
        if normalized_type not in CLAIM_TYPES:
            normalized_type = "unknown"
        self.claim_type = normalized_type

        modality = _normalized_label(self.evidence_modality)
        if self.inferred:
            modality = "inference"
        elif modality not in EVIDENCE_MODALITIES:
            modality = "unknown"
        self.evidence_modality = modality

        temporal = _normalized_label(self.temporal_status)
        if temporal not in TEMPORAL_STATUSES:
            temporal = "unknown"
        self.temporal_status = temporal

        if self.predicate is not None:
            self.predicate = " ".join(str(self.predicate).split()).strip() or None
        operation = _normalized_label(self.derivation_operation).replace(" ", "_")
        self.derivation_operation = operation if operation in DERIVATION_OPERATIONS else None


@dataclass
class EpisodeManifest:
    episode_id: str
    source_id: str
    source_type: str
    occurred_at: str | None
    participants: list[str]
    segment_ids: list[str]
    claim_ids: list[str] = field(default_factory=list)
    ignored_segment_ids: list[str] = field(default_factory=list)
    extraction_status: str = "pending"
    extraction_error: str | None = None


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-") or str(uuid.uuid4())


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root
        self.sources_dir = root / "sources"
        self.episodes_dir = root / "episodes"
        self.claims_dir = root / "claims"
        for directory in (self.sources_dir, self.episodes_dir, self.claims_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def save_source(self, source: SourceDocument) -> None:
        _atomic_json(self.sources_dir / f"{_safe_id(source.source_id)}.json", asdict(source))

    def get_source(self, source_id: str) -> SourceDocument:
        data = self._read(self.sources_dir / f"{_safe_id(source_id)}.json")
        data["segments"] = [SourceSegment(**item) for item in data.get("segments", [])]
        return SourceDocument(**data)

    def list_sources(self) -> list[SourceDocument]:
        return [self.get_source(path.stem) for path in sorted(self.sources_dir.glob("*.json"))]

    def save_episode(self, episode: EpisodeManifest) -> None:
        _atomic_json(self.episodes_dir / f"{_safe_id(episode.episode_id)}.json", asdict(episode))

    def get_episode(self, episode_id: str) -> EpisodeManifest:
        return EpisodeManifest(**self._read(self.episodes_dir / f"{_safe_id(episode_id)}.json"))

    def list_episodes(self) -> list[EpisodeManifest]:
        return [self.get_episode(path.stem) for path in sorted(self.episodes_dir.glob("*.json"))]

    def save_claim(self, claim: MemoryClaim) -> None:
        _atomic_json(self.claims_dir / f"{_safe_id(claim.claim_id)}.json", asdict(claim))

    def get_claim(self, claim_id: str) -> MemoryClaim:
        data = self._read(self.claims_dir / f"{_safe_id(claim_id)}.json")
        data["provenance"] = [ClaimProvenance(**item) for item in data.get("provenance", [])]
        return MemoryClaim(**data)

    def clear(self) -> dict[str, int]:
        """Delete all derived artifacts while leaving canonical UI conversations untouched."""
        counts = {"sources": 0, "episodes": 0, "claims": 0}
        for label, directory in (
            ("sources", self.sources_dir),
            ("episodes", self.episodes_dir),
            ("claims", self.claims_dir),
        ):
            for path in directory.glob("*.json"):
                path.unlink()
                counts[label] += 1
        return counts

    def list_claims(self, *, status: str | None = None) -> list[MemoryClaim]:
        claims = [self.get_claim(path.stem) for path in sorted(self.claims_dir.glob("*.json"))]
        return [claim for claim in claims if status is None or claim.status == status]

    def claims_for_sources(self, source_ids: Iterable[str], *, active_only: bool = True) -> list[MemoryClaim]:
        wanted = set(source_ids)
        return [
            claim for claim in self.list_claims(status="active" if active_only else None)
            if any(prov.source_id in wanted for prov in claim.provenance)
        ]

    def assign_pages(self, claim_ids: Iterable[str], page_slug: str) -> None:
        for claim_id in set(claim_ids):
            try:
                claim = self.get_claim(claim_id)
            except FileNotFoundError:
                continue
            if page_slug not in claim.page_slugs:
                claim.page_slugs.append(page_slug)
                self.save_claim(claim)

    def claims_for_page(self, page_slug: str) -> list[MemoryClaim]:
        return [claim for claim in self.list_claims(status="active") if page_slug in claim.page_slugs]

    def coverage_report(self) -> dict[str, Any]:
        sources = self.list_sources()
        claims = self.list_claims()
        episodes = self.list_episodes()
        all_segments = {segment.segment_id for source in sources for segment in source.segments}
        claimed_segments = {
            segment_id for claim in claims for provenance in claim.provenance
            for segment_id in provenance.segment_ids
        }
        ignored_segments = {
            segment_id for episode in episodes for segment_id in episode.ignored_segment_ids
        }
        unresolved = claimed_segments - all_segments
        accounted_segments = (claimed_segments | ignored_segments) & all_segments
        return {
            "sources": len(sources),
            "episodes": len(episodes),
            "claims": len(claims),
            "active_claims": sum(claim.status == "active" for claim in claims),
            "segments": len(all_segments),
            "claimed_segments": len(all_segments & claimed_segments),
            "segment_coverage": (len(all_segments & claimed_segments) / len(all_segments)) if all_segments else 1.0,
            "ignored_segments": len(all_segments & ignored_segments),
            "accounted_segments": len(accounted_segments),
            "accounted_coverage": (len(accounted_segments) / len(all_segments)) if all_segments else 1.0,
            "unassigned_segment_ids": sorted(all_segments - claimed_segments),
            "unaccounted_segment_ids": sorted(all_segments - claimed_segments - ignored_segments),
            "unassigned_claim_ids": sorted(claim.claim_id for claim in claims if not claim.page_slugs),
            "unresolved_provenance_ids": sorted(unresolved),
            "failed_episode_ids": sorted(ep.episode_id for ep in episodes if ep.extraction_status == "failed"),
            "partial_episode_ids": sorted(ep.episode_id for ep in episodes if ep.extraction_status == "partial"),
        }

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)


_LOC0MO_LINE = re.compile(
    r"^\[(?P<label>[^]]+)]\s*(?:\((?P<time>[^)]+)\)\s*)?(?P<speaker>[^:]+):\s*(?P<text>.*)$"
)
_ROLE_LINE = re.compile(r"^(?P<role>USER|ASSISTANT|SYSTEM|TOOL)(?:\s*\([^)]*\))?:\s*(?P<text>.*)$", re.I)


def segment_transcript(transcript: str, source_id: str) -> list[SourceSegment]:
    """Split common transcript formats while preserving every nonempty line."""
    segments: list[SourceSegment] = []
    current: SourceSegment | None = None
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not segments and re.match(r"^(Session|Timestamp|Sample):\s*", line, re.I):
            continue
        locomo = _LOC0MO_LINE.match(line)
        role_match = _ROLE_LINE.match(line)
        if locomo:
            current = SourceSegment(
                segment_id=f"{source_id}#seg-{len(segments) + 1:04d}",
                index=len(segments),
                speaker=locomo.group("speaker").strip(),
                timestamp=locomo.group("time"),
                content=locomo.group("text").strip(),
                metadata={"source_label": locomo.group("label")},
            )
            segments.append(current)
        elif role_match:
            role = role_match.group("role").lower()
            current = SourceSegment(
                segment_id=f"{source_id}#seg-{len(segments) + 1:04d}",
                index=len(segments), role=role, speaker=role,
                content=role_match.group("text").strip(),
            )
            segments.append(current)
        elif current is not None:
            current.content = f"{current.content}\n{line}".strip()
        else:
            current = SourceSegment(
                segment_id=f"{source_id}#seg-{len(segments) + 1:04d}",
                index=len(segments), content=line,
            )
            segments.append(current)
    return segments


def normalize_temporal_facets(
    facets: dict[str, Any], anchor: str | None, claim_text: str | None = None
) -> dict[str, Any]:
    """Add normalized dates for a conservative set of relative expressions."""
    result = dict(facets or {})
    expression = str(result.get("when") or result.get("time_expression") or "").strip()
    if not expression and claim_text:
        match = re.search(
            r"\b(today|yesterday|tomorrow|last week|next week|this month|"
            r"(?:last|next) (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
            r"(?:(?:a|one|two|three|\d+) )?years? ago)\b",
            claim_text,
            re.I,
        )
        if match:
            expression = match.group(0)
            result["when"] = expression
    if anchor:
        result.setdefault("observed_at", anchor)
    if not expression or not anchor:
        return result
    base = parse_source_datetime(anchor)
    if base is None:
        return result
    lowered = expression.lower()
    target: datetime | None = None
    if lowered == "today":
        target = base
    elif lowered == "yesterday":
        target = base - timedelta(days=1)
    elif lowered == "tomorrow":
        target = base + timedelta(days=1)
    elif lowered == "last week":
        target = base - timedelta(days=7)
    elif lowered == "next week":
        target = base + timedelta(days=7)
    elif lowered == "this month":
        result["normalized_date"] = base.strftime("%Y-%m")
        result["date_precision"] = "month"
        result["normalization_anchor"] = base.date().isoformat()
        return result
    years_ago = re.fullmatch(r"(?:(a|one|two|three|\d+) )?years? ago", lowered)
    if years_ago:
        raw_years = years_ago.group(1) or "one"
        years = {"a": 1, "one": 1, "two": 2, "three": 3}.get(raw_years)
        if years is None and raw_years.isdigit():
            years = int(raw_years)
        if years is not None and 0 < years <= 100:
            result["normalized_date"] = str(base.year - years)
            result["date_precision"] = "year"
            result["normalization_anchor"] = base.date().isoformat()
            return result
    weekday = re.fullmatch(r"(last|next) (monday|tuesday|wednesday|thursday|friday|saturday|sunday)", lowered)
    if weekday:
        desired = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].index(weekday.group(2))
        delta = (base.weekday() - desired) % 7
        if weekday.group(1) == "last":
            target = base - timedelta(days=delta or 7)
        else:
            target = base + timedelta(days=((desired - base.weekday()) % 7) or 7)
    if target is not None:
        result["normalized_date"] = target.date().isoformat()
        result["date_precision"] = "week" if lowered in {"last week", "next week"} else "day"
        result["normalization_anchor"] = base.date().isoformat()
    return result


def parse_source_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value.strip(), flags=re.I)
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in (
        "%I:%M %p on %d %B, %Y",
        "%I:%M%p on %d %B, %Y",
        "%d %B, %Y",
        "%B %d, %Y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


class ClaimReconciler:
    """Conservative deterministic reconciliation; uncertain semantics remain separate."""
    def __init__(self, store: ArtifactStore):
        self.store = store

    def reconcile(self, incoming: MemoryClaim) -> MemoryClaim:
        incoming.text = re.sub(r"\s+", " ", incoming.text).strip()
        current = self.store.list_claims(status="active")
        incoming_entities = self._entities(incoming)
        for existing in current:
            similarity = SequenceMatcher(None, existing.text.lower(), incoming.text.lower()).ratio()
            predicates_compatible = (
                not existing.predicate
                or not incoming.predicate
                or existing.predicate == incoming.predicate
            )
            structured_shape = (
                existing.claim_type != "unknown"
                and existing.claim_type == incoming.claim_type
                and predicates_compatible
            )
            same_semantic_shape = structured_shape and similarity >= 0.92
            effectively_identical = similarity >= 0.98
            if incoming_entities == self._entities(existing) and (
                same_semantic_shape or effectively_identical
            ):
                existing.provenance = self._merge_provenance(existing.provenance, incoming.provenance)
                existing.confidence = max(existing.confidence, incoming.confidence)
                existing.salience = max(existing.salience, incoming.salience)
                if incoming.claim_type != "unknown" and (
                    existing.claim_type == "unknown"
                ):
                    existing.claim_type = incoming.claim_type
                if incoming.predicate and not existing.predicate:
                    existing.predicate = incoming.predicate
                if incoming.evidence_modality != "unknown":
                    if existing.evidence_modality == "unknown":
                        existing.evidence_modality = incoming.evidence_modality
                    elif existing.evidence_modality != incoming.evidence_modality:
                        existing.evidence_modality = "mixed"
                if incoming.temporal_status != "unknown" and (
                    existing.temporal_status == "unknown"
                ):
                    existing.temporal_status = incoming.temporal_status
                if incoming.derivation_operation and not existing.derivation_operation:
                    existing.derivation_operation = incoming.derivation_operation
                existing.facets.update(incoming.facets)
                self.store.save_claim(existing)
                return existing
        if incoming.slot and incoming_entities:
            for existing in current:
                if existing.slot == incoming.slot and self._entities(existing) == incoming_entities:
                    existing.status = "superseded"
                    existing.links.append({"relation": "superseded_by", "target": incoming.claim_id})
                    incoming.links.append({"relation": "supersedes", "target": existing.claim_id})
                    self.store.save_claim(existing)
        self.store.save_claim(incoming)
        return incoming

    @staticmethod
    def _entities(claim: MemoryClaim) -> tuple[str, ...]:
        return tuple(sorted(str(item.get("entity", "")).strip().lower() for item in claim.about if item.get("entity")))

    @staticmethod
    def _merge_provenance(left: list[ClaimProvenance], right: list[ClaimProvenance]) -> list[ClaimProvenance]:
        result = list(left)
        keys = {(item.source_id, tuple(item.segment_ids)) for item in left}
        for item in right:
            key = (item.source_id, tuple(item.segment_ids))
            if key not in keys:
                result.append(item)
                keys.add(key)
        return result
