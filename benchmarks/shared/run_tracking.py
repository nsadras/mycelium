"""Invocation accounting for resumable evaluations, including interrupted runs."""
from __future__ import annotations

import functools
import json
import os
import platform
import subprocess
import time
import tempfile
import uuid
from contextvars import ContextVar
from pathlib import Path

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
    state.update(root=root, invocation_id=uuid.uuid4().hex)
    _append(root, {
        'invocation_id': state['invocation_id'], 'status': 'running',
        'started_at': state['started_at'],
    })


def _record_execution_error(root: Path, error: str) -> None:
    path = root / 'run_manifest.json'
    manifest = json.loads(path.read_text())
    manifest['status'] = 'failed'
    if manifest.get('execution_status') != 'blocked':
        manifest['execution_status'] = 'failed'
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


def environment_manifest():
    return {
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'working_tree_patch': subprocess.check_output(['git', 'diff', 'HEAD'], text=True),
        'python': platform.python_version(), 'platform': platform.platform(),
        'scorer_version': 'legacy-token-v1',
        'evidence_metric': 'typed-citation-coverage-v2',
        'elapsed_accounting': 'completed-invocations-only; interrupted durations unknown',
    }
