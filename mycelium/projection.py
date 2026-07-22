"""Deterministic projection policy from comprehensive claims to readable wiki views."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from mycelium.artifacts import MemoryClaim, parse_source_datetime

ProjectionScope = Literal["main", "timeline", "details", "interaction_archive"]

INTERACTION_KINDS = {
    "acknowledgement", "acknowledgment", "compliment", "encouragement",
    "farewell", "greeting", "gratitude", "reaction", "reinforcement",
    "sentiment", "support", "interaction", "question", "inquiry",
}
TIMELINE_KINDS = {
    "event", "activity", "action", "achievement", "experience", "change",
    "status update", "status change", "purchase", "sharing event",
}
MAIN_KINDS = {
    "biographical fact", "preference", "relationship", "goal", "decision",
    "commitment", "plan", "action item", "belief", "current state", "status",
}

BUCKET_RULES = (
    ("Identity & Background", {"biographical fact", "identity", "background"}),
    ("Preferences", {"preference", "interest"}),
    ("Relationships", {"relationship"}),
    ("Goals & Plans", {"goal", "plan", "commitment", "action item", "decision", "intent"}),
    ("Current State", {"current state", "status", "state", "change"}),
    ("Beliefs & Opinions", {"belief", "opinion", "value"}),
    ("Activities & Experiences", {"activity", "experience", "achievement", "event", "action"}),
    ("Visual References", {"image description", "image caption", "visual", "photo description"}),
)


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


def normalized_kind(claim: MemoryClaim) -> str:
    return re.sub(r"[^a-z0-9]+", " ", claim.kind.lower()).strip()


def presentation_bucket(claim: MemoryClaim) -> str:
    kind = normalized_kind(claim)
    for label, terms in BUCKET_RULES:
        if any(term in kind for term in terms):
            return label
    return "Other Durable Facts"


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
    kind = normalized_kind(claim)
    scope_hint = claim.display_scope if claim.display_scope in {
        "main", "timeline", "details", "interaction_archive"
    } else "main"

    interaction_text = re.match(
        r"^[A-Z][\w'-]+\s+(?:asked|thanked|greeted|congratulated|complimented|"
        r"praised|said goodbye to|wished|apologized to)\b",
        claim.text.strip(),
        re.IGNORECASE,
    )
    is_interaction = any(term in kind for term in INTERACTION_KINDS) or bool(interaction_text)
    is_timeline = any(term in kind for term in TIMELINE_KINDS)
    is_main = any(term in kind for term in MAIN_KINDS)

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

    # Deterministic placement overrides model hints for conversational scaffolding.
    if is_interaction and not is_main:
        scope: ProjectionScope = "interaction_archive"
    elif is_timeline and not is_main:
        scope = "timeline"
    elif scope_hint == "interaction_archive":
        scope = "interaction_archive"
    elif scope_hint == "timeline":
        scope = "timeline"
    elif is_main or score >= 0.72:
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


def partition_claims(claims: list[MemoryClaim], *, main_claim_limit: int = 28) -> dict[ProjectionScope, list[ProjectedClaim]]:
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
    return qualifiers


def compact_record_qualifiers(
    item: ProjectedClaim, *, include_date: bool = False
) -> list[str]:
    qualifiers = compact_qualifiers(item.claim, include_date=include_date)
    if item.scope == "interaction_archive" and len(item.members) > 1:
        dates = sorted({claim_date_key(claim) for claim in item.members})
        qualifiers.append(f"repeated {len(item.members)} times")
        if len(dates) > 1:
            qualifiers.append(f"from {dates[0]} to {dates[-1]}")
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
