"""Display cleanup shared by fact materialization and manual curation."""

from __future__ import annotations

import re

from mycelium.artifacts import MemoryClaim, parse_source_datetime, temporal_record


def display_claim_text(claim: MemoryClaim) -> str:
    """Remove model-added calendar dates that conflict with normalized relative time."""
    text = claim.text.strip()
    temporal = temporal_record(claim.facets)
    when = str(temporal.get("expression") or "").strip() if temporal else ""
    normalized_date = str(temporal.get("start") or "") if temporal else ""
    if normalized_date and when.lower() in {"today", "yesterday", "tomorrow"}:
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
