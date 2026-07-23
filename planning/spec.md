# Mycelium — Developer Spec
## For use with Claude Code / Cursor

This document is the implementation spec for **Mycelium** (internally: Mycelium), a neurobiologically-inspired agent memory library. Use it as the authoritative reference for all implementation decisions. When in doubt, refer back here.

---

## 0. Before You Start

### Verify Ollama is running
```bash
ollama list          # should show at least one model
ollama pull gemma3:12b   # pull default model if not present
curl http://localhost:11434/api/tags  # confirm API is up
```

### Python version
Requires Python 3.11+. Use `pyproject.toml` for packaging, not `setup.py`.

---

## 1. Repo Structure

Create this layout from scratch. Do not deviate.

```
mycelium/
│
├── mycelium/                  # library source
│   ├── __init__.py            # public API exports
│   ├── core.py                # Mycelium main client class
│   ├── session.py             # Session context manager
│   ├── store.py               # File store read/write (WikiStore, LogStore)
│   ├── ollama.py              # Ollama HTTP client wrapper
│   ├── encoder.py             # Encoding process
│   ├── dream.py               # Dream / consolidation process
│   ├── reconsolidation.py     # Reconsolidation + lability window
│   ├── budget.py              # Token budget / context window manager
│   ├── models.py              # Dataclasses: WikiPage, LogEntry, etc.
│   ├── prompts.py             # All LLM prompt templates (single source of truth)
│   └── config.py              # Config loading from mycelium.toml
│
├── tests/
│   ├── conftest.py            # shared fixtures
│   ├── test_store.py
│   ├── test_encoder.py
│   ├── test_dream.py
│   ├── test_reconsolidation.py
│   └── test_session.py
│
├── examples/
│   ├── basic_session.py       # minimal working example
│   └── langgraph_integration.py
│
├── pyproject.toml
├── README.md
└── mycelium.toml                # default config (copied to store on init)
```

---

## 2. Dependencies

`pyproject.toml` dependencies — keep this list short, no framework bloat:

```toml
[project]
name = "mycelium-memory"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",          # Ollama HTTP client
    "pyyaml>=6.0",          # frontmatter parsing
    "python-frontmatter>=1.1",  # markdown + YAML frontmatter
    "tiktoken>=0.7",        # token counting (model-agnostic)
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.12",
    "ruff",
    "mypy",
]
```

Do not add LangChain, LangGraph, numpy, sentence-transformers, chromadb, or any vector/graph DB dependency.

---

## 3. Data Models (`models.py`)

Define all dataclasses here. These are the canonical data structures — everything else works with these.

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

@dataclass
class Edge:
    target: str                          # slug of target wiki page
    relation: Literal[
        'causes', 'contradicts', 'exemplifies',
        'generalizes', 'precedes', 'enables', 'informs'
    ]
    weight: float = 1.0

@dataclass
class UpdateLogEntry:
    version: int
    date: datetime
    session_id: str
    trigger: Literal['reconsolidation', 'dream', 'manual']
    discrepancy_score: float
    reason: str
    previous_confidence: float
    new_confidence: float

@dataclass
class WikiPage:
    slug: str                            # filename without .md
    title: str
    content: str                         # full markdown body (no frontmatter)
    created: datetime
    last_updated: datetime
    version: int
    confidence: float                    # 0.0–1.0
    importance: float                    # 0.0–1.0
    tags: list[str] = field(default_factory=list)
    related: list[Edge] = field(default_factory=list)
    source_log_entries: list[str] = field(default_factory=list)
    labile: bool = False
    labile_session: Optional[str] = None
    update_log: list[UpdateLogEntry] = field(default_factory=list)

    # Set after retrieval, not stored on disk
    was_flagged: bool = field(default=False, repr=False)
    discrepancy_score: float = field(default=0.0, repr=False)
    discrepancy_explanation: str = field(default='', repr=False)

@dataclass
class LogEntry:
    entry_id: str                        # e.g. "2026-05-10#entry-1"
    session_id: str
    timestamp: datetime
    content: str
    importance: float
    tags: list[str]
    status: Literal['raw', 'consolidated', 'archived']
    consolidated: bool = False

