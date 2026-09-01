"""Authoritative rendering for memory supplied to an assistant."""

from __future__ import annotations

from mycelium.materialization import sections_markdown
from mycelium.models import WikiPage


def render_memory_context(pages: list[WikiPage]) -> str:
    """Render retrieved pages exactly as they should appear in a model prompt."""
    blocks: list[str] = []
    seen_project_role_claim_ids: set[str] = set()
    for page in pages:
        body = (
            sections_markdown(page.sections, seen_project_role_claim_ids)
            if page.sections
            else page.content
        )
        if page.source_context:
            body = f"{body}\n\n{page.source_context}" if body.strip() else page.source_context
        if not body.strip():
            continue
        header = (
            f"=== MEMORY: {page.title} "
            f"(v{page.version}) ==="
        )
        blocks.append(f"{header}\n{body}")
    return "\n\n".join(blocks) + "\n\n=== END MEMORY ===" if blocks else ""
