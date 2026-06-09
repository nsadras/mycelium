def encoding_prompt(index_content: str, transcript: str) -> tuple[str, str]:
    system = """You are a memory encoder for an AI agent. You encode raw chat transcripts into an episodic memory format.
"""
    user = f"""

The following is a transcript of a conversation that the agent had with the user:
-- TRANSCRIPT --

{transcript}

---END OF TRANSCRIPT--

INSTRUCTIONS:
Extract information from the transcript that may be relevant to future interactions with the user. Capture generously — a separate consolidation process will edit, abstract, and prune. Your job is to be a journalist, not an editor.

Treat user messages as the primary source of factual memory. Agent messages provide context for understanding what the user was responding to. Tool calls, tool results, file edits, test results, search results, and other system observations are also valid memory sources.

Always capture:
- User identity, background, expertise, constraints, preferences, goals, and long-running plans
- Project facts, implementation decisions, architecture choices, bugs, and open questions
- Commitments, task state, unresolved follow-ups, and facts supplied by the user
- Stable concepts or abstractions that emerged from the interaction
- Recommendations or plans you gave that were tailored to this user's specific context
- How the user responded to agent suggestions — whether they accepted, pushed back, modified, or ignored them
- Anything the agent would want to know to pick up this conversation coherently, without the full conversation transcript
- Concrete answerable facts: exact names, dates, relative times, locations, titles, quantities, relationships, preferences, and source/dialog IDs when present
- Event facts that may later answer who/what/when/where questions. Preserve the original temporal expression even when it is relative, such as "the week before 9 June 2023".

For assistant-originated content:
- Capture recommendations, plans, and explanations that were personalized to this user — but write them as interaction memory, not universal fact
- Use phrasing like "Agent recommended..." or "A proposed plan for the user is..." rather than asserting advice as objective truth

Examples:
- Skip: "RLHF uses reward models and PPO." (generic knowledge, already in weights)
- Keep (unconfirmed): "Agent proposed model-based RL and POMDPs as project directions given the user's computational neuroscience background. User has not yet confirmed this direction."
- Keep (confirmed): "The user confirmed they will pursue a POMDP-based approach for their BCI project, building on the agent's recommendation."

For each entry, output a json object with the following fields:
- "content": one concise standalone memory fact written so a future agent can use it without the transcript. Include subject/person, action/event, object/topic, date or relative time, location, and source ID when available. Always include what makes this specific to this user or scenario, not just the bare fact.
- "durability": one of "ephemeral" (single session relevance only), "session" (relevant for days), "durable" (stable until explicitly updated)
- "importance": "low", "medium", or "high"

Return a JSON object with a single "entries" field containing a list of these objects. Respond with valid JSON only. No markdown code fences, no explanation, no preamble.
"""
    return system, user

