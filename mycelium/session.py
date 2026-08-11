from typing import List, Dict, TYPE_CHECKING

from mycelium.models import WikiPage

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
        self.transcript: List[Dict[str, str]] = []
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
        for page in self.loaded_pages:
            header = f"=== MEMORY: {page.title} (confidence: {page.confidence:.2f}, v{page.version}) ==="
            body = page.content
            if page.source_context:
                body = f"{body}\n\n{page.source_context}"
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
        self.transcript.append({"role": role, "content": content})
