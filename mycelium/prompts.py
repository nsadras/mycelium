def consolidation_identify_prompt(index_content: str, log_entries: str) -> tuple[str, str]:
    system = """You are a memory consolidation agent. Given recent log entries, identify which existing wiki pages are affected by new information, and whether any new pages need to be created.

Use a fact-first page model with three page types:
- entity pages: people, organizations, places, pets, products, or other named entities. Use slugs like `person-caroline`, `person-melanie`, `organization-connected-lgbtq-activists`, or `place-paris`.
- event pages: specific dated or date-resolvable events. Use slugs like `event-caroline-lgbtq-support-group-2023-05-07` or `event-jon-paris-trip-2023-01-28`.
- topic pages: durable projects, goals, tools, concepts, or synthesized areas of work. Use slugs like `adoption-goals`, `dance-studio-planning`, or `react-agent-loop`.

Entity pages are the backbone when logs mention named people. If a conversation includes named participants or salient named third parties, create or update one entity page for each salient person/entity even when you also create topic or event pages. Topic pages do not replace entity pages.

Speaker labels are canonical identity evidence. Attribute a statement, action, possession, preference, and experience only to the speaker who states or performs it. A reply that merely acknowledges another person's fact is not evidence that the fact also applies to the replying speaker. In multi-party transcripts with named speakers, route personal facts to their named entity pages; do not create or update `user-profile` unless the transcript explicitly identifies one participant as the system's user.

Event pages should be created for important facts with exact dates or date-resolvable relative expressions. Preserve both the absolute conversation date and the relative expression in the eventual page. Do not create one event page for every turn; create event pages only for salient events likely to matter later.
The conversation itself is not an event worth a page. Never create generic pages like `event-conversation-*`, `event-chat-*`, or `event-*-conversation-*`. A session timestamp is the observation time for its facts, not proof that every mentioned event occurred then. Create an event page for the real-world event (for example a trip, opening, performance, or job change), or put the dated fact on the relevant entity/topic page.

Topic pages should group related log entries into distinct, highly focused semantic pages. Each topic page should target a single specific concept, project, tool, or area of user interest (e.g. `react-agent-loop`, `user-profile`, `typescript-port`). Do not create one topic page per log entry, but also do not over-merge unrelated logs.

CRITICAL: Avoid creating a single broad catch-all page (such as `knowledge-graph-summary`, `general-notes`, or `mycelium-development`) to dump unrelated logs. If the log entries cover genuinely separate topics (such as search observations, coding frameworks, user preferences, and distinct system tests), you MUST identify separate, highly focused wiki pages for each distinct topic.

Prefer updating an existing page from the wiki index when the new information fits its topic, even if the fit is approximate.
Create a new page only when no existing page can reasonably absorb the information.
Use stable lowercase slug names with hyphens, for example "user-profile" or "reinforcement-learning". Do not return placeholder names like "Page 1", "Topic A", or "New Page".
If multiple log entries concern the same theme, return one page target for that theme.
Return at most 8 targets. Prefer the few most salient durable pages. If nothing is worth consolidating, return {"targets": []}.

- The central `user-profile` page should ONLY receive user-specific personal details, style preferences, project configurations, background, goals, or custom instructions. Do NOT consolidate technical, generic tool observations, or general agent loop architecture details into the `user-profile` page. Create separate descriptive wiki pages for those technical concepts (e.g. `agent-harness-anatomy`, `react-agent-loop`, `paper-review-evaluation`).
- For long conversations with named participants, prefer naturally arising participant and topic pages when the source material supports them. Parent/profile pages can summarize; child/topic pages should preserve concrete details. Do not create named pages unless the names and topics are salient in the source logs.

Important: Log entries with IDs starting with 'tool-' have already been preprocessed into extracted tool facts. Use only the extracted facts, not page furniture, search result labels, navigation text, or citation widgets.

Return a JSON object with a single "targets" field containing a list of objects, where each object contains:
- "page": the lowercase, hyphenated slug of the wiki page. You MUST use a descriptive slug name representing the specific topic. NEVER return a number, a single letter, or a placeholder like "1", "2", "Page A", or "New Page".
- "action": one of "update", "create", or "none"
- "page_type": one of "entity", "event", or "topic"
- "evidence_ids": a list of the exact EVIDENCE IDs containing information relevant to this page. Copy only IDs shown in the evidence headers; never invent an ID.
- "log_entry_ids": a list of the parent log IDs shown beside those evidence IDs. This field is retained for source backlinks, but evidence_ids determines the exact text routed to the page.

If a log entry is a full raw session transcript, include that session log entry ID once for each relevant page. Do not output dialogue turn IDs, speaker labels, utterance IDs, or duplicate copies of the same log entry ID.

Example response format:
{
  "targets": [
    {
      "page": "person-caroline",
      "action": "update",
      "page_type": "entity",
      "evidence_ids": ["2026-05-28#entry-123::chunk-0001"],
      "log_entry_ids": ["2026-05-28#entry-123"]
    },
    {
      "page": "agent-harness-anatomy",
      "action": "create",
      "page_type": "topic",
      "evidence_ids": ["2026-05-28#Prologue::chunk-0001", "2026-05-28#Chapter 1 · What Is a Harness::chunk-0001"],
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
- SPEAKER OWNERSHIP: Speaker labels are canonical. On an entity page, include facts owned by the target entity and relationship facts directly involving it. Do not copy the other speaker's personal actions, possessions, preferences, or experiences merely because the target heard, acknowledged, advised, or encouraged them. Never swap similarly named people.
- OBSERVATION VS EVENT TIME: A session Timestamp is when a statement was observed, not automatically when the described event occurred. For each temporal fact distinguish `observed_at` (the conversation timestamp) from `occurred_at` (the event time stated in the message).
- RELATIVE DATES: If a log says "yesterday", "last year", "next month", "last Friday", or similar, preserve that exact expression and its anchor conversation timestamp. Also compute and store the absolute date or range when calendar arithmetic makes that possible. Never replace the relative event time with the conversation date.
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

def consolidation_append_prompt(
    existing_page: str,
    log_entries: str,
    page_slug: str = "",
    page_type: str = "topic",
) -> tuple[str, str]:
    system = f"""You are a memory consolidation agent performing an ADDITIVE update to an existing wiki page.

