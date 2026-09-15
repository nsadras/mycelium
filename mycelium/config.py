from dataclasses import dataclass, field
from pathlib import Path
import tomllib
import math


def _positive_integer(name, value):
    if type(value) is not int or value <= 0:
        raise ValueError(f'{name} must be a positive integer')

@dataclass
class LLMConfig:
    url: str = 'http://localhost:11434'
    model: str = 'gemma4:12b'
    temperature: float = 1.0
    top_p: float = 0.95
    top_k: int = 64
    timeout_seconds: int = 900
    context_window_tokens: int = 65536
    reasoning_enabled: bool = True
    reasoning_output_tokens: int = 32768
    reasoning_format: str = "prompt"

    def __post_init__(self):
        if not self.model.strip() or not self.url.strip():
            raise ValueError("Model and URL must be nonempty")
        for name in ('context_window_tokens', 'timeout_seconds', 'reasoning_output_tokens', 'top_k'):
            _positive_integer(name, getattr(self, name))
        for name in ('temperature', 'top_p'):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f'{name} must be finite')
        if self.temperature < 0 or not 0 < self.top_p <= 1:
            raise ValueError('temperature must be nonnegative and top_p in (0, 1]')
        if type(self.reasoning_enabled) is not bool:
            raise ValueError("reasoning_enabled must be a boolean")
        if self.reasoning_output_tokens <= 0:
            raise ValueError("reasoning_output_tokens must be positive")
        if self.reasoning_format not in {"prompt", "native"}:
            raise ValueError("reasoning_format must be prompt or native")

@dataclass
class RetrievalConfig:
    embedding_model: str = 'embeddinggemma:latest'
    candidate_limit: int = 20
    initial_result_limit: int = 5
    tool_result_limit: int = 6
    tool_search_limit: int = 3
    tool_evidence_budget_tokens: int = 6000

    def __post_init__(self):
        if not isinstance(self.embedding_model, str) or not self.embedding_model.strip():
            raise ValueError('embedding_model must be nonempty')
        for name in ('candidate_limit', 'initial_result_limit', 'tool_result_limit',
                     'tool_search_limit', 'tool_evidence_budget_tokens'):
            _positive_integer(name, getattr(self, name))
        if self.initial_result_limit > 5 or self.tool_result_limit > 6:
            raise ValueError('Initial and tool result limits must be at most 5 and 6')

@dataclass
class Config:
    context_budget_tokens: int = 32768
    llm: LLMConfig = field(default_factory=LLMConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)

    def __post_init__(self):
        _positive_integer('context_budget_tokens', self.context_budget_tokens)

    @classmethod
    def from_toml(cls, path: Path) -> 'Config':
        """Loads config from mycelium.toml, returns Config with defaults for missing keys."""
        with open(path, "rb") as f:
            data = tomllib.load(f)
            
        return cls(
            **data.get('session', {}),
            llm=LLMConfig(**data.get('llm', {})),
            retrieval=RetrievalConfig(**data.get('retrieval', {})),
        )

    @classmethod
    def defaults(cls) -> 'Config':
        return cls()
