from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import tomllib

@dataclass
class LLMConfig:
    provider: str = 'ollama'
    url: str = 'http://localhost:11434'
    model: str = 'gemma4:latest'
    temperature: float = 0.1
    timeout_seconds: int = 120
    max_retries: int = 3
    context_window_tokens: int = 32768

@dataclass
class ReconsolidationConfig:
    enabled: bool = True
    lability_threshold: float = 0.35
    lability_window: str = 'session'
    check_on_load: bool = True

@dataclass
class DreamConfig:
    strategy: str = 'full'
    conflict_policy: str = 'override'
    max_pages_per_run: int = 20
    evidence_mode: str = 'hybrid'
    main_page_claim_limit: int = 18
    projection_page_max_chars: int = 14000
    projection_page_max_records: int = 60
    derived_insights_enabled: bool = True

@dataclass
class DecayConfig:
    archive_threshold: float = 0.10
    log_threshold: float = 0.05
    half_life_hours: int = 168

@dataclass
class Config:
    store_path: Path = Path('./mycelium_store')
    context_budget_tokens: int = 32768
    llm: Optional[LLMConfig] = None
    reconsolidation: Optional[ReconsolidationConfig] = None
    dream: Optional[DreamConfig] = None
    decay: Optional[DecayConfig] = None

    def __post_init__(self):
        if self.llm is None:
            self.llm = LLMConfig()
        if self.reconsolidation is None:
            self.reconsolidation = ReconsolidationConfig()
        if self.dream is None:
            self.dream = DreamConfig()
        if self.decay is None:
            self.decay = DecayConfig()

    @classmethod
    def from_toml(cls, path: Path) -> 'Config':
        """Loads config from mycelium.toml, returns Config with defaults for missing keys."""
        if not path.exists():
            return cls.defaults()
        
        with open(path, "rb") as f:
            data = tomllib.load(f)
            
        store_path = Path(data.get('store', {}).get('path', './mycelium_store'))
        context_budget_tokens = data.get('session', {}).get('context_budget_tokens', 32768)
        
        llm_data = data.get('llm', {})
        llm = LLMConfig(
            provider=llm_data.get('provider', 'ollama'),
            url=llm_data.get('url', 'http://localhost:11434'),
            model=llm_data.get('model', 'gemma3:12b'),
            temperature=llm_data.get('temperature', 0.2),
            timeout_seconds=llm_data.get('timeout_seconds', 120),
            max_retries=llm_data.get('max_retries', 3),
            context_window_tokens=int(llm_data.get('context_window_tokens', 32768)),
        )
        
        recon_data = data.get('reconsolidation', {})
        reconsolidation = ReconsolidationConfig(
            enabled=recon_data.get('enabled', True),
            lability_threshold=recon_data.get('lability_threshold', 0.35),
            lability_window=recon_data.get('lability_window', 'session'),
            check_on_load=recon_data.get('check_on_load', True)
        )
        
        dream_data = data.get('dream', {})
        dream = DreamConfig(
            strategy=dream_data.get('strategy', 'full'),
            conflict_policy=dream_data.get('conflict_policy', 'override'),
            max_pages_per_run=dream_data.get('max_pages_per_run', 20),
            evidence_mode=dream_data.get('evidence_mode', 'hybrid'),
            main_page_claim_limit=int(dream_data.get('main_page_claim_limit', 18)),
            projection_page_max_chars=int(dream_data.get('projection_page_max_chars', 14000)),
            projection_page_max_records=int(dream_data.get('projection_page_max_records', 60)),
            derived_insights_enabled=bool(dream_data.get('derived_insights_enabled', True)),
        )
        
        decay_data = data.get('decay', {})
        decay = DecayConfig(
            archive_threshold=decay_data.get('archive_threshold', 0.10),
            log_threshold=decay_data.get('log_threshold', 0.05),
            half_life_hours=decay_data.get('half_life_hours', 168)
        )
        
        return cls(
            store_path=store_path,
            context_budget_tokens=context_budget_tokens,
            llm=llm,
            reconsolidation=reconsolidation,
            dream=dream,
            decay=decay
        )

    @classmethod
    def defaults(cls) -> 'Config':
        return cls()
