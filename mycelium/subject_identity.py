"""Resolve a source-discovered subject and its name from identity evidence."""

import json
from typing import Literal, Union

from pydantic import ConfigDict, Field, create_model, model_validator

from mycelium.prompting import render_prompt_pair


def subject_identity_model(candidate_ids, evidence):
    ids = tuple(candidate_ids)
    evidence = json.loads(evidence)
    cited = {
        (citation["source_id"], citation["segment_id"])
        for claim in evidence["claims"].values()
        for citation in claim["citations"]
    }
    name_evidence = [
        evidence["sources"][sid]["segments"][segment_id]["text"]
        for sid, segment_id in sorted(cited)
    ]
    common = {"reason": (str, Field(min_length=1, max_length=500))}
    names = {
        "title_basis": (
            Literal["source_name", "description"],
            Field(
                description="source_name for a name explicitly supplied in the source, copied with its exact spelling; description only for a subject whose name is not supplied."
            ),
        ),
        "title": (
            str,
            Field(
                min_length=1,
                description="Source-established name or a descriptive title when unnamed",
            ),
        ),
        "aliases": (list[str], Field(max_length=12)),
    }

    @model_validator(mode="after")
    def exact_source_name(self):
        # The model declares whether this is a name or an unnamed description.
        # Validate a declared name's spelling, never infer identity from text.
        if self.title_basis == "source_name" and not any(
            self.title in text for text in name_evidence
        ):
            raise ValueError(
                "A declared source name must be copied exactly from cited source text."
            )
        return self

    variants = [
        create_model(
            "NewSubjectIdentity",
            __config__=ConfigDict(extra="forbid"),
            __validators__={"exact_source_name": exact_source_name},
            **common,
            resolution=(Literal["new"], ...),
            **names,
        )
    ]
    if ids:
        existing_fields = create_model(
            "ExistingSubjectIdentityFields",
            __config__=ConfigDict(extra="forbid"),
            **common,
            resolution=(Literal["existing"], ...),
            entity_id=(Literal.__getitem__(ids), ...),
            preferred_name_update=(
                str | None,
                Field(
                    description="A new preferred name explicitly established by this source, copied with its exact spelling; null means retain the matched registry title. Choosing an existing identity does not require changing its name.",
                    min_length=1,
                ),
            ),
            aliases=(list[str], Field(max_length=12)),
        )

        class ExistingSubjectIdentity(existing_fields):
            @model_validator(mode="after")
            def exact_name_copy(self):
                # The model decides meaning. Only fidelity to its cited spelling
                # is deterministic; this never infers identity from matching text.
                if self.preferred_name_update is not None and not any(
                    self.preferred_name_update in text for text in name_evidence
                ):
                    raise ValueError(
                        "A new preferred name must be copied exactly from cited source evidence; "
                        "return null when no name update is established."
                    )
                return self

        variants.append(ExistingSubjectIdentity)
    unresolved = create_model(
        "UnresolvedSubjectIdentityFields",
        __config__=ConfigDict(extra="forbid"),
        __validators__={"exact_source_name": exact_source_name},
        **common,
        resolution=(Literal["review_required"], ...),
        candidate_entity_ids=(
            list[Literal.__getitem__(ids)] if ids else list[str],
            Field(max_length=len(ids)),
        ),
        **names,
    )

    class UnresolvedSubjectIdentity(unresolved):
        @model_validator(mode="after")
        def unique_candidates(self):
            if len(self.candidate_entity_ids) != len(set(self.candidate_entity_ids)):
                raise ValueError("Review candidates must be unique")
            return self

    variants.append(UnresolvedSubjectIdentity)
    return create_model(
        "SubjectIdentity",
        __config__=ConfigDict(extra="forbid"),
        decision=(Union[tuple(variants)], ...),
    )


def subject_identity_prompt(subject, registry, evidence, reviewed="none"):
    # Classification and publication state do not establish identity. Keep those
    # fields for downstream routing, outside this semantic matching decision.
    excluded = {"entity_type", "page_state"}
    return render_prompt_pair(
        "memory/subject_identity",
        subject=json.dumps(
            {k: v for k, v in subject.items() if k not in excluded}, ensure_ascii=False
        ),
        registry=json.dumps(
            {
                eid: {k: v for k, v in row.items() if k not in excluded}
                for eid, row in registry.items()
            },
            ensure_ascii=False,
        ),
        evidence=evidence,
        reviewed=reviewed,
    )
