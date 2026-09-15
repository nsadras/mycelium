import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request

from engram.config import EngramConfig
from mycelium.telemetry import trace_operation, trace_metadata
from server.upload_limits import AudioUploadLimitMiddleware


@pytest.mark.asyncio
async def test_trace_context_is_task_local_and_restores_parent():
    async def task(identifier):
        with trace_operation('answer', query_id=identifier) as outer:
            await asyncio.sleep(0)
            with trace_operation('search') as inner:
                assert inner['query_id'] == identifier
                assert inner['parent_operation_id'] == outer['operation_id']
            assert trace_metadata() == outer
            return outer['operation_id']
    ids = await asyncio.gather(task('q1'), task('q2'))
    assert len(set(ids)) == 2
    assert trace_metadata() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize('declared', [False, True])
async def test_upload_body_limit_applies_before_endpoint_and_closes_partial_files(monkeypatch, declared):
    import starlette.formparsers as parser
    files = []
    original = parser.SpooledTemporaryFile
    def spooled(*args, **kwargs):
        file = original(*args, **kwargs)
        files.append(file)
        return file
    monkeypatch.setattr(parser, 'SpooledTemporaryFile', spooled)
    app = FastAPI()
    admitted = []
    @app.post('/api/engram/meetings/upload')
    async def upload(request: Request):
        async with request.form() as form:
            admitted.append(form['file'])
        return {'accepted': True}
    app.add_middleware(AudioUploadLimitMiddleware, max_body_bytes=lambda: 200)
    prefix = b'--abc\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\n\r\n'
    chunks = [prefix, b'x' * 100, b'x' * 100, b'\r\n--abc--\r\n']
    async def content():
        for chunk in chunks:
            yield chunk
    headers = {'Content-Type': 'multipart/form-data; boundary=abc'}
    if declared:
        headers['Content-Length'] = str(sum(map(len, chunks)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://localhost') as client:
        response = await client.post('/api/engram/meetings/upload', headers=headers, content=content())
    assert response.status_code == 413
    assert admitted == []
    assert all(file.closed for file in files)
    assert bool(files) is not declared


@pytest.mark.parametrize('field,value', [('max_upload_bytes', True), ('whisper_batch_size', 1.5),
    ('summary_context_window_tokens', 0), ('summary_temperature', float('nan')), ('ollama_model', '')])
def test_engram_config_rejects_invalid_values(field, value):
    with pytest.raises(ValueError):
        EngramConfig(**{field: value})


def test_engram_requested_config_must_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        EngramConfig.from_toml(tmp_path / 'missing.toml')


@pytest.mark.asyncio
async def test_model_inventory_records_exact_digests_and_rejects_changed_resume(monkeypatch):
    from benchmarks.shared.adapters import OllamaQaClient
    from benchmarks.shared.provenance import model_inventory, validate_model_resume
    async def get(self, url):
        return httpx.Response(200, request=httpx.Request('GET', url),
                              json={'models': [{'name': 'configured:latest', 'digest': 'digest-1'}]})
    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    qa = OllamaQaClient(url='http://localhost:11434', model='configured')
    inventory = await model_inventory(SimpleNamespace(qa_client=qa))
    assert inventory['qa']['digest'] == 'digest-1'
    validate_model_resume(inventory, inventory)
    with pytest.raises(ValueError, match='provenance differs'):
        validate_model_resume(inventory, {'qa': {**inventory['qa'], 'digest': 'digest-2'}})


@pytest.mark.asyncio
async def test_benchmark_question_trace_matches_nested_model_trace(tmp_path, monkeypatch):
    from benchmarks.suites.locomo import run_locomo
    from tests.test_benchmarks import FakeMemorySystem
    system = FakeMemorySystem()
    captured = []
    original = system.answer
    async def answer(question, metadata):
        captured.append(trace_metadata())
        return await original(question, metadata)
    system.answer = answer
    monkeypatch.setattr('benchmarks.suites.locomo.model_inventory', AsyncMock(return_value={}))
    await run_locomo(data_path=Path('tests/fixtures/locomo_tiny.json'), output_dir=tmp_path,
                     system=system, prediction_key='answer')
    row = json.loads(next((tmp_path/'questions').glob('*.json')).read_text())
    assert row['metadata']['trace'] == captured[0]
    assert captured[0]['query_id']
    journal = [json.loads(line) for line in (tmp_path/'invocations.jsonl').read_text().splitlines()]
    assert captured[0]['invocation_id'] == journal[0]['invocation_id']


def test_provenance_includes_new_source_modules():
    import hashlib
    from benchmarks.shared.run_tracking import environment_manifest
    manifest = environment_manifest()
    path = Path('mycelium/telemetry.py')
    assert manifest['source_sha256'][str(path)] == hashlib.sha256(path.read_bytes()).hexdigest()