@dataclass
class PredictionError:
    conflict_type: Literal['none', 'additive', 'partial', 'major']
    discrepancy_score: float             # 0.0–1.0
    explanation: str
    suggested_update: Optional[str]

@dataclass
class DreamReport:
    pages_updated: int
    pages_created: int
    entries_consolidated: int
    conflicts_found: list[str]           # page slugs
    conflicts_resolved: int

@dataclass
class MemoryResult:
    page: WikiPage
    load_priority: int
    tokens_used: int
```

---

## 4. File Store (`store.py`)

The store is the only module that reads and writes files. All other modules go through the store — never call `open()` directly anywhere else.

### WikiStore

```python
class WikiStore:
    def __init__(self, wiki_dir: Path): ...

    def get(self, slug: str) -> WikiPage: ...
    # raises FileNotFoundError if not found

    def save(self, page: WikiPage) -> None: ...
    # writes frontmatter + body to wiki/<slug>.md
    # creates file if new, overwrites if exists

    def list_all(self) -> list[WikiPage]: ...
    # reads all .md files in wiki/ (not _archive/)
    # excludes _index.md

    def get_index(self) -> str: ...
    # returns raw content of _index.md as string

    def save_index(self, content: str) -> None: ...

    def archive(self, slug: str) -> None: ...
    # moves wiki/<slug>.md → wiki/_archive/<slug>.md

    def mark_labile(self, slug: str, session_id: str) -> None: ...
    # copies wiki/<slug>.md → labile/<slug>.<session_id>.md
    # updates page frontmatter: labile=true, labile_session=session_id

    def resolve_labile(self, slug: str, session_id: str) -> None: ...
    # removes labile/<slug>.<session_id>.md
    # updates page frontmatter: labile=false, labile_session=null

    def exists(self, slug: str) -> bool: ...
```

### LogStore

```python
class LogStore:
    def __init__(self, logs_dir: Path): ...

    def append(self, entry: LogEntry) -> None: ...
    # appends to logs/YYYY-MM-DD.md (today's date)
    # creates file with header if it doesn't exist

    def get_unconsolidated(self, days: int = 7) -> list[LogEntry]: ...
    # returns all entries with consolidated=False from last N days

    def mark_consolidated(self, entry_ids: list[str]) -> None: ...
    # sets consolidated=True in the log file for given entry IDs

```

### Frontmatter convention

Use `python-frontmatter` for all file parsing. The YAML frontmatter schema matches the `WikiPage` dataclass exactly. Serialize `datetime` as ISO 8601. Serialize `list[Edge]` as:

```yaml
related:
  - target: other-page
    relation: contradicts
    weight: 0.6
```

---

## 5. Ollama Client (`ollama.py`)

Single HTTP client for all LLM calls. Everything goes through here.

```python
import httpx
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(self, url: str, model: str, temperature: float = 0.2, timeout: int = 120):
        self.url = url
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self._call_log: list[dict] = []   # in-memory log for debugging

    async def call(
        self,
        system: str,
        user: str,
        expect_json: bool = False,
        max_retries: int = 3,
    ) -> str | dict:
        """
        Makes a single chat completion call to Ollama.

        If expect_json=True:
          - Appends "Respond with valid JSON only. No markdown, no explanation."
            to the system prompt.
          - Parses response as JSON.
          - Retries up to max_retries times on parse failure.
          - Raises ValueError after all retries exhausted.

        Logs every call to self._call_log with: timestamp, system[:200],
        user[:200], response[:200], latency_ms, success.
        """
        ...

    async def call_structured(
        self,
        system: str,
        user: str,
        schema: dict,           # JSON schema dict for the expected response
        max_retries: int = 3,
    ) -> dict:
        """
        Like call() with expect_json=True, but also validates the response
        against the provided JSON schema. Retries on validation failure.
        """
        ...
