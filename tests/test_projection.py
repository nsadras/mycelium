from mycelium.artifacts import ClaimProvenance, MemoryClaim
from mycelium.projection import display_claim_text


def test_display_claim_text_removes_conflicting_model_added_date():
    claim = MemoryClaim(
        claim_id="event",
        text="Ava visited Kyoto yesterday, on January 9, 2023.",
        kind="fact",
        about=[{"entity": "Ava"}],
        provenance=[ClaimProvenance("source-1", ["source-1#seg-0001"])],
        recorded_at="2024-01-10T12:00:00",
        facets={"temporal": {
            "expression": "yesterday",
            "start": "2024-01-09",
            "end": "2024-01-09",
            "precision": "day",
            "status": "resolved",
            "certainty": "exact",
        }},
        claim_type="event",
    )

    rendered = display_claim_text(claim)

    assert "yesterday" in rendered
    assert "2023" not in rendered