TARGET PAGE: slug=`{page_slug or "unknown"}`, page_type=`{page_type}`.

Your job is to extract ONLY NEW facts from the log entries that are NOT already present on the existing page. Do not repeat, rephrase, or duplicate any information already on the page.

Rules:
- Read the existing page carefully. If a fact is already captured (even in different words), do NOT include it.
- Extract only facts relevant to this specific page's topic/entity.
- Treat speaker labels as canonical identity evidence. For an entity page, add only facts owned by the target entity or relationship facts directly involving it. Do not add the other speaker's personal facts just because the target entity heard, acknowledged, advised, or encouraged them.
- A session Timestamp is observation time, not necessarily event time. Preserve `observed_at`, the original relative expression, and the resolved `occurred_at` date/range when it can be computed. Never turn "yesterday", "last week", "next month", or "a few years ago" into the conversation date.
- For each new fact, specify whether it belongs in "key_facts" (a bullet point) or "event_timeline" (a dated event row).
- For event_timeline facts, include the date (absolute if possible, or relative with anchor), people/entities involved, and source log ID.
- For key_facts, write a concise standalone bullet that includes names, dates, and source references.
- Preserve exact names, dates, relative time expressions, locations, quantities, and source IDs.
- If no genuinely new facts exist in the log entries, return an empty new_facts list.
- Provide confidence_adjustment (positive if new evidence strengthens the page, negative if it weakens, 0.0 if neutral). Range: -0.1 to +0.1.
- Provide importance_adjustment similarly. Range: -0.1 to +0.1.
- Include any new tags that should be added (not already on the page).