```

**Important:** every LLM call must be `async`. Do not use `requests` or any sync HTTP. Use `httpx.AsyncClient`.

---

## 6. Prompts (`prompts.py`)

All prompt strings live here. No prompt text anywhere else in the codebase. Each prompt is a function that takes parameters and returns `(system: str, user: str)`.

```python
def encoding_prompt(index_content: str, transcript: str) -> tuple[str, str]:
    system = """You are a memory encoder for an AI agent..."""
    user = f"""WIKI INDEX:\n{index_content}\n\nTRANSCRIPT:\n{transcript}"""
    return system, user

def consolidation_identify_prompt(index_content: str, log_entries: str) -> tuple[str, str]: ...
def consolidation_rewrite_prompt(existing_page: str, log_entries: str) -> tuple[str, str]: ...
def consolidation_index_prompt(current_index: str, changes_summary: str) -> tuple[str, str]: ...
def prediction_error_prompt(wiki_page: str, current_context: str) -> tuple[str, str]: ...
def reconsolidation_rewrite_prompt(original_page: str, update_signals: str) -> tuple[str, str]: ...
def routing_prompt(index_content: str, query: str, budget_tokens: int) -> tuple[str, str]: ...
def importance_rating_prompt(content: str) -> tuple[str, str]: ...
```

Write out the full prompt text for each function. Refer to section 5 of the PRD for the exact prompt wording — use that as the starting point and refine for JSON output reliability.

For all prompts that return JSON, end the system prompt with:

```
Respond with valid JSON only. No markdown code fences, no explanation, no preamble.
```

---

## 7. Token Budget (`budget.py`)

```python
import tiktoken

# Use cl100k_base encoding for all models (close enough for budgeting)
_enc = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_enc.encode(text))

class ContextBudget:
    def __init__(self, total: int):
        self.total = total
        self.used = 0

    def fits(self, text: str) -> bool:
        return self.used + count_tokens(text) <= self.total

    def consume(self, text: str) -> None:
        self.used += count_tokens(text)

    def remaining(self) -> int:
        return self.total - self.used

    def utilization(self) -> float:
        return self.used / self.total
```

---

## 8. Core Processes

### 8.1 Encoder (`encoder.py`)

```python
class Encoder:
    def __init__(self, llm: OllamaClient, store: WikiStore, log_store: LogStore, config: Config): ...

    async def encode_session(
        self,
        transcript: str,
        session_id: str,
        min_importance: float = 0.3,
    ) -> list[LogEntry]:
        """
        1. Load _index.md from wiki store
        2. Call encoding_prompt(index, transcript) → LLM → JSON list of entries
        3. Filter entries below min_importance
        4. For each entry: generate entry_id, create LogEntry dataclass
        5. Append all entries to today's log via LogStore.append()
        6. Return list of created LogEntry objects
        """
        ...

    async def encode(
        self,
        content: str,
        session_id: str,
        importance: float | None = None,
        tags: list[str] | None = None,
    ) -> LogEntry:
        """
        Encode a single piece of content directly (not from transcript).
        If importance is None, call importance_rating_prompt to get LLM rating.
        """
        ...
```

### 8.2 Dream Process (`dream.py`)

```python
class DreamProcess:
    def __init__(self, llm: OllamaClient, wiki: WikiStore, logs: LogStore, config: Config): ...

    async def run(
        self,
        strategy: Literal['full', 'new_only', 'association_only'] = 'full',
        dry_run: bool = False,
        conflict_policy: Literal['fork', 'override', 'merge'] = 'fork',
    ) -> DreamReport:
        """
        Full consolidation pipeline:

        1. Get unconsolidated log entries from LogStore
        2. If no entries and strategy != 'association_only': return empty report
        3. Call consolidation_identify_prompt → LLM → list of {page, action}
        4. For each page marked 'update':
             a. Load existing page from WikiStore
             b. Call consolidation_rewrite_prompt → LLM → new page content
             c. Parse new frontmatter + body
             d. Handle conflicts per conflict_policy
             e. Save updated page (unless dry_run)
        5. For each page marked 'create':
             a. Call consolidation_rewrite_prompt with empty existing page
             b. Create new WikiPage dataclass
             c. Save (unless dry_run)
        6. Update _index.md via consolidation_index_prompt
        7. Mark consolidated entries in LogStore
        8. Return DreamReport
        """
        ...

    async def _handle_conflict(
        self,
        existing: WikiPage,
        proposed: WikiPage,
        policy: str,
    ) -> WikiPage:
        """
        fork: keep both, add 'contradicts' edge between them,
              lower confidence on both by 0.1
        override: use proposed, deprecate existing (move to _archive)
        merge: call LLM to synthesize both into one page
        """
        ...
