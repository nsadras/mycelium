from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from mycelium import Mycelium
from mycelium.artifacts import ArtifactStore, SourceDocument, SourceSegment, MemoryClaim, ClaimProvenance
from mycelium.claim_index import ClaimSearchHit
from mycelium.config import Config
from mycelium.database import UnitOfWork
from mycelium.memory_workspace import merge_memory_evidence
from mycelium.operations import EvidenceRecord, EvidenceClaim, MemoryEvidence, RetrievalRequest, RetrievalError
from mycelium.retrieval_context import RetrievedContextBuilder
from mycelium.store import WikiStore


def test_explicit_config_precedence_and_missing_file(tmp_path):
    path = tmp_path / 'config.toml'
    path.write_text('[llm]\nmodel="file-model"\nurl="http://file:123"\n[session]\ncontext_budget_tokens=20000\n')
    with Mycelium(tmp_path / 'store', config_path=path, ollama_model='override', memory_profile='none') as memory:
        assert memory.llm.model == 'override'
        assert memory.llm.url == 'http://file:123'
        assert memory.config.context_budget_tokens == 20000
    with pytest.raises(FileNotFoundError):
        Config.from_toml(tmp_path / 'missing.toml')


def test_workspace_unions_equal_revision_and_rejects_older_interpretation():
    original = EvidenceRecord('f1','fact','A supported fact.',None,None,('c1','c2'),
                              canonical_claims=(EvidenceClaim('c1','First assertion.'),),revision=2)
    addition = replace(original,canonical_claims=(EvidenceClaim('c2','Second assertion.'),))
    merged = merge_memory_evidence(MemoryEvidence(records=(original,)),MemoryEvidence(records=(addition,)))
    assert {c.claim_id for c in merged.records[0].canonical_claims} == {'c1','c2'}
    assert merge_memory_evidence(merged,MemoryEvidence(records=(addition,))) == merged
    newer = replace(original,statement='Corrected fact.',revision=3)
    updated = merge_memory_evidence(merged,MemoryEvidence(records=(newer,)))
    assert merge_memory_evidence(updated,MemoryEvidence(records=(original,))) == updated


def seed(root: Path):
    artifacts = ArtifactStore(root / 'artifacts')
    artifacts.save_source(SourceDocument('s1','conversation','session','2026-01-01',None,[],[SourceSegment('seg1',0,'Nora prefers tea.')]))
    claim = MemoryClaim('c1','Nora prefers tea.',[{'entity':'Nora','role':'subject'}],[ClaimProvenance('s1',['seg1'])],'2026-01-01')
    artifacts.save_claim(claim)
    hit = ClaimSearchHit('c1',claim.text,'short_term',None,None,None,None,None)
    return artifacts,claim,hit


def test_renderer_drops_retracted_hit_without_scanning_facts(tmp_path, monkeypatch):
    artifacts,claim,hit = seed(tmp_path)
    monkeypatch.setattr(artifacts,'list_consolidated_facts',lambda: pytest.fail('whole fact scan'))
    builder = RetrievedContextBuilder(WikiStore(tmp_path/'wiki'),artifacts)
    builder.build([hit], budget_tokens=1000)
    artifacts.save_claim(replace(claim,status='retracted'))
    assert builder.build([hit],budget_tokens=1000).records == ()


def test_snapshot_indexed_lookup_merges_writes_and_detects_conflicts(tmp_path):
    artifacts,claim,_ = seed(tmp_path)
    unit = UnitOfWork(artifacts.db)
    assert unit.ids('claims','status','active') == ['c1']
    unit.put('claims','c1',{'status':'retracted'})
    unit.put('claims','c2',{'status':'active'})
    assert unit.ids('claims','status','active') == ['c2']
    artifacts.save_claim(replace(claim,text='Nora prefers coffee.'))
    with pytest.raises(ValueError,match='changed'):
        unit.validate_reads()
    unit.close()


@pytest.mark.asyncio
async def test_retrieval_reselects_after_retraction(tmp_path,monkeypatch):
    from mycelium.context_selection import AssistantContextSelection, AssistantContextSelector
    with Mycelium(tmp_path,memory_profile='none') as memory:
        artifacts,claim,hit = seed(tmp_path)
        memory.retriever.claim_index.search = AsyncMock(side_effect=[[hit],[]])
        async def select(self,query,candidates):
            if candidates:
                artifacts.save_claim(replace(claim,status='retracted'))
            return AssistantContextSelection(tuple(c.candidate_id for c in candidates),{})
        monkeypatch.setattr(AssistantContextSelector,'select_with_trace',select)
        result = await memory.retrieve_context(RetrievalRequest('Preferences?'))
        assert result.evidence.records == ()
        assert memory.retriever.claim_index.search.await_count == 2


