"""Source-first discovery followed by bounded, typed identity resolution."""

import json

from mycelium.claim_index import OllamaEmbedder
from mycelium.identity_candidates import identity_documents, identity_records
from mycelium.semantic_candidates import SemanticCandidates
from mycelium.subject_discovery import subject_discovery_model, subject_discovery_prompt
from mycelium.subject_identity import subject_identity_model, subject_identity_prompt
from mycelium.subject_review_bindings import subject_review_model, subject_review_prompt


class IdentityPlanner:
    def __init__(self, llm, artifacts, config):
        self.llm, self.artifacts = llm, artifacts
        self.embedder = OllamaEmbedder(
            config.llm.url,
            config.retrieval.embedding_model,
            timeout=config.llm.timeout_seconds,
            trace_path=artifacts.root.parent / "diagnostics" / "embedding-calls.jsonl",
        )

    async def plan(self, aliases, participants, bindings, planned, staged, formatter):
        active = {
            eid: entity for eid, entity in planned.items() if entity.status == "active"
        }
        for binding in bindings.values():
            if (
                binding["entity_id"] not in active
                or binding["claim_alias"] not in aliases
            ):
                raise ValueError(
                    "A human identity binding must cite an active entity and current claim"
                )
        reviewed = {
            alias: {
                **binding,
                "entity_type": active[binding["entity_id"]].entity_type,
                "title": active[binding["entity_id"]].title,
            }
            for alias, binding in bindings.items()
        }
        roles = {p: role for p, (_, _, role) in participants.items()}
        evidence = json.loads(formatter.format_evidence(aliases, participants))
        # Whole-claim identity metadata narrows discovery to the reviewed
        # subject. Assign reviews only after discovering source subjects.
        for claim in evidence["claims"].values():
            del claim["identity_references"]
        evidence_text = json.dumps(evidence, ensure_ascii=False)
        schema = subject_discovery_model(aliases, roles, {})
        system, user = subject_discovery_prompt(evidence_text, "none")
        discovered = schema.model_validate(
            await self.llm.call_structured(
                system,
                user,
                schema,
                num_predict=8192,
                debug_label="dream-subject-discovery",
                cache_store=self.artifacts.db,
            )
        ).model_dump()
        assignments = {}
        discovered_subjects = {
            f"S{i:03d}": subject for i, subject in enumerate(discovered["subjects"], 1)
        }
        if reviewed:
            schema = subject_review_model(discovered_subjects, reviewed)
            system, user = subject_review_prompt(
                discovered_subjects, reviewed, evidence_text
            )
            assignments = schema.model_validate(
                await self.llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=2048,
                    debug_label="dream-subject-review-bindings",
                    cache_store=self.artifacts.db,
                )
            ).model_dump()["assignments"]
            for alias, assignment in assignments.items():
                if assignment["subject_alias"] == "unresolved":
                    raise ValueError(
                        f"Cannot bind human identity review {alias}: {assignment['reason']}"
                    )
        records = identity_records(self.artifacts, active.values(), staged)
        documents = identity_documents(records)
        reviews = formatter.identity_review_catalog(aliases)
        subjects = []
        selections = []
        for subject_alias, original_subject in discovered_subjects.items():
            subject = {
                **original_subject,
                "supporting_evidence": [
                    *original_subject["supporting_evidence"],
                    *(
                        r
                        for r, assignment in assignments.items()
                        if assignment["subject_alias"] == subject_alias
                    ),
                ],
            }
            confirmed = {
                bindings[a]["entity_id"]
                for a in subject["supporting_evidence"]
                if a in bindings
            }
            if any(roles.get(a) == "user" for a in subject["supporting_evidence"]):
                confirmed.add("you")
            if len(confirmed) > 1:
                raise ValueError(
                    "Distinct human identity bindings must remain separate subjects"
                )
            if confirmed:
                eid = confirmed.pop()
                if eid not in active:
                    raise ValueError("Declared canonical identity is not active")
                decision = {
                    "resolution": "existing",
                    "entity_id": eid,
                    "title": None,
                    "aliases": [],
                    "reason": "Explicit source-role or human-reviewed identity binding.",
                }
                selections.append({"subject": subject, "required_entity_id": eid})
            else:
                kind = subject["entity_type"]
                typed = {
                    eid: document
                    for eid, document in documents.items()
                    if records[eid]["entity_type"] == kind
                    or (kind == "person" and records[eid]["entity_type"] == "you")
                }
                index = SemanticCandidates(
                    self.artifacts.root.parent / "indexes" / "identity" / kind,
                    self.embedder,
                    self.artifacts.db,
                )
                ids = await index.select(
                    typed,
                    [json.dumps(subject, ensure_ascii=False)],
                    limit=24,
                    required_ids={"you"} if "you" in typed else (),
                )
                schema = subject_identity_model(ids)
                support = set(subject["supporting_evidence"])
                claim_aliases = (support & aliases.keys()) | {
                    bindings[a]["claim_alias"] for a in support if a in bindings
                }
                selected_claims = {
                    a: evidence["claims"][a] for a in sorted(claim_aliases)
                }
                source_ids = {
                    p["source_id"]
                    for claim in selected_claims.values()
                    for p in claim["citations"]
                }
                source_ids.update(
                    participants[p][0].source_id for p in support if p in participants
                )
                scoped_evidence = json.dumps(
                    {
                        "claims": selected_claims,
                        "participants": {
                            p: value
                            for p, value in evidence["participants"].items()
                            if p in support
                        },
                        "sources": {
                            sid: value
                            for sid, value in evidence["sources"].items()
                            if sid in source_ids
                        },
                    },
                    ensure_ascii=False,
                )
                system, user = subject_identity_prompt(
                    subject,
                    {eid: records[eid] for eid in ids},
                    scoped_evidence,
                    reviews,
                )
                decision = schema.model_validate(
                    await self.llm.call_structured(
                        system,
                        user,
                        schema,
                        num_predict=2048,
                        debug_label="dream-subject-identity",
                        cache_store=self.artifacts.db,
                    )
                ).model_dump()["decision"]
                selections.append(
                    {
                        "subject": subject,
                        "candidate_ids": ids,
                        "index": index.last_trace,
                    }
                )
            node = {
                "supporting_evidence": subject["supporting_evidence"],
                "aliases": subject["alternate_names"],
                **decision,
            }
            if decision["resolution"] != "existing":
                node.update(title=subject["title"], entity_type=subject["entity_type"])
            subjects.append(node)
        # Multiple source occurrences may resolve to one exact canonical ID.
        merged = []
        by_id = {}
        for node in subjects:
            if node["resolution"] != "existing" or node["entity_id"] not in by_id:
                merged.append(node)
                if node["resolution"] == "existing":
                    by_id[node["entity_id"]] = node
                continue
            prior = by_id[node["entity_id"]]
            if (
                prior["title"] is not None
                and node["title"] is not None
                and prior["title"] != node["title"]
            ):
                raise ValueError(
                    "Identity resolutions propose conflicting name changes"
                )
            prior["title"] = prior["title"] or node["title"]
            prior["aliases"] = list(
                dict.fromkeys([*prior["aliases"], *node["aliases"]])
            )
            prior["supporting_evidence"] = list(
                dict.fromkeys(
                    [*prior["supporting_evidence"], *node["supporting_evidence"]]
                )
            )
            prior["reason"] += "\n" + node["reason"]
        return {
            "subjects": merged,
            "discovery": discovered,
            "review_bindings": assignments,
            "candidate_selection": selections,
        }
