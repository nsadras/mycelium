# MAGMA ideas for a later retrieval milestone

Date: 2026-08-27

Source: [MAGMA: A Multi-Graph based Agentic Memory Architecture for AI Agents](https://aclanthology.org/2026.acl-long.1709/)

## Why this may be useful

MAGMA's strongest idea is not simply to store more graphs. It keeps different kinds of relationships separate and
chooses which relationships matter for the question being asked. Its experiments suggest that this task-aware
selection contributes more than an entity graph alone.

Mycelium already stores most of the raw material needed for a simpler version of this approach: canonical claims,
stable entities, typed relationships, timestamps, source references, wiki pages, and raw-log backlinks. Retrieval
can use different views of those records without introducing another source of truth or a graph database.

This work belongs after the page-structure and entity-relationship milestone. It should not be used to compensate
for incorrect identities, ownership, or page construction.

## Approaches worth testing

### 1. Choose a relationship view for the question

Classify the retrieval need with a small structured model decision. Useful views include:

- entity: facts involving a person, organization, project, place, or other stable subject;
- temporal: events, deadlines, changes, and sequences;
- causal: explicitly supported reasons, consequences, and dependencies;
- semantic: conceptually relevant evidence that is not connected by a stronger declared relationship.

The classifier should select views, not answer the question. Retrieval should preserve every selected path so the
choice can be inspected.

Do not use hard-coded question words or benchmark vocabulary to choose a view. Test the structured decision by
calling Ollama directly before integrating it.

### 2. Find anchors with several independent signals

Begin traversal from a small set of likely memory records selected from:

- exact stable entity or page IDs when available;
- page-title and alias matches;
- existing full-page text search;
- structured time overlap;
- a semantic retrieval signal, if later experiments show it adds value.

MAGMA combines ranked lists rather than requiring every signal to agree. A similarly simple rank-fusion experiment
could make Mycelium more robust to different question styles. These signals should identify candidates, not make
durable semantic decisions.

### 3. Traverse a bounded neighborhood

From each anchor, follow only the relationship types selected for the question. Apply explicit limits for depth,
node count, and context size. Prefer paths supported by canonical claims and direct source evidence.

Examples:

- an entity question can follow subject, object, participant, and ownership links;
- a time question can follow timestamped claims and occurrence relationships;
- a project question can follow component, occurrence, production, and participation relationships;
- a why question can follow only explicitly supported causal or dependency relationships.

The traversal must not create identities, relationships, or claims. It is a read-only view over persisted memory.

### 4. Preserve relationship paths in the model context

Render retrieved evidence as short paths rather than an undifferentiated collection of page text. Each block should
retain the claim or fact ID, timestamp when present, relationship direction, and source reference.

For example:

```text
Project P <- occurrence_of - Event E <- subject - Claim C
Claim C: ...
Observed: ...
Evidence: source/segment ID
```

Order temporal evidence chronologically. If explicit causal relationships are present, place causes before effects.
The final context should make the evidence chain easy for both the model and the user to inspect.

### 5. Budget after structure is known

Apply the token budget after anchors and relationship paths have been selected. Keep the most relevant complete
paths rather than clipping unrelated page fragments together. When space is limited, retain direct evidence and
relationship endpoints before narrative page text.

### 6. Keep one canonical store with several projections

Claims, sources, entities, and their persisted relationships remain canonical. Entity, temporal, causal, and
semantic views should be computed indexes or projections over those records. Do not create four independent stores
that can disagree.

## Approaches not to copy

- Do not add automatic or scheduled consolidation. Mycelium memory operations remain user-initiated through the API
  or web interface.
- Do not add a graph database unless the existing artifact store produces a demonstrated scaling problem.
- Do not treat embedding similarity as a durable semantic relationship. It may rank retrieval candidates only.
- Do not infer durable causal links without cited evidence and an inspectable model decision. Ambiguous causal links
  may require user review.
- Do not copy MAGMA's numerical thresholds, traversal weights, or query categories. They were tuned for its models
  and benchmarks and are not Mycelium product requirements.
- Do not replace stable identities and pages with event nodes. MAGMA primarily evaluates question answering, while
  Mycelium also needs conservative page admission and durable user-maintainable identity.

## Suggested experimental sequence

1. Finish the page-structure and entity-relationship milestone.
2. Select a small neutral retrieval case for each relationship view and a counterexample with tempting irrelevant
   evidence.
3. Test the query-view decision directly against the configured Ollama model using a strict structured response.
4. Compare the existing whole-page retrieval context with a bounded relationship-path context using the same stored
   evidence.
5. Integrate only the smallest approach that improves required evidence while controlling unrelated evidence.
6. Run focused tests, then the Daily Driver retrieval probes and both transfer fixtures.
7. Measure required fact recall, unrelated-fact rate, context tokens, latency, and inspectability separately.

## Success conditions

The experiment is useful only if it:

- retrieves evidence missed by whole-page search;
- reduces unrelated context;
- preserves exact provenance and timestamps;
- does not mutate memory during retrieval;
- works across paraphrased and unrelated-domain fixtures;
- remains understandable without adopting MAGMA's full infrastructure.
