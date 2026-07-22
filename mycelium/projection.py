"""Deterministic projection policy from comprehensive claims to readable wiki views."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from mycelium.artifacts import MemoryClaim, parse_source_datetime

ProjectionScope = Literal["main", "timeline", "details", "insights", "interaction_archive"]

CLAIM_TYPE_BUCKETS = {
    "identity": "Identity & Background",
    "state": "Current State",
    "event": "Activities & Experiences",
    "preference": "Preferences",
    "plan": "Goals & Plans",
    "belief": "Beliefs & Opinions",
    "relationship": "Relationships",
    "decision": "Goals & Plans",
    "commitment": "Goals & Plans",
    "interaction": "Interactions",
    "observation": "Supporting Observations",
    "unknown": "Other Durable Facts",
}
MAIN_CLAIM_TYPES = {
    "identity", "state", "preference", "plan", "belief", "relationship",
    "decision", "commitment",
}


@dataclass(frozen=True)
class ProjectedClaim:
    claim: MemoryClaim
    scope: ProjectionScope
    bucket: str
    salience: float
    date_key: str
    claims: tuple[MemoryClaim, ...] = ()

    @property
    def members(self) -> tuple[MemoryClaim, ...]:
        return self.claims or (self.claim,)

    @property
    def claim_ids(self) -> tuple[str, ...]:
        return tuple(claim.claim_id for claim in self.members)


def presentation_bucket(claim: MemoryClaim) -> str:
    if claim.inferred and claim.derivation_operation:
        return "Derived Insights"
    if claim.evidence_modality == "visual":
        return "Visual References"
    return CLAIM_TYPE_BUCKETS.get(claim.claim_type, "Other Durable Facts")


def claim_date_key(claim: MemoryClaim) -> str:
    normalized = claim.facets.get("normalized_date")
    if normalized:
        if claim.facets.get("date_precision") == "week":
            return f"Week of {normalized}"
        return str(normalized)
    observed = claim.facets.get("observed_at")
    parsed = parse_source_datetime(str(observed)) if observed else None
    if parsed:
        # An observation date is useful for navigation but must not masquerade as
        # the date on which the described event occurred.
        return f"Observed {parsed.date().isoformat()}"
    return "Date unknown"


def project_claim(claim: MemoryClaim) -> ProjectedClaim:
    claim_type = claim.claim_type
    is_main = claim_type in MAIN_CLAIM_TYPES
    is_timeline = claim_type == "event" or (
        claim_type in {"plan", "commitment", "decision", "state"}
        and claim.temporal_status == "past"
    )
    is_interaction = claim_type == "interaction"
    is_visual = claim.evidence_modality == "visual"

    score = max(0.0, min(1.0, (claim.salience + claim.confidence) / 2))
    if is_main:
        score += 0.18
    if is_timeline:
        score += 0.08
    if claim.facets.get("normalized_date") or claim.facets.get("deadline"):
        score += 0.08
    if claim.slot:
        score += 0.10
    if claim.inferred:
        score -= 0.15
    if is_interaction:
        score -= 0.35
    score = max(0.0, min(1.0, score))

    # Semantic fields determine placement. Unknown claims fail closed into details.
    scope: ProjectionScope
    if claim.inferred and claim.derivation_operation:
        scope = "insights"
    elif is_visual:
        scope = "details"
    elif is_interaction:
        scope = "interaction_archive"
    elif is_timeline:
        scope = "timeline"
    elif is_main:
        scope = "main"
    else:
        scope = "details"

    return ProjectedClaim(
        claim=claim,
        scope=scope,
        bucket=presentation_bucket(claim),
        salience=score,
        date_key=claim_date_key(claim),
        claims=(claim,),
    )


_DISPLAY_STOPWORDS = {
    "a", "about", "an", "and", "as", "at", "be", "because", "for", "from",
    "he", "her", "hers", "him", "his", "i", "in", "is", "it", "my", "of",
    "on", "she", "that", "the", "their", "them", "they", "this", "to", "was",
    "will", "with", "would", "stated", "said", "mentioned", "confirmed",
    "affirmed", "reported", "acknowledged", "expressed",
}


def _diversity_terms(text: str) -> set[str]:
    normalized = text.lower()
    normalized = re.sub(
        r"\b(?:not giving up|never giving up|will not quit|won't quit)\b",
        " persevere ",
        normalized,
    )
    terms = set()
    for token in re.findall(r"[a-z0-9]+", normalized):
        if token in _DISPLAY_STOPWORDS or (len(token) < 3 and not token.isdigit()):
            continue
        for suffix in ("ing", "ment", "ed", "es", "s"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 4:
                token = token[:-len(suffix)]
                break
        token = {
            "open": "start",
            "launch": "start",
            "cloth": "clothing",
            "shop": "store",
        }.get(token, token)
        terms.add(token)
    return terms


def _too_similar(candidate: ProjectedClaim, selected: list[ProjectedClaim]) -> bool:
    terms = _diversity_terms(candidate.claim.text)
    if not terms:
        return False
    for existing in selected:
        if existing.bucket != candidate.bucket:
            continue
        other = _diversity_terms(existing.claim.text)
        if other and len(terms & other) / len(terms | other) >= 0.5:
            return True
    return False


def _entity_key(item: ProjectedClaim) -> tuple[str, ...]:
    return tuple(sorted(
        str(entity.get("entity", "")).strip().lower()
        for entity in item.claim.about
        if entity.get("entity")
    ))


def _equivalent_for_display(left: ProjectedClaim, right: ProjectedClaim) -> bool:
    """Conservatively identify redundant wording without mutating canonical claims."""
    if left.scope != right.scope or left.bucket != right.bucket:
        return False
    if _entity_key(left) != _entity_key(right):
        return False
    if left.scope == "timeline" and left.date_key != right.date_key:
        return False
    left_terms = _diversity_terms(display_claim_text(left.claim))
    right_terms = _diversity_terms(display_claim_text(right.claim))
    if not left_terms or not right_terms:
        return False
    overlap = len(left_terms & right_terms)
    containment = overlap / min(len(left_terms), len(right_terms))
    jaccard = overlap / len(left_terms | right_terms)
    return containment >= 0.9 and jaccard >= 0.6


def _representative(items: list[ProjectedClaim]) -> ProjectedClaim:
    best = max(
        items,
        key=lambda item: (
            len(_diversity_terms(display_claim_text(item.claim))),
            item.claim.confidence,
            -int(item.claim.inferred),
            len(item.claim.text),
        ),
    )
    members = tuple(dict.fromkeys(
        claim.claim_id for item in items for claim in item.members
    ))
    claims_by_id = {
        claim.claim_id: claim for item in items for claim in item.members
    }
    return ProjectedClaim(
        claim=best.claim,
        scope=best.scope,
        bucket=best.bucket,
        salience=max(item.salience for item in items),
        date_key=best.date_key,
        claims=tuple(claims_by_id[claim_id] for claim_id in members),
    )


def compact_display_claims(items: list[ProjectedClaim]) -> list[ProjectedClaim]:
    """Build traceable display records while retaining every member claim."""
    clusters: list[list[ProjectedClaim]] = []
    for item in sorted(items, key=lambda value: (-value.salience, value.claim.text.lower())):
        cluster = next(
            (group for group in clusters if _equivalent_for_display(item, group[0])),
            None,
        )
        if cluster is None:
            clusters.append([item])
        else:
            cluster.append(item)
    return [_representative(cluster) for cluster in clusters]


def _select_main_claims(
    candidates: list[ProjectedClaim], limit: int
) -> tuple[list[ProjectedClaim], list[ProjectedClaim]]:
    """Select a compact, diverse main view; all rejected claims remain in details."""
    if limit <= 0:
        return [], candidates
    bucket_limit = max(3, (limit + 2) // 3)
    counts: Counter[str] = Counter()
    selected: list[ProjectedClaim] = []
    demoted: list[ProjectedClaim] = []
    for item in candidates:
        if (
            len(selected) >= limit
            or counts[item.bucket] >= bucket_limit
            or _too_similar(item, selected)
        ):
            demoted.append(item)
            continue
        selected.append(item)
        counts[item.bucket] += 1
    return selected, demoted


def partition_claims(claims: list[MemoryClaim], *, main_claim_limit: int = 18) -> dict[ProjectionScope, list[ProjectedClaim]]:
    projected = compact_display_claims([
        project_claim(claim) for claim in claims if claim.status == "active"
    ])
    main = sorted(
        (item for item in projected if item.scope == "main"),
        key=lambda item: (-item.salience, item.bucket, item.claim.text.lower()),
    )
    selected_main, demoted = _select_main_claims(main, main_claim_limit)
    result: dict[ProjectionScope, list[ProjectedClaim]] = {
        "main": selected_main,
        "timeline": sorted(
            (item for item in projected if item.scope == "timeline"),
            key=lambda item: (item.date_key, item.claim.text.lower()),
        ),
        "details": sorted(
            [item for item in projected if item.scope == "details"] + demoted,
            key=lambda item: (item.bucket, item.date_key, item.claim.text.lower()),
        ),
        "insights": sorted(
            (item for item in projected if item.scope == "insights"),
            key=lambda item: (item.bucket, item.claim.text.lower()),
        ),
        "interaction_archive": sorted(
            (item for item in projected if item.scope == "interaction_archive"),
            key=lambda item: (item.date_key, item.claim.text.lower()),
        ),
    }
    return result


def compact_qualifiers(claim: MemoryClaim, *, include_date: bool = False) -> list[str]:
    facets = claim.facets
    qualifiers: list[str] = []
    claim_terms = _diversity_terms(display_claim_text(claim))
    when = facets.get("when") or facets.get("time_expression")
    normalized = facets.get("normalized_date")
    if include_date and normalized:
        label = "event week" if facets.get("date_precision") == "week" else "event date"
        qualifiers.append(f"{label}: {normalized}")
    if when and str(when).lower() != str(normalized).lower():
        qualifiers.append(f"stated: {when}")
    for key in ("location", "reason", "deadline", "owner", "value", "quantity"):
        value = facets.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            value_terms = _diversity_terms(str(value))
            if not value_terms or not value_terms <= claim_terms:
                qualifiers.append(f"{key}: {value}")
    if claim.inferred:
        qualifiers.append("inferred")
        basis_ids = claim.facets.get("basis_claim_ids")
        if isinstance(basis_ids, list) and basis_ids:
            qualifiers.append(f"based on {len(basis_ids)} facts")
    return qualifiers


def compact_record_qualifiers(
    item: ProjectedClaim, *, include_date: bool = False
) -> list[str]:
    qualifiers = compact_qualifiers(item.claim, include_date=include_date)
    source_ids = {
        provenance.source_id
        for claim in item.members
        for provenance in claim.provenance
        if provenance.source_id
    }
    if len(source_ids) > 1:
        qualifiers.append(f"recorded in {len(source_ids)} sessions")
    return qualifiers


def display_claim_text(claim: MemoryClaim) -> str:
    """Remove model-added calendar dates that conflict with normalized relative time."""
    text = claim.text.strip()
    when = str(claim.facets.get("when") or claim.facets.get("time_expression") or "").strip()
    if claim.facets.get("normalized_date") and when.lower() in {"today", "yesterday", "tomorrow"}:
        month = (
            r"(?:january|february|march|april|may|june|july|august|september|"
            r"october|november|december)"
        )
        text = re.sub(
            rf"\b({re.escape(when)})\s*,?\s*(?:on\s+)?(?:"
            rf"{month}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,\s*\d{{4}})?|"
            rf"\d{{1,2}}(?:st|nd|rd|th)?\s+{month}(?:,\s*\d{{4}})?|"
            rf"\d{{4}}-\d{{2}}-\d{{2}})",
            r"\1",
            text,
            flags=re.I,
        )
    normalized_date = str(claim.facets.get("normalized_date") or "")
    relative_time = re.fullmatch(
        r"(?:today|yesterday|tomorrow|last week|next week|this month|"
        r"(?:last|next) (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))",
        when,
        re.IGNORECASE,
    )
    if normalized_date and relative_time:
        month = (
            r"(?:january|february|march|april|may|june|july|august|september|"
            r"october|november|december)"
        )
        explicit_date = re.compile(
            rf"(?:{month}\s+\d{{1,2}}(?:st|nd|rd|th)?,\s*\d{{4}}|"
            rf"\d{{1,2}}(?:st|nd|rd|th)?\s+{month},\s*\d{{4}}|"
            rf"\d{{4}}-\d{{2}}-\d{{2}})",
            re.IGNORECASE,
        )
        for match in reversed(list(explicit_date.finditer(text))):
            parsed = parse_source_datetime(match.group())
            if parsed is None or parsed.date().isoformat() == normalized_date:
                continue
            start = match.start()
            prefix = text[:start]
            on_match = re.search(r"\s+on\s+$", prefix, re.IGNORECASE)
            if on_match:
                start = on_match.start()
            text = f"{text[:start]}{text[match.end():]}"
        text = re.sub(r"\s+([,.;])", r"\1", text)
        text = re.sub(r",\s*\.", ".", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
    return text
