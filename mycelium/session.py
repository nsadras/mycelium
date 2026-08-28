from datetime import datetime, timezone
from typing import Any, List, TYPE_CHECKING

from mycelium.context import render_memory_context
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
        self.transcript: List[dict[str, Any]] = []
        self._mycelium = mycelium

    @property
    def memory_context(self) -> str:
        """Return loaded pages in the canonical assistant-context format."""
        return render_memory_context(self.loaded_pages)

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
