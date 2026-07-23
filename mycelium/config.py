from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import tomllib

@dataclass
class LLMConfig:
    url: str = 'http://localhost:11434'
    model: str = 'gemma4:latest'
    temperature: float = 0.1
    timeout_seconds: int = 120
    context_window_tokens: int = 32768

@dataclass
class ReconsolidationConfig:
    lability_threshold: float = 0.35
    check_on_load: bool = True

@dataclass
class DreamConfig:
    conflict_policy: str = 'override'
    evidence_mode: str = 'hybrid'
    main_page_claim_limit: int = 18
    derived_insights_enabled: bool = True

@dataclass
class Config:
    context_budget_tokens: int = 32768
    llm: Optional[LLMConfig] = None
    reconsolidation: Optional[ReconsolidationConfig] = None
    dream: Optional[DreamConfig] = None

    def __post_init__(self):
        if self.llm is None:
            self.llm = LLMConfig()
        if self.reconsolidation is None:
            self.reconsolidation = ReconsolidationConfig()
        if self.dream is None:
            self.dream = DreamConfig()

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
        
        recon_data = data.get('reconsolidation', {})
        reconsolidation = ReconsolidationConfig(
            lability_threshold=recon_data.get('lability_threshold', 0.35),
            check_on_load=recon_data.get('check_on_load', True)
        )
        
        dream_data = data.get('dream', {})
        dream = DreamConfig(
            conflict_policy=dream_data.get('conflict_policy', 'override'),
            evidence_mode=dream_data.get('evidence_mode', 'hybrid'),
            main_page_claim_limit=int(dream_data.get('main_page_claim_limit', 18)),
            derived_insights_enabled=bool(dream_data.get('derived_insights_enabled', True)),
        )
        
        return cls(
            context_budget_tokens=context_budget_tokens,
            llm=llm,
            reconsolidation=reconsolidation,
            dream=dream,
        )

    @classmethod
    def defaults(cls) -> 'Config':
        return cls()
