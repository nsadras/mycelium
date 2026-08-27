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

### Memory lifecycle

Encoding preserves the complete raw transcript, splits it into exact source segments, and extracts atomic
claims in one logical pass. Each claim cites its supporting segment IDs and is persisted immediately with a
`pending` disposition. This is durable short-term memory: retrieval can use relevant pending or deferred
claims immediately, but labels them as recent and unconsolidated rather than presenting them as canonical
wiki knowledge.

Dream is the only transition from short-term claims into the wiki. Source-structure policy first records
assistant/system exclusions and extraction rejections as typed non-wiki retention—not as deferred or
canonical claims. The scope planner then considers pending claims plus explicit deferred evidence, discovers
sparse durable entities, resolves early descriptions against later names, assigns every admitted claim one
semantic owner, and resolves structured meeting-speaker occurrences to explicit entity IDs. Deterministic
code validates the structured plan and its cited evidence; it does not use claim keywords, lexical overlap,
or title matching to infer semantic identity or ownership. When a new entity materializes, a bounded second
pass revisits its persisted source/cohort/reference neighborhood, including older You-owned claims, so scope
can change without whole-store or token-overlap reactivation. The owner's typed
section is derived deterministically
from claim semantics. A second presentation layer groups compatible placed claims into persisted, grounded
`ConsolidatedFact` records; wiki pages render those concise facts while retaining every member claim and exact
source reference. When current evidence cannot establish a page or owner,
the claim becomes `deferred` instead of being discarded or permanently unassigned. A later Dream can revisit
it alongside newly accumulated evidence.

Dream readiness becomes true at 20 pending/retryable claims or when the oldest has waited 24 hours. This is
advisory until a user explicitly runs Dream or a caller invokes the run-if-ready API.
Deferred claims receive a broader review after seven days. Queue thresholds only choose when to invoke Dream;
they do not introduce another consolidation path. Failed routing remains retryable, and manual assignment
uses the same placement and deterministic materialization records.

Page identity lives in `artifacts/entities/`, where a resolved identity may remain `provisional` before it
has enough evidence for a page. Entity-creation and participant decisions live in
`artifacts/entity-resolution-decisions/`; structured subject, object, context, and canonical-owner endpoints
live in `artifacts/entity-references/`; scope neighborhoods live in `artifacts/scope-cohorts/`; typed source
exclusions live in `artifacts/retention-records/`. Claim ownership and its append-only rationale live in
`artifacts/placements/` and `artifacts/scope-decisions/`; editable display statements live in
`artifacts/consolidated-facts/`. Named meeting participants also receive source-grounded encounter records,
so a useful Person page can exist before the system knows enough to assert a profile fact. Entity IDs survive
title and slug changes. The seven page types—You, Person, Project, Topic, Organization, Place, and Event—have
stable ordered section contracts. Claims have one canonical owner; explicitly referenced entities normally
become compact reciprocal links. The deliberate exception is a `project_role` relationship: one person-owned
claim and its provenance are projected on both the Person/You page and the Project's stakeholder section, so
either human navigation path is useful without creating two sources of truth. The Wiki inspector exposes the
fact synthesis and scope audit, edits fact text and scope, and can group or split facts while leaving source
claims intact. Prompt rendering deduplicates a role if both endpoint pages are retrieved. Tool and web evidence
is labeled and kept in Research & References (or Event evidence).

When a new claim may update existing memory, Dream compares it with a bounded set of related claims. Additive information routes normally and supporting relationships are linked automatically. Contradictions and supersessions create durable proposals in the Memory Inspector. Until review, both alternatives are withheld from authoritative sections and shown under Needs Review. Approval immediately updates canonical claim links or status and regenerates every affected page; rejection keeps both claims active and unrelated. Retrieval itself is read-only.

The Wiki curation controls edit organization rather than evidence: rename entities, manage aliases, correct a type, move facts between owners or sections, merge duplicate identities, split selected facts, and archive subjects. Generated Markdown is not directly editable; factual correction and source retraction remain claim-level operations.

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

