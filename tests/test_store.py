import pytest
from datetime import datetime
from pathlib import Path
from mycelium.models import WikiPage, LogEntry, Edge, UpdateLogEntry
from mycelium.store import WikiStore, LogStore

def test_wiki_store_save_and_get(tmp_path):
    store = WikiStore(tmp_path / "wiki")
    
    page = WikiPage(
        slug="test-page",
        title="Test Page",
        content="This is the content.",
        created=datetime(2026, 5, 10, 10, 0, 0),
        last_updated=datetime(2026, 5, 10, 10, 0, 0),
        version=1,
        confidence=0.9,
        importance=0.8,
        retrievability=0.95,
        tags=["test"],
        related=[Edge(target="other-page", relation="causes", weight=0.5)],
        update_log=[
            UpdateLogEntry(
                version=1,
                date=datetime(2026, 5, 10, 10, 0, 0),
                session_id="ses-123",
                trigger="manual",
                discrepancy_score=0.0,
                reason="Initial creation",
                previous_confidence=0.0,
                new_confidence=0.9
            )
        ]
    )
    
    store.save(page)
    
    loaded = store.get("test-page")
    assert loaded.slug == "test-page"
    assert loaded.title == "Test Page"
    assert loaded.content == "This is the content."
    assert loaded.version == 1
    assert loaded.confidence == 0.9
    assert len(loaded.related) == 1
    assert loaded.related[0].target == "other-page"
    assert len(loaded.update_log) == 1
    assert loaded.update_log[0].session_id == "ses-123"

def test_wiki_store_list_all(tmp_path):
    store = WikiStore(tmp_path / "wiki")
    
    store.save(WikiPage(slug="page1", title="1", content="", created=datetime.now(), last_updated=datetime.now(), version=1, confidence=1.0, importance=1.0))
    store.save(WikiPage(slug="page2", title="2", content="", created=datetime.now(), last_updated=datetime.now(), version=1, confidence=1.0, importance=1.0))
    store.save_index("# Index")
    
    pages = store.list_all()
    assert len(pages) == 2
    slugs = [p.slug for p in pages]
    assert "page1" in slugs
    assert "page2" in slugs

def test_wiki_store_archive(tmp_path):
    store = WikiStore(tmp_path / "wiki")
    store.save(WikiPage(slug="archive-me", title="A", content="", created=datetime.now(), last_updated=datetime.now(), version=1, confidence=1.0, importance=1.0))
    assert store.exists("archive-me")
    store.archive("archive-me")
    assert not store.exists("archive-me")
    assert (tmp_path / "wiki" / "_archive" / "archive-me.md").exists()

def test_wiki_store_labile(tmp_path):
    store = WikiStore(tmp_path / "wiki")
    store.save(WikiPage(slug="labile-page", title="L", content="", created=datetime.now(), last_updated=datetime.now(), version=1, confidence=1.0, importance=1.0))
    
    store.mark_labile("labile-page", "ses-123")
    assert (tmp_path / "labile" / "labile-page.ses-123.md").exists()
    page = store.get("labile-page")
    assert page.labile
    assert page.labile_session == "ses-123"
    
    store.resolve_labile("labile-page", "ses-123")
    assert not (tmp_path / "labile" / "labile-page.ses-123.md").exists()
    page = store.get("labile-page")
    assert not page.labile
    assert page.labile_session is None

def test_log_store_append_and_get(tmp_path):
    store = LogStore(tmp_path / "logs")
    
    entry = LogEntry(
        entry_id="2026-05-10#Entry 1",
        session_id="ses-123",
        timestamp=datetime(2026, 5, 10, 10, 0, 0),
        content="User said hello.",
        importance=0.5,
        status="raw",
        durability="durable",
        consolidated=False,
        decay_score=1.0
    )
    
    store.append(entry)
    
    unconsolidated = store.get_unconsolidated()
    assert len(unconsolidated) == 1
    assert unconsolidated[0].content == "User said hello."
    assert unconsolidated[0].session_id == "ses-123"
    assert unconsolidated[0].durability == "durable"
    assert not unconsolidated[0].consolidated

def test_log_store_mark_consolidated(tmp_path):
    store = LogStore(tmp_path / "logs")
    
    entry = LogEntry(
        entry_id="2026-05-10#Entry 1",
        session_id="ses-123",
        timestamp=datetime(2026, 5, 10, 10, 0, 0),
        content="User said hello.",
        importance=0.5,
        status="raw",
        consolidated=False,
        decay_score=1.0
    )
    
    store.append(entry)
    store.mark_consolidated(["2026-05-10#Entry 1"])
    
    unconsolidated = store.get_unconsolidated()
    assert len(unconsolidated) == 0


def test_log_store_markdown_headings_inside_body_are_not_entries(tmp_path):
    store = LogStore(tmp_path / "logs")

    entry = LogEntry(
        entry_id="2026-05-10#tool-abc123",
        session_id="ses-123",
        timestamp=datetime(2026, 5, 10, 10, 0, 0),
        content=(
            "Tool observation from chat.\n\n"
            "## Submission history\n\n"
            "This heading is part of the tool result.\n\n"
            "---\n\n"
            "## Access Paper:\n\n"
            "This is also body content, not a new log entry."
        ),
        importance=0.5,
        status="raw",
        durability="durable",
        consolidated=False,
        decay_score=1.0,
    )

    store.append(entry)
    unconsolidated = store.get_unconsolidated()

    assert len(unconsolidated) == 1
    assert unconsolidated[0].entry_id == "2026-05-10#tool-abc123"
    assert "## Submission history" in unconsolidated[0].content
    assert "## Access Paper:" in unconsolidated[0].content

    store.mark_consolidated(["2026-05-10#tool-abc123"])
    assert store.get_unconsolidated() == []

