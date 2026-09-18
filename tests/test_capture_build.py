"""Capture, resumable Build and failure visibility on the real production path."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from mycelium import Mycelium, SourceInput
from mycelium import memory_contract
from mycelium.budget import count_tokens
from mycelium.operations import ConsolidationRequest
from mycelium.retention import Retainer
from mycelium.retrieval_context import RetrievedContextBuilder, render_memory_evidence
from tests.lifecycle_support import lifecycle_response


def configure(memory, monkeypatch):
    memory.llm.call_structured = AsyncMock(side_effect=lifecycle_response)
    monkeypatch.setattr(memory.retriever.claim_index, 'search', AsyncMock(return_value=[]))


@pytest.mark.asyncio
async def test_snapshot_leaves_concurrent_capture_pending(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        configure(memory, monkeypatch)
        first = await memory.ingest_source(SourceInput('One retained statement.', 'first', idempotency_key='first'))
        entered, resume = asyncio.Event(), asyncio.Event()
        original = memory_contract.retain

        async def retain(llm, payload):
            entered.set()
            await resume.wait()
            return await original(llm, payload)

        monkeypatch.setattr(memory_contract, 'retain', retain)
        task = asyncio.create_task(memory.consolidate())
        await asyncio.wait_for(entered.wait(), 2)
        second = await memory.ingest_source(SourceInput('A later statement.', 'second', idempotency_key='second'))
        resume.set()
        result = await task
        assert result.processed_episode_ids == first.episode_ids
        assert memory.artifacts.get_episode(second.episode_ids[0]).extraction_status != 'complete'
        assert memory.artifacts.build_incomplete()
        assert not (await memory.consolidate()).report.failures
        assert len(memory.artifacts.list_claims()) == 2
        repeated = await memory.ingest_source(SourceInput('A later statement.', 'second', idempotency_key='second'))
        assert repeated.source_ids == second.source_ids
        calls = memory.llm.call_structured.call_count
        assert not (await memory.consolidate()).report.failures
        assert memory.llm.call_structured.call_count == calls


@pytest.mark.asyncio
async def test_cancelled_view_resumes_after_restart_without_reextracting(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        configure(memory, monkeypatch)
        await memory.ingest_source(SourceInput('A durable statement.', 'source'))
        original = memory_contract.present
        monkeypatch.setattr(memory_contract, 'present', AsyncMock(side_effect=asyncio.CancelledError))
        with pytest.raises(asyncio.CancelledError):
            await memory.consolidate()
        assert len(memory.artifacts.list_claims()) == 1
        assert memory.artifacts.list_episodes()[0].extraction_status == 'complete'
        assert memory.artifacts.list_dream_runs()[-1].status == 'cancelled'
        evidence = RetrievedContextBuilder(memory.wiki, memory.artifacts).build([], budget_tokens=2000)
        assert evidence.build_incomplete
        assert 'Build Memory is incomplete' in render_memory_evidence(evidence)
    with Mycelium(tmp_path) as restarted:
        configure(restarted, monkeypatch)
        monkeypatch.setattr(memory_contract, 'present', original)
        assert not (await restarted.consolidate()).report.failures
        assert [call.kwargs['debug_label'] for call in restarted.llm.call_structured.call_args_list] == ['memory-presentation']
        assert not restarted.artifacts.build_incomplete()


@pytest.mark.asyncio
async def test_invalid_retention_never_partially_persists_and_can_retry(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        configure(memory, monkeypatch)
        await memory.ingest_source(SourceInput('A durable statement.', 'source'))
        original = memory_contract.retain

        async def invalid(llm, payload):
            result = await original(llm, payload)
            result['memories'][0]['segment_ids'] = ['missing-reference']
            return result

        monkeypatch.setattr(memory_contract, 'retain', invalid)
        result = await memory.consolidate()
        assert result.report.failures and result.report.pending_source_ids
        assert memory.artifacts.list_claims() == []
        assert len(memory.artifacts.list_entities()) == 1
        monkeypatch.setattr(memory_contract, 'retain', original)
        assert not (await memory.consolidate()).report.failures
        assert len(memory.artifacts.list_claims()) == 1


@pytest.mark.asyncio
async def test_source_chunks_preserve_text_and_metadata_and_bound_requests(tmp_path, monkeypatch):
    text = ('A long source with punctuation.  \n' * 8000)
    with Mycelium(tmp_path) as memory:
        configure(memory, monkeypatch)
        result = await memory.ingest_source(SourceInput(text, 'source', segments=({
            'segment_id': '', 'index': 0, 'speaker': 'Ari', 'role': 'user', 'content': text,
            'timestamp': '2035-02-03T10:00:00Z', 'metadata': {'external_id': 'turn-12'}},)))
        source = memory.artifacts.get_source(result.source_ids[0])
        assert ''.join(s.content for s in source.segments) == text
        assert len(source.segments) > 1
        assert all(s.role == 'user' and s.metadata['external_id'] == 'turn-12' for s in source.segments)
        sizes = []

        async def retain(llm, payload):
            sizes.append(count_tokens(json.dumps(payload['segments'])))
            return {'subjects': [], 'memories': [], 'changes': []}

        monkeypatch.setattr(memory_contract, 'retain', retain)
        assert not (await memory.consolidate()).report.failures
        assert max(sizes) <= memory.config.llm.context_window_tokens // 4
        assert len(sizes) > 1
        assert len(memory.artifacts.list_episodes()[0].segment_dispositions) == len(source.segments)
        memory.llm.call_structured.assert_not_called()


@pytest.mark.asyncio
async def test_system_metadata_never_enters_retention_and_dry_run_is_read_only(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        configure(memory, monkeypatch)
        await memory.ingest_source(SourceInput('internal scaffolding', 'source', segments=({
            'segment_id': '', 'index': 0, 'role': 'system', 'content': 'internal scaffolding'},)))
        before = memory.db.evidence_revision()
        assert not (await memory.consolidate(ConsolidationRequest(dry_run=True))).report.failures
        assert memory.db.evidence_revision() == before
        assert memory.artifacts.list_dream_runs() == []
        assert not (await memory.consolidate()).report.failures
        memory.llm.call_structured.assert_not_called()
        assert memory.artifacts.list_episodes()[0].segment_dispositions[0].disposition == 'source_only'


@pytest.mark.asyncio
async def test_context_citations_preserve_original_source_and_speaker(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        configure(memory, monkeypatch)
        first = await memory.ingest_source(SourceInput('An earlier request.', 's1', segments=({
            'segment_id': '', 'index': 0, 'role': 'assistant', 'speaker': 'Assistant', 'content': 'An earlier request.'},)))
        second = await memory.ingest_source(SourceInput('I accept that.', 's2', metadata={'context_source_ids': list(first.source_ids)}, segments=({
            'segment_id': '', 'index': 0, 'role': 'user', 'speaker': 'You', 'content': 'I accept that.'},)))
        source = memory.artifacts.get_source(second.source_ids[0])
        retainer = Retainer(memory.llm, memory.artifacts, memory.config)
        payload = await retainer.input(source, source.segments, 'b', prior_ids=[])
        value = lifecycle_response('', json.dumps(payload), memory_contract.retention_model(payload), debug_label='memory-retention')
        value['memories'][0]['segment_ids'].append(payload['context_segments'][0]['id'])
        with memory.db.transaction():
            ids = retainer.persist(source, 'b', payload, value)
        claim = memory.artifacts.get_claim(ids[0])
        assert {(p.source_id, p.speaker) for p in claim.provenance} == {(first.source_ids[0], 'Assistant'), (second.source_ids[0], 'You')}
