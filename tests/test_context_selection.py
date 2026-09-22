from dataclasses import replace
import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from mycelium.budget import require_request_budget
from mycelium.context_selection import AssistantContextSelector, compact_evidence
from mycelium.operations import EvidenceRecord, EvidenceSource, EvidenceSegment, MemoryEvidence, EvidenceCitation, EvidenceClaim, EvidenceSourceCitation, EvidenceReview, EvidenceSubject
from mycelium.structured_outputs import complementary_selection_model


def evidence(count=2, words=1):
    return MemoryEvidence(records=tuple(
        EvidenceRecord(str(i), "claim", "material " * words + f"TAIL-{i}", None, None, (str(i),))
        for i in range(count)
    ))


def model(window=32768, selected=None):
    llm = AsyncMock()
    llm.context_window_tokens = window
    llm.call_structured.return_value = {
        "selected_ids": selected or [], "supported_aspects": [], "remaining_gaps": ["Missing details"]
    }
    return llm


def test_context_selection_schema_preserves_order_and_rejects_invalid_ids():
    schema = complementary_selection_model(["M001", "M002"])
    valid = {"selected_ids": ["M002", "M001"], "supported_aspects": [], "remaining_gaps": []}
    assert schema.model_validate(valid).selected_ids == ["M002", "M001"]
    for invalid in (["M003"], ["M001", "M001"]):
        with pytest.raises(ValidationError):
            schema.model_validate({**valid, "selected_ids": invalid})


@pytest.mark.asyncio
async def test_selector_can_abstain_from_all_evidence_in_one_call():
    llm = model()
    result = await AssistantContextSelector(llm).select_with_trace("Unrelated", evidence())
    assert not result.selected_ids and result.error is None
    assert result.remaining_gaps == ("Missing details",)
    assert llm.call_structured.await_count == 1


@pytest.mark.asyncio
async def test_selector_rejects_unknown_output_without_retry():
    llm = model(selected=["M999"])
    result = await AssistantContextSelector(llm).select_with_trace("Question", evidence())
    assert not result.selected_ids and result.error
    assert llm.call_structured.await_count == 1


@pytest.mark.asyncio
async def test_selection_fits_complete_candidates_once_and_cannot_select_omitted_ids():
    llm = model(window=6000, selected=["M001"])
    result = await AssistantContextSelector(llm).select_with_trace("Question", evidence(6, words=1500))
    assert result.selected_ids == ("0",)
    assert llm.call_structured.await_count == 1
    system, user, schema = llm.call_structured.call_args.args
    assert "TAIL-0" in user and "TAIL-5" not in user
    require_request_budget([{"role": "system", "content": system}, {"role": "user", "content": user}],
        context_window=6000, output_tokens=1024, schema=schema.model_json_schema())
    with pytest.raises(ValidationError):
        schema.model_validate({"selected_ids": ["M006"], "supported_aspects": [], "remaining_gaps": []})


@pytest.mark.asyncio
async def test_shared_source_is_rendered_once_and_selected_order_is_preserved():
    llm = model(selected=["M002", "M001"])
    shared = replace(evidence(), sources=(EvidenceSource("s", "2030-01-01", (), (
        EvidenceSegment("line", "cited", "A speaker", "A source-only detail."),)),))
    result = await AssistantContextSelector(llm).select_with_trace("Question", shared, limit=2)
    assert result.selected_ids == ("1", "0")
    assert llm.call_structured.call_args.args[1].count("A source-only detail.") == 1
    assert llm.call_structured.call_args.args[2].model_json_schema()["properties"]["selected_ids"]["maxItems"] == 2


@pytest.mark.asyncio
async def test_no_fitting_candidate_is_an_explicit_error_without_model_call():
    llm = model(window=5000)
    result = await AssistantContextSelector(llm).select_with_trace("Question", evidence(1, words=6000))
    assert result.error and not result.selected_ids
    llm.call_structured.assert_not_called()


def test_compaction_preserves_literal_text_identity_roles_and_exact_citations():
    cid, sid, segment = 'claim-0123456789', 'source-0123456789', 'source-0123456789#seg-0001'
    literal = f'The label is {cid}; leave r0 unchanged.'
    record = EvidenceRecord(cid, 'claim', literal, None, None, (cid,), state='superseded',
        subjects=(EvidenceSubject('person-0123456789', 'Ari', 'context', ('A. K.',)),),
        citations=(EvidenceCitation(cid, sid, (segment,), '2032-01-01'),),
        canonical_claims=(EvidenceClaim(cid, literal),),
        reviews=(EvidenceReview('proposal-0123456789', 'pending', 'contradicts', ('another-claim',), (cid,)),),
        revisions=({'relation': 'superseded_by', 'claim_id': 'another-claim', 'status': 'active', 'text': literal},),
        uncertainty=('Identity remains uncertain.',))
    source = EvidenceSource(sid, '2032-01-01', (EvidenceSourceCitation(cid, (segment,)),),
        (EvidenceSegment(segment, 'cited', 'Ari', 'Exact original words.'),))
    original = MemoryEvidence((record,), (source,), more_available=True)
    rendered, ids = compact_evidence(original, {'M001': cid})
    data = json.loads(rendered)
    item, = data['records']
    excerpt, = data['sources']
    assert item['record_id'] == item['claim_ids'][0] == 'M001'
    assert item['statement'] == item['revisions'][0]['text'] == literal
    assert item['subjects'][0]['role'] == 'context' and item['subjects'][0]['aliases'] == ['A. K.']
    assert ids[item['subjects'][0]['entity_id']] == 'person-0123456789'
    assert ids[item['citations'][0]['source_id']] == ids[excerpt['source_id']] == sid
    assert ids[item['citations'][0]['segment_ids'][0]] == segment
    assert excerpt['citations'][0]['segment_ids'] == [excerpt['segments'][0]['segment_id']]
    assert item['reviews'][0]['incoming_claim_ids'] == [item['revisions'][0]['claim_id']]
    assert item['reviews'][0]['target_claim_ids'] == ['M001']
    assert item['state'] == 'superseded' and item['uncertainty'] == ['Identity remains uncertain.']
    assert data['more_available'] and excerpt['conversation_time'] == '2032-01-01'
    assert original == MemoryEvidence((record,), (source,), more_available=True)