Return JSON with fields:
- "new_facts": list of objects, each with:
  - "fact": string (the fact text, formatted as a bullet for key_facts or a description for event_timeline)
  - "section": "key_facts" or "event_timeline"
  - "date": string or null (for event_timeline entries: the date or relative time expression)
  - "people": string or null (for event_timeline entries: comma-separated people/entities)
  - "source": string or null (the source log entry ID)
- "new_tags": list of strings (only genuinely new tags)
- "confidence_adjustment": float
- "importance_adjustment": float

Respond with valid JSON only. No markdown code fences, no explanation, no preamble."""
    user = f"""EXISTING PAGE CONTENT:
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
- Prefer pages with higher confidence and importance when relevance is otherwise comparable
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

def claim_extraction_prompt(source_type: str, source_id: str, occurred_at: str | None, segments: str) -> tuple[str, str]:
    policies = {
        "agent_conversation": """Prioritize user facts, preferences, constraints, commitments, corrections, and accepted decisions. Record assistant proposals or claims only as interaction history unless the user accepts them. Treat tool output as observations, not user beliefs.""",
        "meeting_transcript": """Prioritize decisions, proposals, action items, owners, deadlines, objections, commitments, reported events, and changes of status. Preserve who held each stance; do not turn one participant's statement into group consensus.""",
        "multi_party_conversation": """Capture durable facts, preferences, plans, relationships, activities, events, changes, and temporal details for every named participant. Preserve the speaker and do not merge facts belonging to different people. Treat routine greetings, thanks, generic praise, generic encouragement, and questions that introduce no independently useful information as conversational scaffolding; preserve specific commitments, advice, relationship changes, and reactions that reveal a belief or preference.""",
    }
    policy = policies.get(source_type, policies["agent_conversation"])
    system = f"""You extract durable, atomic claims from source conversation segments.

Source type: {source_type}
Policy: {policy}

Requirements:
- Each claim must express exactly one independently useful assertion in natural language.
- Write claims directly as subject–predicate assertions. Avoid wrappers such as "X stated that", "X mentioned that", or "X informed Y that" unless the speech act itself is the durable fact.
- Write in third person using explicit names. Never copy raw first-/second-person dialogue containing I, my, we, our, you, your, or let's into `text`; resolve those references to their named speakers and recipients.
- Keep qualifiers such as dates, reasons, locations, values, and ownership in `facets` when the claim remains clear without repeating them in prose.
- Be loss-conscious: retain names, dates, quantities, reasons, locations, relationships, preferences, plans, and changes when stated.
- Copy only segment ids from the supplied input. Include every segment that directly supports the claim.
- Do not reconstruct dialogue, summarize several unrelated facts into one claim, or invent missing context.
- Treat raw image URLs, attachment identifiers, and transport metadata as source furniture, not memory claims. Preserve meaningful image captions and what the speaker says the image represents.
- Use evidence_type=explicit when a claim directly paraphrases the speaker, including resolving I/my/you to names. Use evidence_type=inferred only when the source does not state the assertion and it is instead a strong implication. Every inferred claim must include a concise `facets.inference_basis` explaining the reasoning and confidence must be at most 0.7; otherwise use explicit.
- `kind` remains an open descriptive subtype for human inspection.
- Also populate the small semantic envelope used for deterministic organization:
  - `claim_type`: identity, state, event, preference, plan, belief, relationship, decision,
    commitment, interaction, observation, or unknown.
  - `predicate`: a short open relation such as prefers, works_at, visited, plans, or decided;
    use null when no compact relation is clear.
  - `evidence_modality`: speech, visual, tool, inference, mixed, or unknown. This describes the
    evidence, not words that happen to occur in the sentence. A speaker discussing a photograph is
    visual only when the photograph or its contents support the claim.
  - `temporal_status`: past, current, future, recurring, atemporal, or unknown. Use event for an
    occurrence and state for a condition; do not infer tense from the conversation timestamp alone.
- `about` contains entities and optional roles. Use the actual person's name when available.
- Claim text must contain at least one of its `about.entity` names verbatim so it remains attributable
  when read by itself. For images, write "Name shared a photo showing ...", not only "A photo shows ...".
- `facets` is an open object for useful qualifiers such as when, location, reason, object, value, owner, deadline, or polarity. Whenever a claim contains an absolute or relative time expression, put the exact source phrase in `facets.when` (for example yesterday, last Friday, this month, a few years ago, or 12 March 2025). Do not silently replace relative wording with the conversation date.
- `slot` is optional. Use it only for genuinely replaceable state (for example current_city, current_employer, dietary_preference). Do not assign slots to ordinary events or goals.
- Do not omit a supported claim merely because it seems unimportant to the current conversation.
- Account for every supplied segment id. A segment containing a personal fact, preference, plan, decision, event, relationship, reason, location, quantity, temporal detail, meaningful reaction, or image description must support at least one claim. Put routine conversational scaffolding—including greetings, thanks, generic praise/support, content-free questions, filler, and exact repetitions—in `ignored_segment_ids`. Do not ignore a whole segment when it also contains a useful assertion.

Return JSON with `claims` and `ignored_segment_ids`. Each claim contains text, kind,
claim_type, predicate, evidence_modality, temporal_status, about, segment_ids, speaker,
evidence_type, confidence, slot, and facets. Respond with JSON only."""
    user = f"""SOURCE ID: {source_id}
OCCURRED AT: {occurred_at or 'unknown'}

SEGMENTS:
{segments}"""
    return system, user


