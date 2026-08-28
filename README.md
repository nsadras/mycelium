<p align="center">
  <img src="banner.svg" alt="Mycelium Banner" width="100%" />
</p>

# Mycelium

Mycelium is a plaintext memory system for local AI agents. It keeps the original conversation as a durable record, turns useful information into an organized Markdown wiki, and brings the relevant parts back when they are needed later.

It is designed for users who want a local assistant that can build context over time without hiding its memory in an opaque database. You can chat with it through the included web app, inspect the complete evidence-to-claim pipeline, review proposed memory updates, or add the Python library to another agent.

## Why use it?

Most chat assistants either forget everything between sessions or require the entire conversation history to be sent again. Mycelium takes a different approach:

- **Memory persists across conversations.** Projects, preferences, decisions, research, and prior discussions can carry into a new session.
- **Everything stays inspectable.** Raw experiences and generated wiki views are Markdown; source documents, episode manifests, claims, and audits are JSON.
- **Local models do the work.** Chat, retrieval, and memory consolidation run through Ollama on your machine.
- **You stay in control.** The UI shows the memories used for a response and requires review before contradictions or replacements change canonical claims.

## Features

- Multi-session chat with a local Ollama model
- Automatic retrieval of relevant long-term memories
- Durable short-term memory that is retrievable before wiki consolidation
- Plain-text episodic logs and an Obsidian-compatible Markdown wiki
- Evidence-triggered, claim-level reconsolidation with human review
- Deterministic, read-only wiki projections with exact source provenance
- Meeting ingestion pipeline - upload meeting audio to have it transcribed, diarized, and consolidated into the memory system
- A Python API for adding Mycelium memory to other agents and frameworks

## Quick start

### Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js and npm
- [Ollama](https://ollama.com/) running locally

Clone and install dependencies:

```bash
git clone https://github.com/nsadras/mycelium.git
cd mycelium
uv sync
cd ui
npm install
cd ..
```

Mycelium is currently configured to use `gemma4:12b`. Download that model with Ollama, or change the model under `[llm]` in `mycelium.toml`:

```bash
ollama pull gemma4:12b
```

With Ollama running, start the backend and frontend together:

```bash
./start.sh
```

Open [http://localhost:5173](http://localhost:5173) to use the app. The FastAPI backend is available at [http://localhost:8000](http://localhost:8000).


## Using the app

The UI is organized around five main areas:

| Area | What it is for |
| --- | --- |
| **Chat** | Create, rename, resume, and continue conversations. Each answer can show which memory pages were loaded and which tools were called. |
| **Memory** | Inspect sources, segments, claims, Dream audits, and pending reconciliation proposals. |
| **Wiki** | Browse and curate entity-owned views deterministically generated from canonical claims. |
| **Logs** | Inspect the original episodic records that serve as source evidence for the wiki. |
| **Engram** | Upload meeting audio, review the transcript and speakers, then save the finished meeting into memory. |

A typical workflow is simple:

1. Start a chat and use the assistant normally.
2. Use **Flush Current**, **Flush Idle**, or **Flush All** when you want chat episodes encoded into
   source-grounded claims and inspectable short-term memory.
3. Run **Dream Pass** when you want to consolidate pending claims and review deferred memory.
4. Start another chat about the same subject. Mycelium retrieves relevant pages and includes them in the assistant's context.
5. Open **Memory** to trace what was remembered and approve or reject proposed contradictions and replacements.

The sidebar provides manual controls for flushing episodes, running Dream, and clearing the development
store. The server does not schedule memory work in the background. **Flush Idle** checks idle and episode-size
conditions only when selected; elapsed time and queue thresholds do not trigger work by themselves.

### How memory works

Flushing a conversation preserves the original transcript and extracts source-linked claims into inspectable
short-term memory. Running Dream organizes useful claims into the Markdown wiki. Both operations happen only when
you request them through the UI or API.

Every wiki fact links back to its source. When new information conflicts with existing memory, Mycelium creates a
review proposal instead of silently overwriting either version. The Memory and Wiki views let you inspect evidence,
correct organization, merge duplicate subjects, and approve or reject proposed changes.

For the detailed lifecycle, entity model, retrieval design, and validation rules, see [DESIGN.md](DESIGN.md).

### Web search

To let the chat assistant use Ollama's web search and fetch tools, add an Ollama API key to a `.env` file in the project root:

```bash
OLLAMA_API_KEY=your_api_key_here
```

Tool calls and the result seen by the model are visible in the chat and retained as source observations for later consolidation.

### Meeting memory with Engram

Engram is optional. Install its speech-processing dependencies separately:

```bash
uv sync --group engram
```

For speaker diarization, accept the terms for `pyannote/speaker-diarization-community-1` on Hugging Face and provide a token:

```bash
export HF_TOKEN=your_hugging_face_token
```

Upload a recording from the **Engram** tab, click **Process**, review the generated transcript and speaker labels, then finalize it. Mycelium saves the transcript and structured meeting summary into the same memory system used by chat.

GPU acceleration is detected automatically when available. See [DESIGN.md](DESIGN.md#engram-meeting-pipeline) for model, device, and testing options.

## Use Mycelium as a library

The web app is optional. The Python API can load memory into an agent prompt and record the resulting exchange:

```python
import asyncio

import mycelium


async def main():
    memory = mycelium.Mycelium(
        store_path="./agent_memory",
        ollama_model="gemma4:12b",
    )

    question = "What did we decide about the project architecture?"
    async with memory.session(query=question) as session:
        prompt = session.build_prompt(question)

        # Send `prompt` to your agent or model.
        answer = "We chose a plain-text wiki backed by source logs."

        session.record("user", question)
        session.record("assistant", answer)

    await memory.dream()


if __name__ == "__main__":
    asyncio.run(main())
```

The context manager retrieves relevant canonical pages and short-term claims on entry and records the
exchange on exit. `dream()` manually consolidates pending and deferred claims. Library integrations can call
`dream_if_ready()` to apply the configured queue policy. See [`examples/basic_session.py`](examples/basic_session.py)
for a runnable example and [`examples/langgraph_integration.py`](examples/langgraph_integration.py) for a
LangGraph integration pattern.

## Configuration

The main settings live in `mycelium.toml`:

```toml
[store]
path = "./mycelium_store"

[llm]
model = "gemma4:12b"
url = "http://localhost:11434"
context_window_tokens = 32768

[session]
context_budget_tokens = 32768

[dream]
queue_claim_threshold = 20
max_pending_hours = 24
deferred_revisit_hours = 168
```

The default memory store is `./mycelium_store`. It consists primarily of Markdown and JSON, so it can be
inspected with ordinary text tools or opened as a wiki outside the app. Every saved chat message carries its own
timestamp, allowing one conversation to span multiple days without losing temporal context.

Architecture, storage contracts, retrieval details, migrations, development checks, and benchmark workflows are
documented in [DESIGN.md](DESIGN.md). The Daily Driver fixture has its own
[benchmark guide](benchmarks/fixtures/daily_driver_v1/README.md).

## License

Mycelium is available under the MIT License. See [LICENSE](LICENSE).
