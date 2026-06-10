import pytest
from unittest.mock import AsyncMock, MagicMock
from mycelium.dream import DreamProcess
from mycelium.models import LogEntry, WikiPage
from mycelium.config import Config
from datetime import datetime

@pytest.fixture
def mock_llm():
    return AsyncMock()

@pytest.fixture
def mock_wiki():
    return MagicMock()

@pytest.fixture
def mock_logs():
    return MagicMock()

@pytest.fixture
def dream_process(mock_llm, mock_wiki, mock_logs):
    config = Config.defaults()
    return DreamProcess(mock_llm, mock_wiki, mock_logs, config)

@pytest.mark.asyncio
async def test_dream_process_run(dream_process, mock_llm, mock_wiki, mock_logs):
    # Setup state
    entry = LogEntry(
        entry_id="2026-05-10#Entry1",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="New experience",
        importance=0.8,
        status="raw"
    )
    mock_logs.get_unconsolidated.return_value = [entry]
    mock_wiki.get_index.return_value = "# Index"
    
    # LLM responses
    mock_llm.call_structured.side_effect = [
        # Identify
        [{"page": "project-notes", "action": "create"}, {"page": "existing-page", "action": "update"}],
        # Canonicalize
        {
            "mappings": [
                {"proposed_page": "project-notes", "action": "create_new", "canonical_page": "project-notes", "log_entry_ids": ["2026-05-10#Entry1"]},
                {"proposed_page": "existing-page", "action": "use_existing", "canonical_page": "existing-page", "log_entry_ids": ["2026-05-10#Entry1"]},
            ]
        },
        # Rewrite new
        {"title": "New Title", "content": "New content", "confidence": 0.8, "importance": 0.7},
        # Rewrite existing
        {"title": "Existing Title", "content": "Updated content", "confidence": 0.9, "importance": 0.8},
    ]
    
    mock_wiki.exists.side_effect = lambda slug: slug == "existing-page"
    
    existing = WikiPage(
        slug="existing-page", title="Existing", content="Old",
        created=datetime.now(), last_updated=datetime.now(),
        version=1, confidence=0.8, importance=0.5
    )
    mock_wiki.get.return_value = existing
    
    report = await dream_process.run(strategy="full", conflict_policy="override")
    
    assert report.pages_updated == 1
    assert report.pages_created == 1
    assert report.entries_consolidated == 1
    
    # Verify saves
    assert mock_wiki.save.call_count == 2
    saved_pages = [call.args[0] for call in mock_wiki.save.call_args_list]
    assert all("2026-05-10#Entry1" in page.source_log_entries for page in saved_pages)
    saved_index = mock_wiki.save_index.call_args.args[0]
    assert "[[project-notes]]" in saved_index
    assert "[[existing-page]]" in saved_index
    mock_logs.mark_consolidated.assert_called_once_with(["2026-05-10#Entry1"])


@pytest.mark.asyncio
async def test_dream_process_dedupes_duplicate_identification(dream_process, mock_llm, mock_wiki, mock_logs):
    entry = LogEntry(
        entry_id="2026-05-10#Entry1",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="New experience",
        importance=0.8,
        status="raw"
    )
    mock_logs.get_unconsolidated.return_value = [entry]
    mock_wiki.get_index.return_value = "# Index"
    mock_wiki.exists.return_value = False
    mock_wiki.list_all.return_value = []
    mock_llm.call_structured.side_effect = [
        [
            {"page": "RLHF", "action": "create"},
            {"page": "[[rlhf]]", "action": "create"},
            {"page": "rlhf.md", "action": "create"},
        ],
        {"title": "RLHF", "content": "One page", "confidence": 0.8, "importance": 0.7},
    ]

    report = await dream_process.run(strategy="full", conflict_policy="override")

    assert report.pages_created == 1
    assert mock_wiki.save.call_count == 1


@pytest.mark.asyncio
async def test_dream_identification_splits_failed_raw_log_batch(dream_process, mock_llm):
    entry1 = LogEntry(
        entry_id="2026-05-10#session-1",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="A" * 4000,
        importance=0.8,
        status="raw",
    )
    entry2 = LogEntry(
        entry_id="2026-05-10#session-2",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="B" * 4000,
        importance=0.8,
        status="raw",
    )
    mock_llm.call_structured.side_effect = [
        ValueError("bad json"),
        [{"page": "caroline-profile", "action": "create", "log_entry_ids": [entry1.entry_id]}],
        [{"page": "melanie-profile", "action": "create", "log_entry_ids": [entry2.entry_id]}],
    ]

    targets = await dream_process._identify_targets_for_chunk("# Index", [entry1, entry2])

    assert [target["page"] for target in targets] == ["caroline-profile", "melanie-profile"]
    assert mock_llm.call_structured.call_count == 3


