from dataclasses import dataclass, field
from pathlib import Path
import tomllib

@dataclass
class LLMConfig:
    url: str = 'http://localhost:11434'
    model: str = 'gemma4:latest'
    temperature: float = 0.1
    timeout_seconds: int = 120
    context_window_tokens: int = 32768

@dataclass
class DreamConfig:
    queue_claim_threshold: int = 20
    max_pending_hours: float = 24.0
    deferred_revisit_hours: float = 168.0

@dataclass
class RetrievalConfig:
    embedding_model: str = 'embeddinggemma:latest'
    candidate_limit: int = 20
    initial_result_limit: int = 5
    tool_result_limit: int = 6
    tool_search_limit: int = 3
    tool_evidence_budget_tokens: int = 6000

@dataclass
class Config:
    context_budget_tokens: int = 32768
    llm: LLMConfig = field(default_factory=LLMConfig)
    dream: DreamConfig = field(default_factory=DreamConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)

    @classmethod
    def from_toml(cls, path: Path) -> 'Config':
        """Loads config from mycelium.toml, returns Config with defaults for missing keys."""
        if not path.exists():
            return cls.defaults()
        
        with open(path, "rb") as f:
            data = tomllib.load(f)
            
        context_budget_tokens = data.get('session', {}).get('context_budget_tokens', 32768)
        
        llm_data = data.get('llm', {})
        llm = LLMConfig(
            url=llm_data.get('url', 'http://localhost:11434'),
            model=llm_data.get('model', 'gemma3:12b'),
            temperature=llm_data.get('temperature', 0.2),
            timeout_seconds=llm_data.get('timeout_seconds', 120),
            context_window_tokens=int(llm_data.get('context_window_tokens', 32768)),
        )
        
        dream_data = data.get('dream', {})
        dream = DreamConfig(
            queue_claim_threshold=max(1, int(dream_data.get('queue_claim_threshold', 20))),
            max_pending_hours=max(0.0, float(dream_data.get('max_pending_hours', 24.0))),
            deferred_revisit_hours=max(
                0.0, float(dream_data.get('deferred_revisit_hours', 168.0))
            ),
        )

        retrieval_data = data.get('retrieval', {})
        retrieval = RetrievalConfig(
            embedding_model=str(
                retrieval_data.get('embedding_model', 'embeddinggemma:latest')
            ),
            candidate_limit=max(1, int(retrieval_data.get('candidate_limit', 20))),
            initial_result_limit=max(
                1, int(retrieval_data.get('initial_result_limit', 5))
            ),
            tool_result_limit=max(
                1, int(retrieval_data.get('tool_result_limit', 6))
            ),
            tool_search_limit=max(
                1, int(retrieval_data.get('tool_search_limit', 3))
            ),
            tool_evidence_budget_tokens=max(
                1, int(retrieval_data.get('tool_evidence_budget_tokens', 6000))
            ),
        )
        
        return cls(
            context_budget_tokens=context_budget_tokens,
            llm=llm,
            dream=dream,
            retrieval=retrieval,
        )

    @classmethod
    def defaults(cls) -> 'Config':
        return cls()