```

### 8.3 Reconsolidation (`reconsolidation.py`)

```python
class ReconsolidationEngine:
    def __init__(self, llm: OllamaClient, wiki: WikiStore, config: Config): ...

    async def check(
        self,
        page: WikiPage,
        context: str,
    ) -> PredictionError:
        """
        Calls prediction_error_prompt(page, context) → LLM → PredictionError.
        Always returns a PredictionError even if conflict_type='none'.
        """
        ...

    async def flag_labile(self, page: WikiPage, session_id: str) -> None:
        """
        Marks the page as labile in the wiki store.
        Copies to labile/ directory via WikiStore.mark_labile().
        """
        ...

    async def accumulate_signal(
        self,
        slug: str,
        session_id: str,
        signal: PredictionError,
    ) -> None:
        """
        Appends the prediction error signal to an in-memory list
        keyed by (slug, session_id). Called each time a labile page
        is retrieved again within the same session.
        """
        ...

    async def resolve_labile_pages(self, session_id: str) -> list[str]:
        """
        Called at session end. For all pages flagged labile in this session:

        1. Gather accumulated signals from memory
        2. Call reconsolidation_rewrite_prompt(original_page, signals) → LLM
        3. Parse updated page content + frontmatter
        4. Increment version
        5. Append UpdateLogEntry to page.update_log
        6. Save updated page to WikiStore
        7. Call WikiStore.resolve_labile() to clean up labile/ copy
        8. Return list of resolved slugs
        """
        ...
```

## 9. Session Context Manager (`session.py`)

This is the primary integration point for agent developers.

```python
from contextlib import asynccontextmanager

class Session:
    def __init__(
        self,
        mycelium: 'Mycelium',
        session_id: str,
        query: str,
    ):
        self.session_id = session_id
        self.query = query
        self.loaded_pages: list[WikiPage] = []
        self.transcript: list[dict] = []   # [{role, content}, ...]
        self._mycelium = mycelium

    @property
    def memory_context(self) -> str:
        """
        Returns loaded wiki pages formatted for prompt injection:

        === MEMORY: <title> (confidence: X.XX, v<N>) ===
        <page content>

        === MEMORY: <title> ... ===
        ...

        === END MEMORY ===
        """
        ...

    def build_prompt(self, user_message: str) -> str:
        """
        Returns: memory_context + "\n\n" + user_message
        """
        ...

    def record(self, role: str, content: str) -> None:
        """Appends to self.transcript."""
        ...


class Mycelium:
    ...

    @asynccontextmanager
    async def session(self, query: str, session_id: str | None = None):
        """
        Usage:
            async with mem.session(query=q) as session:
                prompt = session.build_prompt(q)
                ...
                session.record('user', q)
                session.record('assistant', response)

        On __aenter__:
          1. Generate session_id if None (uuid4 short)
          2. Call load_context(query) → populate session.loaded_pages
          3. yield session

        On __aexit__:
          1. Encode transcript via Encoder.encode_session()
          2. Resolve labile pages via ReconsolidationEngine.resolve_labile_pages()
        """
        ...
