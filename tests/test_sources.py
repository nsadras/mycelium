from datetime import datetime

from mycelium.models import LogEntry, WikiPage
from mycelium.sources import (
    select_source_snippets,
    source_context_for_page,
    source_contexts_for_pages,
)
from mycelium.store import LogStore


def test_source_context_for_page_uses_backlinked_logs(tmp_path):
    logs = LogStore(tmp_path / "logs")
    entry = LogEntry(
        entry_id="2026-05-10#session-abc123",
        session_id="ses-123",
        timestamp=datetime(2026, 5, 10, 10, 0, 0),
        content=(
            "Raw conversation transcript.\n\n"
            "[D1:1] Caroline: I adopted Pixel from Denver.\n"
            "[D1:2] Melanie: Pixel loves red toys."
        ),
        importance=0.8,
        status="raw",
        consolidated=False,
    )
    logs.append(entry)
    logs.mark_consolidated([entry.entry_id])

    page = WikiPage(
        slug="pixel",
        title="Pixel",
        content="Pixel is Caroline's pet.",
        created=datetime.now(),
        last_updated=datetime.now(),
        version=1,
        confidence=0.9,
        importance=0.8,
        source_log_entries=[entry.entry_id],
    )

    context = source_context_for_page(page, logs, "Where did Caroline adopt Pixel?")

    assert "SOURCE LOG SNIPPETS FOR [[pixel]]" in context
    assert "2026-05-10#session-abc123" in context
    assert "Caroline: I adopted Pixel from Denver." in context


def test_source_contexts_for_pages_deduplicates_logs_and_preserves_conversation_time(tmp_path):
    logs = LogStore(tmp_path / "logs")
    entry = LogEntry(
        entry_id="2026-07-20#session-abc123",
        session_id="session_1",
        timestamp=datetime(2026, 7, 20, 10, 0, 0),
        content=(
            "Raw conversation transcript.\n\n"
            "Timestamp: 4:04 pm on 20 January, 2023\n"
            "[D1:2] Jon: I lost my banker job yesterday."
        ),
        importance=0.8,
        status="raw",
        consolidated=False,
    )
    logs.append(entry)
    pages = [
        WikiPage(
            slug=slug,
            title=slug,
            content="Summary.",
            created=datetime.now(),
            last_updated=datetime.now(),
            version=1,
            confidence=0.9,
            importance=0.8,
            source_log_entries=[entry.entry_id],
        )
        for slug in ("person-jon", "dance-studio")
    ]

    contexts = source_contexts_for_pages(pages, logs, "When did Jon lose his banker job?")
    combined = "\n".join(contexts.values())

    assert combined.count(entry.entry_id) == 1
    assert "conversation_time=4:04 pm on 20 January, 2023" in combined
    assert "Jon: I lost my banker job yesterday." in combined


def test_source_ranking_uses_rare_terms_without_losing_named_entity_weight():
    entries = [
        LogEntry(
            entry_id="common", session_id="one", timestamp=datetime.now(),
            content="Gina discussed her store.\nGina discussed her weekly plans.",
            importance=0.8, status="raw",
        ),
        LogEntry(
            entry_id="specific", session_id="two", timestamp=datetime.now(),
            content="Gina mentioned Shia Labeouf during the interview.",
            importance=0.8, status="raw",
        ),
        LogEntry(
            entry_id="wrong-person", session_id="three", timestamp=datetime.now(),
            content="Jon mentioned Shia Labeouf during the interview.",
            importance=0.8, status="raw",
        ),
    ]

    snippets = select_source_snippets(
        entries, "When did Gina mention Shia Labeouf?", max_entries=3
    )

    assert snippets[0].entry_id == "specific"
    assert snippets[0].score > snippets[1].score


def test_source_snippets_respect_narrow_evidence_window():
    entry = LogEntry(
        entry_id="long", session_id="one", timestamp=datetime.now(),
        content="\n".join([
            "Gina discussed unrelated plans." * 10,
            "Gina mentioned Shia Labeouf during the interview.",
            "Jon discussed unrelated plans." * 10,
        ]),
        importance=0.8, status="raw",
    )

    snippet = select_source_snippets(
        [entry], "When did Gina mention Shia Labeouf?",
        max_entries=1, max_chars_per_entry=90,
    )[0]

    assert len(snippet.text) <= 90
    assert "Shia Labeouf" in snippet.text
