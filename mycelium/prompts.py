"""Typed entry point for context selection."""

from mycelium.prompting import render_prompt_pair


def assistant_context_selection_prompt(
    query: str,
    candidates: str,
    *, limit: int = 5,
) -> tuple[str, str]:
    return render_prompt_pair(
        "assistant/context_selection",
        query=query,
        candidates=candidates,
        limit=limit,
    )