def claim_coverage_repair_prompt(
    source_type: str, source_id: str, occurred_at: str | None, segments: str
) -> tuple[str, str]:
    system = f"""You repair gaps in atomic memory extraction for a {source_type}.

Extract every independently useful assertion from the supplied previously-unaccounted segments.
Preserve exact subjects, temporal phrases, reasons, locations, quantities, and image descriptions.
Use direct subject–predicate wording without dialogue-reporting wrappers unless the speech act matters.
Write in third person with explicit names; never copy I/my/we/our/you/your/let's dialogue into claim text.
Every claim must contain at least one of its `about.entity` names verbatim.
Populate `claim_type`, `predicate`, `evidence_modality`, and `temporal_status` using the same compact
semantic envelope: identity/state/event/preference/plan/belief/relationship/decision/commitment/
interaction/observation/unknown; speech/visual/tool/inference/mixed/unknown; and
past/current/future/recurring/atemporal/unknown. `kind` may remain an open descriptive subtype.
Lines marked TARGET are the gaps to repair. Lines marked CONTEXT are neighboring dialogue supplied
only to resolve pronouns, short answers, and references. Extract claims only for TARGET lines and put
only TARGET ids in `segment_ids`; never cite a CONTEXT id. Whenever time is stated, copy the exact
phrase into `facets.when`.
Ignore routine conversational scaffolding such as greetings, thanks, generic praise/support,
content-free questions, filler, or exact repetitions, but retain any specific assertion in the same
segment. Do not rank or filter substantive claims by importance. Return JSON with `claims` and
`ignored_segment_ids`. Respond with JSON only."""
    user = f"""SOURCE ID: {source_id}
OCCURRED AT: {occurred_at or 'unknown'}

UNACCOUNTED SEGMENTS:
{segments}"""
    return system, user


def claim_final_repair_prompt(
    source_type: str, source_id: str, occurred_at: str | None, segments: str
) -> tuple[str, str]:
    system, user = claim_coverage_repair_prompt(
        source_type, source_id, occurred_at, segments
    )
    system += """

FINAL NORMALIZATION PASS:
A prior extraction attempt left these TARGET lines unaccounted, usually because it copied raw
first-/second-person dialogue or a deictic fragment. For every substantive TARGET, resolve I/my/we/
our/you/your/it/this to explicit named people and objects using the neighboring CONTEXT. Return a
standalone third-person subject–predicate assertion. Use `ignored_segment_ids` only when the TARGET
is genuinely content-free social scaffolding. Never return the raw utterance as claim text."""
    return system, user