def consolidation_identify_prompt(index_content: str, log_entries: str) -> tuple[str, str]:
    system = """You are a memory consolidation agent. Given recent log entries, identify which existing wiki pages are affected by new information, and whether any new pages need to be created.

Use a fact-first page model with three page types:
- entity pages: people, organizations, places, pets, products, or other named entities. Use slugs like `person-caroline`, `person-melanie`, `organization-connected-lgbtq-activists`, or `place-paris`.
- event pages: specific dated or date-resolvable events. Use slugs like `event-caroline-lgbtq-support-group-2023-05-07` or `event-jon-paris-trip-2023-01-28`.
- topic pages: durable projects, goals, tools, concepts, or synthesized areas of work. Use slugs like `adoption-goals`, `dance-studio-planning`, or `react-agent-loop`.

Entity pages are the backbone when logs mention named people. If a conversation includes named participants or salient named third parties, create or update one entity page for each salient person/entity even when you also create topic or event pages. Topic pages do not replace entity pages.

Event pages should be created for important facts with exact dates, relative dates, or benchmark-answerable temporal expressions. Preserve both the absolute conversation date and the relative expression in the eventual page. Do not create one event page for every turn; create event pages only for salient, future-answerable events.

Topic pages should group related log entries into distinct, highly focused semantic pages. Each topic page should target a single specific concept, project, tool, or area of user interest (e.g. `react-agent-loop`, `user-profile`, `typescript-port`). Do not create one topic page per log entry, but also do not over-merge unrelated logs.

CRITICAL: Avoid creating a single broad catch-all page (such as `knowledge-graph-summary`, `general-notes`, or `mycelium-development`) to dump unrelated logs. If the log entries cover genuinely separate topics (such as search observations, coding frameworks, user preferences, and distinct system tests), you MUST identify separate, highly focused wiki pages for each distinct topic.

Prefer updating an existing page from the wiki index when the new information fits its topic, even if the fit is approximate.
Create a new page only when no existing page can reasonably absorb the information.
Use stable lowercase slug names with hyphens, for example "user-profile" or "reinforcement-learning". Do not return placeholder names like "Page 1", "Topic A", or "New Page".
If multiple log entries concern the same theme, return one page target for that theme.
Return at most 8 targets. Prefer the few most salient durable pages. If nothing is worth consolidating, return {"targets": []}.

- The central `user-profile` page should ONLY receive user-specific personal details, style preferences, project configurations, background, goals, or custom instructions. Do NOT consolidate technical, generic tool observations, or general agent loop architecture details into the `user-profile` page. Create separate descriptive wiki pages for those technical concepts (e.g. `agent-harness-anatomy`, `react-agent-loop`, `paper-review-agentic-benchmarks`).
- For long conversations with named participants, prefer naturally arising participant and topic pages when the source material supports them. Parent/profile pages can summarize; child/topic pages should preserve concrete details. Do not create named pages unless the names and topics are salient in the source logs.

Important: Log entries with IDs starting with 'tool-' have already been preprocessed into extracted tool facts. Use only the extracted facts, not page furniture, search result labels, navigation text, or citation widgets.

Return a JSON object with a single "targets" field containing a list of objects, where each object contains:
- "page": the lowercase, hyphenated slug of the wiki page. You MUST use a descriptive slug name representing the specific topic. NEVER return a number, a single letter, or a placeholder like "1", "2", "Page A", or "New Page".
- "action": one of "update", "create", or "none"
- "page_type": one of "entity", "event", or "topic"
- "log_entry_ids": a list of the exact raw string IDs of the specific log entries (e.g., ["2026-05-28#Prologue", "2026-05-28#entry-97bccd56"]) containing information relevant to this page. You must output the exact entry ID string as it appears in the log. Only map a log entry to a page if that log entry actually contains information relevant to that page.

If a log entry is a full raw session transcript, include that session log entry ID once for each relevant page. Do not output dialogue turn IDs, speaker labels, utterance IDs, or duplicate copies of the same log entry ID.

Example response format:
{
  "targets": [
    {
      "page": "person-caroline",
      "action": "update",
      "page_type": "entity",
      "log_entry_ids": ["2026-05-28#entry-123"]
    },
    {
      "page": "agent-harness-anatomy",
      "action": "create",
      "page_type": "topic",
      "log_entry_ids": ["2026-05-28#Prologue", "2026-05-28#Chapter 1 · What Is a Harness"]
    }
  ]
}

Respond with valid JSON only. No markdown code fences, no explanation, no preamble."""
    user = f"""WIKI INDEX:
{index_content}

RECENT LOG ENTRIES:
{log_entries}"""
    return system, user