@pytest.mark.asyncio
async def test_dream_identification_splits_failed_single_long_raw_log(dream_process, mock_llm):
    entry = LogEntry(
        entry_id="2026-06-09#session-b7ce924b",
        session_id="session_1",
        timestamp=datetime.now(),
        content="\n\n".join(
            [
                "Raw conversation transcript.",
                "speaker_a: Caroline talks about pottery and running." * 80,
                "speaker_b: Melanie discusses Paris travel plans." * 80,
            ]
        ),
        importance=0.8,
        status="raw",
    )
    mock_llm.call_structured.return_value = [
        {"page": "caroline-profile", "action": "create", "log_entry_ids": [entry.entry_id]}
    ]

    targets = await dream_process._identify_targets_for_chunk("# Index", [entry])

    assert targets
    assert all(target["log_entry_ids"] == [entry.entry_id] for target in targets)
    assert mock_llm.call_structured.call_count >= 1
    first_prompt = mock_llm.call_structured.call_args_list[0][0][1]
    assert "Excerpt 1/" in first_prompt
    assert entry.entry_id in first_prompt
    assert "session-b7ce924b-1" not in first_prompt


@pytest.mark.asyncio
async def test_dream_process_merges_same_title_creates(dream_process, mock_llm, mock_wiki, mock_logs):
    entry = LogEntry(
        entry_id="2026-05-10#Entry1",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="New experience",
        importance=0.8,
        status="raw"
    )
    mock_logs.get_unconsolidated.return_value = [entry]
    mock_wiki.get_index.return_value = "# Index"
    mock_wiki.list_all.return_value = []
    saved_pages = {}

    def exists(slug):
        return slug in saved_pages

    def save(page):
        saved_pages[page.slug] = page

    def get(slug):
        return saved_pages[slug]

    mock_wiki.exists.side_effect = exists
    mock_wiki.save.side_effect = save
    mock_wiki.get.side_effect = get
    mock_llm.call_structured.side_effect = [
        [
            {"page": "rlhf", "action": "create"},
            {"page": "dpo", "action": "create"},
        ],
        {
            "mappings": [
                {"proposed_page": "rlhf", "action": "create_new", "canonical_page": "rlhf", "log_entry_ids": []},
                {"proposed_page": "dpo", "action": "create_new", "canonical_page": "dpo", "log_entry_ids": []},
            ]
        },
        {"title": "Reinforcement Learning and Cognitive Modeling", "content": "First", "confidence": 0.8, "importance": 0.7},
        {"title": "Reinforcement Learning and Cognitive Modeling", "content": "Second", "confidence": 0.85, "importance": 0.75},
    ]

    report = await dream_process.run(strategy="full", conflict_policy="override")

    assert report.pages_created == 1
    assert report.pages_updated == 1
    assert list(saved_pages) == ["rlhf"]
    assert saved_pages["rlhf"].content == "Second"


@pytest.mark.asyncio
async def test_dream_process_fork_on_actual_contradiction(dream_process, mock_llm, mock_wiki, mock_logs):
    entry = LogEntry(
        entry_id="2026-05-10#Entry1",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="Contradictory experience",
        importance=0.8,
        status="raw"
    )
    mock_logs.get_unconsolidated.return_value = [entry]
    mock_wiki.get_index.return_value = "# Index"
    mock_wiki.list_all.return_value = []
    
    saved_pages = {}
    def exists(slug):
        return slug in saved_pages or slug == "existing-page"
    def save(page):
        saved_pages[page.slug] = page
    mock_wiki.exists.side_effect = exists
    mock_wiki.save.side_effect = save

    existing = WikiPage(
        slug="existing-page", title="Existing", content="Original content",
        created=datetime.now(), last_updated=datetime.now(),
        version=1, confidence=0.8, importance=0.5
    )
    mock_wiki.get.return_value = existing

    # LLM calls:
    # 1. Identify
    # 2. Rewrite
    # 3. Prediction Error check (returns contradiction!)
    mock_llm.call_structured.side_effect = [
        [{"page": "existing-page", "action": "update"}],
        {"title": "Existing Title", "content": "Updated contradictory content", "confidence": 0.9, "importance": 0.8},
        {"conflict_type": "major", "discrepancy_score": 0.8, "explanation": "Strong contradiction detected", "suggested_update": None},
    ]

    report = await dream_process.run(strategy="full", conflict_policy="fork")

    assert report.pages_created == 1
    assert report.pages_updated == 1
    assert report.conflicts_resolved == 1
    assert report.conflicts_found == ["existing-page"]
    
    # We should have a fork page saved
    fork_slug = [k for k in saved_pages.keys() if k.startswith("existing-page-fork-")][0]
    fork_page = saved_pages[fork_slug]
    assert fork_page.content == "Updated contradictory content"
    assert fork_page.title == "Existing Title (Fork)"
    assert any(edge.target == "existing-page" and edge.relation == "contradicts" for edge in fork_page.related)
    
    # Existing page should have a reference to the fork, and lower confidence
    assert existing.confidence == pytest.approx(0.7) # 0.8 - 0.1
    assert any(edge.target == fork_slug and edge.relation == "contradicts" for edge in existing.related)


