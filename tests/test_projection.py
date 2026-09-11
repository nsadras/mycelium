from mycelium.artifacts import ClaimProvenance, MemoryClaim
from mycelium.projection import display_claim_text


def test_display_preserves_dates_even_when_metadata_disagrees():
    claim = MemoryClaim(
        claim_id="event",
        text="Ava visited Kyoto yesterday, on January 9, 2023.",
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
    assert rendered == claim.text


def test_explicit_calendar_metadata_resolves_without_inventing_a_year():
    from mycelium.temporal import normalize_temporal_facets
    for expression in ["2031-02-14", "February 14, 2031", "14 February, 2031"]:
        value = normalize_temporal_facets({"deadline": expression}, None)["temporal"]
        assert value["start"] == "2031-02-14"
        assert value["role"] == "deadline"
        assert value["expression"] == expression
    value = normalize_temporal_facets({"when": "February 14"}, None)["temporal"]
    assert value["status"] == "unresolved"
    assert "start" not in value