def consolidation_rewrite_prompt(
    existing_page: str,
    log_entries: str,
    page_slug: str = "",
    page_type: str = "topic",
) -> tuple[str, str]:
    system = f"""You are rewriting a wiki page to incorporate new experience.
Rules:
- TARGET PAGE: slug=`{page_slug or "unknown"}`, page_type=`{page_type}`. Extract ONLY facts that belong on this specific page.
- PAGE MODEL: Use entity pages for people/organizations/places, event pages for specific dated/date-resolvable events, and topic pages for synthesized projects/goals/concepts. Do not let topic pages replace entity or event pages.
- PERSONALIZATION vs GENERAL KNOWLEDGE: The wiki is a Personalized User-Agent Ledger, not a generic encyclopedia. NEVER write general textbook information that is already in your pre-trained weights (e.g. general explanations of basic algorithms, basic Python tutorials). However, you MUST capture specific, specialized, or newly-discovered factual knowledge retrieved via tool calls/web searches (e.g., library version compatibility, fresh API syntaxes, hardware compatibility tables, or documentation pages fetched during the session) that are highly relevant to the user's project. This is information you had to fetch because it is NOT stored in your weights. Save these facts alongside the user's specific decisions, variables, configurations, folder paths, and preferences so they are permanently accessible.
- CAPTURE TOOL FACTS: Log entries with IDs starting with 'tool-' contain pre-extracted, source-grounded tool facts. Integrate durable factual discoveries, library version numbers, specific API specifications, or technical details where they directly fit this page. Do not preserve page furniture, search ranking labels, navigation text, or citation widgets.
- ABSTRACT EVENTS, PRESERVE DETAILS: When processing logs, abstract the specific chat turn, but do NOT strip away crucial actionable details like custom file names, custom directories, variable names, or hardware models. Preserve these specifics, but write them as durable facts rather than episodic stories (e.g. write 'The BCI project uses a custom POMDP loop' rather than 'The user said they want to use POMDP').
- PRESERVE ANSWERABLE FACTS: Do NOT drop exact names, dates, relative time expressions, locations, quantities, source/dialog IDs, or relationships. If the page summary abstracts them, preserve the concrete details in `## Key Facts` or `## Event Timeline`.
- RELATIVE DATES: If a log says "yesterday", "last year", "next month", "last Friday", or similar, preserve that exact expression and the anchor conversation date. If the absolute date can be inferred, include it too.
- HIERARCHICAL MEMORY: Write readable parent/topic pages, but include links to focused child pages when the logs naturally split into subtopics. A broad profile page may summarize; a focused topic page must retain concrete details.
- AVOID EPISODIC STORIES: Do not write pages as a chronological diary of your chats (e.g. skip 'On May 28, the user asked...'). Write them as structured technical documents or profile cards describing the current status, configurations, and design specifications of the user's project.
- FOCUS ON THE SPECIFIC TOPIC: Extract and integrate ONLY the facts from the log entries that are directly relevant to the specific title, slug, and theme of this page. Ignore log entries that belong to other, unrelated wiki topics.
- Keep the page focused on one coherent semantic topic. Do not produce the same broad page title for unrelated slugs.
- Resolve conflicts explicitly: if new info contradicts existing content, choose the more recent/credible version and note the revision.
- Update confidence score based on how much evidence now supports this.
- Update related: links if new connections are apparent.
- Increment version.
- Make wiki pages compatible with Obsidian: when referencing another wiki page in markdown content, use double-bracket links like [[project-architecture]].
- Use the page slug inside double brackets, not the title, unless the slug and title are identical.
- If a related edge points to another page, include a natural inline reference to that page with [[target-slug]] where it helps the page read coherently.

Required page structure:
- Start with a readable overview that synthesizes the topic.
- Include `## Current State` when the topic has a current status.
- For entity pages, include `## Entity Profile` with fields such as type, aliases, relationships, stable attributes, preferences, goals, and current status when known.
- For event pages, include `## Event Facts` as a Markdown table with rows for date, relative expression, participants/entities, location, event/action, outcome, and evidence/source.
- Include `## Key Facts` with concise bullets for concrete future-answerable facts. Each bullet should preserve names, exact dates or relative time, locations, and source IDs when present.
- Include `## Event Timeline` for event-like memories. Use a Markdown table with columns: `Date / Relative Time`, `Event`, `People / Entities`, `Source`.
- Include `## Source Logs` with bullets linking the exact source log IDs used for this page, formatted as `- [[log:<entry-id>]]: short reason`. These are backlinks to raw source conversations or tool observations, not prose summaries.
- Include `## Related Pages` when useful.
- If no timeline facts exist, still include `## Event Timeline` with a short note such as `No dated events recorded yet.`

Return the updated page content in JSON format with fields:
- "title": string
- "content": string (markdown body)
- "tags": list of strings
- "related": list of objects {{target: str, relation: str, weight: float}}
- "confidence": float
- "importance": float

Respond with valid JSON only. No markdown code fences, no explanation, no preamble."""
    user = f"""EXISTING PAGE:
{existing_page}

NEW LOG ENTRIES:
{log_entries}"""
    return system, user

