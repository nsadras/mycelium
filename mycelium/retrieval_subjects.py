"""Project existing identity bindings without making new identity decisions."""

from mycelium.artifacts import ArtifactStore
from mycelium.operations import EvidenceSubject


def claim_subjects(artifacts: ArtifactStore, claim_id: str) -> tuple[EvidenceSubject, ...]:
    subjects = {}
    for reference in artifacts.list_entity_references(claim_id=claim_id, status="active"):
        if reference.entity_id is None:
            continue
        entity = artifacts.get_entity(reference.entity_id)
        if entity.status == "active":
            subjects[(entity.entity_id, reference.role)] = EvidenceSubject(
                entity.entity_id, entity.title, reference.role, tuple(entity.aliases)
            )
    return tuple(subjects[key] for key in sorted(subjects))
