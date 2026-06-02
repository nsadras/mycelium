import json
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

from mycelium.models import WikiPage, PredictionError, UpdateLogEntry
from mycelium.store import WikiStore
from mycelium.ollama import OllamaClient
from mycelium.config import Config
from mycelium import prompts
from mycelium.decay import record_memory_event
from mycelium.structured_outputs import PredictionErrorOutput, ReconsolidationRewriteOutput

class ReconsolidationEngine:
    def __init__(self, llm: OllamaClient, wiki: WikiStore, config: Config):
        self.llm = llm
        self.wiki = wiki
        self.config = config
        # in-memory store for accumulated signals: {(slug, session_id): [PredictionError, ...]}
        self._signals: Dict[tuple[str, str], List[PredictionError]] = defaultdict(list)

    async def check(self, page: WikiPage, context: str) -> PredictionError:
        system, user = prompts.prediction_error_prompt(page.content, context)
        response = await self.llm.call_structured(system, user, PredictionErrorOutput)
        if not isinstance(response, dict):
            # Fallback
            return PredictionError(
                conflict_type="none",
                discrepancy_score=0.0,
                explanation="Failed to parse prediction error from LLM",
                suggested_update=None
            )
            
        return PredictionError(
            conflict_type=response.get("conflict_type", "none"),
            discrepancy_score=float(response.get("discrepancy_score", 0.0)),
            explanation=response.get("explanation", ""),
            suggested_update=response.get("suggested_update")
        )

    async def flag_labile(self, page: WikiPage, session_id: str) -> None:
        self.wiki.mark_labile(page.slug, session_id)

    async def accumulate_signal(self, slug: str, session_id: str, signal: PredictionError) -> None:
        self._signals[(slug, session_id)].append(signal)

    async def resolve_labile_pages(self, session_id: str) -> List[str]:
        resolved_slugs = []
        
        # Find all keys for this session
        keys_to_resolve = [k for k in self._signals.keys() if k[1] == session_id]
        
        for key in keys_to_resolve:
            slug, _ = key
            signals = self._signals[key]
            
            if not self.wiki.exists(slug):
                continue
                
            original_page = self.wiki.get(slug)
            
            # Format signals
            signals_str = json.dumps([{
                "discrepancy_score": s.discrepancy_score,
                "explanation": s.explanation,
                "suggested_update": s.suggested_update
            } for s in signals], indent=2)
            
            system, user = prompts.reconsolidation_rewrite_prompt(original_page.content, signals_str)
            response = await self.llm.call_structured(system, user, ReconsolidationRewriteOutput)
            
            if isinstance(response, dict):
                # Apply updates
                original_page.title = response.get("title", original_page.title)
                original_page.content = response.get("content", original_page.content)
                original_page.tags = response.get("tags", original_page.tags)
                original_page.confidence = response.get("confidence", original_page.confidence)
                original_page.importance = response.get("importance", original_page.importance)
                
                reason = response.get("update_reason", "Reconsolidated based on recent session context.")
                max_score = max([s.discrepancy_score for s in signals]) if signals else 0.0
                
                # Create log entry
                log_entry = UpdateLogEntry(
                    version=original_page.version + 1,
                    date=datetime.now(),
                    session_id=session_id,
                    trigger="reconsolidation",
                    discrepancy_score=max_score,
                    reason=reason,
                    previous_confidence=original_page.confidence,
                    new_confidence=response.get("confidence", original_page.confidence)
                )
                
                original_page.version += 1
                original_page.last_updated = datetime.now()
                original_page.update_log.append(log_entry)
                record_memory_event(original_page, "contradicted", now=original_page.last_updated)
                record_memory_event(original_page, "dream_updated", now=original_page.last_updated)
                
                # Save it (resolving labile status)
                self.wiki.save(original_page)
                self.wiki.resolve_labile(slug, session_id)
                resolved_slugs.append(slug)
                
            # Clean up signals
            del self._signals[key]
            
        return resolved_slugs