@pytest.mark.asyncio
async def test_dream_process_override_on_non_contradiction(dream_process, mock_llm, mock_wiki, mock_logs):
    entry = LogEntry(
        entry_id="2026-05-10#Entry1",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="Additive experience",
        importance=0.8,
        status="raw"
    )
    mock_logs.get_unconsolidated.return_value = [entry]
    mock_wiki.get_index.return_value = "# Index"
    mock_wiki.list_all.return_value = []
    
    saved_pages = {}
    def exists(slug):
        return slug in saved_pages or slug == "existing-page"
    def save(page):
        saved_pages[page.slug] = page
    mock_wiki.exists.side_effect = exists
    mock_wiki.save.side_effect = save

    existing = WikiPage(
        slug="existing-page", title="Existing", content="Original content",
        created=datetime.now(), last_updated=datetime.now(),
        version=1, confidence=0.8, importance=0.5
    )
    mock_wiki.get.return_value = existing

    # LLM calls:
    # 1. Identify
    # 2. Rewrite
    # 3. Prediction Error check (returns non-contradiction / additive!)
    mock_llm.call_structured.side_effect = [
        [{"page": "existing-page", "action": "update"}],
        {"title": "Existing Title", "content": "Updated additive content", "confidence": 0.9, "importance": 0.8},
        {"conflict_type": "additive", "discrepancy_score": 0.2, "explanation": "Compatible additive update", "suggested_update": None},
    ]

    report = await dream_process.run(strategy="full", conflict_policy="fork")

    # Should NOT have created a fork page, just updated existing-page in place!
    assert report.pages_created == 0
    assert report.pages_updated == 1
    assert report.conflicts_resolved == 0
    assert report.conflicts_found == []
    
    assert not any(k.startswith("existing-page-fork-") for k in saved_pages.keys())
    assert existing.content == "Updated additive content"
    assert existing.confidence == 0.9
    assert existing.version == 2


