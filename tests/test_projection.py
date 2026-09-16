from tests.extraction_support import stored_time
from mycelium.artifacts import ClaimProvenance, MemoryClaim
from mycelium.projection import display_claim_text


def test_display_preserves_dates_even_when_metadata_disagrees():
    claim = MemoryClaim(
        claim_id="event",
        text="Ava visited Kyoto yesterday, on January 9, 2023.",
        about=[{"entity": "Ava"}],
        provenance=[ClaimProvenance("source-1", ["source-1#seg-0001"])],
        recorded_at="2024-01-10T12:00:00",
        facets=stored_time('source-1#seg-0001','yesterday',{'kind':'day_offset','days':-1},'2024-01-10'),
        claim_type="event",
    )

    rendered = display_claim_text(claim)

    assert "yesterday" in rendered
    assert rendered == claim.text


def test_explicit_calendar_declaration_does_not_require_an_anchor():
    facets = stored_time('s1', '14 February, 2031',
        {'kind':'absolute','start':'2031-02-14','end':'2031-02-14','precision':'day'}, None, role='deadline')
    assert facets['temporal'][0]['start'] == '2031-02-14'
    unresolved = stored_time('s1', 'February 14', {'kind':'unresolved','reason':'Missing year'}, None)
    assert unresolved['temporal'][0]['start'] is None
