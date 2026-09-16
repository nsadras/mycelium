"""Exact evidence exclusions from explicit human page reviews."""

from mycelium.artifacts import ArtifactStore


def reviewed_page_exclusions(artifacts: ArtifactStore, aliases):
    """A no-page review constrains its cited evidence, never the whole identity."""
    alias_for_claim = {item.claim.claim_id: alias for alias, item in aliases.items()}
    exclusions: dict[str, set[str]] = {}
    reviews = []
    for decision in artifacts.list_entity_resolution_decisions(review_state="accepted"):
        overlap = set(decision.supporting_claim_ids) & alias_for_claim.keys()
        if (
            not overlap
            or decision.reviewed_at is None
            or decision.proposed_page_state != "no_page"
        ):
            continue
        if decision.entity_id is None:
            raise ValueError(
                "A no-page review must identify its exact subject before routing"
            )
        for claim_id in sorted(overlap):
            refs = [
                ref
                for ref in artifacts.list_entity_references(
                    claim_id=claim_id, status="active"
                )
                if ref.role == "identity_subject"
                and ref.origin == "manual"
                and ref.identity_decision_id == decision.decision_id
            ]
            if not refs and not any(
                ref.identity_decision_id == decision.decision_id
                and ref.status == "superseded"
                for ref in artifacts.list_entity_references(claim_id=claim_id)
            ):
                raise ValueError(
                    "A no-page review is missing its evidence identity binding"
                )
            for ref in refs:
                if ref.entity_id is None:
                    raise ValueError("A reviewed page exclusion has no bound identity")
                alias = alias_for_claim[claim_id]
                exclusions.setdefault(alias, set()).add(ref.entity_id)
                reviews.append(
                    {
                        "decision_id": decision.decision_id,
                        "entity_id": ref.entity_id,
                        "claim_ids": [alias],
                        "page_state": "no_page",
                    }
                )
    return exclusions, reviews
