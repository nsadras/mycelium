from mycelium.artifacts import ClaimProvenance, MemoryClaim
from mycelium.projection import (
    compact_display_claims,
    compact_qualifiers,
    compact_record_qualifiers,
    display_claim_text,
    partition_claims,
    project_claim,
)


def claim(
    claim_id: str,
    text: str,
    claim_type: str,
    *,
    salience: float = 0.5,
    facets=None,
    evidence_modality: str = "speech",
    temporal_status: str = "unknown",
    derivation_operation: str | None = None,
) -> MemoryClaim:
    item = MemoryClaim(
        claim_id=claim_id,
        text=text,
        kind="fact",
        about=[{"entity": "Ava"}],
        provenance=[ClaimProvenance("source-1", ["source-1#seg-0001"])],
        recorded_at="2024-01-10T12:00:00",
        salience=salience,
        confidence=0.8,
        facets=facets or {"observed_at": "4:24 pm on 10 January, 2024"},
        claim_type=claim_type,
        evidence_modality=evidence_modality,
        temporal_status=temporal_status,
        derivation_operation=derivation_operation,
    )
    if derivation_operation:
        item.inferred = True
    return item


def test_projection_separates_durable_timeline_and_social_claims():
    projected = partition_claims([
        claim("preference", "Ava prefers oolong tea.", "preference", salience=0.9),
        claim("event", "Ava visited Kyoto.", "event", temporal_status="past"),
        claim("greeting", "Ava greeted Ben.", "interaction"),
        claim("detail", "Ava described the room as blue.", "observation"),
    ])

    assert [item.claim.claim_id for item in projected["main"]] == ["preference"]
    assert [item.claim.claim_id for item in projected["timeline"]] == ["event"]
    assert [item.claim.claim_id for item in projected["interaction_archive"]] == ["greeting"]
    assert [item.claim.claim_id for item in projected["details"]] == ["detail"]


def test_projection_uses_semantics_instead_of_claim_wording():
    event = claim("purchase", "A book purchase by Ava occurred.", "event")
    interaction = claim("departure", "Ava ended the conversation.", "interaction")
    visual = claim(
        "photo",
        "Ava's newly arranged desk has a blue surface.",
        "state",
        evidence_modality="visual",
    )

    projected = partition_claims([event, interaction, visual])

    assert [item.claim.claim_id for item in projected["timeline"]] == ["purchase"]
    assert [item.claim.claim_id for item in projected["interaction_archive"]] == ["departure"]
    assert [item.claim.claim_id for item in projected["details"]] == ["photo"]


def test_projection_keeps_traceable_inferences_separate():
    item = claim(
        "derived-duration",
        "Ava completed the project in four months.",
        "event",
        facets={"basis_claim_ids": ["started", "finished"]},
        derivation_operation="temporal_arithmetic",
    )

    projected = partition_claims([item])

    assert [value.claim.claim_id for value in projected["insights"]] == ["derived-duration"]
    assert "based on 2 facts" in compact_qualifiers(item)


def test_projection_reports_repeated_support_as_sessions_not_event_count():
    item = claim("preference", "Ava prefers tea.", "preference")
    item.provenance.append(ClaimProvenance("source-2", ["source-2#seg-0001"]))

    qualifiers = compact_record_qualifiers(partition_claims([item])["main"][0])

    assert "recorded in 2 sessions" in qualifiers
    assert all("times" not in value for value in qualifiers)


def test_projection_labels_observation_date_without_claiming_event_date():
    item = claim(
        "state",
        "Ava owns a bicycle.",
        "state",
        facets={"observed_at": "2024-01-10T12:00:00"},
    )

    assert project_claim(item).date_key == "Observed 2024-01-10"


def test_display_claim_text_removes_conflicting_model_added_date():
    item = claim(
        "event",
        "Ava visited Kyoto yesterday, on January 9, 2023.",
        "event",
        facets={"when": "yesterday", "normalized_date": "2024-01-09"},
    )

    rendered = display_claim_text(item)

    assert "yesterday" in rendered
    assert "2023" not in rendered


def test_display_compaction_does_not_conflate_handwritten_synonyms():
    items = [
        project_claim(claim("open", "Ava plans to open a bakery.", "plan")),
        project_claim(claim("start", "Ava plans to start a bakery.", "plan")),
    ]

    compacted = compact_display_claims(items)

    assert len(compacted) == 2


def test_display_compaction_preserves_member_claim_ids():
    first = claim("first", "Ava prefers green tea.", "preference")
    second = claim("second", "Ava prefers green tea.", "preference")

    compacted = compact_display_claims([project_claim(first), project_claim(second)])

    assert len(compacted) == 1
    assert set(compacted[0].claim_ids) == {"first", "second"}


def test_main_projection_caps_repetitive_bucket_without_losing_details():
    items = [
        claim(f"preference-{index}", f"Ava prefers tea variety {index}.", "preference")
        for index in range(10)
    ]

    projected = partition_claims(items, main_claim_limit=4)

    assert len(projected["main"]) <= 4
    assert len(projected["main"]) + len(projected["details"]) == 10


def test_compact_qualifiers_hide_provenance_and_redundant_values():
    item = claim(
        "location",
        "Ava moved to Paris.",
        "event",
        facets={"location": "Paris", "when": "last week", "normalized_date": "2024-01-03"},
    )

    qualifiers = compact_qualifiers(item, include_date=True)

    assert "location: Paris" not in qualifiers
    assert "stated: last week" in qualifiers
    assert all("source" not in value for value in qualifiers)
