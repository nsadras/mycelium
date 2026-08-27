# Entity-Owned Wiki Architecture

## Purpose

The wiki is a concise, human-readable picture of what Mycelium knows, not the canonical fact store. Its
organization must therefore be stable, inspectable, and reproducible without copying facts across pages or
letting an LLM rewrite a whole page.

Milestone 1 replaces slug-first routing and post-hoc taxonomy with one staged mechanism:

```text
source segments → durable short-term claims → cohort scope plan → consolidated facts → typed wiki
```

## Canonical records

- `artifacts/entities/*.json` stores stable identity: immutable typed ID, editable title and slug, aliases,
  and `active | archived | merged` lifecycle state. `you` is the singleton owner profile.
- `artifacts/placements/*.json` stores presentation semantics separately from claims: exactly one nullable
  owner entity, one validated deterministic or manually curated section key, explicit linked entities, and
  an inspectable reason.
- `artifacts/scope-decisions/*.json` is the append-only audit of automatic, reviewed, and manual scope
  decisions, including cohort support, confidence, and supersession.
- `artifacts/consolidated-facts/*.json` stores stable, editable wiki statements above claims: display text,
  member claim IDs, owner/section/links, synthesis origin, confidence, and rationale.
- `artifacts/encounters/*.json` records source-grounded participation in meetings so named people can have a
  useful page without inventing profile facts.
- `artifacts/organization-proposals/*.json` stores reviewable duplicate merges and candidate homes for
  deferred claims.
- Claims no longer contain page slugs. Their text, semantic envelope, status, and exact provenance remain
  independent of wiki organization.

The owner is the entity whose state, requirements, plans, or relationship the claim changes. Speaker,
conversation focus, and noun order are not ownership rules. A claim remains in short-term memory with a
`deferred` placement when no existing entity fits and sparse page-creation thresholds are not met. Deferred
is a request for future context, not a terminal failure.

## Sparse identity and page contract

The registry supports `you`, `person`, `project`, `topic`, `organization`, `place`, and `event`. Creation is
type-specific: named continuous outcomes become Projects; durable relationships become People; Topics need
explicit research intent or two non-equivalent claims; Organizations and Places need lasting relevance; and
Events must be named and substantial. Incidental nouns and catchalls never become pages.

One structured scope plan evaluates the accumulated cohort across source episodes and makes discovery and
ownership globally consistent, so several individually ambiguous observations can jointly establish a page
and early aliases can attach to a later name. Invalid owners defer only the affected claim after the plan has
parsed; they do not roll back an otherwise valid source episode. The server invokes this one Dream
pipeline by pending-claim count, maximum pending age, weekly deferred review, or explicit manual action.
Pending and deferred claims remain directly searchable and are labeled as unconsolidated during retrieval.
Structured meeting-speaker occurrences are also resolved in this contract to `you`, an existing Person ID,
or a declared Person candidate; encounter creation does not compare participant names to page titles.

Deterministic code validates only structured invariants: exact alias coverage, entity references, creation
basis, cited evidence, source diversity, entity types, and role cardinality. It does not inspect claim text to
discover identities, infer aliases, ground an owner, or override `deferred`/`source_only`. Entity meaning and
identity resolution therefore remain explicit model decisions with auditable evidence or manual review.

Each type has an ordered, validated section vocabulary in `mycelium.models.PAGE_SECTION_KEYS`. Empty sections
are omitted. The model selects an existing owner ID, a declared candidate ID, or `deferred`; typed retention
policy handles structurally excluded source material before ownership planning. Generated sections come from
the deterministic claim-type mapping and may later be manually curated. This
avoids contradictory status/owner/section outputs and prevents the renderer from asking an LLM to invent an
outline. Tool/web evidence is forced into Research & References, or Evidence on an Event, and cannot
automatically establish a fact on You.

Every rendered fact is a persisted `ConsolidatedFact` containing its supporting claim IDs, evidence modality,
scope and synthesis rationale, and exact source/segment references. Compatible claims may be synthesized for
display, but all member claim IDs remain attached and hard temporal/quantitative anchors are validated. Manual
fact text and grouping are authoritative; later automation does not silently overwrite them. Explicit
entity references normally create reciprocal links without duplicating the fact. A continuing person–project
role is the deliberate exception: extraction marks it `claim_type=relationship` and `predicate=project_role`,
the Person or You remains the single canonical owner, and deterministic projection renders the same claim ID
and provenance in both the person's Shared Projects/Priorities view and the project's People & Organizations
view. Materialized fact records expose their canonical owner, canonical links, and whether the current item is
a shared endpoint projection. The Wiki inspector therefore edits the one underlying placement even from the
Project view. If retrieval selects both endpoints, prompt rendering includes the shared role only once.
Ordinary linked facts and one-off action items are not copied. The You page otherwise contains self-owned facts
plus a generated memory map and recent-entity dashboard rather than a digest of everyone else's facts.

## Truth and maintenance boundaries

Claims involved in a pending contradiction or supersession are absent from authoritative sections and appear
only under Needs Review. Organization review never changes claim truth. Wiki curation can rename, retype,
archive, merge, split, move, and relink entity-owned views; factual editing and source retraction remain a
separate claim-level milestone.

Merged entity IDs permanently redirect to the surviving identity. Archived entities remain inspectable but
do not appear in the active index. Generated Markdown is read-only and may always be rebuilt from entities,
placements, and active claims.

## Rebuild boundary

There is intentionally no runtime compatibility path for slug-owned pages. **Clear Wiki** deletes derived
pages, entities, placements, consolidated facts, encounters, scope decisions, and organization proposals,
removes the retired `page_slugs` field from preserved
claims, requeues active claims, marks logs unconsolidated, and seeds a fresh You identity. The next Dream pass
rebuilds from source-grounded claims. A page with missing entity metadata fails clearly instead of being
guessed into the new schema.
