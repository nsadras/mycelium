from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import TypeVar

from mycelium.budget import count_tokens

DEFAULT_CONTEXT_WINDOW_TOKENS = 32768
DEFAULT_SAFETY_TOKENS = 2048

T = TypeVar("T")


def structured_input_budget(
    context_window_tokens: int,
    num_predict: int,
    safety_tokens: int = DEFAULT_SAFETY_TOKENS,
) -> int:
    """Return the tokens available for system, schema, and user input."""
    available = context_window_tokens - num_predict - safety_tokens
    if available <= 0:
        raise ValueError("context window is too small for the requested output budget")
    return available


def split_text_by_tokens(text: str, max_tokens: int) -> list[str]:
    """Split text without dropping characters, preferring line boundaries."""
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if not text:
        return []
    if count_tokens(text) <= max_tokens:
        return [text]

    chunks: list[str] = []
    current = ""
    for piece in _pieces_with_separators(text):
        candidate = current + piece
        if current and count_tokens(candidate) > max_tokens:
            chunks.append(current)
            current = ""
        if count_tokens(piece) <= max_tokens:
            current += piece
            continue
        hard_chunks = _hard_split(piece, max_tokens)
        if current:
            chunks.append(current)
        chunks.extend(hard_chunks[:-1])
        current = hard_chunks[-1]
    if current:
        chunks.append(current)
    return chunks


def batch_items(
    items: Sequence[T] | Iterable[T],
    render: Callable[[Sequence[T]], str],
    max_tokens: int,
) -> list[list[T]]:
    """Greedily batch complete items according to the rendered prompt size."""
    batches: list[list[T]] = []
    current: list[T] = []
    for item in items:
        candidate = [*current, item]
        if current and count_tokens(render(candidate)) > max_tokens:
            batches.append(current)
            current = [item]
        else:
            current = candidate
        if count_tokens(render(current)) > max_tokens:
            raise ValueError("a single item exceeds the prompt token budget")
    if current:
        batches.append(current)
    return batches


def _pieces_with_separators(text: str) -> list[str]:
    pieces: list[str] = []
    start = 0
    for index, char in enumerate(text):
        if char == "\n":
            pieces.append(text[start : index + 1])
            start = index + 1
    if start < len(text):
        pieces.append(text[start:])
    return pieces


def _hard_split(text: str, max_tokens: int) -> list[str]:
    chunks: list[str] = []
    remainder = text
    while remainder:
        low = 1
        high = len(remainder)
        best = 0
        while low <= high:
            midpoint = (low + high) // 2
            if count_tokens(remainder[:midpoint]) <= max_tokens:
                best = midpoint
                low = midpoint + 1
            else:
                high = midpoint - 1
        if best == 0:
            raise ValueError("max_tokens cannot accommodate the next character")
        chunks.append(remainder[:best])
        remainder = remainder[best:]
    return chunks
