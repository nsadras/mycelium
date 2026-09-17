"""Invocation accounting for resumable evaluations, including interrupted runs."""
from __future__ import annotations

import functools
import hashlib
import json
import os
import platform
import subprocess
import time
import tempfile
import uuid
from contextvars import ContextVar
from pathlib import Path

from mycelium.telemetry import trace_operation, trace_metadata

_active: ContextVar[dict | None] = ContextVar('benchmark_invocation', default=None)


def _append(root: Path, event: dict) -> None:
    with (root / 'invocations.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def begin_invocation(root: Path) -> None:
    """Call only after settings validation so rejected resumes leave no journal."""
    state = _active.get()
    if state is None:
        raise RuntimeError('Invocation is not being tracked')
    state.update(root=root, invocation_id=trace_metadata()['invocation_id'])
    _append(root, {
        'invocation_id': state['invocation_id'], 'status': 'running',
        'started_at': state['started_at'],
        'environment': environment_manifest(),
    })


def _record_execution_error(root: Path, error: str) -> None:
    path = root / 'run_manifest.json'
    manifest = json.loads(path.read_text())
    manifest['status'] = 'failed'
    if manifest.get('execution_status') != 'blocked':
        manifest['execution_status'] = 'failed'
    # A terminal invocation cannot leave a stage advertised as still running.
    # Preserve completed/disabled/blocked stages and their progress counters.
    for stage in ('encoding_status', 'qa_status', 'scoring_status', 'assessment_status'):
        if manifest.get(stage) == 'running':
            manifest[stage] = 'incomplete'
    manifest['execution_error'] = error
    with tempfile.NamedTemporaryFile(mode='w', dir=root, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(manifest, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def recorded_run(function):
    @functools.wraps(function)
    async def run(*args, **kwargs):
        state = {'started_at': time.time(), 'clock': time.perf_counter()}
        token = _active.set(state)
        status, error = 'complete', None
        try:
            with trace_operation('benchmark_invocation', invocation_id=uuid.uuid4().hex):
                return await function(*args, **kwargs)
        except BaseException as exc:
            status, error = 'failed', f'{type(exc).__name__}: {exc}'
            raise
        finally:
            try:
                if 'root' in state:
                    _append(state['root'], {
                        'invocation_id': state['invocation_id'],
                        'started_at': state['started_at'],
                        'elapsed_seconds': time.perf_counter() - state['clock'],
                        'status': status, 'error': error,
                    })
                    if error is not None:
                        _record_execution_error(state['root'], error)
            finally:
                _active.reset(token)
    return run


def prior_elapsed(root: Path) -> float:
    """Interrupted invocations remain explicitly unknown, never invented time."""
    path = root / 'invocations.jsonl'
    if not path.exists():
        return 0.0
    return sum(json.loads(line).get('elapsed_seconds', 0.0)
               for line in path.read_text().splitlines())


def invocation_started() -> float:
    state = _active.get()
    if state is None:
        raise RuntimeError('Invocation is not being tracked')
    return state['clock']


def environment_manifest():
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
    files = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root,
    ).decode().split('\0')
    source_hashes = {}
    for name in sorted(set(files)):
        path = root / name
        if not name or not path.is_file():
            continue
        if Path(name).parts[0] in {'mycelium', 'benchmarks', 'engram', 'server', 'ui'} or name in {'pyproject.toml', 'uv.lock'}:
            source_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'working_tree_patch': subprocess.check_output(['git', 'diff', 'HEAD'], text=True),
        'source_sha256': source_hashes,
        'python': platform.python_version(), 'platform': platform.platform(),
        'scorer_version': 'legacy-token-v1',
        'evidence_metric': 'rendered-projection-citation-coverage-v3',
        'elapsed_accounting': 'completed-invocations-only; interrupted durations unknown',
    }
