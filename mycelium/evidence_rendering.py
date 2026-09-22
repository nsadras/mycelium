"""Render typed memory evidence for model requests, workspaces and tool results."""

from collections import defaultdict
from html import escape

from mycelium.operations import (
    EvidenceRecord,
    EvidenceSource,
    MemoryEvidence,
    MemoryWorkspace,
)
from mycelium.source_references import segment_references


def render_memory_evidence(evidence: MemoryEvidence) -> str:
    """Render initial evidence with the shared model-facing representation."""
    return _render_evidence_envelope("memory-evidence", evidence)


def render_memory_workspace(
    workspace: MemoryWorkspace, *, include_request: bool = True
) -> str:
    """Render the one current accumulated evidence workspace for an agent round."""
    operation_lines: list[str] = []
    if workspace.operations:
        operation_lines.append("Completed memory operations:")
        for operation in workspace.operations:
            target = operation.query or ", ".join(operation.requested_claim_ids)
            additions = [
                *operation.added_record_ids,
                *operation.added_source_ids,
            ]
            detail = f"; target: {_text(target)}" if target else ""
            added = (
                "; added: " + ", ".join(f"`{_text(value)}`" for value in additions)
                if additions
                else "; added: none"
            )
            error = f"; error: {_text(operation.error)}" if operation.error else ""
            operation_lines.append(
                f"{operation.sequence}. {_text(operation.tool_name)} "
                f"({_text(operation.status)}){detail}{added}{error}"
            )
        operation_lines.append("")
    return _render_evidence_envelope(
        "memory-workspace",
        workspace.evidence,
        attributes={
            "revision": str(workspace.revision),
            "last_operation_status": workspace.last_operation_status,
        },
        preamble=(
            *(
                [f"Original request: {_text(workspace.request)}"]
                if include_request
                else []
            ),
            f"Remaining searches: {workspace.remaining_searches}",
            f"Remaining evidence tokens: {workspace.remaining_evidence_tokens}",
            "",
            *operation_lines,
        ),
    )


def render_memory_search_result(
    evidence: MemoryEvidence,
    *,
    query: str,
    remaining_searches: int,
) -> str:
    """Render a complete, bounded memory-search result."""
    return _render_evidence_envelope(
        "memory-search-results",
        evidence,
        preamble=(
            f"Query: {_text(query)}",
            f"Remaining searches: {remaining_searches}",
        ),
    )


def render_memory_source_result(
    evidence: MemoryEvidence,
    *,
    requested_claim_ids: list[str],
) -> str:
    """Render complete source excerpts with explicit claim ownership."""
    requested = ", ".join(f"`{_text(value)}`" for value in requested_claim_ids)
    return _render_evidence_envelope(
        "memory-source-results",
        evidence,
        preamble=(f"Requested claims: {requested}",),
    )


def render_memory_tool_error(message: str) -> str:
    """Render a model-visible memory-tool failure without an ambiguous partial result."""
    return "\n".join(["<memory-tool-error>", _text(message), "</memory-tool-error>"])


def _render_evidence_envelope(
    tag: str,
    evidence: MemoryEvidence,
    *,
    preamble: tuple[str, ...] = (),
    attributes: dict[str, str] | None = None,
) -> str:
    rendered_attributes = "".join(
        f' {_attribute(key)}="{_attribute(value)}"'
        for key, value in (attributes or {}).items()
    )
    lines = [f"<{tag}{rendered_attributes}>", *preamble]
    if preamble and (evidence.records or evidence.sources):
        lines.append("")
    if evidence.build_incomplete:
        lines.append(
            "Build Memory is incomplete. Captured conversations or view updates are still pending; this evidence may miss recent information."
        )
    lines.extend(_render_records(evidence.records))
    if evidence.records and evidence.sources:
        lines.append("")
    lines.extend(_render_sources(evidence.sources))
    if not evidence.records and not evidence.sources:
        lines.append("No memory evidence found.")
    if evidence.more_available:
        lines.extend(["", "More evidence available: yes"])
    lines.append(f"</{tag}>")
    return "\n".join(lines)


