"""Typed entry point for context selection."""

from mycelium.prompting import render_prompt_pair


def assistant_context_selection_prompt(
    query: str,
    candidates: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "assistant/context_selection",
        query=query,
        candidates=candidates,
    )
