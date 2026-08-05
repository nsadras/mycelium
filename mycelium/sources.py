from __future__ import annotations

import re
from dataclasses import dataclass

from mycelium.models import LogEntry, WikiPage
from mycelium.store import LogStore


@dataclass
class SourceSnippet:
    entry_id: str
    session_id: str
    timestamp: str
    text: str
    score: int


def source_context_for_page(
    page: WikiPage,
    logs: LogStore,
    query: str,
    *,
    max_entries: int = 4,
    max_chars_per_entry: int = 1800,
) -> str:
    entries = logs.get_many(page.source_log_entries)
    snippets = select_source_snippets(
        entries,
        query,
        max_entries=max_entries,
        max_chars_per_entry=max_chars_per_entry,
    )
    if not snippets:
        return ""

    lines = [f"SOURCE LOG SNIPPETS FOR [[{page.slug}]]:"]
    for snippet in snippets:
        lines.append(
            f"- {snippet.entry_id} "
            f"(session={snippet.session_id or 'unknown'}, time={snippet.timestamp}, score={snippet.score})"
        )
        lines.append(_indent(snippet.text.strip()))
    return "\n".join(lines)


def source_contexts_for_pages(
    pages: list[WikiPage],
    logs: LogStore,
    query: str,
    *,
    max_entries: int = 6,
    max_chars_per_entry: int = 2200,
) -> dict[str, str]:
    """Select source evidence once across all loaded pages.

    Entity and topic pages often backlink the same conversation. Selecting sources
    independently for every page repeats long transcript windows, crowds out useful
    evidence, and gives small models several copies of the same fact. This function
    ranks unique logs globally, then attaches each selected snippet to one page.
    """
    owners: dict[str, str] = {}
    entries_by_id: dict[str, LogEntry] = {}
    for page in pages:
        for entry in logs.get_many(page.source_log_entries):
            entries_by_id.setdefault(entry.entry_id, entry)
            owners.setdefault(entry.entry_id, page.slug)

    snippets = select_source_snippets(
        list(entries_by_id.values()),
        query,
        max_entries=max_entries,
        max_chars_per_entry=max_chars_per_entry,
    )
    grouped: dict[str, list[SourceSnippet]] = {}
    for snippet in snippets:
        owner = owners.get(snippet.entry_id)
        if owner:
            grouped.setdefault(owner, []).append(snippet)

    contexts: dict[str, str] = {}
    for slug, page_snippets in grouped.items():
        lines = ["CANONICAL SOURCE LOG SNIPPETS (prefer these over wiki summaries):"]
        for snippet in page_snippets:
            lines.append(
                f"- {snippet.entry_id} "
                f"(session={snippet.session_id or 'unknown'}, conversation_time={snippet.timestamp}, "
                f"score={snippet.score})"
            )
            lines.append(_indent(snippet.text.strip()))
        contexts[slug] = "\n".join(lines)
    return contexts


def select_source_snippets(
    entries: list[LogEntry],
    query: str,
    *,
    max_entries: int = 4,
    max_chars_per_entry: int = 1800,
) -> list[SourceSnippet]:
    query_terms = _terms(query)
    ranked: list[SourceSnippet] = []

    for entry in entries:
        text, score = _best_window(entry.content, query_terms, max_chars=max_chars_per_entry)
        if not text:
            continue
        ranked.append(
            SourceSnippet(
                entry_id=entry.entry_id,
                session_id=entry.session_id,
                timestamp=_conversation_timestamp(entry.content)
                or entry.timestamp.isoformat(timespec="minutes"),
                text=text,
                score=score,
            )
        )

    ranked.sort(key=lambda item: (item.score, len(item.text)), reverse=True)
    return ranked[:max_entries]


def _best_window(content: str, query_terms: set[str], *, max_chars: int) -> tuple[str, int]:
    content = content.strip()
    if not content:
        return "", 0

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return _clip(content, max_chars), 0

    scored_lines = []
    for idx, line in enumerate(lines):
        line_terms = _terms(line)
        overlap = len(query_terms & line_terms)
        scored_lines.append((overlap, idx))

    best_score, best_idx = max(scored_lines, key=lambda item: item[0])
    selected = _window_around(lines, best_idx, max_chars=max_chars)
    if best_score > 0:
        return selected, best_score

    return _clip(content, max_chars), 0


def _window_around(lines: list[str], center_idx: int, *, max_chars: int) -> str:
    start = center_idx
    end = center_idx + 1
    current = lines[center_idx]

    while len(current) < max_chars and (start > 0 or end < len(lines)):
        expanded = False
        if start > 0:
            candidate = "\n".join([lines[start - 1], current])
            if len(candidate) <= max_chars:
                start -= 1
                current = candidate
                expanded = True
        if len(current) >= max_chars:
            break
        if end < len(lines):
            candidate = "\n".join([current, lines[end]])
            if len(candidate) <= max_chars:
                end += 1
                current = candidate
                expanded = True
        if not expanded:
            break

    return current


def _terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9'-]{2,}", text.lower())
        if token not in _STOPWORDS
    }


def _clip(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 12].rstrip() + "\n[truncated]"


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())


def _conversation_timestamp(text: str) -> str | None:
    match = re.search(r"^Timestamp:\s*(.+?)\s*$", text, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else None


_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "because",
    "but",
    "can",
    "did",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "her",
    "him",
    "his",
    "how",
    "into",
    "not",
    "that",
    "the",
    "their",
    "then",
    "there",
    "they",
    "this",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "you",
    "your",
}
