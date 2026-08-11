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
| **Wiki** | Browse the read-only views deterministically generated from canonical claims. |
| **Logs** | Inspect the original episodic records that serve as source evidence for the wiki. |
| **Engram** | Upload meeting audio, review the transcript and speakers, then save the finished meeting into memory. |

A typical workflow is simple:

1. Start a chat and use the assistant normally.
2. Use **Flush Current**, **Flush Idle**, or **Flush All** to encode an episode into source-grounded claims.
3. Run **Dream Pass** to route useful claims and regenerate organized wiki pages.
4. Start another chat about the same subject. Mycelium retrieves relevant pages and includes them in the assistant's context.
5. Open **Memory** to trace what was remembered and approve or reject proposed contradictions and replacements.

The sidebar provides manual controls for flushing episodes, running Dream, and clearing the development store. Memory work is not scheduled automatically.

### Memory lifecycle

Encoding preserves the complete raw transcript, splits it into exact source segments, and extracts atomic claims in one logical pass. Each claim cites its supporting segment IDs. Dream routes every admitted claim exactly once and generates affected wiki pages deterministically from active claims.

When a new claim may update existing memory, Dream reactivates a bounded set of related claims. Additive information routes normally and supporting relationships are linked automatically. Contradictions and supersessions create durable proposals in the Memory Inspector. Both claims remain visible with a pending marker until review. Approval immediately updates canonical claim links or status and regenerates every affected page; rejection keeps both claims active and unrelated. Retrieval itself is read-only.

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

The default memory store is `./mycelium_store`. Because it consists primarily of Markdown and JSON, it can be inspected with normal text tools or opened as a wiki outside the app. Raw logs and claim artifacts are canonical; wiki Markdown is a generated view and should not be edited directly.

At retrieval time, Mycelium builds a lazy in-memory SQLite FTS5 projection over complete non-derived wiki
pages. BM25 selects two page candidates, title/entity matches can add explicitly mentioned pages, and only
then are page-linked source windows ranked and attached. The index is disposable and automatically refreshes
when page versions or content change; the Markdown wiki remains the durable human-readable memory store.

Relative dates are normalized once at encoding against the source occurrence time and retained with their
original wording, bounds, certainty, and semantic role (event time or deadline). Temporal questions such as
“What deadlines are due next week?” resolve against the query time and select active claims whose intervals
overlap, then load those claims' wiki pages and provenance-linked source logs. This structured temporal branch
augments page FTS; it does not introduce a second durable index or guess dates for phrases such as “soon.”

Stores created by older raw, hybrid, or page-rewrite reconsolidation pipelines are not migrated. Clear and re-encode them before using this version.

## Benchmarking taxonomy and projection changes

Use frozen extraction artifacts when comparing routing, taxonomy, or wiki presentation so claim-extraction
variance does not obscure the result. `REPLAY_STORE` must point to one benchmark case store containing
`artifacts/` and `logs/`:

```bash
REPLAY_STORE=benchmark_runs/<baseline>/stores/conv-30 \
QA_MODEL=gemma4:12b MEMORY_MODEL=gemma4:12b \
RUN_TAG=taxonomy-replay SAMPLE_INDEX=2 \
scripts/benchmark-locomo-convo2.sh mycelium
```

Replay copies the original source, episode, claim, and raw-log artifacts into a clean run store, resets
only downstream Dream assignments and links, and then runs the current routing and materialization code.
Use a normal run without `REPLAY_STORE` for the final end-to-end check.

For a projection-only comparison, add `REPLAY_ASSIGNMENTS=1`. This preserves the fixture's primary
claim-to-page assignments, skips routing and reconsolidation, and rebuilds page taxonomy and Markdown in
a clean store. Use the same replay store for both sides of a renderer comparison.

For retrieval-only comparisons against an exact completed store, use `FROZEN_STORE` instead. The
benchmark copies that store verbatim, skips ingestion and Dream, and runs only retrieval and answering.
Set `INCLUDE_RETRIEVAL_CONTEXT=1` when synthetic benchmark contexts need qualitative inspection:

```bash
FROZEN_STORE=benchmark_runs/<baseline>/stores/conv-30 \
INCLUDE_RETRIEVAL_CONTEXT=1 QA_MODEL=gemma4:12b MEMORY_MODEL=gemma4:12b \
RUN_TAG=retrieval-check SAMPLE_INDEX=2 DREAM_POLICY=none \
scripts/benchmark-locomo-convo2.sh mycelium
```

Benchmark diagnostics include source → active claim → assigned wiki → rendered context evidence-survival
rates. The benchmark-only `gold_evidence` system answers from the exact labeled source turns and is useful as
a qualitative encoding/retrieval control, not a numerical ceiling: cited turns can omit adjacent context and
technically correct paraphrases can still receive low scorer values. Neither diagnostic path exposes labels to
the production memory system.

## License

Mycelium is available under the MIT License. See [LICENSE](LICENSE).
