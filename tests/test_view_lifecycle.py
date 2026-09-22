"""Shared evidence, manual editing and exact identity review through production services."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from mycelium import Mycelium
from mycelium import memory_contract
from mycelium.artifacts import ClaimEntityReference, ClaimProvenance, ConsolidatedFact, EntityResolutionDecision, ReconsolidationProposal
from mycelium.context import render_memory_context
from mycelium.organization import EntityCurationService, FactCurationService, IdentityReviewService
from tests.test_claim_lifecycle import setup_service, add_source, add_claim, NOW


def views_fixture(tmp_path):
    artifacts, wiki, service = setup_service(tmp_path)
    sid = add_source(artifacts, 'source')
    claim = add_claim(artifacts, 'statement', [ClaimProvenance('source', [sid])], with_fact=True)
    person = artifacts.create_entity('person', 'Rowan')
    second = ConsolidatedFact('second', 'A distinct presentation.', [claim.claim_id], person.entity_id,
        'Working agreements', 'current', [], 'model', .8, 'Cited view', NOW, NOW)
    artifacts.save_consolidated_fact(second)
    artifacts.save_entity_reference(ClaimEntityReference('person-ref', claim.claim_id, 'subject', person.title,
        person.entity_id, .8, 'Cited subject', 'extraction', 'initial', 'active', NOW))
    service.materializer.regenerate({'you', person.entity_id})
    return artifacts, wiki, service, claim, person, second


def test_move_and_split_change_only_selected_items(tmp_path):
    artifacts, wiki, service, claim, person, second = views_fixture(tmp_path)
    curation = FactCurationService(artifacts, service.materializer)
    first = artifacts.facts_for_claim(claim.claim_id)[0]
    if first.fact_id == second.fact_id:
        first = artifacts.get_consolidated_fact('fact-statement')
    result = curation.split(first.fact_id, [
        {'claim_ids': [claim.claim_id], 'text': 'First aspect.'},
        {'claim_ids': [claim.claim_id], 'text': 'Second aspect.'}], reason='Separate presentations')
    assert len(result.facts) == 2
    moved = curation.move(result.facts[0].fact_id, person.entity_id, 'Any useful heading',
                         linked_entity_ids=[], reason='Manual organization').facts[0]
    assert moved.manual_text and moved.member_claim_ids == [claim.claim_id]
    assert artifacts.get_consolidated_fact(second.fact_id) == second
    assert artifacts.get_consolidated_fact(result.facts[1].fact_id) == result.facts[1]
    rendered = render_memory_context(wiki.list_all())
    assert all(text in rendered for text in ['First aspect.', 'Second aspect.', second.text])
    assert len(artifacts.list_claims()) == 1
    assert artifacts.list_placements() == []
    with pytest.raises(ValueError):
        curation.split(moved.fact_id, [{'claim_ids': ['unknown'], 'text': 'Wrong.'},
                                      {'claim_ids': [claim.claim_id], 'text': 'Valid.'}], reason='Bad refs')
    assert artifacts.get_consolidated_fact(moved.fact_id) == moved


@pytest.mark.asyncio
async def test_manual_edit_during_model_refresh_is_preserved(tmp_path, monkeypatch):
    artifacts, wiki, service, claim, person, fact = views_fixture(tmp_path)

    async def present(llm, payload):
        FactCurationService(artifacts, service.materializer).move(fact.fact_id, person.entity_id,
            'User selected heading', linked_entity_ids=[], reason='Concurrent manual edit')
        return {'items': []}

    monkeypatch.setattr(memory_contract, 'present', present)
    with pytest.raises(ValueError, match='Memory changed'):
        await service.views.refresh({claim.claim_id}, context_ids=[], run_id='refresh')
    assert artifacts.get_consolidated_fact(fact.fact_id).section_key == 'User selected heading'
    assert 'User selected heading' in wiki.get(person.slug).content


@pytest.mark.asyncio
async def test_no_page_review_only_removes_reviewed_evidence_and_build_reopens_it(tmp_path, monkeypatch):
    artifacts, wiki, service, claim, person, first = views_fixture(tmp_path)
    sid = add_source(artifacts, 'useful-source')
    useful = add_claim(artifacts, 'useful', [ClaimProvenance('useful-source', [sid])])
    useful.text = 'A useful independent context.'
    artifacts.save_claim(useful)
    other = replace(first, fact_id='useful-view', text=useful.text, member_claim_ids=[useful.claim_id])
    artifacts.save_consolidated_fact(other)
    artifacts.save_entity_resolution_decision(EntityResolutionDecision('identity', 'entity_creation', person.entity_id,
        'person', person.title, ['source'], [claim.claim_id], claim.provenance[0].segment_ids, .5,
        'Optional identity review', 'review_required', 'initial', NOW))
    IdentityReviewService(artifacts).review('identity', 'approve', scope='context', page_state='no_page')
    assert artifacts.get_claim(claim.claim_id).dream_disposition == 'pending'
    assert artifacts.get_episode('episode-source').extraction_status == 'complete'
    service.materializer.regenerate({person.entity_id})
    assert first.text not in wiki.get(person.slug).content
    assert useful.text in wiki.get(person.slug).content
    with Mycelium(tmp_path) as memory:
        monkeypatch.setattr(memory.retriever.claim_index, 'search', AsyncMock(return_value=[]))
        monkeypatch.setattr(memory_contract, 'retain', AsyncMock(side_effect=AssertionError('Complete evidence must not be re-extracted')))
        seen = []

        async def present(llm, payload):
            seen.append(payload)
            return {'items': []}

        monkeypatch.setattr(memory_contract, 'present', present)
        assert not (await memory.consolidate()).report.failures
        assert seen and {'memory_id': claim.claim_id, 'subject_id': person.entity_id} in seen[0]['page_exclusions']
        assert artifacts.get_consolidated_fact(other.fact_id) == other
        assert useful.text in wiki.get(person.slug).content


def test_identity_binding_changes_only_reviewed_subject_reference(tmp_path):
    artifacts, wiki, service, claim, person, fact = views_fixture(tmp_path)
    other = artifacts.create_entity('person', 'Another Rowan')
    artifacts.save_entity_resolution_decision(EntityResolutionDecision('identity', 'entity_creation', person.entity_id,
        'person', person.title, ['source'], [claim.claim_id], claim.provenance[0].segment_ids, .5,
        'Ambiguous occurrence', 'review_required', 'initial', NOW))
    IdentityReviewService(artifacts).review('identity', 'approve', entity_id=other.entity_id)
    refs = artifacts.list_entity_references(claim_id=claim.claim_id, status='active')
    assert {r.entity_id for r in refs} == {'you', other.entity_id}
    assert artifacts.db.get('entity-references', 'person-ref')['status'] == 'superseded'
    merged = EntityCurationService(artifacts, wiki, service.materializer).merge(other.entity_id, person.entity_id)
    assert merged.entity.entity_id == person.entity_id
    assert all(r.identity_decision_id == 'identity' for r in artifacts.list_entity_references(status='active') if r.role == 'identity_subject')


def test_related_context_cannot_rewrite_or_reuse_unrelated_seed_items(tmp_path):
    artifacts, wiki, service, seed, person, fact = views_fixture(tmp_path)
    before = artifacts.list_consolidated_facts()
    page_before = wiki.get(person.slug).content
    sid = add_source(artifacts, 'independent-source')
    incoming = add_claim(artifacts, 'independent', [ClaimProvenance('independent-source', [sid])])
    project = artifacts.create_entity('project', 'A separate project')
    for ref in artifacts.list_entity_references(claim_id=incoming.claim_id):
        ref.entity_id = project.entity_id
        artifacts.save_entity_reference(ref)
    payload = service.views.input({incoming.claim_id}, [seed.claim_id], ())
    assert payload['existing_items'] == []
    assert {m['id'] for m in payload['context_memories']} == {seed.claim_id}
    assert payload['affected_subject_ids'] == [project.entity_id]
    bad = {'items': [{'owner_id': project.entity_id, 'heading': 'Context',
                     'memory_ids': [seed.claim_id], 'linked_subject_ids': [], 'state': 'current'}]}
    with pytest.raises(ValueError):
        memory_contract.presentation_model(payload).model_validate(bad)
    service.views.persist(payload, {'items': []}, {incoming.claim_id}, 'independent-build')
    assert artifacts.list_consolidated_facts() == before
    assert wiki.get(person.slug).content == page_before
    assert artifacts.get_claim(seed.claim_id) == seed


def test_related_update_keeps_complete_shared_support_and_protected_items(tmp_path):
    artifacts, wiki, service, seed, person, fact = views_fixture(tmp_path)
    sid = add_source(artifacts, 'follow-on-source')
    extra = add_claim(artifacts, 'extra-support', [ClaimProvenance('follow-on-source', [sid])])
    incoming = add_claim(artifacts, 'new-context', [ClaimProvenance('follow-on-source', [sid])])
    for claim, text in [(seed, 'The delivery is planned only if the inspection passes.'),
                        (extra, 'The inspection date is still tentative.'),
                        (incoming, 'An alternate venue is an idea, not an agreed change.')]:
        claim.text = text
        artifacts.save_claim(claim)
    artifacts.save_entity_reference(ClaimEntityReference('update-ref', incoming.claim_id, 'subject', person.title,
        person.entity_id, .8, 'Cited subject', 'extraction', 'update', 'active', NOW))
    shared = artifacts.create_entity('project', 'Shared work')
    fact.member_claim_ids.append(extra.claim_id)
    fact.linked_entity_ids = [shared.entity_id]
    artifacts.save_consolidated_fact(fact)
    manual = artifacts.get_consolidated_fact('fact-statement')
    manual.manual_text = True
    artifacts.save_consolidated_fact(manual)
    payload = service.views.input({incoming.claim_id}, [seed.claim_id], ())
    assert {m['id'] for m in payload['memories']} == {seed.claim_id, extra.claim_id, incoming.claim_id}
    assert shared.entity_id in payload['affected_subject_ids']
    assert next(i for i in payload['existing_items'] if i['id'] == manual.fact_id)['protected']
    view = {'items': [{'owner_id': person.entity_id, 'heading': 'Working agreements',
        'memory_ids': [seed.claim_id, extra.claim_id, incoming.claim_id],
        'linked_subject_ids': [shared.entity_id], 'state': 'current'}]}
    service.views.persist(payload, view, {incoming.claim_id}, 'follow-on-build')
    assert artifacts.get_consolidated_fact(manual.fact_id) == manual
    refreshed, = [f for f in artifacts.list_consolidated_facts() if f.fact_id != manual.fact_id]
    assert set(refreshed.member_claim_ids) == {seed.claim_id, extra.claim_id, incoming.claim_id}
    assert refreshed.linked_entity_ids == [shared.entity_id]
    assert refreshed.text == " ".join(c.text for c in [seed, extra, incoming])


@pytest.mark.parametrize('protection', ['manual', 'pending'])
@pytest.mark.asyncio
async def test_repeated_refresh_preserves_protected_items_without_cloning_them(tmp_path, monkeypatch, protection):
    artifacts, wiki, service, claim, person, fact = views_fixture(tmp_path)
    fact.linked_entity_ids = ['you']
    fact.manual_text = protection == 'manual'
    artifacts.save_consolidated_fact(fact)
    sid = add_source(artifacts, 'later-source')
    incoming = add_claim(artifacts, 'later', [ClaimProvenance('later-source', [sid])])
    if protection == 'pending':
        artifacts.save_reconsolidation_proposal(ReconsolidationProposal('review',
            [incoming.claim_id], [claim.claim_id], 'contradicts', 'Unresolved accounts', .8, 'build', NOW))
    other = artifacts.create_entity('project', 'Independent work')
    untouched = replace(fact, fact_id='unrelated', member_claim_ids=[incoming.claim_id],
                        owner_entity_id=other.entity_id, linked_entity_ids=[])
    artifacts.save_consolidated_fact(untouched)
    service.materializer.regenerate({other.entity_id})
    page_before = wiki.get(other.slug).content
    repeated = {'owner_id': person.entity_id, 'heading': fact.section_key,
                'memory_ids': [claim.claim_id], 'linked_subject_ids': ['you'], 'state': 'current'}
    # Owner/link order does not change the pages receiving the paragraph.
    reordered = {**repeated, 'owner_id': 'you', 'linked_subject_ids': [person.entity_id]}
    distinct = {**repeated, 'linked_subject_ids': []}
    another_heading = {**distinct, 'heading': 'Another aspect'}
    output = {'items': [repeated, reordered, distinct, distinct, another_heading]}
    present = AsyncMock(return_value=output)
    monkeypatch.setattr(memory_contract, 'present', present)
    for index in range(3):
        await service.views.refresh({claim.claim_id}, context_ids=[], run_id=f'refresh-{index}')
        assert artifacts.get_consolidated_fact(fact.fact_id) == fact
        assert artifacts.get_consolidated_fact(untouched.fact_id) == untouched
        assert wiki.get(other.slug).content == page_before
        views = artifacts.facts_for_claim(claim.claim_id)
        assert len(views) == (4 if protection == 'pending' else 3)
        assert sum(v.linked_entity_ids == ['you'] for v in views) == 1
        assert {v.section_key for v in views if v.fact_id != 'fact-statement'} == {fact.section_key, 'Another aspect'}
    assert present.await_count == 3
