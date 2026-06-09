import datetime
from typing import List, Optional
import uuid

from mycelium.models import LogEntry
from mycelium.store import WikiStore, LogStore
from mycelium.ollama import OllamaClient
from mycelium.config import Config
from mycelium import prompts
from mycelium.structured_outputs import ImportanceRatingOutput

IMPORTANCE_LABELS = {
    "low": 0.25,
    "medium": 0.6,
    "high": 0.9,
}


def normalize_importance(value, default: float = 0.5) -> float:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in IMPORTANCE_LABELS:
            return IMPORTANCE_LABELS[normalized]
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class Encoder:
    def __init__(self, llm: OllamaClient, wiki_store: WikiStore, log_store: LogStore, config: Config):
        self.llm = llm
        self.wiki_store = wiki_store
        self.log_store = log_store
        self.config = config

    async def encode_session(
        self,
        transcript: str,
        session_id: str,
    ) -> List[LogEntry]:
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        short_id = str(uuid.uuid4())[:8]
        entry_id = f"{date_str}#session-{short_id}"
        content = transcript.strip()
        if not content:
            return []

        entry = LogEntry(
            entry_id=entry_id,
            session_id=session_id,
            timestamp=now,
            content=(
                "Raw conversation transcript. Treat this as canonical source evidence during dream "
                "consolidation and retrieval.\n\n"
                f"{content}"
            ),
            importance=0.8,
            status="raw",
            durability="durable",
            consolidated=False,
            decay_score=1.0,
        )

        self.log_store.append(entry)
        return [entry]

    async def encode(
        self,
        content: str,
        session_id: str,
        importance: Optional[float] = None,
        durability: str = "durable",
    ) -> LogEntry:
        
        final_importance = importance
        
        if importance is None:
            system, user = prompts.importance_rating_prompt(content)
            response = await self.llm.call_structured(system, user, ImportanceRatingOutput)
            
            if isinstance(response, dict):
                final_importance = float(response.get("importance", 0.5))
            else:
                final_importance = 0.5
                
        if final_importance is None:
            final_importance = 0.5
            
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        short_id = str(uuid.uuid4())[:8]
        entry_id = f"{date_str}#entry-{short_id}"
        
        entry = LogEntry(
            entry_id=entry_id,
            session_id=session_id,
            timestamp=now,
            content=content,
            importance=final_importance,
            status="raw",
            durability=durability,  # type: ignore[arg-type]
            consolidated=False,
            decay_score=1.0
        )
        
        self.log_store.append(entry)
        return entry
