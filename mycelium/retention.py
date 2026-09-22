"""Retain source-backed statements once per bounded, durable source batch."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, TYPE_CHECKING, cast
from copy import deepcopy
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from itertools import zip_longest

from mycelium import memory_contract as contract
from mycelium.artifacts import (
    ArtifactStore,
    ClaimEntityReference,
    ClaimProvenance,
    EntityRecord,
    EntityResolutionDecision,
    ExtractionBatchState,
    ExtractionSegmentDisposition,
    MemoryClaim,
    ReconsolidationProposal,
    SourceDocument,
    SourceSegment,
    EpisodeManifest,
)
from mycelium.batching import split_text_by_tokens
from mycelium.budget import ContextBudgetError
from mycelium.memory_budget import fit_retention
from mycelium.memory_inputs import (
    RetentionInput,
    RetentionResult,
    serialize_claim_context,
)
from mycelium.claim_index import LanceClaimIndex
from mycelium.config import Config
from mycelium.ollama import OllamaClient
from mycelium.database import UnitOfWork
from mycelium import identity_context
from mycelium.memory_diagnostics import failure
from mycelium.telemetry import trace_operation

if TYPE_CHECKING:
    from mycelium.encoder import Encoder


def stable_id(kind: str, *parts: Any) -> str:
    return kind + "-" + hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:20]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def related_claim_ids(index: LanceClaimIndex, text: str) -> list[str]:
    """Learned candidate retrieval; this does not decide identity or truth."""
    rankings = []
    for chunk in split_text_by_tokens(text, 1200):
        rankings.append([hit.claim_id for hit in await index.search(chunk, limit=24)])
    return list(
        dict.fromkeys(
            claim_id
            for rank in zip_longest(*rankings)
            for claim_id in rank
            if claim_id is not None
        )
    )[:48]


class Retainer:
    def __init__(
        self,
        llm: OllamaClient,
        artifacts: ArtifactStore,
        config: Config,
        claim_index: LanceClaimIndex | None = None,
    ) -> None:
        self.llm = llm
        self.artifacts = artifacts
        self.config = config
        self.claim_index = claim_index

    @staticmethod
    def _serialize_segments(
        source: SourceDocument, segments: Sequence[SourceSegment]
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": s.segment_id,
                "index": s.index,
                "text": s.content,
                "speaker": s.speaker,
                "role": s.role,
                "participant_id": identity_context.participant_id(source, s),
                "source_id": source.source_id,
                "source_time": s.timestamp or source.occurred_at,
                "metadata": s.metadata,
            }
            for s in segments
            if s.role != "system"
        ]

    async def prepare_retention_input(
        self,
        source: SourceDocument,
        segments: Sequence[SourceSegment],
        batch_id: str,
        *,
        prior_claim_ids: Sequence[str] | None = None,
        recent_claim_ids: Sequence[str] = (),
        sources: Sequence[SourceDocument] | None = None,
        context_sources: Sequence[SourceDocument] = (),
    ) -> RetentionInput:
        """Gather source context, participant bindings and evidence for identity candidates."""
        sources = sources or [source]
        context_by_id = self._gather_context_sources(sources, context_sources)
        participants = [
            p
            for item in context_by_id.values()
            for p in identity_context.participants(self.artifacts, item)
        ]
        segment_sources = {
            s.segment_id: item for item in sources for s in item.segments
        }
        if prior_claim_ids is None:
            if self.claim_index is None:
                raise ValueError(
                    "Retention requires retrieved or explicit prior context"
                )
            text = "\n".join(
                f"{s.speaker or s.role}: {s.content}"
                if s.speaker or s.role
                else s.content
                for s in segments
                if s.role != "system"
            )
            prior_claim_ids = await related_claim_ids(self.claim_index, text)
            # Query named participants separately so a new topic does not control
            # every identity candidate. Retrieval supplies choices, never matches.
            names = dict.fromkeys(
                p["name"] for p in participants if not p["subject_id"] and p["name"]
            )
            for name in names:
                hits = await self.claim_index.search(name, limit=4)
                prior_claim_ids.extend(hit.claim_id for hit in hits)
        # Preserve a bounded amount of the current source's established context
        # even when its new topic retrieves different evidence. IDs only select
        # context; the model still decides whether any identity is the same.
        ordered_prior_claim_ids = dict.fromkeys(
            [*reversed(list(recent_claim_ids)[-12:]), *prior_claim_ids]
        )
        prior_claims = [
            self.artifacts.get_claim(claim_id) for claim_id in ordered_prior_claim_ids
        ]
        prior_claims = [
            c
            for c in prior_claims
            if c.status == "active" and c.dream_disposition != "excluded_source_policy"
        ][:48]
        candidate_entity_ids = self.artifacts.entities_for_claims(
            {c.claim_id for c in prior_claims}
        )
        candidate_entity_ids.update(
            self.artifacts.entities_for_claims(set(recent_claim_ids))
        )
        candidate_entity_ids.update(
            p["subject_id"] for p in participants if p["subject_id"]
        )
        if any(
            e.entity_id == "you" for e in self.artifacts.list_entities(status="active")
        ):
            candidate_entity_ids.add("you")
        subjects = [
            self.artifacts.get_entity(eid) for eid in sorted(candidate_entity_ids)
        ]
        identity_candidates = self._describe_identity_candidates(subjects, prior_claims)
        new_ids = {s.segment_id for s in segments}
        # The whole conversation is interpretation context when it fits, including
        # later clarifications. Only the designated new segments may be extracted.
        context = [
            row
            for item in sorted(
                context_by_id.values(), key=lambda s: (s.recorded_at, s.source_id)
            )
            for row in self._serialize_segments(item, item.segments)
            if row["id"] not in new_ids
        ]
        return {
            "source_type": source.source_type,
            "occurred_at": source.occurred_at,
            "participants": participants,
            "metadata": source.metadata,
            "segments": [
                row
                for s in segments
                for row in self._serialize_segments(segment_sources[s.segment_id], [s])
            ],
            "context_segments": context,
            "prior_memories": [
                serialize_claim_context(self.artifacts, c) for c in prior_claims
            ],
            "existing_subjects": identity_candidates,
            "new_subject_ids": [stable_id("subject", batch_id, i) for i in range(32)],
        }

    def _gather_context_sources(
        self,
        sources: Sequence[SourceDocument],
        context_sources: Sequence[SourceDocument],
    ) -> dict[str, SourceDocument]:
        """Include active sources from this conversation and explicitly linked context."""
        context_by_id = {
            item.source_id: item
            for item in [*context_sources, *sources]
            if item.status == "active"
        }
        for item in sources:
            for sid in item.metadata.get("context_source_ids", []):
                old = self.artifacts.get_source(sid)
                if old.status == "active":
                    context_by_id[sid] = old
        return context_by_id

    def _describe_identity_candidates(
        self,
        subjects: Sequence[EntityRecord],
        prior_claims: Sequence[MemoryClaim],
    ) -> list[dict[str, Any]]:
        """Attach up to two retained claims to each active identity choice."""
        identity_candidates = []
        for entity in subjects:
            if entity.status != "active":
                continue
            evidence = []
            refs = self.artifacts.list_entity_references(
                entity_id=entity.entity_id, status="active"
            )
            ids = {r.claim_id for r in refs}
            ordered = dict.fromkeys(
                [
                    *(c.claim_id for c in prior_claims if c.claim_id in ids),
                    *reversed(sorted(ids)),
                ]
            )
            for claim_id in ordered:
                claim = self.artifacts.get_claim(claim_id)
                if (
                    claim.status == "active"
                    and claim.dream_disposition != "excluded_source_policy"
                ):
                    evidence.append({"id": claim_id, "text": claim.text})
                    if len(evidence) == 2:
                        break
            identity_candidates.append(
                {
                    "id": entity.entity_id,
                    "title": entity.title,
                    "entity_type": entity.entity_type,
                    "aliases": entity.aliases,
                    "evidence": evidence,
                }
            )
        return identity_candidates

    def save_retained_memories(
        self,
        source: SourceDocument,
        batch_id: str,
        payload: RetentionInput,
        result: RetentionResult,
        *,
        replacement: MemoryClaim | None = None,
    ) -> list[str]:
        """Persist inside the caller's transaction; user replacement text is exact."""
        contract.retention_model(payload).model_validate(
            {k: v for k, v in result.items() if k != "_rejections"}
        )
        for sid in {s["source_id"] for s in payload["segments"]}:
            if self.artifacts.get_source(sid).status != "active":
                raise ValueError("Source was retracted during retention")
        for change in result["changes"]:
            if self.artifacts.get_claim(change["earlier_id"]).status != "active":
                raise ValueError("Prior evidence changed during retention")
        now = now_iso()
        declarations = {s["id"]: s for s in result["subjects"]}
        subjects = {
            **declarations,
            **{s["id"]: s for s in payload["existing_subjects"]},
        }
        evidence = {
            s["id"]: s for s in [*payload["segments"], *payload["context_segments"]]
        }
        claims: list[MemoryClaim] = []
        claim_ids_by_response_id: dict[str, str] = {}
        for row in result["memories"]:
            by_source = defaultdict(list)
            for sid in row["segment_ids"]:
                s = evidence[sid]
                by_source[(s["source_id"], s["speaker"])].append(sid)
            roles = {evidence[sid]["role"] for sid in row["segment_ids"]}
            modality = (
                "tool"
                if roles == {"tool"}
                else "mixed"
                if "tool" in roles
                else "speech"
            )
            claim = replacement or MemoryClaim(
                claim_id=stable_id("claim", batch_id, row["id"]),
                text=row["text"],
                about=[],
                provenance=[
                    ClaimProvenance(
                        source_id=sid,
                        segment_ids=sorted(set(ids)),
                        raw_log_entry_id=self.artifacts.get_source(
                            sid
                        ).raw_log_entry_id,
                        speaker=speaker,
                    )
                    for (sid, speaker), ids in by_source.items()
                ],
                recorded_at=now,
                evidence_modality=modality,
            )
            claim_ids_by_response_id[row["id"]] = claim.claim_id
            if claim.claim_id not in {c.claim_id for c in claims}:
                claims.append(claim)
        if replacement is not None and not claims:
            claims.append(replacement)
        for s in result["subjects"]:
            try:
                entity = self.artifacts.get_entity(s["id"])
            except FileNotFoundError:
                entity = EntityRecord(
                    entity_id=s["id"],
                    entity_type=s["entity_type"],
                    title=s["title"],
                    slug=s["id"],
                    aliases=[],
                    status="active",
                    created_at=now,
                    updated_at=now,
                    materialization_state="provisional",
                )
            self.artifacts.save_entity(entity)
        for claim in claims:
            self.artifacts.save_claim(claim)
        # Redeclaring an unused existing identity supplies no new identity
        # evidence. Do not fabricate a source association from that row alone.
        used = {sid for row in result["memories"] for sid in row["subject_ids"]} | {
            sid
            for sid, declaration in declarations.items()
            if sid in payload["new_subject_ids"] or declaration["participant_ids"]
        }
        decisions = {}
        for sid in sorted(used):
            subject = subjects[sid]
            # Reusing an exact bound identity also reuses its review record,
            # even when the model omits the optional existing-subject declaration.
            participant_ids = sorted(
                set(declarations.get(sid, {}).get("participant_ids", []))
                | {p["id"] for p in payload["participants"] if p["subject_id"] == sid}
            )
            bound = [
                identity_context.binding(self.artifacts, pid) for pid in participant_ids
            ]
            decision_id = next(
                (b["decision_id"] for b in bound if b),
                stable_id("identity", source.source_id, sid),
            )
            claim_ids = {
                claim_ids_by_response_id[m["id"]]
                for m in result["memories"]
                if sid in m["subject_ids"]
            }
            cited = {
                s
                for c in claims
                if c.claim_id in claim_ids
                for p in c.provenance
                for s in p.segment_ids
            }
            cited.update(
                s["id"]
                for s in payload["segments"]
                if s.get("participant_id") in participant_ids
            )
            try:
                decision = self.artifacts.get_entity_resolution_decision(decision_id)
            except FileNotFoundError:
                decision = EntityResolutionDecision(
                    decision_id=decision_id,
                    decision_type="participant_resolution"
                    if participant_ids
                    else "entity_creation",
                    entity_id=sid,
                    proposed_entity_type=subject["entity_type"],
                    proposed_title=subject["title"],
                    source_ids=[source.source_id],
                    supporting_claim_ids=[],
                    supporting_segment_ids=[],
                    confidence=0.8,
                    reason="Subject selected from cited source and candidate evidence",
                    review_state="accepted",
                    dream_run_id=batch_id,
                    created_at=now,
                )
            if decision.entity_id != sid:
                raise ValueError("Identity changed during retention")
            decision.supporting_claim_ids = sorted(
                set(decision.supporting_claim_ids) | claim_ids
            )
            decision.supporting_segment_ids = sorted(
                set(decision.supporting_segment_ids) | cited
            )
            decision.source_ids = sorted(
                set(decision.source_ids)
                | {
                    p.source_id
                    for c in claims
                    if c.claim_id in claim_ids
                    for p in c.provenance
                }
            )
            decision.participant_ids = sorted(
                set(decision.participant_ids) | set(participant_ids)
            )
            self.artifacts.save_entity_resolution_decision(decision)
            decisions[sid] = decision_id
            for pid in participant_ids:
                previous = identity_context.binding(self.artifacts, pid)
                origin = (
                    previous["origin"]
                    if previous
                    else next(
                        p["binding_origin"]
                        for p in payload["participants"]
                        if p["id"] == pid
                    )
                    or "model"
                )
                participant_source = next(
                    p["source_id"] for p in payload["participants"] if p["id"] == pid
                )
                identity_context.save_binding(
                    self.artifacts,
                    participant_source,
                    pid,
                    sid,
                    decision_id,
                    origin=origin,
                )
        for row in result["memories"]:
            for sid in row["subject_ids"]:
                self.artifacts.save_entity_reference(
                    ClaimEntityReference(
                        reference_id=stable_id(
                            "ref", claim_ids_by_response_id[row["id"]], sid
                        ),
                        claim_id=claim_ids_by_response_id[row["id"]],
                        role="subject",
                        surface=subjects[sid]["title"],
                        entity_id=sid,
                        confidence=0.8,
                        reason="Retained with cited source",
                        origin="extraction",
                        dream_run_id=batch_id,
                        status="active",
                        created_at=now,
                        identity_decision_id=decisions[sid],
                    )
                )
        if replacement is None:
            for change in result["changes"]:
                later, earlier = (
                    claim_ids_by_response_id[change["later_id"]],
                    change["earlier_id"],
                )
                self.artifacts.save_reconsolidation_proposal(
                    ReconsolidationProposal(
                        proposal_id=stable_id("proposal", later, earlier),
                        incoming_claim_ids=[later],
                        target_claim_ids=[earlier],
                        proposed_relation=change["relation"],
                        explanation=change["reason"],
                        confidence=0.8,
                        dream_run_id=batch_id,
                        created_at=now,
                        affected_entity_ids=sorted(used),
                    )
                )
        return [c.claim_id for c in claims]

    async def plan_retention_batches(
        self,
        sources: Sequence[SourceDocument],
        episodes: Sequence[EpisodeManifest],
        context_sources: Sequence[SourceDocument],
    ) -> list[tuple[str, set[str]]]:
        """Replan only unprocessed evidence; completed records keep their exact IDs."""
        completed = {
            sid
            for e in episodes
            for b in e.extraction_batches
            if b.status == "complete"
            for sid in b.segment_ids
        }
        remaining = [
            segment
            for source in sources
            for segment in source.segments
            if segment.segment_id not in completed
        ]
        plans = []

        async def measure_batch(segments: Sequence[SourceSegment]) -> str:
            batch_id = stable_id("batch", [s.segment_id for s in segments])
            payload = await self.prepare_retention_input(
                sources[0],
                segments,
                batch_id,
                sources=sources,
                context_sources=context_sources,
                prior_claim_ids=[],
            )
            fit_retention(payload, self.config.llm.context_window_tokens)
            return batch_id

        while remaining:
            try:
                batch_id = await measure_batch(remaining)
                size = len(remaining)
            except ContextBudgetError:
                low, high, size = 1, len(remaining) - 1, 0
                while low <= high:
                    middle = (low + high) // 2
                    try:
                        batch_id = await measure_batch(remaining[:middle])
                        size, low = middle, middle + 1
                    except ContextBudgetError:
                        high = middle - 1
                if not size:
                    await measure_batch(
                        remaining[:1]
                    )  # Surface the actual capacity failure.
                batch_id = stable_id("batch", [s.segment_id for s in remaining[:size]])
            plans.append((batch_id, {s.segment_id for s in remaining[:size]}))
            remaining = remaining[size:]
        with self.artifacts.db.transaction():
            for episode in episodes:
                previous = {b.batch_id: b for b in episode.extraction_batches}
                episode.extraction_batches = [
                    b for b in previous.values() if b.status == "complete"
                ]
                for batch_id, ids in plans:
                    own_ids = [sid for sid in episode.segment_ids if sid in ids]
                    if own_ids:
                        prior = previous.get(batch_id)
                        episode.extraction_batches.append(
                            ExtractionBatchState(
                                batch_id=batch_id,
                                batch_index=len(episode.extraction_batches),
                                segment_ids=own_ids,
                                attempt_count=prior.attempt_count if prior else 0,
                            )
                        )
                self.artifacts.save_episode(episode)
        return plans

    async def retain_sources(
        self,
        sources: Sequence[SourceDocument],
        episodes: Sequence[EpisodeManifest],
        encoder: Encoder,
        *,
        context_sources: Sequence[SourceDocument] = (),
    ) -> tuple[set[str], list[dict[str, Any]], list[dict[str, Any]]]:
        """One request can cover several captures; each source keeps its own manifest."""
        plans = await self.plan_retention_batches(sources, episodes, context_sources)
        prior_claim_ids: set[str] = set()
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for batch_id, segment_ids in plans:
            batch_episodes = [
                episode
                for episode in episodes
                if set(episode.segment_ids) & segment_ids
            ]
            for episode in batch_episodes:
                next(
                    checkpoint
                    for checkpoint in episode.extraction_batches
                    if checkpoint.batch_id == batch_id
                ).attempt_count += 1
            unit = UnitOfWork(self.artifacts.db)
            checkpoints: dict[str, EpisodeManifest] = {}
            try:
                reader = Retainer(
                    self.llm,
                    ArtifactStore(self.artifacts.root, db=unit),
                    self.config,
                    self.claim_index,
                )
                checkpoints = {
                    episode.episode_id: reader.artifacts.get_episode(episode.episode_id)
                    for episode in episodes
                }
                current_sources = [
                    reader.artifacts.get_source(source.source_id) for source in sources
                ]
                context_snapshots = [
                    reader.artifacts.get_source(source.source_id)
                    for source in context_sources
                ]
                segments = [
                    segment
                    for source in current_sources
                    for segment in source.segments
                    if segment.segment_id in segment_ids
                ]
                payload = await reader.prepare_retention_input(
                    current_sources[0],
                    segments,
                    batch_id,
                    sources=current_sources,
                    context_sources=context_snapshots,
                    prior_claim_ids=None
                    if any(segment.role != "system" for segment in segments)
                    else [],
                    recent_claim_ids=[
                        claim_id
                        for episode in episodes
                        for claim_id in episode.claim_ids
                    ],
                )
                payload, budget = fit_retention(
                    payload, self.config.llm.context_window_tokens
                )
                with trace_operation("retention-batch", batch_id=batch_id, **budget):
                    result: RetentionResult = (
                        await contract.retain(self.llm, payload)
                        if payload["segments"]
                        else {"subjects": [], "memories": [], "changes": []}
                    )
                updated_episodes = deepcopy(batch_episodes)
                with self.artifacts.db.transaction():
                    unit.validate_reads()
                    claim_ids = self.save_retained_memories(
                        current_sources[0], batch_id, payload, result
                    )
                    prior_claim_ids.update(m["id"] for m in payload["prior_memories"])
                    for updated_episode in updated_episodes:
                        batch = next(
                            checkpoint
                            for checkpoint in updated_episode.extraction_batches
                            if checkpoint.batch_id == batch_id
                        )
                        source_claim_ids = [
                            claim_id
                            for claim_id in claim_ids
                            if any(
                                provenance.source_id == updated_episode.source_id
                                and set(provenance.segment_ids) & set(batch.segment_ids)
                                for provenance in self.artifacts.get_claim(
                                    claim_id
                                ).provenance
                            )
                        ]
                        updated_episode.claim_ids = list(
                            dict.fromkeys(
                                [*updated_episode.claim_ids, *source_claim_ids]
                            )
                        )
                        batch.status, batch.last_error, batch.response = (
                            "complete",
                            None,
                            cast(dict[str, Any], result),
                        )
                        batch.diagnostics = budget
                        self.finalize_episode(
                            next(
                                source
                                for source in current_sources
                                if source.source_id == updated_episode.source_id
                            ),
                            updated_episode,
                            encoder,
                        )
                for episode, updated_episode in zip(batch_episodes, updated_episodes):
                    episode.__dict__.update(updated_episode.__dict__)
                warnings.extend(
                    {
                        "stage": "retention",
                        "batch_id": batch_id,
                        **{
                            k: v
                            for k, v in rejection.items()
                            if k not in {"record", "request_ids", "request_citations"}
                        },
                    }
                    for rejection in result.get("_rejections", [])
                )
            except (Exception, asyncio.CancelledError) as exc:
                with self.artifacts.db.transaction():
                    for episode in batch_episodes:
                        self._save_failed_batch_checkpoint(
                            episode,
                            batch_id,
                            checkpoints.get(episode.episode_id),
                            exc,
                            encoder,
                        )
                        errors.append(
                            {
                                **failure("retention", episode.source_id, exc),
                                "batch_id": batch_id,
                            }
                        )
                if isinstance(exc, asyncio.CancelledError):
                    raise
            finally:
                unit.close()
        with self.artifacts.db.transaction():
            for episode in episodes:
                current_episode = self.artifacts.get_episode(episode.episode_id)
                self.finalize_episode(
                    self.artifacts.get_source(current_episode.source_id),
                    current_episode,
                    encoder,
                )
                episode.__dict__.update(current_episode.__dict__)
        return prior_claim_ids, errors, warnings

    def _save_failed_batch_checkpoint(
        self,
        episode: EpisodeManifest,
        batch_id: str,
        snapshot: EpisodeManifest | None,
        error: Exception | asyncio.CancelledError,
        encoder: Encoder,
    ) -> None:
        """Merge a failure into current state without failing a competing completion."""
        current_episode = self.artifacts.get_episode(episode.episode_id)
        previous_batch = (
            next(
                (
                    checkpoint
                    for checkpoint in snapshot.extraction_batches
                    if checkpoint.batch_id == batch_id
                ),
                None,
            )
            if snapshot
            else None
        )
        batch = next(
            (
                checkpoint
                for checkpoint in current_episode.extraction_batches
                if checkpoint.batch_id == batch_id
            ),
            None,
        )
        # Never fail a competing completion or a newer attempt.
        # Merge into current state, preserving other batch results.
        if batch is not None and batch == previous_batch and batch.status != "complete":
            batch.attempt_count += 1
            batch.status, batch.last_error = (
                "failed",
                f"{type(error).__name__}: {error}",
            )
            self.finalize_episode(
                self.artifacts.get_source(current_episode.source_id),
                current_episode,
                encoder,
            )
        episode.__dict__.update(current_episode.__dict__)

    def finalize_episode(
        self,
        source: SourceDocument,
        episode: EpisodeManifest,
        encoder: Encoder,
    ) -> None:
        """Derive source dispositions and ingestion status from durable batch checkpoints."""
        complete = all(b.status == "complete" for b in episode.extraction_batches)
        episode.extraction_status = (
            "complete" if complete else "partial" if episode.claim_ids else "failed"
        )
        episode.extraction_error = next(
            (b.last_error for b in episode.extraction_batches if b.last_error), None
        )
        processed = {
            sid
            for b in episode.extraction_batches
            if b.status == "complete"
            for sid in b.segment_ids
        }
        rejected = {
            sid
            for b in episode.extraction_batches
            if b.response and b.response.get("_rejections")
            for sid in b.segment_ids
        }
        cited = defaultdict(list)
        for claim_id in episode.claim_ids:
            for p in self.artifacts.get_claim(claim_id).provenance:
                if p.source_id == source.source_id:
                    for sid in p.segment_ids:
                        cited[sid].append(claim_id)
        episode.segment_dispositions = [
            ExtractionSegmentDisposition(
                segment_id=s.segment_id,
                disposition="claimed" if cited[s.segment_id] else "source_only",
                claim_ids=cited[s.segment_id],
                reason="Cited by retained memory"
                if cited[s.segment_id]
                else "Not retained; inspect rejected records in batch response"
                if s.segment_id in rejected
                else "Not selected; source retained",
            )
            for s in source.segments
            if s.segment_id in processed
        ]
        self.artifacts.save_episode(episode)
        encoder.sync_ingestion_status(episode)
