<p align="center">
  <img src="banner.svg" alt="Mycelium Banner" width="100%" />
</p>

# Mycelium

**Persistent memory for people and AI agents.**

Mycelium turns conversations and meeting transcripts into memory you can browse,
review, and bring into future conversations. It includes a local chat assistant,
an organized Markdown wiki, and a Python library for adding memory to your own agents.

The same memory serves two purposes: readable pages help you follow people,
projects, preferences, and decisions over time; relevant statements and source
passages give an agent context for its next response. You can inspect where a
memory came from and correct it as your understanding changes.

## What you can do

- **Carry context across conversations.** Bring past preferences, decisions, and
  ongoing work into a new chat without manually assembling the conversation history.
- **Browse an organized view of your memory.** Build linked pages about the
  subjects discussed in your conversations. Related information can appear on
  more than one page, and retained details remain searchable even without a page.
- **Inspect the assistant's context.** See the memory evidence supplied to a
  response and follow retained statements back to the original conversation.
- **Keep memory useful as things change.** Correct statements, adjust their
  organization, merge duplicate subjects, and review proposed updates when newer
  information appears to change or conflict with earlier memory.
- **Bring meetings into the same memory.** Upload audio, review the transcript and
  speaker names, then build that discussion into your wiki and future chat context.
- **Run locally.** The supplied configuration uses Ollama for chat
  and memory processing, local models for speech, and storage on your machine.
  The Python API lets other agents use the same memory without the web app.

### What to expect

Mycelium is an early-stage project intended for personal use. Memory is selective:
it can omit useful details, confuse identities, or choose awkward organization.
Retrieval and answers can also miss or misinterpret relevant context. Original
sources and review tools help you check and correct the result.

Builds and audio processing take time, especially for longer conversations.
Speed and memory use depend on your hardware, models, and context settings.

## Install and run

### Requirements

- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js 24 and npm
- [Ollama](https://ollama.com/) installed and running
- For meeting audio: FFmpeg on your `PATH` and access to the speaker-detection
  model described [below](#meeting-audio)

Use a Bash shell for the commands below; on Windows, use WSL.

### 1. Install the application

```bash
git clone https://github.com/nsadras/mycelium.git
cd mycelium
uv sync
cd ui
npm ci
cd ..
```

`uv sync` installs all Python dependencies, including the meeting features.
Speech models download when first used; FFmpeg is a separate system dependency.

### 2. Download the configured models

The supplied [mycelium.toml](mycelium.toml) uses
[Gemma 4 12B](https://ollama.com/library/gemma4:12b) for language tasks and
[EmbeddingGemma](https://ollama.com/library/embeddinggemma) for memory search:

```bash
ollama pull gemma4:12b
ollama pull embeddinggemma
```

You can change the models and context settings in `mycelium.toml` to suit your
machine. Model choice affects memory quality as well as speed.

### 3. Start Mycelium

With Ollama running, launch the app from the project root:

```bash
./start.sh
```

Open [localhost:5173](http://localhost:5173). The launcher starts the web UI and
backend together; stop them with Ctrl+C in that terminal.

The default memory directory is `./mycelium_store`. If an older installation
reports a legacy or unsupported store, choose a fresh directory:

```bash
MYCELIUM_STORE=./mycelium_store_fresh ./start.sh
```

Older stores are not migrated automatically. Keep the old directory if you need
its contents; see [storage and exports](DESIGN.md#storage-layout) for details.

## Use the app

1. **Chat normally.** Completed turns are saved automatically.
2. **Click Build Memory.** Mycelium selects useful statements from pending
   conversations and organizes them into wiki pages.
3. **Browse and review.** Open **Wiki** for the organized pages, **Memory** for
   source evidence and proposed changes, or **Logs** for captured conversations.
4. **Start another chat.** The assistant retrieves built memories relevant to the
   conversation and can search further or inspect their source passages.

**Build controls recall across sessions.** Saving a conversation keeps its source;
Build Memory makes selected information searchable. Your current chat also uses
its recent conversation context. Build status shows unfinished work; a later
Build resumes it.

Use the application's review and editing controls to change memory. The Markdown
wiki is also readable outside the app, but its files are generated views and
external edits are not imported. Corrections involving relative dates show the
interpreted dates for review before saving.

### Meeting audio

The **Engram** area handles uploaded recordings. For speaker detection, accept the
conditions for [pyannote's speaker-diarization-community-1 model](https://huggingface.co/pyannote/speaker-diarization-community-1)
and set a Hugging Face token in the project-root `.env` file before starting the app:

```dotenv
HF_TOKEN=your_hugging_face_token
```

Install FFmpeg through your system package manager if needed; `ffmpeg -version`
should work in the shell that launches Mycelium.

1. Upload a recording in **Engram** and click **Process**.
2. Review the transcript and assign speaker names. Correct mistakes before saving.
3. Click **Finalize** to save the reviewed transcript as a memory source and
   generate a meeting summary.
4. Click **Build Memory** to make the meeting's retained information searchable
   and organize it into the wiki.

Transcript and speaker edits lock when finalization starts. Speaker detection and
summaries can fail independently; the UI shows warnings and retry controls.
Deleting an Engram recording does not withdraw memory already saved from it—use
source retraction in **Memory** for that.

See [meeting processing configuration](DESIGN.md#engram-meeting-pipeline) for
CPU/GPU settings, model options, and recovery details.

### Optional web search

To enable the assistant's Ollama web search and fetch tools, add an API key to
`.env` before starting the app:

```dotenv
OLLAMA_API_KEY=your_ollama_api_key
```

Web searches and page fetches contact external services. Their tool calls and
results are visible in chat.

## Use with your own agent

The Python library exposes capture, Build Memory, and retrieval independently.
This example saves a preference, builds memory, and retrieves context for a later
question:

```python
import asyncio

from mycelium import Mycelium, RetrievalRequest, SourceInput


async def main():
    with Mycelium("./agent_memory", config_path="mycelium.toml") as memory:
        await memory.ingest_source(SourceInput(
            transcript="USER: I prefer written project updates before meetings.",
            session_id="preferences",
            idempotency_key="preferences:1",
        ))

        build = await memory.consolidate()
        print(build.report)

        context = await memory.retrieve_context(RetrievalRequest(
            query="How do I prefer to receive project updates?",
        ))
        print(context.rendered_context)


asyncio.run(main())
```

Run it from the project root with the configured Ollama models available. In an
agent loop, retrieve context before generating a response and capture the completed
exchange afterward. Supply `rendered_context` alongside the user request as
evidence; run `consolidate()` when you want to build the newly captured sources.

A store has one writer process at a time. Give a separate agent process its own
store, as in this example. API contracts and the session helper are described in
[DESIGN.md](DESIGN.md#web-sessions-and-direct-library-sessions).

## Settings and access

Edit [mycelium.toml](mycelium.toml) for language, embedding, and speech models,
context limits, and meeting storage. The app reads it on startup. `MYCELIUM_STORE`
selects the main memory directory; Engram's recording storage is configured
separately under `[engram]`.

The app has no sign-in. Use it on your own machine or a trusted private network.
See [private Wi-Fi, Tailscale, and WSL setup](DESIGN.md#remote-access-and-wsl) for
access from another device.

For architecture, storage formats, development checks, and benchmarks, see
[DESIGN.md](DESIGN.md). Evaluation commands are in the
[benchmark guide](benchmarks/README.md).

## License

[MIT](LICENSE).
