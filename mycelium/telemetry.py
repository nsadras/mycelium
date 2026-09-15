"""Task-local linkage for diagnostics; never included in model prompts."""
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

_context: ContextVar[dict] = ContextVar('mycelium_trace_context', default={})


def trace_metadata() -> dict:
    return dict(_context.get())


@contextmanager
def trace_operation(operation: str, **identifiers):
    parent = _context.get()
    context = {
        **parent,
        **identifiers,
        'operation': operation,
        'operation_id': uuid4().hex,
        'parent_operation_id': parent.get('operation_id'),
    }
    token = _context.set(context)
    try:
        yield dict(context)
    finally:
        _context.reset(token)
