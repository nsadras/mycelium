"""Explicit truth review repairs all cited views atomically."""

from unittest.mock import AsyncMock

import pytest

from mycelium.artifacts import ClaimProvenance, ConsolidatedFact, ReconsolidationProposal
from mycelium.reconsolidation import ReconsolidationReviewService
from tests.test_claim_lifecycle import setup_service, add_source, add_claim, NOW
from tests.lifecycle_support import lifecycle_response


@pytest.mark.asyncio
@pytest.mark.parametrize('action,relation', [('approve', 'supersedes'), ('approve', 'contradicts'), ('reject', 'supersedes')])
async def test_review_preserves_evidence_and_updates_all_views(tmp_path, action, relation):
    artifacts, wiki, lifecycle = setup_service(tmp_path)
    a, b = add_source(artifacts, 'a'), add_source(artifacts, 'b')
    old = add_claim(artifacts, 'old', [ClaimProvenance('a', [a])], with_fact=True)
    new = add_claim(artifacts, 'new', [ClaimProvenance('b', [b])], with_fact=True)
    new.text = 'The user prefers afternoon meetings.'
    artifacts.save_claim(new)
    person = artifacts.create_entity('person', 'Rowan')
    artifacts.save_consolidated_fact(ConsolidatedFact('other-view', old.text, ['old'], person.entity_id,
        'Schedule', 'current', [], 'model', .8, 'cited', NOW, NOW))
    artifacts.save_reconsolidation_proposal(ReconsolidationProposal('proposal', ['new'], ['old'], relation,
        'Explicit accounts differ.', .8, 'build', NOW, affected_entity_ids=['you', person.entity_id]))
    service = ReconsolidationReviewService(artifacts, lifecycle.materializer, lifecycle.views)
    if action == 'approve' and relation == 'supersedes':
        artifacts.save_reconsolidation_proposal(ReconsolidationProposal('overlap', ['new'], ['old'], relation,
            'Overlapping review.', .8, 'build', NOW, affected_entity_ids=['you']))
    result = await getattr(service, action)('proposal')
    assert result.proposal.status == ('applied' if action == 'approve' else 'rejected')
    assert len(artifacts.list_claims()) == 2
    if action == 'approve' and relation == 'supersedes':
        assert artifacts.get_claim('old').status == 'superseded'
        assert artifacts.get_reconsolidation_proposal('overlap').status == 'stale'
        assert not artifacts.facts_for_claim('old')
        assert all(old.text not in p.content for p in wiki.list_all())
    else:
        assert artifacts.get_claim('old').status == 'active'
        assert artifacts.facts_for_claim('old')
    calls = lifecycle.views.llm.call_structured.call_count
    again = await getattr(service, action)('proposal')
    assert again == result
    assert lifecycle.views.llm.call_structured.call_count == calls


@pytest.mark.asyncio
async def test_review_failure_does_not_mutate_claims_or_pages(tmp_path):
    artifacts, wiki, lifecycle = setup_service(tmp_path)
    sid = add_source(artifacts, 'source')
    for cid in ['old', 'new']:
        add_claim(artifacts, cid, [ClaimProvenance('source', [sid])], with_fact=True)
    lifecycle.materializer.regenerate({'you'})
    before = wiki.get('you')
    artifacts.save_reconsolidation_proposal(ReconsolidationProposal('proposal', ['new'], ['old'], 'supersedes',
        'Explicit change.', .8, 'build', NOW, affected_entity_ids=['you']))
    service = ReconsolidationReviewService(artifacts, lifecycle.materializer, lifecycle.views)
    lifecycle.views.llm.call_structured = AsyncMock(side_effect=RuntimeError('model unavailable'))
    with pytest.raises(RuntimeError):
        await service.approve('proposal')
    assert artifacts.get_claim('old').status == 'active'
    assert artifacts.get_reconsolidation_proposal('proposal').status == 'pending'
    assert wiki.get('you') == before
    lifecycle.views.llm.call_structured.side_effect = lifecycle_response
    assert (await service.approve('proposal')).proposal.status == 'applied'
