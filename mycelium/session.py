from datetime import datetime, timezone
from typing import Any, List, TYPE_CHECKING

from mycelium.models import WikiPage
from mycelium.materialization import sections_markdown

if TYPE_CHECKING:
    from mycelium.core import Mycelium

class Session:
    def __init__(
        self,
        mycelium: 'Mycelium',
        session_id: str,
        query: str,
    ):
        self.session_id = session_id
        self.query = query
        self.loaded_pages: List[WikiPage] = []
        self.transcript: List[dict[str, Any]] = []
        self._mycelium = mycelium

    @property
    def memory_context(self) -> str:
        """
        Returns loaded wiki pages formatted for prompt injection:
        === MEMORY: <title> (confidence: X.XX, v<N>) ===
        <page content>
        === END MEMORY ===
        """
        if not self.loaded_pages:
            return ""
            
        blocks = []
        seen_project_role_claim_ids: set[str] = set()
        for page in self.loaded_pages:
            header = f"=== MEMORY: {page.title} (confidence: {page.confidence:.2f}, v{page.version}) ==="
            body = (
                sections_markdown(page.sections, seen_project_role_claim_ids)
                if page.sections
                else page.content
            )
            if page.source_context:
                body = f"{body}\n\n{page.source_context}"
            if not body.strip():
                continue
            blocks.append(f"{header}\n{body}")
            
        return "\n\n".join(blocks) + "\n\n=== END MEMORY ==="

    def build_prompt(self, user_message: str) -> str:
        """
        Returns: memory_context + "\n\n" + user_message
        """
        context = self.memory_context
        if context:
            return f"{context}\n\n{user_message}"
        return user_message

    def record(self, role: str, content: str) -> None:
        """Appends to self.transcript."""
        self.transcript.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
