# Review Decisions

This document records the product decisions accepted during review of the first fixture draft. These choices
are normative for `daily-driver-v1` unless a later review explicitly changes them.

## Source realism

- The app is configured with the user's display name, Maya Chen. That name is transparent identity metadata
  and an alias of the singleton **You** entity; it is not attributed to a conversation as though the user
  introduced herself there. Her chat and meeting turns use the structural speaker label `User`.
- The simulated assistant behaves like a normal chat assistant. It may suggest, summarize, speculate, or be
  corrected, but it never discusses claim extraction, wiki pages, routing, retention, or other internal memory
  operations.
- Assistant assertions are interaction history unless Maya accepts or independently establishes them.
- A personal activity does not need a contrived proper name. Maya describes recurring interviews with her
  grandmother naturally; the memory system infers a descriptively titled **Family Oral History** Project only
  after the activity has continuity, a scheduled interview, and an explicit next step.

## Page discovery

- The unnamed meeting-memory effort remains deferred after `chat-01`; one plan does not create a Project.
- By `meeting-02`, repeated intent, constraints, accepted decisions, tool research, named collaborators, and
  the explicit name **Lantern** establish the Project.
- **Family Oral History** is an inferred organizational title, not a name Maya used. It remains separate from
  Lantern because Maya explicitly distinguishes the personal interviews from Lantern user research.
- Every durable named person receives a Person page. Priya, Luis, and Grandmother therefore have their own
  pages; their relevant project relationships are visible from both endpoint pages.
- WhisperX remains in Lantern's Research & References section rather than becoming a Topic page.
- LANTERN-42, routine meetings, the oral-history interview, Berkeley, the grocery store, and the dentist
  appointment do not receive pages.

## Ownership and links

- A person's role or responsibility has one canonical person-owned relationship claim. Priya owns her
  evaluation/recruitment role, Luis owns his transcription/packaging role, and Maya's Lantern role is owned by
  **You**.
- Project-specific requirements, decisions, status, objectives, and deadlines are owned by the Project.
- A `project_role` relationship is rendered on both endpoints from the same fact ID and provenance: the Person
  page shows their active projects, while Lantern shows its contacts and stakeholders. This is a derived view,
  not a second canonical fact. Ordinary linked facts still render only on their owner.
- Family Oral History links to Grandmother, whose biographical account remains on her Person page.
- The September 13 oral-history interview is a Project timeline fact, not an Event page.

## Concision and history

- Forty-five source-grounded claims consolidate into 29 final facts.
- Repeated support becomes provenance on one fact: three Priya role claims form one shared relationship; her
  completed work remains a separate timeline event. Three consent claims render once, as do the two
  relative-date build claims.
- The original September 22 pilot date remains useful history after September 28 becomes current.
- Once LANTERN-42 is resolved, its combined open/closed history moves entirely to Lantern's Timeline instead
  of remaining in Current Status.
- Routine conversation history and unused tool results remain inspectable sources but not wiki content.

## Corrections and retraction

- State-changing contradictions and supersessions always require human review for now, including explicit
  corrections from the primary user. The system should begin conservatively and may automate narrowly proven
  cases later.
- While the pilot-date proposal is pending, neither September 22 nor September 28 is presented as settled
  current truth. Approval applies immediately through the normal claim-level transaction: September 28 becomes
  current and September 22 remains superseded history.
- The wrong-workspace Northstar meeting remains a narrow lifecycle test, not a comprehensive correction and
  retraction benchmark. Retraction removes its claims, pages, links, retrieval evidence, and answers. A
  read-only audit record may remain, while ordinary retrieval cannot expose the retracted content.

## Retrieval

- Pending and deferred claims are eligible retrieval evidence before wiki placement.
- Current questions prefer current facts and avoid superseded history unless the question asks about change.
- Negative probes ensure that retracted Northstar data, the dentist appointment, and the cosmetic dark-mode
  issue are not surfaced.
- Answers are evaluated by required and forbidden semantic facts, not reference-string similarity.

With these decisions recorded, the fixture can serve as the behavioral specification for its first automated
system-under-test runner.