@pytest.mark.asyncio
async def test_dream_process_precise_log_routing(dream_process, mock_llm, mock_wiki, mock_logs):
    # 1. Setup two distinct unconsolidated log entries
    entry1 = LogEntry(
        entry_id="2026-05-10#Entry1",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="Technical ReAct agent loop implementation details",
        importance=0.8,
        status="raw"
    )
    entry2 = LogEntry(
        entry_id="2026-05-10#Entry2",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="User likes dark forest green styling and HSL obsidian panels",
        importance=0.9,
        status="raw"
    )
    mock_logs.get_unconsolidated.return_value = [entry1, entry2]
    mock_wiki.get_index.return_value = "# Index"
    mock_wiki.exists.return_value = False
    mock_wiki.list_all.return_value = []
    
    saved_pages = {}
    def save(page):
        saved_pages[page.slug] = page
    mock_wiki.save.side_effect = save

    # 2. LLM response mocks
    # First: Identify returns pages mapping to specific log entry IDs
    # Second & Third: Rewrite outputs
    mock_llm.call_structured.side_effect = [
        # Identify pass maps each page to a specific log entry ID!
        [
            {"page": "react-loop", "action": "create", "log_entry_ids": ["2026-05-10#Entry1"]},
            {"page": "user-profile", "action": "create", "log_entry_ids": ["2026-05-10#Entry2"]}
        ],
        {
            "mappings": [
                {"proposed_page": "react-loop", "action": "create_new", "canonical_page": "react-loop", "log_entry_ids": ["2026-05-10#Entry1"]},
                {"proposed_page": "user-profile", "action": "create_new", "canonical_page": "user-profile", "log_entry_ids": ["2026-05-10#Entry2"]},
            ]
        },
        # Rewrite for react-loop
        {"title": "ReAct Loop", "content": "ReAct loop notes", "confidence": 0.9, "importance": 0.8},
        # Rewrite for user-profile
        {"title": "User Profile", "content": "Obsidian style preference", "confidence": 0.95, "importance": 0.9},
    ]

    report = await dream_process.run(strategy="full", conflict_policy="override")

    assert report.pages_created == 2
    assert report.entries_consolidated == 2

    # Verify that the correct specific log entry content was fed to the rewrite calls
    # Call 0 is Identify, Call 1 is Canonicalize, Call 2 is Rewrite react-loop, Call 3 is Rewrite user-profile
    calls = mock_llm.call_structured.call_args_list
    assert len(calls) == 4

    # Call 2 (react-loop rewrite) should receive only entry1 content, NOT entry2 content
    react_loop_rewrite_user_prompt = calls[2][0][1] # (system, user, output_class) -> user prompt is index 1
    assert "Technical ReAct agent loop" in react_loop_rewrite_user_prompt
    assert "User likes dark forest green" not in react_loop_rewrite_user_prompt

    # Call 3 (user-profile rewrite) should receive only entry2 content, NOT entry1 content
    user_profile_rewrite_user_prompt = calls[3][0][1]
    assert "User likes dark forest green" in user_profile_rewrite_user_prompt
    assert "Technical ReAct agent loop" not in user_profile_rewrite_user_prompt

    # Verify saved page source links are also precisely isolated!
    assert "react-loop" in saved_pages
    assert "user-profile" in saved_pages
    assert saved_pages["react-loop"].source_log_entries == ["2026-05-10#Entry1"]
    assert saved_pages["user-profile"].source_log_entries == ["2026-05-10#Entry2"]


@pytest.mark.asyncio
async def test_dream_process_passes_page_type_to_rewrite_and_tags_page(
    dream_process,
    mock_llm,
    mock_wiki,
    mock_logs,
):
    entry = LogEntry(
        entry_id="2026-05-10#Entry1",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="Melanie painted a lake sunrise last year.",
        importance=0.9,
        status="raw",
    )
    mock_logs.get_unconsolidated.return_value = [entry]
    mock_wiki.get_index.return_value = "# Index"
    mock_wiki.exists.return_value = False
    mock_wiki.list_all.return_value = []

    saved_pages = {}
    mock_wiki.save.side_effect = lambda page: saved_pages.setdefault(page.slug, page)
    mock_llm.call_structured.side_effect = [
        [
            {
                "page": "person-melanie",
                "action": "create",
                "page_type": "entity",
                "log_entry_ids": ["2026-05-10#Entry1"],
            }
        ],
        {
            "title": "Melanie",
            "content": "Melanie painted a lake sunrise last year.",
            "tags": ["person"],
            "confidence": 0.9,
            "importance": 0.8,
        },
    ]

    report = await dream_process.run(strategy="full", conflict_policy="override")

    assert report.pages_created == 1
    rewrite_call = mock_llm.call_structured.call_args_list[1]
    rewrite_system_prompt = rewrite_call[0][0]
    assert "slug=`person-melanie`" in rewrite_system_prompt
    assert "page_type=`entity`" in rewrite_system_prompt
    assert rewrite_call.kwargs["num_predict"] == 8192
    assert rewrite_call.kwargs["dump_success"] is True
    assert rewrite_call.kwargs["debug_label"] == "wiki-rewrite-person-melanie"
    assert saved_pages["person-melanie"].tags == ["person", "page-type-entity"]