def test_log_store_update_decay(tmp_path):
    store = LogStore(tmp_path / "logs")
    
    entry = LogEntry(
        entry_id="2026-05-10#Entry 1",
        session_id="ses-123",
        timestamp=datetime(2026, 5, 10, 10, 0, 0),
        content="User said hello.",
        importance=0.5,
        status="raw",
        consolidated=False,
        decay_score=1.0
    )
    
    store.append(entry)
    store.update_decay("2026-05-10#Entry 1", 0.75)
    
    unconsolidated = store.get_unconsolidated()
    assert len(unconsolidated) == 1
    assert unconsolidated[0].decay_score == 0.75

def test_mycelium_init_seeds_user_profile(tmp_path):
    from mycelium.core import Mycelium
    
    myc = Mycelium(store_path=tmp_path)
    
    assert myc.wiki.exists("user-profile")
    
    page = myc.wiki.get("user-profile")
    assert page.title == "User Profile"
    assert page.pinned
    assert page.confidence == 0.8
    assert "profile" in page.tags
    
    index_content = myc.wiki.get_index()
    assert "[[user-profile]]" in index_content

def test_log_store_mark_unconsolidated(tmp_path):
    store = LogStore(tmp_path / "logs")
    
    entry = LogEntry(
        entry_id="2026-05-10#Entry 1",
        session_id="ses-123",
        timestamp=datetime(2026, 5, 10, 10, 0, 0),
        content="User said hello.",
        importance=0.5,
        status="raw",
        consolidated=False,
        decay_score=1.0
    )
    
    store.append(entry)
    # Initially unconsolidated
    assert len(store.get_unconsolidated()) == 1
    
    # Mark consolidated
    store.mark_consolidated(["2026-05-10#Entry 1"])
    assert len(store.get_unconsolidated()) == 0
    
    # Mark unconsolidated
    store.mark_unconsolidated("2026-05-10")
    unconsolidated = store.get_unconsolidated()
    assert len(unconsolidated) == 1
    assert unconsolidated[0].entry_id == "2026-05-10#Entry 1"
    assert not unconsolidated[0].consolidated

def test_clear_wiki_store(tmp_path, monkeypatch):
    from mycelium.core import Mycelium
    from server.runtime import clear_wiki_store
    
    myc = Mycelium(store_path=tmp_path)
    monkeypatch.setattr("server.runtime.get_mem", lambda: myc)
    
    # Create consolidated log entry
    from mycelium.models import LogEntry
    entry = LogEntry(
        entry_id="2026-05-10#Entry 1",
        session_id="ses-123",
        timestamp=datetime(2026, 5, 10, 10, 0, 0),
        content="User said hello.",
        importance=0.5,
        status="raw",
        consolidated=True,
        decay_score=1.0
    )
    myc.log_store.append(entry)
    assert len(myc.log_store.get_unconsolidated()) == 0
    
    from mycelium.models import WikiPage
    myc.wiki.save(WikiPage(slug="page-a", title="Page A", content="", created=datetime.now(), last_updated=datetime.now(), version=1, confidence=1.0, importance=1.0))
    myc.wiki.save(WikiPage(slug="page-b", title="Page B", content="", created=datetime.now(), last_updated=datetime.now(), version=1, confidence=1.0, importance=1.0))
    myc.wiki.save_index("# Wiki Index\n\n## Pages\n- [[user-profile]]\n- [[page-a]]\n- [[page-b]]")
    
    assert myc.wiki.exists("page-a")
    assert myc.wiki.exists("page-b")
    assert myc.wiki.exists("user-profile")
    
    clear_wiki_store()
    
    assert not myc.wiki.exists("page-a")
    assert not myc.wiki.exists("page-b")
    assert myc.wiki.exists("user-profile")
    
    index_content = myc.wiki.get_index()
    assert "[[user-profile]]" in index_content
    assert "[[page-a]]" not in index_content
    assert "[[page-b]]" not in index_content
    
    # Logs should be automatically marked as unconsolidated!
    unconsolidated = myc.log_store.get_unconsolidated()
    assert len(unconsolidated) == 1
    assert not unconsolidated[0].consolidated

@pytest.mark.asyncio
async def test_delete_individual_wiki_page_api(tmp_path, monkeypatch):
    from mycelium.core import Mycelium
    from server.api.memory import delete_wiki_page
    
    myc = Mycelium(store_path=tmp_path)
    monkeypatch.setattr("server.api.memory.get_mem", lambda: myc)
    
    from mycelium.models import WikiPage
    myc.wiki.save(WikiPage(slug="target-page", title="Target", content="", created=datetime.now(), last_updated=datetime.now(), version=1, confidence=1.0, importance=1.0))
    myc.wiki.save_index("# Wiki Index\n\n## Pages\n- [[user-profile]]\n- [[target-page]]")
    
    assert myc.wiki.exists("target-page")
    
    await delete_wiki_page("target-page")
    
    assert not myc.wiki.exists("target-page")
    
    index_content = myc.wiki.get_index()
    assert "[[target-page]]" not in index_content
    assert "[[user-profile]]" in index_content