```

---

## 10. Main Client (`core.py`)

```python
class Mycelium:
    def __init__(
        self,
        store_path: str | Path,
        ollama_model: str = 'gemma3:12b',
        ollama_url: str = 'http://localhost:11434',
        context_budget_tokens: int = 8192,
        lability_threshold: float = 0.35,
        conflict_policy: Literal['fork', 'override', 'merge'] = 'fork',
        config_path: str | Path | None = None,
    ):
        """
        Initializes all sub-components. If store_path doesn't exist,
        calls _init_store() to create the directory structure and
        default files (_index.md, mycelium.toml).

        If config_path is provided, loads config from TOML and
        config values override constructor arguments.
        """
        ...

    def _init_store(self) -> None:
        """
        Creates:
          store_path/wiki/
          store_path/wiki/_index.md  (empty index template)
          store_path/logs/
          store_path/labile/
          store_path/wiki/_archive/
          store_path/mycelium.toml     (default config)
        """
        ...

    async def load_context(
        self,
        query: str,
        budget_tokens: int | None = None,
        reconsolidate: bool = True,
    ) -> list[WikiPage]:
        """
        1. Load _index.md
        2. Call routing_prompt(index, query, budget) → LLM →
           list of {page: str, reason: str, priority: int}
        3. Sort by priority
        4. Load pages in priority order until budget exhausted
        5. For each loaded page, if reconsolidate=True:
             a. Call reconsolidation_engine.check(page, query)
             b. If discrepancy_score > lability_threshold:
                  - Set page.was_flagged = True
                  - Set page.discrepancy_score
                  - Call reconsolidation_engine.flag_labile()
        6. Return loaded pages with was_flagged populated
        """
        ...

    async def dream(self, **kwargs) -> DreamReport:
        """Delegates to DreamProcess.run()"""
        ...

    async def encode(self, content: str, **kwargs) -> LogEntry:
        """Delegates to Encoder.encode()"""
        ...

    # wiki property: returns WikiStore for direct access
    @property
    def wiki(self) -> WikiStore: ...
```

---

## 11. Config (`config.py`)

```python
import tomllib
from dataclasses import dataclass
from pathlib import Path

@dataclass
class LLMConfig:
    url: str = 'http://localhost:11434'
    model: str = 'gemma3:12b'
    temperature: float = 0.2
    timeout_seconds: int = 120

@dataclass
class ReconsolidationConfig:
    lability_threshold: float = 0.35
    check_on_load: bool = True

@dataclass
class DreamConfig:
    conflict_policy: str = 'fork'

@dataclass
class Config:
    context_budget_tokens: int = 8192
    llm: LLMConfig = LLMConfig()
    reconsolidation: ReconsolidationConfig = ReconsolidationConfig()
    dream: DreamConfig = DreamConfig()

    @classmethod
    def from_toml(cls, path: Path) -> 'Config':
        """Loads config from mycelium.toml, returns Config with defaults for missing keys."""
        ...

    @classmethod
    def defaults(cls) -> 'Config':
        return cls()
```

---

## 12. Public API (`__init__.py`)

```python
from mycelium.core import Mycelium
from mycelium.models import WikiPage, LogEntry, DreamReport, PredictionError
from mycelium.session import Session

__all__ = ['Mycelium', 'WikiPage', 'LogEntry', 'DreamReport', 'PredictionError', 'Session']
__version__ = '0.1.0'
```

Usage should be:
```python
import mycelium
mem = mycelium.Mycelium(store_path='./store')
```

---

## 13. Tests

### Fixtures (`conftest.py`)

```python
import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from mycelium import Mycelium
from mycelium.ollama import OllamaClient
from mycelium.store import WikiStore, LogStore

@pytest.fixture
def tmp_store(tmp_path):
    """Creates a Mycelium instance backed by a temp directory."""
    return Mycelium(store_path=tmp_path / 'store')

@pytest.fixture
def mock_llm():
    """AsyncMock OllamaClient that returns configurable responses."""
    client = AsyncMock(spec=OllamaClient)
    return client
