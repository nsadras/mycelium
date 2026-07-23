# Mycelium
## Neurobiologically-Inspired Agent Memory System
### Product Requirements Document & Technical Specification — v0.2

**Author:** Nitin  
**Status:** DRAFT  
**Date:** May 2026  
**Changes from v0.1:** Architecture revised to plain-text-first storage (Karpathy wiki pattern). Vector DB, graph DB, and embedding model dependencies removed. Local LLM (Ollama) replaces API-based LLM calls. LangChain/LangGraph explicitly out of scope.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Motivation & Background](#2-motivation--background)
3. [Architecture](#3-architecture)
4. [File System Layout](#4-file-system-layout)
5. [Core Processes](#5-core-processes)
6. [Python API Specification](#6-python-api-specification)
7. [Local LLM Integration](#7-local-llm-integration)
8. [Configuration Reference](#8-configuration-reference)
9. [Open Research Questions](#9-open-research-questions)
10. [Implementation Roadmap](#10-implementation-roadmap)
11. [Publication Potential](#11-publication-potential)
12. [Appendix: Key References](#appendix-key-references)

---

## 1. Overview

### 1.1 Vision

Mycelium is a **dependency-light Python library** that gives LLM-based agents a memory system modeled on human neurobiology. It implements encoding, consolidation, reconsolidation, and associative recall using nothing but **plain markdown files and a locally-running LLM**.

There are no vector databases. No embedding models. No graph databases. No cloud API calls. The entire memory store is a directory of human-readable text files, and all intelligence (consolidation, relevancy ranking, reconsolidation) is performed by a local LLM via Ollama.

### 1.2 The Two Foundational Ideas

**From Karpathy's wiki pattern:** intelligence should happen at *write time*, not query time. Rather than re-deriving knowledge from raw documents on every retrieval, an agent continuously compiles experience into a structured, pre-digested wiki. The wiki is loaded into context at session start — no retrieval step required.

**From neuroscience:** retrieval is not read-only. When a memory is recalled, it enters a labile (destabilized) state and can be updated before restabilizing. This is **reconsolidation** — the mechanism by which humans correct beliefs, integrate new experience, and keep memory context-sensitive over time.

Mycelium is the first agent memory framework to implement reconsolidation. That is its primary research contribution.

### 1.3 Design Principles

- **Plain text over infrastructure.** Every memory artifact is a readable markdown file. The store can be inspected, edited, backed up or version-controlled externally, and understood without Mycelium-specific tooling.
- **Local LLM over API calls.** All LLM work (encoding, consolidation, reconsolidation, relevancy routing) runs via Ollama. No token costs, no rate limits, no data leaving the machine.
- **LLM calls over algorithms.** Clustering, ranking, conflict detection, and abstraction are all LLM calls — not embedding similarity or graph traversal. This is more powerful, more flexible, and eliminates the entire embedding stack.
- **No frameworks.** Mycelium has no dependency on LangChain, LangGraph, or any agent framework. It is a plain Python library. Agent harnesses can be built on top of it using whatever framework the developer prefers.

### 1.4 Scope

This document covers:

- Plain-text memory architecture and file layout
- The four core memory processes and their implementation as LLM calls
- Python library API
- Local LLM integration via Ollama
- Open research questions
- Implementation roadmap and publication potential

---

## 2. Motivation & Background

### 2.1 Biological Analogs

Mycelium maps directly to well-established neuroscience. The plain-text architecture does not change these mappings — it changes only the substrate.

| Neurobiology | Mycelium Component | File Artifact |
|---|---|---|
| Hippocampus | Episodic Log | `logs/YYYY-MM-DD.md` |
| Neocortex | Wiki (semantic store) | `wiki/<topic>.md` |
| Slow-wave sleep | Dream Process | Rewrites wiki pages from logs |
| REM sleep | Association Pass | Updates `_index.md` cross-links |
| Reconsolidation | Lability Window | Rewrites wiki page on retrieval conflict |
| Working memory | Context Buffer | In-process string, injected into prompt |

### 2.2 Why Plain Text

The Karpathy wiki pattern (April 2026) makes the case compellingly: for curated agent knowledge bases, loading pre-digested markdown into the context window outperforms RAG on accuracy, speed, and maintainability. RAG re-discovers knowledge on every query — nothing accumulates. A maintained wiki *compounds* over time.

The additional advantages for Mycelium specifically:

- **Debuggability.** Memory failures are visible. You can read the wiki pages that the agent read, see exactly what was in context, and understand why it behaved as it did.
- **Auditability.** Memory artifacts remain readable files, so operators can inspect changes and choose their own backup or version-control workflow.
- **Portability.** The memory store is just a folder. It can be copied, backed up, shared, or inspected without any database tooling.
- **Publishability.** Plain-text memory traces are easier to analyze, benchmark, and report on than opaque vector store states.

### 2.3 Why Local LLM

Using a local LLM (Gemma 3, Llama 3, Mistral, etc. via Ollama) for all memory operations changes the economics entirely. Operations that would be prohibitively expensive with API pricing — re-ranking all retrieved pages, running a reconsolidation check on every retrieval, running nightly dream passes over the full episodic log — become essentially free. This allows Mycelium to be *much more aggressive* with LLM-driven intelligence than any API-based system could be.

### 2.4 Gap in Existing Systems

A survey of current agent memory frameworks (Mem0, A-MEM, HippoRAG, MemoryBank, Karpathy wiki) reveals a consistent gap:

- **Retrieval is stateless.** Querying a memory does not modify it, regardless of context.
- **Consolidation is one-shot.** Memories are written once and updated manually.
- **No prediction error signal.** No system computes the discrepancy between a recalled memory and present context.
- **No lability window.** No concept of a memory being temporarily destabilized and editable.

The Karpathy wiki addresses the first two partially (the agent can rewrite wiki pages) but provides no protocol for *when* or *why* a page should be rewritten on retrieval. Mycelium provides that protocol.

---

## 3. Architecture

### 3.1 Memory Tiers

| Tier | Biological Analog | Storage | Lifetime |
|---|---|---|---|
| Context Buffer | Working memory | In-process `str` | Single session |
| Episodic Log | Hippocampus | `logs/YYYY-MM-DD.md` | Days–weeks |
| Wiki | Neocortex | `wiki/<topic>.md` | Permanent |

### 3.2 System Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                          AGENT SESSION                           │
│                                                                  │
│  session start                                                   │
│      │                                                           │
│      ▼                                                           │
│  load_context(query)                                             │
│      │  1. read _index.md                                        │
│      │  2. local LLM selects relevant wiki pages                 │
│      │  3. inject selected pages into Context Buffer             │
│      │  4. [reconsolidation check on each loaded page]           │
│      │                                                           │
│      ▼                                                           │
│  ┌─────────────────────────────┐                                 │
│  │       Context Buffer        │  ← wiki pages + session history │
│  │    (in-process string)      │                                 │
│  └─────────────────────────────┘                                 │
│                    │                                             │
│             agent operates                                       │
│                    │                                             │
│  session end       │                                             │
│      │             ▼                                             │
│      │   append to logs/YYYY-MM-DD.md                           │
│      │                                                           │
│      ▼                                                           │
│  Dream Process (manually triggered)                              │
│      │  1. local LLM reads recent log entries                    │
│      │  2. identifies patterns / abstractions                    │
│      │  3. rewrites relevant wiki/<topic>.md pages               │
│      │  4. updates _index.md cross-links                         │
│      │                                                           │
│      ▼                                                           │
│  ┌────────────────────────────────────────────────────┐         │
│  │                    WIKI (markdown files)            │         │
│  │  wiki/                                              │         │
│  │  ├── _index.md          ← table of contents + links│         │
│  │  ├── <topic-a>.md       ← semantic memory page     │         │
│  │  ├── <topic-b>.md                                  │         │
│  │  └── _archive/          ← manually archived pages  │         │
│  │                                                     │         │
│  │  logs/                                              │         │
│  │  ├── 2026-05-01.md      ← raw episodic entries      │         │
│  │  └── 2026-05-02.md                                  │         │
│  └────────────────────────────────────────────────────┘         │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3 The Index File

`wiki/_index.md` is the routing layer — the replacement for vector similarity search. It is a structured markdown file listing all wiki pages with one-line descriptions, topic tags, and typed cross-links between pages. At session start, the local LLM reads the index and selects which pages to load. This is cheap: the index stays compact even as the wiki grows.

```markdown
# Mycelium Wiki Index
_last updated: 2026-05-10 02:14_

## Pages

### [project-architecture](project-architecture.md)
High-level decisions about how the system is structured.
tags: architecture, design, tech-stack
related: [python-conventions contradicts early-prototypes], [deployment enables scaling]

### [user-feedback](user-feedback.md)
Patterns and themes from user interactions and testing sessions.
tags: ux, feedback, iteration
related: [project-architecture informs], [known-bugs exemplifies]

### [known-bugs](known-bugs.md)
Active and resolved issues with root cause notes.
tags: bugs, debugging
related: [user-feedback causes], [python-conventions generalizes]
```

Note the typed relationships on `related:` links. These encode the knowledge graph directly in plain text — no graph database required. The local LLM can traverse these when doing associative retrieval.

---

## 4. File System Layout

```
mycelium_store/
│
├── wiki/
│   ├── _index.md                  # routing index + cross-links
│   ├── <topic>.md                 # one page per semantic concept
│   └── _archive/
│       └── <topic>.md             # manually archived pages
│
├── logs/
│   ├── YYYY-MM-DD.md              # daily episodic log
│   └── _consolidated.md           # marker file: last dream run timestamp
│
├── labile/
│   └── <topic>.<session_id>.md    # wiki pages currently in labile state
│
└── mycelium.toml                    # configuration
```

### 4.1 Wiki Page Format

Every wiki page follows a consistent YAML frontmatter + markdown body structure:

```markdown
---
id: project-architecture
title: Project Architecture
created: 2026-04-15T10:22:00
last_updated: 2026-05-09T02:14:00
version: 4
confidence: 0.82
importance: 0.9
tags: [architecture, design, tech-stack]
related:
  - target: python-conventions
    relation: contradicts
    weight: 0.6
  - target: deployment
    relation: enables
    weight: 0.8
source_log_entries:
  - logs/2026-04-15.md#entry-3
  - logs/2026-04-22.md#entry-1
labile: false
labile_session: null
---

# Project Architecture

[Content written by and for the LLM agent — principle-level, abstracted,
not a summary of raw events. Updated by the Dream Process and
Reconsolidation Engine.]
```

### 4.2 Episodic Log Format

Daily logs are append-only markdown files. Each entry is a fenced block with metadata:

```markdown
# Log: 2026-05-10

## Entry 1 — 09:14

**session_id:** ses-a1b2c3  
**importance:** 0.7  
**tags:** architecture, decision  
**status:** raw  
**consolidated:** false  

The user decided to switch from PostgreSQL to SQLite for the episodic
store, citing operational simplicity. This contradicts the earlier
decision in entry logs/2026-04-20.md#entry-2.

---

## Entry 2 — 09:31
...
```

---

## 5. Core Processes

All four core processes are implemented as **local LLM calls** — no algorithms, no embeddings, no graph traversal. The LLM is the intelligence layer throughout.

### 5.1 Encoding

Triggered at session end. The encoder reads the session transcript and appends significant memories to the daily log.

**LLM call — extraction:**
```
SYSTEM: You are a memory encoder for an AI agent. Given a session
transcript, extract the most significant events, decisions, beliefs,
or facts worth remembering. For each, rate importance 0.0–1.0 and
assign topic tags. Format as structured log entries.

Filter out: small talk, routine confirmations, anything already well
covered in the wiki (which is provided below for reference).

[wiki _index.md injected here]

TRANSCRIPT:
[session transcript]
```

The LLM returns structured entries which are appended to `logs/YYYY-MM-DD.md`.

---

### 5.2 Consolidation — The Dream Process

A manually triggered consolidation pass. Reads recent log entries and rewrites relevant wiki pages. Models slow-wave sleep consolidation: episodic → semantic, lossy compression, principle extraction.

**Step 1 — Identify affected pages:**
```
SYSTEM: You are a memory consolidation agent. Given recent log entries,
identify which existing wiki pages are affected by new information,
and whether any new pages need to be created.

Return a JSON list: [{page: str, action: 'update'|'create'|'none'}]

[_index.md injected]
[recent unprocessed log entries injected]
```

**Step 2 — Rewrite each affected page:**
```
SYSTEM: You are rewriting a wiki page to incorporate new experience.
Rules:
- Abstract, do not summarize. Extract the principle, not the event.
- Resolve conflicts explicitly: if new info contradicts existing content,
  choose the more recent/credible version and note the revision.
- Update confidence score based on how much evidence now supports this.
- Update related: links if new connections are apparent.
- Increment version.
- Do NOT include specific dates, people's names, or episodic details
  unless they are themselves the principle being recorded.

EXISTING PAGE:
[current wiki/<topic>.md]

NEW LOG ENTRIES:
[relevant entries]
```

**Step 3 — Update index:**

After all page rewrites, the LLM updates `_index.md` to reflect new pages, updated descriptions, and new cross-links.

**Step 4 — Finalize episodic entries:**

Log entries that have been successfully consolidated have their `consolidated: true` flag set so later dream passes do not process them again.

```python
dream = mem.dream_process()

report = await dream.run(
    dry_run=False,           # True previews changes without writing
    strategy='full',         # 'full' | 'new_only' | 'association_only'
    conflict_policy='fork',  # 'fork' | 'override' | 'merge'
)
```

---

### 5.3 Reconsolidation — The Novel Core

**This is Mycelium's primary research contribution.** When a wiki page is loaded into context, Mycelium runs a prediction error check by asking the local LLM whether the retrieved content conflicts with the current context. If the discrepancy exceeds the configured threshold, the page enters a **labile state** and is eligible for rewriting.

#### 5.3.1 Prediction Error Check

Runs on every wiki page loaded into context (cheap with local LLM):

```
SYSTEM: You are a memory reconsolidation monitor. Given a stored wiki
page and the current session context, assess whether the stored belief
is still accurate.

Return JSON:
{
  "conflict_type": "none" | "partial" | "major" | "additive",
  "discrepancy_score": 0.0–1.0,
  "explanation": str,
  "suggested_update": str | null
}

- "none": content matches context well (score < 0.2)
- "additive": context adds nuance not captured (score 0.2–0.35)
- "partial": context partially contradicts stored belief (score 0.35–0.65)
- "major": context strongly contradicts stored belief (score > 0.65)

STORED WIKI PAGE:
[wiki/<topic>.md content]

CURRENT CONTEXT:
[current session context / user query / recent exchanges]
```

#### 5.3.2 The Lability Window

A page with `discrepancy_score > lability_threshold` (default 0.35) is placed into a labile state:

1. The page is copied to `labile/<topic>.<session_id>.md`
2. Its frontmatter is updated: `labile: true`, `labile_session: <session_id>`
3. During the session, additional update signals are accumulated in the labile copy
4. At session end (or when the window closes), all accumulated signals are synthesized into a single rewrite

#### 5.3.3 Rewrite Synthesis

At the end of the lability window, the LLM synthesizes accumulated signals:

```
SYSTEM: A wiki page has been flagged for reconsolidation. One or more
retrieval events during this session revealed that its content may be
outdated or incomplete. Rewrite the page to incorporate the updates.

Rules:
- Maintain the page's abstracted, principle-level voice
- Add an _update_log entry to the frontmatter documenting what changed
  and why (for audit trail)
- Increment version
- Adjust confidence score appropriately
- Set labile: false

ORIGINAL PAGE:
[wiki/<topic>.md]

ACCUMULATED UPDATE SIGNALS:
[list of {discrepancy_score, explanation, suggested_update} from session]
```

The rewritten page replaces the original. The labile copy is removed.

#### 5.3.4 Update Log (Provenance)

Every reconsolidation event appends to the page's frontmatter `update_log`:

```yaml
update_log:
  - version: 4
    date: 2026-05-10T09:44:00
    session_id: ses-a1b2c3
    trigger: reconsolidation
    discrepancy_score: 0.51
    reason: "New session context showed PostgreSQL decision was reversed;
             page updated to reflect SQLite choice and rationale."
    previous_confidence: 0.75
    new_confidence: 0.82
```

This gives a complete, human-readable audit trail for every memory revision without any database infrastructure.

---

### 5.4 Retrieval (Context Loading)

At session start, Mycelium loads relevant wiki pages into the Context Buffer. The routing step replaces vector similarity search with an LLM call over the index:

**Step 1 — Page selection:**
```
SYSTEM: You are a memory retrieval agent. Given the user's query and
the wiki index, select the pages most relevant to load into context.

Constraints:
- Total loaded content must stay under [context_budget] tokens
- Prefer pages with higher confidence and importance when relevance is otherwise comparable
- Follow related: links to include associated pages if budget allows
- If no pages are clearly relevant, return an empty list

Return JSON: [{page: str, reason: str, priority: 1-5}]

USER QUERY: [query]

WIKI INDEX:
[_index.md]
```

**Step 2 — Load and check:**

Selected pages are loaded in priority order until the context budget is reached. Each loaded page triggers the reconsolidation check (Section 5.3.1).

**Step 3 — Inject:**

Selected pages are formatted and prepended to the session context:

```
=== MEMORY: project-architecture (confidence: 0.82, v4) ===
[page content]

=== MEMORY: python-conventions (confidence: 0.91, v2) ===
[page content]

=== END MEMORY ===
```

---

## 6. Python API Specification

Mycelium is a plain Python library with no LangChain, vector database, or embedding-model dependency.

### 6.1 Core Client

```python
import mycelium

mem = mycelium.Mycelium(
    store_path='./mycelium_store',       # path to file store
    ollama_model='gemma3:12b',         # local model via Ollama
    ollama_url='http://localhost:11434',
    context_budget_tokens=8192,        # max tokens to inject per session
    lability_threshold=0.35,
    conflict_policy='fork',            # 'fork' | 'override' | 'merge'
)
```

### 6.2 Session API

```python
# Context manager — handles load, record, and dream automatically
async with mem.session(query=user_query, session_id='ses-abc') as session:

    # Relevant wiki pages are pre-loaded into session.context
    prompt = session.build_prompt(user_query)
    response = await your_llm.complete(prompt)
    session.record(user_query, response)

# On __aexit__:
#   1. Session transcript appended to today's log
#   2. Labile pages resolved and rewritten
# Dream consolidation remains an explicit `mem.dream()` call.
```

### 6.3 Retrieval API

```python
# Load relevant pages into context (called automatically by session)
pages = await mem.load_context(
    query: str,
    budget_tokens: int = None,    # defaults to config
    reconsolidate: bool = True,
) -> List[WikiPage]

# WikiPage fields:
#   .slug           str    — filename without .md
#   .content        str    — full page content
#   .confidence     float
#   .version        int
#   .was_flagged    bool   — True if reconsolidation was triggered
#   .discrepancy    float  — prediction error score (0 if not flagged)
```

### 6.4 Encoding API

```python
# Encode a single experience directly (outside session context)
entry = await mem.encode(
    content: str,
    importance: float = None,    # auto-rated by LLM if None
    tags: List[str] = None,
    session_id: str = None,
)

# Encode full session transcript
entries = await mem.encode_session(
    transcript: str,
    session_id: str,
    min_importance: float = 0.3,
)
```

### 6.5 Dream Process API

```python
report = await mem.dream(
    strategy: str = 'full',      # 'full' | 'new_only' | 'association_only'
    dry_run: bool = False,
)

# DreamReport fields:
#   .pages_updated       int
#   .pages_created       int
#   .entries_consolidated int
#   .conflicts_found     List[str]   — page slugs with conflicts
#   .conflicts_resolved  int
```

### 6.6 Wiki Management API

```python
# Read a specific page
page = mem.wiki.get('project-architecture')

# List all pages (from index)
pages = mem.wiki.list(tag='architecture', min_confidence=0.5)

# Manually trigger reconsolidation on a page
result = await mem.reconsolidate(
    slug='project-architecture',
    context=current_context,
    force=False,    # skip threshold check
)

# Inspect update log for a page
history = mem.wiki.history('project-architecture')
# returns List[UpdateLogEntry] in chronological order
```

### 6.7 Agent Harness Integration (Framework-Agnostic)

Mycelium is framework-agnostic. Here is how it integrates with a LangGraph outer loop:

```python
from langgraph.graph import StateGraph
import mycelium

mem = mycelium.Mycelium(store_path='./store', ollama_model='gemma3:12b')

async def memory_node(state):
    """Load relevant memory into agent state."""
    pages = await mem.load_context(query=state['input'])
    state['memory_context'] = mem.format_for_prompt(pages)
    return state

async def record_node(state):
    """Record session output to episodic log."""
    await mem.encode(
        content=f"Q: {state['input']}\nA: {state['output']}",
        session_id=state['session_id'],
    )
    return state

graph = StateGraph(...)
graph.add_node('load_memory', memory_node)
graph.add_node('record_memory', record_node)
# ... rest of graph definition
```

---

## 7. Local LLM Integration

### 7.1 Ollama Setup

Mycelium targets Ollama as the local LLM runtime. All LLM calls go to `http://localhost:11434/api/generate` (or chat endpoint).

```toml
# mycelium.toml
[llm]
provider = "ollama"
url = "http://localhost:11434"
model = "gemma3:12b"            # recommended baseline
timeout_seconds = 120
temperature = 0.2               # low temp for memory operations
```

### 7.2 Recommended Models

| Model | Context | Best For | VRAM |
|---|---|---|---|
| `gemma3:12b` | 128k | Default; best quality/speed balance | 10GB |
| `llama3.2:3b` | 128k | Fast operations, low VRAM | 4GB |
| `mistral:7b` | 32k | Solid baseline | 6GB |
| `gemma3:27b` | 128k | Highest quality, slower | 20GB |

### 7.3 LLM Call Wrapper

All Mycelium LLM calls go through a single wrapper that handles structured output parsing, retries, and logging:

```python
class OllamaClient:
    async def call(
        self,
        system: str,
        user: str,
        expect_json: bool = False,
        temperature: float = 0.2,
    ) -> str | dict:
        """
        Makes a chat completion call to Ollama.
        If expect_json=True, prompts for JSON-only output and
        parses the response, retrying up to 3 times on parse failure.
        All calls are logged to logs/_llm_calls.jsonl for debugging.
        """
        ...
```

### 7.4 Token Budget Management

Since local models have finite context windows, Mycelium tracks token usage using `tiktoken` (approximate, model-agnostic):

```python
class ContextBudget:
    def __init__(self, total: int):
        self.total = total
        self.used = 0

    def fits(self, text: str) -> bool:
        return self.used + token_count(text) <= self.total

    def consume(self, text: str):
        self.used += token_count(text)

    @property
    def remaining(self) -> int:
        return self.total - self.used
```

Pages are loaded in priority order until the budget is exhausted. The index file always loads first (it's compact by design). If the wiki grows large, the LLM routing step ensures only the most relevant pages are selected.

---

## 8. Configuration Reference

```toml
# mycelium.toml — full reference

[store]
path = "./mycelium_store"

[llm]
provider = "ollama"
url = "http://localhost:11434"
model = "gemma3:12b"
temperature = 0.2
timeout_seconds = 120
max_retries = 3

[session]
context_budget_tokens = 8192  # max wiki content to inject per session
min_importance_to_encode = 0.3

[reconsolidation]
enabled = true
lability_threshold = 0.35     # prediction error score threshold
lability_window = "session"   # "session" | int (seconds)
check_on_load = true          # run prediction error check on every load

[dream]
strategy = "full"             # "full" | "new_only" | "association_only"
conflict_policy = "fork"      # "fork" | "override" | "merge"
max_pages_per_run = 20        # safety limit

```

---

## 9. Open Research Questions

Mycelium is designed to be publishable. The following are open empirical questions each suitable as a focused experiment.

### 9.1 Prediction Error Calibration

What is the optimal `lability_threshold`? Too low: memories update constantly, losing stability. Too high: the system loses malleability and behaves like a static wiki. A calibration study on the LOCOMO benchmark across thresholds [0.2, 0.3, 0.4, 0.5] would produce a clean publishable result.

### 9.2 LLM-as-Algorithm vs. Embedding-as-Algorithm

Mycelium uses LLM calls for routing, ranking, and conflict detection — replacing cosine similarity and graph traversal. How do these compare on accuracy and latency? A controlled experiment (Mycelium vs. embedding-based Mycelium-E on the same benchmark) would quantify the tradeoff and justify the design choice.

### 9.3 Consolidation Selectivity

Should the Dream Process consolidate all new log entries, or only those above anmportance threshold? Biological sleep consolidation is selective — emotionally salient memories are preferentially processed. A study on importance-weighted vs. greedy consolidation strategy would test this hypothesis computationally.

### 9.4 Forgetting as a Feature

Mycelium archives rather than deletes. Does active forgetting (deletion below threshold) improve long-horizon agent performance by reducing context noise? Comparing full-retention vs. active-forgetting conditions on a multi-session task would swer this.

### 9.5 Multi-Agent Shared Memory

What conflict-resolution protocol is optimal when multiple agents share a wiki store? A naïve approach (last-write-wins) would cause reconsolidation events to overwrite each other. This is an open problem in the 2025–2026 agent memory survey literature.

### 9.6 Reconsolidation as Fine-tuning Signal

Every reconsolidation event captures a structured pair: (original belief, corrected belief, context that triggered correction). This is a natural supervised finuning signal. A study using accumulated reconsolidation events to fine-tune the local model would test whether in-context memory and parametric memory can be unified via this mechanism.

---

## 10. Implementation Roadmap

| Phase | Milestone | Key Deliverables |
|---|---|---|
| **v0.1 — Foundation** | File store + episodic log | `Mycelium` client, `mycelium_store/` layout, log append, TOML config, Ollama wrapper |
| **v0.2 — Encoding** | LLM-based memory extraction | `encode()`, `encode_session()`, importascoring LLM call, log frontmatter |
| **v0.3 — Wiki + Retrieval** | Index routing + context loading | `_index.md` format, `load_context()` LLM routing call, context budget manager, `session()` context manager |
| **v0.4 — Dream Process** | Async consolidation pipeline | `dream()`, page identification LLM call, page rewrite LLM call, index update |
| **v0.5 — Reconsolidation** | Lability window + prediction error | Prediction error LLM call, labile file management, rewrite sys, `update_log` provenance |
| **v0.6 — Harness** | Agent integration examples | LangGraph integration example, CLI tool (`mycelium dream`, `mycelium status`), documentation |
| **v1.0 — Benchmarks** | Evaluation + release | LOCOMO eval, comparison vs. Mem0 / HippoRAG / plain Karpathy wiki, PyPI release |

---

## 11. Publication Potential

Mycelium addresses a gap explicitly identified in the 2025–2026 agent memory survey literature: retrieval-triggered reconsolidation has no implementation in any existingwork. The plain-text-first architecture also provides a clean comparison point against embedding-based systems.

The combination of:
- Neurobiologically grounded design (citable to Nader et al. 2000; Squire & Alvarez 1995)
- Karpathy wiki as the storage substrate (timely, well-cited)
- LLM-as-algorithm replacing embeddings (novel systems contribution)
- Concrete open-source Python implementation
- Empirical evaluation on LOCOMO benchmark
- Ablations: reconsolidation on/off, plain wiki vs. Mycelium, local vs. API LLM

...constitutes a strong submission to:

- **ICLR MemAgents Workshop** — directly on-topic
- **NeurIPS** — systems or cognitive science track
- **EMNLP / ACL** — language grounding and memory
- **Journal of Neural Engineering** — framing Mycelium as a computational model of reconsolidation bridges neuroscience and AI in a way that is rare and highly reviewable given your publication history there

The JNE framing is particularly strong: reconsolidation is well-established neuroscience (Nader 24000+ citations), implementing it computationally and validating it on agent benchmarks is a genuine contribution to computational cognitive neuroscience, not just ML systems.

---

## Appendix: Key References

**Nader, K., Schafe, G. E., & Le Doux, J. E. (2000).** Fear memories require protein synthesis in the amygdala for reconsolidation after retrieval. *Nature, 406*(6797), 722–726. — Original reconsolidation paper.

**Squire, L. R., & Alvarez, P. (1995).** Retrograde amnesia and memory consolidationneurobiological perspective. *Current Opinion in Neurobiology, 5*(2), 169–177.

**Karpathy, A. (2026).** Personal knowledge base with LLM agents. GitHub Gist, April 2026. — Foundational reference for the plain-text wiki pattern.

**Gutiérrez, B. J. et al. (2024).** HippoRAG: Neurobiologically inspired long-term memory for large language models. arXiv:2405.14831.

**Xu, W. et al. (2025).** A-MEM: Agentic memory for LLM agents. arXiv:2502.12110. NeurIPS 2025.

**Zhang, G. et al. (2025).** Memory in the A AI Agents: A Survey. arXiv:2512.13564.

**Park, J. S. et al. (2023).** Generative agents: Interactive simulacra of human behavior. *UIST 2023.*