@pytest.mark.asyncio
async def test_admission_failure_is_not_empty_memory(tmp_path,monkeypatch):
    from mycelium.context_selection import AssistantContextSelection, AssistantContextSelector
    with Mycelium(tmp_path,memory_profile='none') as memory:
        _,_,hit = seed(tmp_path)
        memory.retriever.claim_index.search = AsyncMock(return_value=[hit])
        monkeypatch.setattr(AssistantContextSelector,'select_with_trace',AsyncMock(return_value=AssistantContextSelection((),{},'timeout')))
        with pytest.raises(RetrievalError,match='admission'):
            await memory.retrieve_context(RetrievalRequest('Preferences?'))


@pytest.mark.asyncio
async def test_private_network_requests_require_allowed_host_and_same_origin():
    import httpx
    from server.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        assert (await client.get('/api/nonexistent')).status_code == 404
        assert (await client.get('/api/nonexistent', headers={'Origin': 'http://localhost'})).status_code == 404
        for origin in ('http://untrusted.example', 'null', 'https://localhost', 'http://['):
            assert (await client.get('/api/nonexistent', headers={'Origin': origin})).status_code == 403
        assert (await client.get('/api/nonexistent', headers={'Host': 'untrusted.example'})).status_code == 400


@pytest.mark.asyncio
async def test_benchmark_rejected_resume_does_not_change_invocation_accounting(tmp_path):
    import json
    from benchmarks.suites.locomo import run_locomo
    from benchmarks.shared.run_tracking import prior_elapsed
    from tests.test_benchmarks import FakeMemorySystem

    args = dict(data_path=Path('tests/fixtures/locomo_tiny.json'), output_dir=tmp_path,
                system=FakeMemorySystem(), prediction_key='answer')
    await run_locomo(**args)
    journal = (tmp_path / 'invocations.jsonl').read_text()
    events = [json.loads(line) for line in journal.splitlines()]
    assert [event['status'] for event in events] == ['running', 'complete']
    assert events[0]['invocation_id'] == events[1]['invocation_id']
    assert prior_elapsed(tmp_path) > 0
    with pytest.raises(ValueError, match='settings differ'):
        await run_locomo(**args, max_questions=0)
    assert (tmp_path / 'invocations.jsonl').read_text() == journal


@pytest.mark.asyncio
async def test_incomplete_encoding_blocks_qa_and_records_failure(tmp_path):
    import json
    from benchmarks.suites.locomo import run_locomo
    from tests.test_benchmarks import FakeMemorySystem

    system = FakeMemorySystem()
    system.stats = lambda: {'encoding_status': 'incomplete'}
    system.answer = AsyncMock()
    with pytest.raises(RuntimeError, match='Encoding is incomplete'):
        await run_locomo(data_path=Path('tests/fixtures/locomo_tiny.json'), output_dir=tmp_path,
                         system=system, prediction_key='answer')
    system.answer.assert_not_awaited()
    manifest = json.loads((tmp_path / 'run_manifest.json').read_text())
    assert manifest['encoding_status'] == 'incomplete'
    assert manifest['qa_status'] == 'not_run'
    assert manifest['execution_status'] == 'blocked'
    assert json.loads((tmp_path / 'invocations.jsonl').read_text().splitlines()[-1])['status'] == 'failed'


@pytest.mark.parametrize('section, field, value', [
    ('retrieval', 'candidate_limit', '0'),
    ('retrieval', 'tool_search_limit', '-1'),
    ('retrieval', 'initial_result_limit', '6'),
    ('session', 'context_budget_tokens', 'true'),
    ('llm', 'temperature', 'nan'),
    ('llm', 'top_p', '1.5'),
    ('llm', 'context_window_tokens', '2.5'),
])
def test_config_rejects_invalid_values_without_silent_clamping(tmp_path, section, field, value):
    path = tmp_path / 'invalid.toml'
    path.write_text(f'[{section}]\n{field}={value}\n')
    with pytest.raises(ValueError):
        Config.from_toml(path)