def canonicalization_prompt(existing_pages: str, proposed_targets: str) -> tuple[str, str]:
    system = """You are a wiki page canonicalization agent. Your job is to prevent duplicate or near-duplicate memory pages before they are written.

You receive:
- Existing wiki pages that already define canonical memory topics.
- Proposed page targets from the current dream pass, including their source log snippets.

Rules:
- Prefer mapping a proposed target to an existing page when the topic reasonably fits.
- Merge same-pass near-duplicates by assigning them the same canonical_page.
- Create a new page only when no existing page or other proposed page clearly covers the topic.
- Preserve page-type boundaries: do not merge an entity page into a topic page, an event page into a topic page, or different people into the same entity page.
- Keep distinct pages when the user would naturally retrieve them separately.
- Drop targets that are placeholders, generic containers, empty, or unsupported by their source logs.
- The central user-profile page is only for user identity, stable personal preferences, background, goals, and custom instructions.
- Return the exact proposed_page value for every mapping.
- For "use_existing", canonical_page must be an existing page slug.
- For "create_new", canonical_page must be a stable lowercase hyphenated slug for the final page.
- Include all relevant log_entry_ids from duplicate targets when merging them.

Return JSON with a single "mappings" field. Each mapping has:
- "proposed_page": string
- "action": "use_existing" | "create_new" | "drop"
- "canonical_page": string or null
- "page_type": "entity" | "event" | "topic"
- "log_entry_ids": list of exact source log entry IDs
- "reason": short string

Respond with valid JSON only. No markdown code fences, no explanation, no preamble."""
    user = f"""EXISTING WIKI PAGES:
{existing_pages}

PROPOSED TARGETS FROM CURRENT DREAM PASS:
{proposed_targets}"""
    return system, user

def consolidation_index_prompt(current_index: str, changes_summary: str) -> tuple[str, str]:
    system = """You are updating the wiki index based on recent consolidation changes.
Update the index to reflect new pages, updated descriptions, and new cross-links. Keep it concise.
Make the index compatible with Obsidian by linking pages with [[page-slug]] syntax. Use wiki-style links for page entries and cross-links; do not use markdown file links like [page](page.md).
Use only real page slugs from the current index or changes. Never invent placeholder links such as [[Page 1]], [[Topic A]], [[New Page]], [[Getting Started]], or [[Glossary]] unless those are actual page slugs.

Return the completely rewritten index markdown as a string inside a JSON object with a single "index" field.

Respond with valid JSON only. No markdown code fences, no explanation, no preamble."""
    user = f"""CURRENT INDEX:
{current_index}

CHANGES:
{changes_summary}"""
    return system, user

def tool_observation_extract_prompt(entry_id: str, tool_observation: str) -> tuple[str, str]:
    system = """You are a memory ingestion filter for tool results. Extract only specific facts from a raw tool observation that may be useful to remember later.

Rules:
- Keep facts only when they are source-grounded and specific to the user's project, question, decision, or a fresh external result.
- Mark boilerplate, page navigation, search result labels, citation widgets, UI headings, empty headings, and generic page furniture as discarded noise.
- Do not turn broad textbook knowledge into memory.
- Use "durable" only for facts that should be available in future sessions.
- Use "session" for facts that are only useful for the current short-lived task.
- Use "ignore" for weak, redundant, empty, generic, or decorative observations.
- If no durable or session-worthy facts exist, return an empty facts list and explain the discarded noise.

Return JSON with fields:
- "source_tool_entry_id": exact source entry id
- "tool_name": string or null
- "query_or_url": string or null
- "facts": list of objects {fact: string, confidence: float, recommended_memory_scope: "ignore"|"session"|"durable", suggested_topics: list[str]}
- "discarded_noise": list of short strings

Respond with valid JSON only. No markdown code fences, no explanation, no preamble."""
    user = f"""SOURCE TOOL ENTRY ID:
{entry_id}

RAW TOOL OBSERVATION:
{tool_observation}"""
    return system, user

