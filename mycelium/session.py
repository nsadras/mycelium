from datetime import datetime, timezone
from typing import Any, List, TYPE_CHECKING

from mycelium.operations import MemoryEvidence, WikiPageReference
from mycelium.prompting import render_prompt
from mycelium.retrieval_context import render_memory_evidence

if TYPE_CHECKING:
    from mycelium.core import Mycelium


class Session:
    def __init__(
        self,
        mycelium: "Mycelium",
        session_id: str,
        query: str,
    ):
        self.session_id = session_id
        self.query = query
        self.page_references: tuple[WikiPageReference, ...] = ()
        self.memory_evidence = MemoryEvidence()
        self.transcript: List[dict[str, Any]] = []
        self._mycelium = mycelium

    @property
    def memory_context(self) -> str:
        """Return the retrieved evidence in the canonical model-facing format."""
        return render_memory_evidence(self.memory_evidence)

    def build_prompt(self, user_message: str) -> str:
        """
        Returns: memory_context + "\n\n" + user_message
        """
        return render_prompt(
            "assistant/library_message.user.jinja",
            memory_context=self.memory_context,
            user_message=user_message,
        )

    def record(self, role: str, content: str) -> None:
        """Appends to self.transcript."""
        self.transcript.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