@pytest.mark.asyncio
async def test_dream_process_canonicalizes_same_pass_near_duplicates(dream_process, mock_llm, mock_wiki, mock_logs):
    entry1 = LogEntry(
        entry_id="2026-05-10#Entry1",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="The user wants local LLM model selection criteria for 4B-8B models.",
        importance=0.8,
        status="raw",
    )
    entry2 = LogEntry(
        entry_id="2026-05-10#Entry2",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="The user needs a deployment strategy for quantized local LLMs on consumer GPUs.",
        importance=0.9,
        status="raw",
    )
    mock_logs.get_unconsolidated.return_value = [entry1, entry2]
    mock_wiki.get_index.return_value = "# Index"
    mock_wiki.exists.return_value = False
    mock_wiki.list_all.return_value = []

    saved_pages = {}
    mock_wiki.save.side_effect = lambda page: saved_pages.setdefault(page.slug, page)
    mock_llm.call_structured.side_effect = [
        [
            {"page": "llm-selection", "action": "create", "log_entry_ids": ["2026-05-10#Entry1"]},
            {"page": "local-llm-deployment", "action": "create", "log_entry_ids": ["2026-05-10#Entry2"]},
        ],
        {
            "mappings": [
                {
                    "proposed_page": "llm-selection",
                    "action": "create_new",
                    "canonical_page": "llm-deployment-strategy",
                    "log_entry_ids": ["2026-05-10#Entry1"],
                },
                {
                    "proposed_page": "local-llm-deployment",
                    "action": "create_new",
                    "canonical_page": "llm-deployment-strategy",
                    "log_entry_ids": ["2026-05-10#Entry2"],
                },
            ]
        },
        {
            "title": "LLM Deployment Strategy",
            "content": "Local model selection and deployment strategy.",
            "confidence": 0.9,
            "importance": 0.9,
        },
    ]

    report = await dream_process.run(strategy="full", conflict_policy="override")

    assert report.pages_created == 1
    assert report.pages_updated == 0
    assert set(saved_pages) == {"llm-deployment-strategy"}
    assert saved_pages["llm-deployment-strategy"].source_log_entries == [
        "2026-05-10#Entry1",
        "2026-05-10#Entry2",
    ]
    rewrite_prompt = mock_llm.call_structured.call_args_list[2][0][1]
    assert "4B-8B models" in rewrite_prompt
    assert "consumer GPUs" in rewrite_prompt


@pytest.mark.asyncio
async def test_dream_process_extracts_tool_facts_before_identification(dream_process, mock_llm, mock_wiki, mock_logs):
    entry = LogEntry(
        entry_id="2026-05-10#tool-abc123",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="Tool observation from chat.\n\n## Navigation\n\nResult: Library X version 2.0 adds frobnicate().",
        importance=0.5,
        status="raw",
        durability="durable",
    )
    mock_logs.get_unconsolidated.return_value = [entry]
    mock_wiki.get_index.return_value = "# Index"
    mock_wiki.exists.return_value = False
    mock_wiki.list_all.return_value = []

    saved_pages = {}
    mock_wiki.save.side_effect = lambda page: saved_pages.setdefault(page.slug, page)
    mock_llm.call_structured.side_effect = [
        {
            "source_tool_entry_id": "2026-05-10#tool-abc123",
            "tool_name": "web_search",
            "query_or_url": "Library X",
            "facts": [
                {
                    "fact": "Library X version 2.0 adds frobnicate().",
                    "confidence": 0.9,
                    "recommended_memory_scope": "durable",
                    "suggested_topics": ["library-x"],
                },
                {
                    "fact": "Navigation heading",
                    "confidence": 0.2,
                    "recommended_memory_scope": "ignore",
                    "suggested_topics": [],
                },
            ],
            "discarded_noise": ["Navigation"],
        },
        [{"page": "library-x", "action": "create", "log_entry_ids": ["2026-05-10#tool-abc123"]}],
        {"title": "Library X", "content": "Library X version 2.0 adds frobnicate().", "confidence": 0.9, "importance": 0.8},
    ]

    report = await dream_process.run(strategy="full", conflict_policy="override")

    assert report.pages_created == 1
    calls = mock_llm.call_structured.call_args_list
    identify_prompt = calls[1][0][1]
    assert "Library X version 2.0 adds frobnicate()." in identify_prompt
    assert "## Navigation" not in identify_prompt
    mock_logs.mark_consolidated.assert_called_once_with(["2026-05-10#tool-abc123"])


@pytest.mark.asyncio
async def test_dream_process_skips_session_durability_entries(dream_process, mock_llm, mock_wiki, mock_logs):
    entry = LogEntry(
        entry_id="2026-05-10#Entry1",
        session_id="ses-123",
        timestamp=datetime.now(),
        content="User has a temporary cold today.",
        importance=0.9,
        status="raw",
        durability="session",
    )
    mock_logs.get_unconsolidated.return_value = [entry]

    report = await dream_process.run(strategy="full", conflict_policy="override")

    assert report.pages_created == 0
    assert report.pages_updated == 0
    assert report.entries_consolidated == 1
    mock_llm.call_structured.assert_not_called()
    mock_logs.mark_consolidated.assert_called_once_with(["2026-05-10#Entry1"])
