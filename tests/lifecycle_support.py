"""Explicit neutral decisions for lifecycle mechanics; native probes prove semantics."""

from tests.discovery_support import discovery_response

import json


def lifecycle_response(_system, user, schema, **kwargs):
    stage = kwargs.get("debug_label")
    if stage == "memory-correction":
        return {
            "about": [{"entity": "user", "role": "subject"}],
            "claim_type": "preference",
            "predicate": None,
            "temporal_status": "atemporal",
            "facets": {"times": [], "inference_basis": None},
        }
    if stage == "dream-subject-discovery":
        return discovery_response(
            {
                "subjects": [
                    {
                        "entity_type": "person",
                        "title": "You",
                        "description": "The statement concerns the user.",
                        "supporting_evidence": ["C001"],
                        "alternate_names": [],
                    }
                ]
            }
        )
    if stage == "dream-subject-identity":
        return {
            "decision": {
                "resolution": "existing",
                "entity_id": "you",
                "title": "You",
                "reason": "The statement concerns the user.",
                "aliases": [],
            }
        }
    if stage == "dream-source-attribution":
        return {
            "attributions": {
                a: {
                    "you": {
                        "assertions": ["Explicit fixture assertion"],
                        "relation_to_claim": "described",
                        "reason": "Fixture user preference.",
                    }
                }
                for a in schema.model_fields["attributions"].annotation.model_fields
            }
        }
    if stage == "dream-claim-routing":
        return {
            "decisions": {
                a: {
                    "primary_subject": "you",
                    "primary_reason": "User preference.",
                    "pages": {"you": "preferences_working_style"},
                    "uncertainty": None,
                    "prominence": "briefing",
                }
                for a in schema.model_fields["decisions"].annotation.model_fields
            }
        }
    if stage == "dream-fact-candidate-selection":
        return {
            "decisions": {
                a: {"candidate_fact_ids": [], "reason": "Independent fixture claim."}
                for a in schema.model_fields["decisions"].annotation.model_fields
            }
        }
    if stage == "dream-truth-candidates":
        return unrelated_truth_candidates(schema)
    if stage == "dream-fact-grouping":
        claims = json.loads(
            user.split("CANONICAL STORED CLAIMS\n", 1)[1].split(
                "\n\nALLOWED SECTIONS", 1
            )[0]
        )
        return {
            "groups": [
                {
                    "member_claim_aliases": [a],
                    "memory_scope": "An independent fixture statement.",
                    "state": "current",
                    "section_key": "preferences_working_style",
                    "prominence": "briefing",
                }
                for a in claims
            ]
        }
    raise AssertionError(f"Unexpected lifecycle model call: {stage}")


def unrelated_truth_candidates(schema):
    return {
        "decisions": {
            a: {
                "candidates": {
                    target: "unrelated"
                    for target in field.annotation.model_fields[
                        "candidates"
                    ].annotation.model_fields
                },
                "reason": "Independent fixture statements.",
            }
            for a, field in schema.model_fields[
                "decisions"
            ].annotation.model_fields.items()
        }
    }