The default memory store is `./mycelium_store`. Because it consists primarily of Markdown and JSON, it can be inspected with normal text tools or opened as a wiki outside the app. Raw logs and claim artifacts are canonical; wiki Markdown is a generated view and should not be edited directly.

At retrieval time, Mycelium builds a lazy in-memory SQLite FTS5 projection over complete non-derived wiki
pages. BM25 selects two page candidates, title/entity matches can add explicitly mentioned pages, and only
then are page-linked source windows ranked and attached. The index is disposable and automatically refreshes
when page versions or content change; the Markdown wiki remains the durable human-readable memory store.

Every saved chat message has its own server-recorded UTC timestamp. Relative dates are normalized once at
encoding against the timestamp of the exact supporting message; sources without message-level wall-clock
times use their declared source occurrence time. Original wording, bounds, certainty, and semantic role
(event time or deadline) are retained. Temporal questions such as
“What deadlines are due next week?” resolve against the query time and select active claims whose intervals
overlap, then load those claims' wiki pages and provenance-linked source logs. This structured temporal branch
augments page FTS; it does not introduce a second durable index or guess dates for phrases such as “soon.”

Stores with the old slug-owned or terminal-`unassigned` wiki schema are not loaded. Use **Clear Wiki** in the
UI to remove old derived pages and assignments, requeue preserved active claims, then run Dream to rebuild
the entity registry and placements. Older raw, hybrid, or page-rewrite claim schemas still require a full
clear and re-encode.

## Benchmarking ownership and projection changes

Use frozen extraction artifacts when comparing ownership, entity creation, or wiki presentation so claim-extraction
variance does not obscure the result. `REPLAY_STORE` must point to one benchmark case store containing
`artifacts/` and `logs/`:

```bash
REPLAY_STORE=benchmark_runs/<baseline>/stores/conv-30 \
QA_MODEL=gemma4:12b MEMORY_MODEL=gemma4:12b \
RUN_TAG=ownership-replay SAMPLE_INDEX=2 \
scripts/benchmark-locomo-convo2.sh mycelium
```

Replay copies the original source, episode, claim, and raw-log artifacts into a clean run store, resets
only downstream Dream assignments and links, and then runs the current routing and materialization code.
Use a normal run without `REPLAY_STORE` for the final end-to-end check.

For a projection-only comparison, add `REPLAY_ASSIGNMENTS=1`. This requires a fixture already using the
current entity/placement schema. It preserves registry identities and placements, skips ownership planning
and reconsolidation, and rebuilds typed Markdown in a clean store. Use the same replay store for both sides
of a renderer comparison.

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

### Daily-driver artifact benchmark

`benchmarks/fixtures/daily_driver_v1` is a product-oriented complement to LoCoMo. It follows one fictional
user through assistant chats, meeting transcripts, and tool observations, with gold records for source
retention, atomic claims, lifecycle checkpoints, entity ownership, the final wiki, and semantic retrieval.
The fixture emphasizes wiki coherence, correction, source retraction, and avoiding tangential memories;
reference-answer wording is not normative.

The runner executes the fixture rubric as independent artifact-level dimensions and hard gates, records
checkpoint retrieval/answer probes, and reports proposition completeness for multi-assertion source segments.
It also supports extraction replay for downstream semantic iterations and repeated fresh trials for variance.
The renamed/paraphrased and unrelated-domain transfer cases live beside the primary fixture and must not
introduce scenario vocabulary into production routing.

Validate the fixture before changing it or using it as a regression authority:

```bash
uv run python -m benchmarks.mycelium_bench.daily_driver \
  validate benchmarks/fixtures/daily_driver_v1
```

See the fixture README for `run`, `--replay-extraction-store`, `--trials 3`, output artifacts, and transfer
fixture commands.

See `benchmarks/fixtures/daily_driver_v1/REVIEW.md` for the accepted product decisions that govern the fixture
before wiring it into an automated system-under-test runner.

## License

Mycelium is available under the MIT License. See [LICENSE](LICENSE).