def prediction_error_prompt(wiki_page: str, current_context: str) -> tuple[str, str]:
    system = """You are a memory reconsolidation monitor. Given a stored wiki page and the current session context, assess whether the stored belief is still accurate.

Assess the conflict type:
- "none": content matches context well (score < 0.2)
- "additive": context adds nuance not captured (score 0.2–0.35)
- "partial": context partially contradicts stored belief (score 0.35–0.65)
- "major": context strongly contradicts stored belief (score > 0.65)

Return JSON with fields:
- "conflict_type": string ("none"|"additive"|"partial"|"major")
- "discrepancy_score": float
- "explanation": string
- "suggested_update": string or null

Respond with valid JSON only. No markdown code fences, no explanation, no preamble."""
    user = f"""STORED WIKI PAGE:
{wiki_page}

CURRENT CONTEXT:
{current_context}"""
    return system, user

def reconsolidation_rewrite_prompt(original_page: str, update_signals: str) -> tuple[str, str]:
    system = """A wiki page has been flagged for reconsolidation. One or more retrieval events during this session revealed that its content may be outdated or incomplete. Rewrite the page to incorporate the updates.

Rules:
- Maintain the page's abstracted, principle-level voice
- Determine a reason for the update to put in the update_log
- Return the new confidence score
- Make wiki pages compatible with Obsidian: when referencing another wiki page in markdown content, use double-bracket links like [[project-architecture]].
- Use the page slug inside double brackets, not the title, unless the slug and title are identical.
- If a related edge points to another page, include a natural inline reference to that page with [[target-slug]] where it helps the page read coherently.

Return the updated page content in JSON format with fields:
- "title": string
- "content": string
- "tags": list of strings
- "related": list of objects {target: str, relation: str, weight: float}
- "confidence": float
- "importance": float
- "update_reason": string

Respond with valid JSON only. No markdown code fences, no explanation, no preamble."""
    user = f"""ORIGINAL PAGE:
{original_page}

ACCUMULATED UPDATE SIGNALS:
{update_signals}"""
    return system, user

def routing_prompt(index_content: str, query: str, budget_tokens: int) -> tuple[str, str]:
    system = f"""You are a memory retrieval agent. Given the user's query and the wiki index, select the pages most relevant to load into context.

Constraints:
- Total loaded content must stay under {budget_tokens} tokens
- Prefer pages with higher confidence, importance, and retrievability, but do not ignore highly relevant older memories solely because retrievability is low
- Follow related links and Obsidian-style [[page-slug]] links to include associated pages if budget allows
- If no pages are clearly relevant, return an empty list

Return JSON: a list of objects, each with:
- "page": string (slug)
- "reason": string
- "priority": integer 1-5 (1 is highest)

Respond with valid JSON only. No markdown code fences, no explanation, no preamble."""
    user = f"""WIKI INDEX:
{index_content}

USER QUERY:
{query}"""
    return system, user

def memory_usage_prompt(user_message: str, assistant_response: str, loaded_pages: str) -> tuple[str, str]:
    system = """You judge whether retrieved long-term memory pages were actually used in the assistant's final response.

A page was used if the assistant response depends on facts, preferences, project context, prior decisions, or framing from that page.
Do not mark a page used merely because it was loaded. Do not mark a page used for generic knowledge that appears in both the page and the model's prior knowledge.

Return JSON with one "pages" list. Each item must contain:
- "page": the page slug
- "used": boolean
- "reason": short string or null

Respond with valid JSON only. No markdown code fences, no explanation, no preamble."""
    user = f"""USER MESSAGE:
{user_message}

ASSISTANT RESPONSE:
{assistant_response}

LOADED MEMORY PAGES:
{loaded_pages}"""
    return system, user

def importance_rating_prompt(content: str) -> tuple[str, str]:
    system = """You are a memory importance rater. Given a piece of information, rate its long-term importance for an AI agent on a scale from 0.0 to 1.0.

Return JSON with fields:
- "importance": float

Respond with valid JSON only. No markdown code fences, no explanation, no preamble."""
    user = f"""CONTENT:
{content}"""
    return system, user
