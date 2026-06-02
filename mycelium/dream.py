import json
import re
from datetime import datetime
from typing import Literal, Optional
import uuid

from mycelium.models import DreamReport, WikiPage, Edge, UpdateLogEntry
from mycelium.store import WikiStore, LogStore
from mycelium.ollama import OllamaClient
from mycelium.config import Config
from mycelium import prompts
from mycelium.decay import DecayEngine, record_memory_event
from mycelium.structured_outputs import (
    ConsolidationIdentifyOutput,
    WikiIndexOutput,
    WikiMergeOutput,
    WikiRewriteOutput,
    PredictionErrorOutput,
)


def _normalize_page_key(value: str) -> str:
    value = value.strip()
    if value.startswith("[[") and value.endswith("]]"):
        value = value[2:-2]
    value = value.replace(".md", "")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def _slugify(value: str) -> str:
    return _normalize_page_key(value) or "untitled"

class DreamProcess:
    def __init__(self, llm: OllamaClient, wiki: WikiStore, logs: LogStore, config: Config):
        self.llm = llm
        self.wiki = wiki
        self.logs = logs
        self.config = config
        self.decay_engine = DecayEngine(wiki, logs, config)

    async def run(
        self,
        strategy: Literal['full', 'new_only', 'association_only'] = 'full',
        dry_run: bool = False,
        conflict_policy: Literal['fork', 'override', 'merge'] = 'override',
    ) -> DreamReport:
        
        entries = self.logs.get_unconsolidated()
        
        if not entries and strategy != 'association_only':
            return DreamReport(0, 0, 0, [], 0, None)
            
        source_entry_ids = [e.entry_id for e in entries]
        index_content = self.wiki.get_index()
        
        # Chunk entries to prevent overwhelming the local LLM context window
        chunk_size = 15
        all_targets = []
        
        for idx in range(0, len(entries), chunk_size):
            chunk = entries[idx:idx + chunk_size]
            chunk_str = "\n".join([
                (
                    f"[{e.entry_id}] "
                    f"durability={e.durability}; importance={e.importance:.2f}\n{e.content}"
                )
                for e in chunk
            ])
            
            system, user = prompts.consolidation_identify_prompt(index_content, chunk_str)
            identification_res = await self.llm.call_structured(system, user, ConsolidationIdentifyOutput)
            
            chunk_targets = []
            if isinstance(identification_res, dict):
                chunk_targets = identification_res.get("targets", [])
            elif isinstance(identification_res, list):
                chunk_targets = identification_res
            elif hasattr(identification_res, "targets"):
                chunk_targets = identification_res.targets
                
            all_targets.extend(chunk_targets)
            
        identification = self._dedupe_identification(all_targets)
            
        pages_updated = 0
        pages_created = 0
        conflicts_found = []
        conflicts_resolved = 0
        title_to_slug = self._existing_title_index()
        
        for item in identification:
            if not isinstance(item, dict):
                continue
                
            page_slug = _slugify(str(item.get("page", "")))
            action = item.get("action")
            
            if not page_slug or action not in ("update", "create"):
                continue

            # Determine relevant logs for this specific page
            log_entry_ids = item.get("log_entry_ids", [])
            if log_entry_ids and isinstance(log_entry_ids, list):
                page_entries = [e for e in entries if e.entry_id in log_entry_ids]
                # Fall back to all unconsolidated logs if none are found in the filtered list
                if not page_entries:
                    page_entries = entries
            else:
                page_entries = entries

            page_entries_str = "\n".join([
                (
                    f"[{e.entry_id}] "
                    f"durability={e.durability}; importance={e.importance:.2f}\n{e.content}"
                )
                for e in page_entries
            ])
            page_source_ids = [e.entry_id for e in page_entries]
                
            if action == "update" and self.wiki.exists(page_slug):
                existing_page = self.wiki.get(page_slug)
                system, user = prompts.consolidation_rewrite_prompt(existing_page.content, page_entries_str)
                is_create = False
            else:
                existing_page = None
                system, user = prompts.consolidation_rewrite_prompt("", page_entries_str)
                is_create = True
            
            rewritten = await self.llm.call_structured(system, user, WikiRewriteOutput)
            if not isinstance(rewritten, dict):
                continue
                
            # Parse response
            title = rewritten.get("title", page_slug)
            content = rewritten.get("content", "")
            tags = rewritten.get("tags", [])
            confidence = float(rewritten.get("confidence", 0.5))
            importance = float(rewritten.get("importance", 0.5))
            title_key = _normalize_page_key(title)
            
            raw_related = rewritten.get("related", [])
            related_edges = []
            for r in raw_related:
                if isinstance(r, dict) and "target" in r and "relation" in r:
                    related_edges.append(Edge(target=r["target"], relation=r["relation"], weight=float(r.get("weight", 1.0))))
            
            now = datetime.now()
            
            if is_create:
                duplicate_slug = title_to_slug.get(title_key)
                if duplicate_slug and duplicate_slug != page_slug and self.wiki.exists(duplicate_slug):
                    existing_page = self.wiki.get(duplicate_slug)
                    existing_page.title = title
                    existing_page.content = content
                    existing_page.tags = tags
                    existing_page.related = related_edges
                    existing_page.source_log_entries = self._merge_sources(existing_page.source_log_entries, page_source_ids)
                    existing_page.version += 1
                    existing_page.last_updated = now
                    log = UpdateLogEntry(
                        existing_page.version,
                        now,
                        "system",
                        "dream",
                        0.0,
                        f"Dream consolidation deduplicated proposed page '{page_slug}' into '{duplicate_slug}'",
                        existing_page.confidence,
                        confidence,
                    )
                    existing_page.confidence = confidence
                    existing_page.importance = importance
                    existing_page.update_log.append(log)
                    record_memory_event(existing_page, "dream_updated", now=now)
                    if not dry_run:
                        self.wiki.save(existing_page)
                    pages_updated += 1
                    continue

                new_page = WikiPage(
                    slug=page_slug,
                    title=title,
                    content=content,
                    created=now,
                    last_updated=now,
                    version=1,
                    confidence=confidence,
                    importance=importance,
                    tags=tags,
                    related=related_edges,
                    source_log_entries=page_source_ids,
                    update_log=[UpdateLogEntry(1, now, "system", "dream", 0.0, "Initial creation", 0.0, confidence)]
                )
                record_memory_event(new_page, "dream_created", now=now)
                if not dry_run:
                    self.wiki.save(new_page)
                title_to_slug[title_key] = page_slug
                pages_created += 1
            else:
                # Handle conflict
                # If policy is 'fork', we only fork if there is an actual semantic contradiction/prediction error.
                # Otherwise we perform an in-place update (override).
                should_fork = False
                discrepancy_score = 0.0
                reason = "Dream consolidation: in-place update"
                
                if conflict_policy == "fork":
                    try:
                        system_pe, user_pe = prompts.prediction_error_prompt(existing_page.content, page_entries_str)
                        pe = await self.llm.call_structured(system_pe, user_pe, PredictionErrorOutput)
                        if isinstance(pe, dict):
                            conflict_type = pe.get("conflict_type", "none")
                            discrepancy_score = float(pe.get("discrepancy_score", 0.0))
                            if conflict_type in ("partial", "major") or discrepancy_score >= 0.5:
                                should_fork = True
                                reason = f"Forked during dream due to {conflict_type} conflict: {pe.get('explanation', '')}"
                            else:
                                reason = f"Dream consolidation: in-place update (policy was fork, but no contradiction found: conflict_type={conflict_type})"
                    except Exception as e:
                        # Fallback: if check fails, do not fork, default to in-place override to prevent fork pollution
                        should_fork = False
                        reason = f"Dream consolidation: in-place update (policy was fork, but prediction error check failed: {e})"
                
                if conflict_policy == "override" or (conflict_policy == "fork" and not should_fork):
                    existing_page.title = title
                    existing_page.content = content
                    existing_page.tags = tags
                    existing_page.related = related_edges
                    existing_page.source_log_entries = self._merge_sources(existing_page.source_log_entries, page_source_ids)
                    existing_page.version += 1
                    existing_page.last_updated = now
                    
                    log = UpdateLogEntry(
                        existing_page.version,
                        now,
                        "system",
                        "dream",
                        discrepancy_score,
                        reason,
                        existing_page.confidence,
                        confidence,
                    )
                    existing_page.confidence = confidence
                    existing_page.importance = importance
                    existing_page.update_log.append(log)
                    record_memory_event(existing_page, "dream_updated", now=now)
                    
                    if not dry_run:
                        self.wiki.save(existing_page)
                    pages_updated += 1
                elif conflict_policy == "fork" and should_fork:
                    fork_slug = f"{page_slug}-fork-{str(uuid.uuid4())[:4]}"
                    fork_page = WikiPage(
                        slug=fork_slug,
                        title=f"{title} (Fork)",
                        content=content,
                        created=now,
                        last_updated=now,
                        version=1,
                        confidence=confidence,
                        importance=importance,
                        tags=tags,
                        related=related_edges + [Edge(page_slug, "contradicts", 1.0)],
                        source_log_entries=page_source_ids,
                        update_log=[UpdateLogEntry(
                            1,
                            now,
                            "system",
                            "dream",
                            discrepancy_score,
                            reason,
                            0.0,
                            confidence,
                        )]
                    )
                    record_memory_event(fork_page, "dream_created", now=now)
                    
                    existing_page.related.append(Edge(fork_slug, "contradicts", 1.0))
                    existing_page.confidence = max(0.0, existing_page.confidence - 0.1)
                    record_memory_event(existing_page, "contradicted", now=now)
                    
                    conflicts_found.append(page_slug)
                    conflicts_resolved += 1
                    
                    if not dry_run:
                        self.wiki.save(fork_page)
                        self.wiki.save(existing_page)
                        
                    pages_created += 1
                    pages_updated += 1
                elif conflict_policy == "merge":
                    existing_page = self.wiki.get(page_slug)
                    # Simple merge prompt: synthesis
                    system = "You are a memory synthesis agent. Merge the following two versions of a wiki page into a single, cohesive, abstracted page."
                    user = f"VERSION 1:\n{existing_page.content}\n\nVERSION 2:\n{content}"
                    
                    merged = await self.llm.call_structured(system, user, WikiMergeOutput)
                    if isinstance(merged, dict):
                        existing_page.content = merged.get("content", existing_page.content)
                        existing_page.source_log_entries = self._merge_sources(existing_page.source_log_entries, page_source_ids)
                        existing_page.version += 1
                        existing_page.last_updated = now
                        log = UpdateLogEntry(existing_page.version, now, "system", "dream", 0.0, "Merged during dream", existing_page.confidence, confidence)
                        existing_page.update_log.append(log)
                        record_memory_event(existing_page, "dream_updated", now=now)
                        if not dry_run:
                            self.wiki.save(existing_page)
                        pages_updated += 1
                        conflicts_resolved += 1

        # 6. Update index
        if pages_updated > 0 or pages_created > 0:
            changes = f"Updated {pages_updated} pages, created {pages_created} pages."
            system, user = prompts.consolidation_index_prompt(index_content, changes)
            res_index = await self.llm.call_structured(system, user, WikiIndexOutput)
            if isinstance(res_index, dict) and "index" in res_index and not dry_run:
                self.wiki.save_index(res_index["index"])

        # 7. Mark consolidated
        if not dry_run and entries:
            self.logs.mark_consolidated([e.entry_id for e in entries])

        # 8. Run decay pass
        if not dry_run:
            await self.decay_engine.run_pass()
            
        commit_sha = None
        if self.config.git_commits and not dry_run:
            try:
                import git
                repo = git.Repo(self.config.store_path.parent)
                repo.git.add(A=True)
                commit = repo.index.commit(f"chore: dream process run ({pages_updated} up, {pages_created} cr)")
                commit_sha = commit.hexsha
            except ImportError:
                pass
            except Exception as e:
                pass

        return DreamReport(
            pages_updated=pages_updated,
            pages_created=pages_created,
            entries_consolidated=len(entries),
            conflicts_found=conflicts_found,
            conflicts_resolved=conflicts_resolved,
            git_commit_sha=commit_sha
        )

    def _dedupe_identification(self, identification: list) -> list[dict]:
        deduped: dict[str, dict] = {}
        for item in identification:
            if not isinstance(item, dict):
                continue
            page = item.get("page")
            action = item.get("action")
            if not page or action not in ("update", "create", "none"):
                continue
            slug = _slugify(str(page))
            if not slug or action == "none":
                continue
            # Safety block against numeric-only slug hallucinations (e.g. "1")
            if slug.isdigit():
                continue
                
            # Clean and normalize log entry IDs
            raw_ids = item.get("log_entry_ids", [])
            log_entry_ids = []
            for r_id in raw_ids:
                if isinstance(r_id, str):
                    cleaned = r_id.strip("[]'\" ")
                    if " — " in cleaned:
                        cleaned = cleaned.split(" — ")[0]
                    if " - " in cleaned:
                        cleaned = cleaned.split(" - ")[0]
                    cleaned = cleaned.strip()
                    if cleaned and cleaned not in log_entry_ids:
                        log_entry_ids.append(cleaned)
                        
            existing = deduped.get(slug)
            if existing is None:
                deduped[slug] = {
                    "page": slug,
                    "action": action,
                    "log_entry_ids": log_entry_ids
                }
            else:
                if existing["action"] == "create" and action == "update":
                    existing["action"] = "update"
                # Merge log_entry_ids
                existing_ids = existing.setdefault("log_entry_ids", [])
                for entry_id in log_entry_ids:
                    if entry_id not in existing_ids:
                        existing_ids.append(entry_id)
        return list(deduped.values())

    def _existing_title_index(self) -> dict[str, str]:
        title_to_slug = {}
        for page in self.wiki.list_all():
            title_to_slug.setdefault(_normalize_page_key(page.title), page.slug)
        return title_to_slug

    def _merge_sources(self, existing: list[str], new: list[str]) -> list[str]:
        merged = list(existing)
        for entry_id in new:
            if entry_id not in merged:
                merged.append(entry_id)
        return merged