```

### What to test

`test_store.py`
- WikiStore: save, get, list_all, archive, mark_labile, resolve_labile
- LogStore: append, get_unconsolidated, mark_consolidated
- Frontmatter round-trips (serialize → write → read → deserialize) for all fields including nested dataclasses

`test_encoder.py`
- `encode()` with mocked LLM response → correct LogEntry created
- `encode_session()` with multi-entry LLM response → all entries appended
- Entries below `min_importance` are filtered out
- `importance=None` triggers LLM importance rating call

`test_dream.py`
- `run()` with unconsolidated entries → correct LLM calls made in order
- Pages are updated and saved
- New pages are created when LLM returns `action='create'`
- `dry_run=True` → no files written
- `conflict_policy='fork'` → both pages saved, contradicts edge added

`test_reconsolidation.py`
- `check()` returns correct `PredictionError` from mocked LLM
- `discrepancy_score > threshold` → `flag_labile()` called
- `discrepancy_score < threshold` → no labile flag
- `resolve_labile_pages()` → page rewritten, version incremented, update_log appended
- `accumulate_signal()` → multiple signals accumulated then resolved in single rewrite

`test_session.py`
- `session()` context manager: load_context called on enter
- `session.build_prompt()` injects memory_context
- `session.record()` appends to transcript
- On exit: encode_session called with full transcript
- On exit: resolve_labile_pages called
- Dream consolidation runs only through an explicit `dream()` call

---

## 14. Implementation Order

Build in this order. Each phase should have passing tests before moving to the next.

**Phase 1 — Foundation**
1. `models.py` — all dataclasses
2. `config.py` — Config loading
3. `store.py` — WikiStore + LogStore (file I/O only, no LLM)
4. `budget.py` — ContextBudget + count_tokens
5. `tests/test_store.py` — full coverage

**Phase 2 — LLM Layer**
6. `ollama.py` — OllamaClient with `call()` and `call_structured()`
7. `prompts.py` — all prompt functions (write the actual text)
8. Test OllamaClient with a real Ollama instance (integration test, mark with `@pytest.mark.integration`)

**Phase 3 — Encoding**
9. `encoder.py`
10. `tests/test_encoder.py`

**Phase 4 — Retrieval**
11. `load_context()` in `core.py` (routing LLM call + budget management)
12. `session.py` (context manager, build_prompt, memory_context formatting)
13. `tests/test_session.py` (partial — enter/exit without dream)

**Phase 5 — Reconsolidation**
14. `reconsolidation.py`
15. `tests/test_reconsolidation.py`
16. Wire reconsolidation into `load_context()` and session exit

**Phase 6 — Dream**
17. `dream.py`
18. `tests/test_dream.py`

**Phase 7 — Integration**
19. `core.py` — `Mycelium.__init__()`, `_init_store()`, top-level API
20. `__init__.py` — public exports
21. `examples/basic_session.py` — smoke test against live Ollama
22. `examples/langgraph_integration.py`

---

## 15. Coding Conventions

- All LLM-calling methods are `async`. No sync LLM calls anywhere.
- Never import from a higher-level module into a lower-level one. Dependency direction: `core → encoder/dream/reconsolidation → store/ollama/prompts → models/config/budget`
- No `print()` statements. Use `logging.getLogger(__name__)` in every module.
- Every public method has a docstring.
- Type hints on all function signatures. Run `mypy mycelium/` and fix all errors.
- Format with `ruff format`. Lint with `ruff check`.
- Do not catch bare `Exception`. Catch specific exceptions and re-raise with context.
- Git commit messages follow: `feat:`, `fix:`, `test:`, `refactor:`, `docs:` prefixes.

---

## 16. Quick Smoke Test

After Phase 7 is complete, this should run end-to-end:

```python
# examples/basic_session.py
import asyncio
import mycelium

async def main():
    mem = mycelium.Mycelium(
        store_path='./smoke_test_store',
        ollama_model='gemma3:12b',
    )

    # Session 1: record some experience
    async with mem.session(query="what's the system architecture?") as session:
        print("Loaded pages:", [p.slug for p in session.loaded_pages])
        print("Memory context (first 300 chars):", session.memory_context[:300])
        session.record('user', "what's the system architecture?")
        session.record('assistant', "We're using a plain-text wiki backed by a local LLM.")

    # Run dream manually
    report = await mem.dream()
    print("Dream report:", report)

    # Session 2: check that memory was encoded
    async with mem.session(query="what did we decide about storage?") as session:
        print("Loaded pages:", [p.slug for p in session.loaded_pages])
        for p in session.loaded_pages:
            if p.was_flagged:
                print(f"  ⚠ {p.slug} flagged for reconsolidation (score: {p.discrepancy_score:.2f})")

asyncio.run(main())
```

---

## Reference

Full design rationale, biological mappings, LLM prompt details, and research context are in the PRD: `prd.md`. When a design decision isn't covered here, the PRD is authoritative.
