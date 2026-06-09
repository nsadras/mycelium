from datetime import datetime

from mycelium.models import LogEntry, WikiPage
from mycelium.sources import source_context_for_page
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