def _render_records(records: tuple[EvidenceRecord, ...]) -> list[str]:
    lines: list[str] = []
    shown_claims = {r.record_id for r in records if r.record_type == "claim"}
    for index, record in enumerate(records):
        if index:
            lines.append("")
        lines.extend(
            [
                f"## Record `{_text(record.record_id)}`",
                f"Statement: {_text(record.statement)}",
                f"Type: {_text(record.record_type)}",
            ]
        )
        if record.subject_name or record.subject_entity_id:
            subject = _text(record.subject_name or "Unnamed subject")
            if record.subject_entity_id:
                subject += f" (`{_text(record.subject_entity_id)}`)"
            lines.append(f"Subject: {subject}")
        if record.state:
            lines.append(f"State: {_text(record.state)}")
        for subject in record.subjects:
            aliases = (
                "; aliases: " + ", ".join(_text(a) for a in subject.aliases)
                if subject.aliases
                else ""
            )
            lines.append(
                f"Identity ({_text(subject.role)}): {_text(subject.name)} (`{_text(subject.entity_id)}`){aliases}"
            )
        for qualification in record.uncertainty:
            lines.append(f"Uncertainty: {_text(qualification)}")
        for revision in record.revisions:
            lines.append(
                f"Revision: {_text(revision['relation'])} `{_text(revision['claim_id'])}` "
                f"({_text(revision['status'])}): {_text(revision['text'])}"
            )
        lines.append("Supporting claims:")
        lines.extend(f"- `{_text(value)}`" for value in record.claim_ids)
        unseen_claims = [
            c for c in record.canonical_claims if c.claim_id not in shown_claims
        ]
        if unseen_claims:
            lines.append("Canonical assertions:")
            lines.extend(
                f"- `{_text(c.claim_id)}`: {_text(c.text)}" for c in unseen_claims
            )
            shown_claims.update(c.claim_id for c in unseen_claims)
        for review in record.reviews:
            lines.append(
                f"Review `{_text(review.proposal_id)}`: {_text(review.status)}; "
                f"relation: {_text(review.relation)}; incoming claims: "
                + ", ".join(_text(c) for c in review.incoming_claim_ids)
                + "; target claims: "
                + ", ".join(_text(c) for c in review.target_claim_ids)
                + ". This relationship is unresolved; incoming claims do not establish a replacement."
            )
        if record.temporal:
            lines.append("Timing:")
            for value in record.temporal:
                interval = _text(value.start) if value.start else _text(value.status)
                if value.end and value.end != value.start:
                    interval += f" through {_text(value.end)}"
                expression = (
                    f"; source expression: {_text(value.expression)}"
                    if value.expression
                    else ""
                )
                lines.append(
                    f"- Claim `{_text(value.claim_id)}`: {_text(value.role)} "
                    f"{interval}{expression}"
                    + (f"; applies to: {_text(value.target)}" if value.target else "")
                    + (
                        f"; time evidence: `{_text(value.evidence_segment_id)}`"
                        if value.evidence_segment_id
                        else ""
                    )
                    + (
                        f"; reference date from: `{_text(value.anchor_segment_id)}`"
                        if value.anchor_segment_id
                        and value.anchor_segment_id != value.evidence_segment_id
                        else ""
                    )
                    + (
                        f"; reference choice: {_text(value.reference_reason)}"
                        if value.reference_reason
                        else ""
                    )
                    + (
                        f"; reason: {_text(value.resolution_reason)}"
                        if value.resolution_reason
                        else ""
                    )
                )
        if record.citations:
            lines.append("Evidence references:")
            for citation in record.citations:
                segments = segment_references(citation.source_id, citation.segment_ids)
                source_time = (
                    f"; conversation time: {_text(citation.source_time)}"
                    if citation.source_time
                    else ""
                )
                lines.append(
                    f"- Claim `{_text(citation.claim_id)}` → source "
                    f"`{_text(citation.source_id)}`{source_time}; cited segments: "
                    f"{segments or '(none)'}"
                )
    return lines


def _render_sources(sources: tuple[EvidenceSource, ...]) -> list[str]:
    lines: list[str] = []
    for index, source in enumerate(sources):
        if index:
            lines.append("")
        lines.extend(
            [
                f"## Source `{_text(source.source_id)}`",
                f"Conversation time: {_text(source.conversation_time)}",
                f"Source status: {_text(source.status)}"
                + (
                    f" — {_text(source.retraction_reason)}"
                    if source.retraction_reason
                    else ""
                ),
                "Supports claims:",
            ]
        )
        cited_claims_by_segment: dict[str, list[str]] = defaultdict(list)
        for citation in source.citations:
            segments = segment_references(source.source_id, citation.segment_ids)
            lines.append(
                f"- `{_text(citation.claim_id)}`: cited segments {segments or '(none)'}"
            )
            for segment_id in citation.segment_ids:
                cited_claims_by_segment[segment_id].append(citation.claim_id)
        lines.append("<transcript>")
        for segment in source.segments:
            claim_ids = cited_claims_by_segment.get(segment.segment_id, [])
            cited = (
                ' cited-for="'
                + " ".join(_attribute(value) for value in claim_ids)
                + '"'
                if claim_ids
                else ""
            )
            speaker = f"{_text(segment.speaker)}: " if segment.speaker else ""
            lines.append(
                f"[segment `{_text(segment.segment_id)}`{cited}] "
                f"{speaker}{_text(segment.content)}"
            )
        lines.append("</transcript>")
    return lines


def _text(value: object) -> str:
    return escape(str(value), quote=False)


def _attribute(value: object) -> str:
    return escape(str(value), quote=True)
