<p align="center">
  <img src="banner.svg" alt="Mycelium Banner" width="100%" />
</p>

# Mycelium

Mycelium is a plaintext memory system for local AI agents. It keeps the original conversation as a durable record, turns useful information into an organized Markdown wiki, and brings the relevant parts back when they are needed later.

It is designed for users who want a local assistant that can build context over time without hiding its memory in an opaque database. You can chat with it through the included web app, inspect what it remembers, edit its knowledge directly, or add the Python library to another agent.

## Why use it?

Most chat assistants either forget everything between sessions or require the entire conversation history to be sent again. Mycelium takes a different approach:

- **Memory persists across conversations.** Projects, preferences, decisions, research, and prior discussions can carry into a new session.
- **Everything stays inspectable.** Raw experiences and consolidated knowledge are stored as ordinary Markdown files.
- **Local models do the work.** Chat, retrieval, and memory consolidation run through Ollama on your machine.
- **You stay in control.** The UI shows the memories used for a response and lets you browse or edit the wiki and source logs.

## Features

- Multi-session chat with a local Ollama model
- Automatic retrieval of relevant long-term memories
- Plain-text episodic logs and an Obsidian-compatible Markdown wiki
- Reconsolidation when a conversation contradicts or extends an existing memory
- Memory reinforcement and decay based on use, confidence, and importance
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

The UI is organized around four main areas:

| Area | What it is for |
| --- | --- |
| **Chat** | Create, rename, resume, and continue conversations. Each answer can show which memory pages were loaded and which tools were called. |
| **Wiki** | Browse and edit the durable knowledge Mycelium has consolidated from earlier experiences. |
| **Logs** | Inspect the original episodic records that serve as source evidence for the wiki. |
| **Engram** | Upload meeting audio, review the transcript and speakers, then save the finished meeting into memory. |

A typical workflow is simple:

1. Start a chat and use the assistant normally.
2. Let Mycelium flush the conversation automatically, or use **Flush Current** to save the active episode immediately.
3. Run **Dream Pass** to turn useful details from raw logs into organized wiki pages. A scheduled dream pass also runs every 30 minutes while the backend is active.
4. Start another chat about the same subject. Mycelium retrieves relevant pages and includes them in the assistant's context.
5. Open **Wiki** or **Logs** whenever you want to see, correct, or trace what was remembered.

The sidebar also provides manual controls for flushing episodes, resolving updated memories, running memory decay, and clearing the development store.

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

The context manager retrieves relevant pages on entry and records the exchange on exit. `dream()` then consolidates new logs into the wiki. See [`examples/basic_session.py`](examples/basic_session.py) for a runnable example and [`examples/langgraph_integration.py`](examples/langgraph_integration.py) for a LangGraph integration pattern.

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
```

The default memory store is `./mycelium_store`. Because it consists primarily of Markdown and JSON, it can be inspected with normal text tools or opened as a wiki outside the app. For ordinary edits, the UI is preferable because it also maintains version and memory-state metadata.

