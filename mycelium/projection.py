"""Canonical statement display preserves its meaning verbatim."""

from mycelium.artifacts import MemoryClaim

def display_claim_text(claim: MemoryClaim) -> str:
    """Semantic conflicts belong in explicit reconciliation, never text cleanup."""
    return claim.text.strip()