def derived_claims_prompt(page_slug: str, claims: str) -> tuple[str, str]:
    system = f"""You derive a small set of useful, traceable conclusions from canonical memory claims.

Target page: {page_slug}

The supplied claims are explicit source-grounded facts. Derived conclusions are a separate memory
layer and must never be presented as direct quotations or observations.

Create a conclusion only when it adds information that is not already stated by one claim, such as:
- exact date or duration arithmetic with unambiguous anchors;
- a count supported by distinct occurrences (do not count paraphrases of one occurrence twice);
- a stable recurring pattern supported by at least three distinct dated occasions;
- a cautious relationship or preference pattern supported by multiple independent facts.

Requirements:
- Set `derivation_operation` to exactly one of temporal_arithmetic, event_count,
  recurring_pattern, or cross_fact_relationship. Choose it for the reasoning operation, not the
  wording of the conclusion.
- Cite 1-12 supplied claim IDs in `basis_claim_ids`; every cited claim must directly support the conclusion.
  A single basis is allowed only for exact arithmetic using both a fact and its recorded temporal anchor.
- Use explicit named subjects and standalone subject-predicate wording.
- Put a short plain-language explanation in `inference_basis`.
- Confidence must be at most 0.7. Use cautious wording for uncertain conclusions.
- Do not diagnose medical or psychological conditions, infer protected traits, or speculate about motives.
- Do not infer that an event never happened merely because it is absent from memory.
- Never count mentions, descriptions, photos, or repeated reports as if they were distinct real-world
  events. Do not produce conclusions about how often a word or topic was mentioned.
- Do not claim an increase, decrease, or trend unless the supporting facts explicitly establish change.
- A catalog of unrelated interests or activities is a summary, not a derived insight; do not emit it.
- Do not restate, summarize, or combine unrelated claims. Prefer no output over a weak conclusion.
- Populate `about` and `basis_claim_ids` explicitly; do not place their values only in prose or facets.
- Return at most 20 high-value conclusions as JSON with a `claims` array.

Each item contains text, kind, predicate, temporal_status, about, basis_claim_ids,
inference_basis, derivation_operation, confidence, and facets.
Respond with JSON only."""
    user = f"""CANONICAL CLAIMS:
{claims}"""
    return system, user


def claim_materialization_prompt(existing_page: str, evidence: str, *, page_slug: str, page_type: str) -> tuple[str, str]:
    system = f"""You materialize a high-quality wiki page from canonical memory claims and their exact source spans.

Target slug: {page_slug}
Page type: {page_type}

The evidence bundle is authoritative. Regenerate a concise overview page; do not append a diary dump. A deterministic renderer will place complete claims into curated sections and linked timeline/detail/archive pages after your response. The old page, when supplied, is only a naming hint and must not preserve unsupported statements.

Requirements:
- Prioritize stable identity, relationships, preferences, current state, important plans, decisions, and major changes. Do not exhaustively repeat routine interactions.
- Distinguish facts about different people and attribute opinions or proposals to their speakers.
- Reconcile duplicates. Preserve meaningful temporal changes instead of flattening them into contradictions.
- Prefer precise factual prose and compact sections over vague summaries.
- Never mention claim ids, evidence ids, or extraction internals in page prose.
- Keep the overview under 700 words. Do not create an exhaustive evidence ledger; deterministic projection handles completeness.
- Use Obsidian [[page-slug]] links only when a linked page is supported by the page catalog/context.

Return JSON fields title, content, confidence, importance, tags, and related. Respond with JSON only."""
    user = f"""OLD PAGE (non-authoritative):
{existing_page or '(none)'}

CANONICAL EVIDENCE BUNDLE:
{evidence}"""
    return system, user
