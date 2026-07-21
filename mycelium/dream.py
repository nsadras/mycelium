import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Literal
import uuid

from mycelium.models import DreamReport, WikiPage, Edge, UpdateLogEntry, LogEntry
from mycelium.store import WikiStore, LogStore
from mycelium.ollama import OllamaClient
from mycelium.config import Config
from mycelium.batching import batch_items, split_text_by_tokens, structured_input_budget
from mycelium import prompts
from mycelium.decay import DecayEngine, record_memory_event
from mycelium.structured_outputs import (
    CanonicalizationOutput,
    ConsolidationIdentifyOutput,
    ToolObservationExtractionOutput,
    WikiMergeOutput,
    WikiRewriteOutput,
    PredictionErrorOutput,
    WikiAppendOutput,
)

logger = logging.getLogger(__name__)

VALID_EDGE_RELATIONS = {
    "causes",
    "contradicts",
    "exemplifies",
    "generalizes",
    "precedes",
    "enables",
    "informs",
}

PLACEHOLDER_SLUG_RE = re.compile(r"^(page-slug|new-page|page|topic|untitled)(-\d+|-?[a-z])?$")
PLACEHOLDER_TITLE_RE = re.compile(r"^(page|topic|new page|project documentation)$", re.IGNORECASE)
PAGE_TYPES = {"entity", "event", "topic"}


@dataclass(frozen=True)
class EvidenceChunk:
    evidence_id: str
    entry_id: str
    session_id: str
    timestamp: datetime
    content: str
    importance: float
    durability: str
    chunk_index: int
    chunk_count: int


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


def _is_tool_entry(entry: LogEntry) -> bool:
    name = entry.entry_id.split("#", 1)[1] if "#" in entry.entry_id else entry.entry_id
    return name.startswith("tool-")

class DreamProcess:
    def __init__(self, llm: OllamaClient, wiki: WikiStore, logs: LogStore, config: Config):
        self.llm = llm
        self.wiki = wiki
        self.logs = logs
        self.config = config
        self.decay_engine = DecayEngine(wiki, logs, config)
        self._identification_failures: dict[str, str] = {}
        self._preparation_failures: dict[str, str] = {}

    async def run(
        self,
        strategy: Literal['full', 'new_only', 'association_only'] = 'full',
        dry_run: bool = False,
        conflict_policy: Literal['fork', 'override', 'merge'] = 'override',
    ) -> DreamReport:
        
        raw_entries = self.logs.get_unconsolidated()
        self._preparation_failures = {}
        entries = await self._prepare_entries(raw_entries)
        evidence = self._build_evidence(entries)
        self._identification_failures = {}
        
        if not entries and strategy != 'association_only':
            completed_source_ids = [
                entry.entry_id
                for entry in raw_entries
                if entry.entry_id not in self._preparation_failures
            ]
            pending_source_ids = [
                entry.entry_id
                for entry in raw_entries
                if entry.entry_id in self._preparation_failures
            ]
            if not dry_run and completed_source_ids:
                self.logs.mark_consolidated(completed_source_ids)
                await self.decay_engine.run_pass()
            if not dry_run and self._index_needs_rebuild():
                self._save_deterministic_index({}, dry_run=False, now=datetime.now())
            return DreamReport(
                0,
                0,
                len(completed_source_ids),
                [],
                0,
                None,
                completed_source_ids=completed_source_ids,
                pending_source_ids=pending_source_ids,
                failures=[
                    {"stage": "preparation", "source_id": source_id, "reason": reason}
                    for source_id, reason in self._preparation_failures.items()
                ],
            )
            
        index_content = self.wiki.get_index()
        
        all_targets = []
        identify_batches = self._evidence_batches(
            evidence,
            lambda text: prompts.consolidation_identify_prompt(index_content, text),
            num_predict=2048,
        )
        for chunk in identify_batches:
            all_targets.extend(await self._identify_targets_for_chunk(index_content, chunk))
            
        identification = self._dedupe_identification(all_targets)
        identification = await self._canonicalize_identification(identification, evidence)
        evidence_by_id = {chunk.evidence_id: chunk for chunk in evidence}
        failed_source_ids = {
            evidence_by_id[evidence_id].entry_id
            for evidence_id in self._identification_failures
            if evidence_id in evidence_by_id
        }
        failed_source_ids.update(self._preparation_failures)
        failures = [
            {
                "stage": "identification",
                "source_id": evidence_by_id[evidence_id].entry_id,
                "reason": reason,
            }
            for evidence_id, reason in self._identification_failures.items()
            if evidence_id in evidence_by_id
        ]
        failures.extend(
            {"stage": "preparation", "source_id": source_id, "reason": reason}
            for source_id, reason in self._preparation_failures.items()
        )
            
        pages_updated = 0
        pages_created = 0
        updated_operations: dict[str, int] = {}
        created_operations: dict[str, int] = {}
        conflicts_found = []
        conflicts_resolved = 0
        title_to_slug = self._existing_title_index()
        changed_pages: dict[str, WikiPage] = {}
        changed_page_sources: dict[str, set[str]] = {}
        
        for item in identification:
            if not isinstance(item, dict):
                continue
                
            page_slug = _slugify(str(item.get("page", "")))
            action = item.get("action")
            page_type = self._page_type_for_target(item)
            
            if not page_slug or action not in ("update", "create"):
                continue
            if self._is_placeholder_slug(page_slug):
                continue

            evidence_ids = set(item.get("evidence_ids", []))
            page_evidence = [chunk for chunk in evidence if chunk.evidence_id in evidence_ids]
            if not page_evidence:
                continue
            page_source_ids = list(dict.fromkeys(chunk.entry_id for chunk in page_evidence))

            page_exists = self.wiki.exists(page_slug)
            if page_exists:
                existing_page = self.wiki.get(page_slug)
                existing_content = existing_page.content
                is_create = False
            else:
                existing_page = None
                existing_content = ""
                is_create = True
            
            try:
                rewritten, rewrite_batches = await self._rewrite_evidence_batches(
                    page_slug,
                    page_type,
                    existing_content,
                    page_evidence,
                )
            except Exception as exc:
                logger.warning("Skipping dream rewrite for %s after structured output failure: %s", page_slug, exc)
                failed_source_ids.update(page_source_ids)
                failures.append({"stage": "rewrite", "source_id": ",".join(page_source_ids), "reason": str(exc)})
                continue
            if not isinstance(rewritten, dict):
                failed_source_ids.update(page_source_ids)
                continue
                
            # Parse response
            title = rewritten.get("title", page_slug)
            content = rewritten.get("content", "")
            tags = rewritten.get("tags", [])
            tags = self._typed_tags(tags, page_type)
            confidence = float(rewritten.get("confidence", 0.5))
            importance = float(rewritten.get("importance", 0.5))
            title_key = _normalize_page_key(title)
            if self._is_low_quality_rewrite(page_slug, title, content):
                failed_source_ids.update(page_source_ids)
                failures.append({"stage": "rewrite", "source_id": ",".join(page_source_ids), "reason": "low-quality rewrite"})
                continue
            
            raw_related = rewritten.get("related", [])
            valid_slugs = self._valid_slugs(extra=[page_slug])
            related_edges = []
            for r in raw_related:
                if isinstance(r, dict) and "target" in r and "relation" in r:
                    relation = str(r["relation"]).strip().lower()
                    target = _slugify(str(r["target"]))
                    if relation in VALID_EDGE_RELATIONS and target in valid_slugs:
                        related_edges.append(Edge(target=target, relation=relation, weight=float(r.get("weight", 1.0))))

            content = self._sanitize_wiki_links(content, valid_slugs)
            
            now = datetime.now()
            
            if is_create:
                duplicate_slug = title_to_slug.get(title_key)
                if (
                    duplicate_slug
                    and duplicate_slug != page_slug
                    and (duplicate_slug in changed_pages or self.wiki.exists(duplicate_slug))
                ):
                    existing_page = changed_pages.get(duplicate_slug) or self.wiki.get(duplicate_slug)
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
                    changed_pages[existing_page.slug] = existing_page
                    changed_page_sources.setdefault(existing_page.slug, set()).update(page_source_ids)
                    pages_updated += 1
                    updated_operations[existing_page.slug] = updated_operations.get(existing_page.slug, 0) + 1
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
                changed_pages[new_page.slug] = new_page
                changed_page_sources.setdefault(new_page.slug, set()).update(page_source_ids)
                title_to_slug[title_key] = page_slug
                pages_created += 1
                created_operations[new_page.slug] = created_operations.get(new_page.slug, 0) + 1
            else:
                # Handle conflict
                # If policy is 'fork', we only fork if there is an actual semantic contradiction/prediction error.
                # Otherwise we perform an in-place update (override).
                should_fork = False
                discrepancy_score = 0.0
                reason = "Dream consolidation: in-place update"
                
                if conflict_policy == "fork":
                    try:
                        for page_entries_str in rewrite_batches:
                            system_pe, user_pe = prompts.prediction_error_prompt(existing_page.content, page_entries_str)
                            pe = await self.llm.call_structured(system_pe, user_pe, PredictionErrorOutput)
                            if not isinstance(pe, dict):
                                continue
                            conflict_type = pe.get("conflict_type", "none")
                            discrepancy_score = max(
                                discrepancy_score,
                                float(pe.get("discrepancy_score", 0.0)),
                            )
                            if conflict_type in ("partial", "major") or discrepancy_score >= 0.5:
                                should_fork = True
                                reason = f"Forked during dream due to {conflict_type} conflict: {pe.get('explanation', '')}"
                                break
                            reason = f"Dream consolidation: in-place update (policy was fork, but no contradiction found: conflict_type={conflict_type})"
                    except Exception as e:
                        # Fallback: if check fails, do not fork, default to in-place override to prevent fork pollution
                        should_fork = False
                        reason = f"Dream consolidation: in-place update (policy was fork, but prediction error check failed: {e})"
                
                if conflict_policy == "override" or (conflict_policy == "fork" and not should_fork):
                    # Additive update: extract only new facts and append them
                    try:
                        append_outputs = await self._append_evidence_batches(
                            existing_page,
                            page_slug,
                            page_type,
                            page_evidence,
                        )
                    except Exception as exc:
                        logger.warning("Additive append failed for %s, skipping: %s", page_slug, exc)
                        failed_source_ids.update(page_source_ids)
                        failures.append({"stage": "append", "source_id": ",".join(page_source_ids), "reason": str(exc)})
                        continue

                    facts_added = any(output[1] for output in append_outputs)
                    append_data = self._merge_append_outputs([output[0] for output in append_outputs])

                    if not facts_added:
                        # Fallback to full rewrite if no facts were appended
                        if self._is_noop_update(existing_page, title, content, tags, related_edges, page_source_ids):
                            continue

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
                            reason + " (Fallback to full rewrite)",
                            existing_page.confidence,
                            confidence,
                        )
                        existing_page.confidence = confidence
                        existing_page.importance = importance
                        existing_page.update_log.append(log)
                    else:
                        existing_page.source_log_entries = self._merge_sources(existing_page.source_log_entries, page_source_ids)
                        existing_page.version += 1
                        existing_page.last_updated = now

                        conf_adj = float(append_data.get("confidence_adjustment", 0.0))
                        imp_adj = float(append_data.get("importance_adjustment", 0.0))
                        new_confidence = max(0.0, min(1.0, existing_page.confidence + conf_adj))
                        new_importance = max(0.0, min(1.0, existing_page.importance + imp_adj))

                        n_facts = len(append_data.get("new_facts", []))
                        log = UpdateLogEntry(
                            existing_page.version,
                            now,
                            "system",
                            "dream",
                            discrepancy_score,
                            f"Additive dream update: {n_facts} new fact(s) appended",
                            existing_page.confidence,
                            new_confidence,
                        )
                        existing_page.confidence = new_confidence
                        existing_page.importance = new_importance
                        existing_page.update_log.append(log)

                    record_memory_event(existing_page, "dream_updated", now=now)

                    changed_pages[existing_page.slug] = existing_page
                    changed_page_sources.setdefault(existing_page.slug, set()).update(page_source_ids)
                    pages_updated += 1
                    updated_operations[existing_page.slug] = updated_operations.get(existing_page.slug, 0) + 1
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
                    
                    changed_pages[fork_page.slug] = fork_page
                    changed_pages[existing_page.slug] = existing_page
                    changed_page_sources.setdefault(fork_page.slug, set()).update(page_source_ids)
                    changed_page_sources.setdefault(existing_page.slug, set()).update(page_source_ids)
                        
                    pages_created += 1
                    pages_updated += 1
                    created_operations[fork_page.slug] = created_operations.get(fork_page.slug, 0) + 1
                    updated_operations[existing_page.slug] = updated_operations.get(existing_page.slug, 0) + 1
                elif conflict_policy == "merge":
                    existing_page = self.wiki.get(page_slug)
                    # Simple merge prompt: synthesis
                    system = "You are a memory synthesis agent. Merge the following two versions of a wiki page into a single, cohesive, abstracted page."
                    user = f"VERSION 1:\n{existing_page.content}\n\nVERSION 2:\n{content}"
                    
                    try:
                        merged = await self.llm.call_structured(system, user, WikiMergeOutput)
                    except Exception as exc:
                        logger.warning("Skipping dream merge for %s after structured output failure: %s", page_slug, exc)
                        failed_source_ids.update(page_source_ids)
                        failures.append({"stage": "merge", "source_id": ",".join(page_source_ids), "reason": str(exc)})
                        continue
                    if isinstance(merged, dict):
                        merged_content = self._sanitize_wiki_links(merged.get("content", existing_page.content), self._valid_slugs(extra=[page_slug]))
                        if self._normalized_text(merged_content) == self._normalized_text(existing_page.content):
                            continue
                        existing_page.content = merged_content
                        existing_page.source_log_entries = self._merge_sources(existing_page.source_log_entries, page_source_ids)
                        existing_page.version += 1
                        existing_page.last_updated = now
                        log = UpdateLogEntry(existing_page.version, now, "system", "dream", 0.0, "Merged during dream", existing_page.confidence, confidence)
                        existing_page.update_log.append(log)
                        record_memory_event(existing_page, "dream_updated", now=now)
                        changed_pages[existing_page.slug] = existing_page
                        changed_page_sources.setdefault(existing_page.slug, set()).update(page_source_ids)
                        pages_updated += 1
                        updated_operations[existing_page.slug] = updated_operations.get(existing_page.slug, 0) + 1
                        conflicts_resolved += 1

        # A failed source invalidates every staged page in its connected source/page group.
        changed = True
        while changed:
            changed = False
            for source_ids in changed_page_sources.values():
                if source_ids & failed_source_ids and not source_ids <= failed_source_ids:
                    failed_source_ids.update(source_ids)
                    changed = True

        changed_pages = {
            slug: page
            for slug, page in changed_pages.items()
            if not (changed_page_sources.get(slug, set()) & failed_source_ids)
        }
        pages_created = sum(created_operations.get(slug, 0) for slug in changed_pages)
        pages_updated = sum(updated_operations.get(slug, 0) for slug in changed_pages)

        if not dry_run:
            for page in changed_pages.values():
                self.wiki.save(page)

        # 6. Update index
        if changed_pages:
            self._save_deterministic_index(changed_pages, dry_run=dry_run, now=datetime.now())

        # 7. Mark consolidated
        completed_source_ids = [
            entry.entry_id for entry in raw_entries if entry.entry_id not in failed_source_ids
        ]
        pending_source_ids = [
            entry.entry_id for entry in raw_entries if entry.entry_id in failed_source_ids
        ]
        if not dry_run and completed_source_ids:
            self.logs.mark_consolidated(completed_source_ids)

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
            except Exception:
                pass

        return DreamReport(
            pages_updated=pages_updated,
            pages_created=pages_created,
            entries_consolidated=len(completed_source_ids),
            conflicts_found=conflicts_found,
            conflicts_resolved=conflicts_resolved,
            git_commit_sha=commit_sha,
            completed_source_ids=completed_source_ids,
            pending_source_ids=pending_source_ids,
            failures=failures,
        )

    async def compact(
        self,
        slugs: list[str] | None = None,
        dry_run: bool = False,
    ) -> DreamReport:
        """Compact wiki pages by doing a full rewrite to deduplicate and reorganize accumulated facts."""
        pages = self.wiki.list_all()
        if slugs:
            pages = [p for p in pages if p.slug in slugs]

        pages_updated = 0
        changed_pages: dict[str, WikiPage] = {}
        now = datetime.now()

        for page in pages:
            if self._is_placeholder_slug(page.slug):
                continue

            page_type = self._page_type_for_slug(page.slug, page.tags)
            # Gather all source logs for this page
            source_entries = []
            if page.source_log_entries:
                try:
                    source_entries = self.logs.get_many(page.source_log_entries)
                except Exception:
                    pass

            try:
                source_evidence = self._build_evidence(source_entries)
                if source_evidence:
                    rewritten, _ = await self._rewrite_evidence_batches(
                        page.slug,
                        page_type,
                        page.content,
                        source_evidence,
                    )
                else:
                    system, user = prompts.consolidation_rewrite_prompt(
                        page.content,
                        "",
                        page_slug=page.slug,
                        page_type=page_type,
                    )
                    rewritten = await self.llm.call_structured(
                        system,
                        user,
                        WikiRewriteOutput,
                        num_predict=8192,
                        debug_label=f"wiki-compact-{page.slug}",
                    )
            except Exception as exc:
                logger.warning("Skipping compaction for %s: %s", page.slug, exc)
                continue

            if not isinstance(rewritten, dict):
                continue

            title = rewritten.get("title", page.slug)
            content = rewritten.get("content", "")
            if self._is_low_quality_rewrite(page.slug, title, content):
                continue
            if self._normalized_text(content) == self._normalized_text(page.content):
                continue

            page.title = title
            page.content = content
            page.tags = rewritten.get("tags", page.tags)
            page.version += 1
            page.last_updated = now

            confidence = float(rewritten.get("confidence", page.confidence))
            importance = float(rewritten.get("importance", page.importance))
            log = UpdateLogEntry(
                page.version,
                now,
                "system",
                "dream",
                0.0,
                "Compaction: full rewrite to deduplicate and reorganize",
                page.confidence,
                confidence,
            )
            page.confidence = confidence
            page.importance = importance
            page.update_log.append(log)
            record_memory_event(page, "dream_updated", now=now)

            if not dry_run:
                self.wiki.save(page)
            changed_pages[page.slug] = page
            pages_updated += 1

        if changed_pages and not dry_run:
            self._save_deterministic_index(changed_pages, dry_run=False, now=now)

        return DreamReport(
            pages_updated=pages_updated,
            pages_created=0,
            entries_consolidated=0,
            conflicts_found=[],
            conflicts_resolved=0,
            git_commit_sha=None,
        )

    async def _identify_targets_for_chunk(
        self,
        index_content: str,
        evidence: list[EvidenceChunk] | list[LogEntry],
    ) -> list:
        if not evidence:
            return []
        if isinstance(evidence[0], LogEntry):
            evidence = self._build_evidence(evidence)
        chunk_str = self._format_evidence_for_prompt(evidence)
        system, user = prompts.consolidation_identify_prompt(index_content, chunk_str)
        try:
            identification_res = await self.llm.call_structured(
                system,
                user,
                ConsolidationIdentifyOutput,
                num_predict=2048,
            )
        except Exception as exc:
            if len(evidence) <= 1:
                evidence_id = evidence[0].evidence_id
                logger.warning(
                    "Skipping dream identification for %s after structured output failure: %s",
                    evidence_id,
                    exc,
                )
                self._identification_failures[evidence_id] = str(exc)
                return []

            midpoint = max(1, len(evidence) // 2)
            return [
                *await self._identify_targets_for_chunk(index_content, evidence[:midpoint]),
                *await self._identify_targets_for_chunk(index_content, evidence[midpoint:]),
            ]

        if isinstance(identification_res, dict):
            targets = identification_res.get("targets", [])
        elif isinstance(identification_res, list):
            targets = identification_res
        elif hasattr(identification_res, "targets"):
            targets = identification_res.targets
        else:
            targets = []

        allowed_ids = {item.evidence_id for item in evidence}
        evidence_by_entry: dict[str, list[str]] = {}
        for item in evidence:
            evidence_by_entry.setdefault(item.entry_id, []).append(item.evidence_id)
        validated = []
        for target in targets:
            if not isinstance(target, dict):
                continue
            evidence_ids = [
                evidence_id
                for evidence_id in target.get("evidence_ids", [])
                if evidence_id in allowed_ids
            ]
            if not evidence_ids:
                for entry_id in self._clean_log_entry_ids(target.get("log_entry_ids", [])):
                    evidence_ids.extend(evidence_by_entry.get(entry_id, []))
            if not evidence_ids and target.get("action") in ("update", "create"):
                evidence_ids = [item.evidence_id for item in evidence]
            target = dict(target)
            target["evidence_ids"] = list(dict.fromkeys(evidence_ids))
            target["log_entry_ids"] = list(
                dict.fromkeys(
                    item.entry_id for item in evidence if item.evidence_id in target["evidence_ids"]
                )
            )
            if target["evidence_ids"] or target.get("action") == "none":
                validated.append(target)
        return validated

    def _build_evidence(self, entries: list[LogEntry]) -> list[EvidenceChunk]:
        input_budget = structured_input_budget(
            self.config.llm.context_window_tokens,
            num_predict=4096,
        )
        chunk_tokens = max(256, min(4096, input_budget // 3))
        evidence: list[EvidenceChunk] = []
        for entry in entries:
            chunks = split_text_by_tokens(entry.content, chunk_tokens)
            for index, content in enumerate(chunks, start=1):
                evidence.append(
                    EvidenceChunk(
                        evidence_id=f"{entry.entry_id}::chunk-{index:04d}",
                        entry_id=entry.entry_id,
                        session_id=entry.session_id,
                        timestamp=entry.timestamp,
                        content=content,
                        importance=entry.importance,
                        durability=entry.durability,
                        chunk_index=index,
                        chunk_count=len(chunks),
                    )
                )
        return evidence

    def _evidence_batches(
        self,
        evidence: list[EvidenceChunk],
        prompt_factory,
        *,
        num_predict: int,
    ) -> list[list[EvidenceChunk]]:
        max_tokens = structured_input_budget(
            self.config.llm.context_window_tokens,
            num_predict=num_predict,
        )

        def render(items: list[EvidenceChunk]) -> str:
            system, user = prompt_factory(self._format_evidence_for_prompt(items))
            return f"{system}\n{user}"

        return batch_items(evidence, render, max_tokens)

    def _format_evidence_for_prompt(self, evidence: list[EvidenceChunk]) -> str:
        return "\n\n".join(
            (
                f"[EVIDENCE {item.evidence_id}] parent_log={item.entry_id}; "
                f"chunk={item.chunk_index}/{item.chunk_count}; durability={item.durability}; "
                f"importance={item.importance:.2f}\n{item.content}"
            )
            for item in evidence
        )

    async def _rewrite_evidence_batches(
        self,
        page_slug: str,
        page_type: str,
        existing_content: str,
        evidence: list[EvidenceChunk],
    ) -> tuple[dict, list[str]]:
        remaining = list(evidence)
        working_content = existing_content
        rendered_batches: list[str] = []
        latest: dict = {}
        while remaining:
            def prompt_factory(text: str) -> tuple[str, str]:
                return prompts.consolidation_rewrite_prompt(
                    working_content,
                    text,
                    page_slug=page_slug,
                    page_type=page_type,
                )

            batch = self._next_fitting_evidence_batch(
                remaining,
                prompt_factory,
                num_predict=8192,
            )
            rendered = self._format_evidence_for_prompt(batch)
            system, user = prompt_factory(rendered)
            response = await self.llm.call_structured(
                system,
                user,
                WikiRewriteOutput,
                num_predict=8192,
                dump_success=True,
                debug_label=f"wiki-rewrite-{page_slug}",
            )
            if not isinstance(response, dict):
                raise ValueError(f"wiki rewrite for {page_slug} did not return an object")
            latest = response
            working_content = str(response.get("content", working_content))
            rendered_batches.append(rendered)
            del remaining[: len(batch)]
        return latest, rendered_batches

    async def _append_evidence_batches(
        self,
        page: WikiPage,
        page_slug: str,
        page_type: str,
        evidence: list[EvidenceChunk],
    ) -> list[tuple[dict, bool]]:
        remaining = list(evidence)
        outputs: list[tuple[dict, bool]] = []
        while remaining:
            def prompt_factory(text: str) -> tuple[str, str]:
                return prompts.consolidation_append_prompt(
                    page.content,
                    text,
                    page_slug=page_slug,
                    page_type=page_type,
                )

            batch = self._next_fitting_evidence_batch(
                remaining,
                prompt_factory,
                num_predict=4096,
            )
            system, user = prompt_factory(self._format_evidence_for_prompt(batch))
            response = await self.llm.call_structured(
                system,
                user,
                WikiAppendOutput,
                num_predict=4096,
                debug_label=f"wiki-append-{page_slug}",
            )
            if not isinstance(response, dict):
                raise ValueError(f"wiki append for {page_slug} did not return an object")
            outputs.append((response, self._append_facts_to_page(page, response)))
            del remaining[: len(batch)]
        return outputs

    def _next_fitting_evidence_batch(
        self,
        evidence: list[EvidenceChunk],
        prompt_factory,
        *,
        num_predict: int,
    ) -> list[EvidenceChunk]:
        batches = self._evidence_batches(
            evidence,
            prompt_factory,
            num_predict=num_predict,
        )
        return batches[0]

    def _merge_append_outputs(self, outputs: list[dict]) -> dict:
        return {
            "new_facts": [fact for output in outputs for fact in output.get("new_facts", [])],
            "new_tags": list(
                dict.fromkeys(tag for output in outputs for tag in output.get("new_tags", []))
            ),
            "confidence_adjustment": sum(
                float(output.get("confidence_adjustment", 0.0)) for output in outputs
            ),
            "importance_adjustment": sum(
                float(output.get("importance_adjustment", 0.0)) for output in outputs
            ),
        }

    def _format_entries_for_prompt(
        self,
        entries: list[LogEntry],
        *,
        max_chars_per_entry: int | None = None,
        max_total_chars: int | None = None,
    ) -> str:
        return "\n".join(self._format_entry_for_prompt(entry) for entry in entries)

    def _format_entry_for_prompt(self, entry: LogEntry, *, max_chars: int | None = None) -> str:
        return (
            f"[{entry.entry_id}] "
            f"durability={entry.durability}; importance={entry.importance:.2f}\n{entry.content}"
        )

    def _page_type_for_target(self, item: dict, fallback: str = "topic") -> str:
        raw_page_type = str(item.get("page_type", fallback)).strip().lower()
        if raw_page_type in PAGE_TYPES:
            return raw_page_type
        return self._page_type_for_slug(_slugify(str(item.get("page", ""))), [])

    def _page_type_for_slug(self, slug: str, tags: list | tuple | None) -> str:
        normalized_tags = {_slugify(str(tag)) for tag in (tags or [])}
        for page_type in PAGE_TYPES:
            if f"page-type-{page_type}" in normalized_tags:
                return page_type
        if slug.startswith(("person-", "organization-", "place-", "pet-", "product-")):
            return "entity"
        if slug.startswith("event-"):
            return "event"
        return "topic"

    def _merge_page_type(self, existing: str, new: str) -> str:
        if existing == new:
            return existing
        if existing == "topic":
            return new
        return existing

    def _typed_tags(self, tags: list, page_type: str) -> list[str]:
        cleaned = [str(tag) for tag in tags if str(tag).strip()]
        type_tag = f"page-type-{page_type}"
        if type_tag not in {_slugify(tag) for tag in cleaned}:
            cleaned.append(type_tag)
        return cleaned

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
            if slug.isdigit() or self._is_placeholder_slug(slug):
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
            evidence_ids = [
                evidence_id.strip()
                for evidence_id in item.get("evidence_ids", [])
                if isinstance(evidence_id, str) and evidence_id.strip()
            ]
                        
            existing = deduped.get(slug)
            if existing is None:
                deduped[slug] = {
                    "page": slug,
                    "action": action,
                    "page_type": self._page_type_for_target(item),
                    "log_entry_ids": log_entry_ids,
                    "evidence_ids": list(dict.fromkeys(evidence_ids)),
                }
            else:
                if existing["action"] == "create" and action == "update":
                    existing["action"] = "update"
                existing["page_type"] = self._merge_page_type(
                    str(existing.get("page_type", "topic")),
                    self._page_type_for_target(item),
                )
                # Merge log_entry_ids
                existing_ids = existing.setdefault("log_entry_ids", [])
                for entry_id in log_entry_ids:
                    if entry_id not in existing_ids:
                        existing_ids.append(entry_id)
                existing_evidence_ids = existing.setdefault("evidence_ids", [])
                for evidence_id in evidence_ids:
                    if evidence_id not in existing_evidence_ids:
                        existing_evidence_ids.append(evidence_id)
        return list(deduped.values())

    async def _canonicalize_identification(
        self,
        identification: list[dict],
        evidence: list[EvidenceChunk],
    ) -> list[dict]:
        if not identification:
            return []

        existing_pages = self._canonicalization_page_catalog()
        if len(identification) < 2 and not existing_pages:
            return identification

        proposed_targets = self._canonicalization_target_catalog(identification, evidence)
        if not proposed_targets:
            return identification

        system, user = prompts.canonicalization_prompt(
            json.dumps(existing_pages, indent=2),
            json.dumps(proposed_targets, indent=2),
        )
        try:
            response = await self.llm.call_structured(system, user, CanonicalizationOutput)
        except Exception:
            return identification

        mappings = []
        if isinstance(response, dict):
            mappings = response.get("mappings", [])
        elif hasattr(response, "mappings"):
            mappings = response.mappings
        if not mappings:
            return identification

        original_by_slug = {
            _slugify(str(item.get("page", ""))): item
            for item in identification
            if isinstance(item, dict) and item.get("page")
        }
        existing_slugs = {page["slug"] for page in existing_pages}
        canonicalized: list[dict] = []

        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            proposed_slug = _slugify(str(mapping.get("proposed_page", "")))
            original = original_by_slug.get(proposed_slug)
            if original is None:
                continue

            action = mapping.get("action")
            if action == "drop":
                continue

            canonical_slug = _slugify(str(mapping.get("canonical_page") or proposed_slug))
            if not canonical_slug or self._is_placeholder_slug(canonical_slug):
                continue

            log_entry_ids = list(original.get("log_entry_ids", []))
            evidence_ids = list(original.get("evidence_ids", []))
            page_type = self._page_type_for_target(mapping, fallback=self._page_type_for_target(original))
            lexical_match = self._lexical_existing_match(canonical_slug, existing_pages)
            if lexical_match:
                canonical_slug = lexical_match
                canonical_action = "update"
            elif action == "use_existing":
                if canonical_slug not in existing_slugs:
                    canonical_slug = proposed_slug
                    canonical_action = original.get("action", "create")
                else:
                    canonical_action = "update"
            elif self.wiki.exists(canonical_slug):
                canonical_action = "update"
            else:
                canonical_action = "create"

            canonicalized.append(
                {
                    "page": canonical_slug,
                    "action": canonical_action,
                    "page_type": page_type,
                    "log_entry_ids": log_entry_ids,
                    "evidence_ids": evidence_ids,
                }
            )

        if not canonicalized:
            return identification
        return self._dedupe_identification(canonicalized)

    def _canonicalization_page_catalog(self) -> list[dict]:
        try:
            pages = self.wiki.list_all()
        except Exception:
            return []
        if not isinstance(pages, list):
            return []

        catalog = []
        for page in pages:
            if self._is_placeholder_slug(page.slug):
                continue
            catalog.append(
                {
                    "slug": page.slug,
                    "title": page.title,
                    "tags": page.tags,
                    "page_type": self._page_type_for_slug(page.slug, page.tags),
                    "summary": self._index_summary(page),
                    "confidence": page.confidence,
                    "importance": page.importance,
                    "source_count": len(page.source_log_entries),
                }
            )
        return catalog

    def _canonicalization_target_catalog(
        self,
        identification: list[dict],
        evidence: list[EvidenceChunk],
    ) -> list[dict]:
        evidence_by_id = {item.evidence_id: item for item in evidence}
        catalog = []
        for item in identification:
            if not isinstance(item, dict):
                continue
            page_slug = _slugify(str(item.get("page", "")))
            if not page_slug or self._is_placeholder_slug(page_slug):
                continue

            log_entry_ids = list(item.get("log_entry_ids", []))
            evidence_ids = list(item.get("evidence_ids", []))
            target_evidence = [
                evidence_by_id[evidence_id]
                for evidence_id in evidence_ids
                if evidence_id in evidence_by_id
            ]

            catalog.append(
                {
                    "page": page_slug,
                    "action": item.get("action"),
                    "page_type": self._page_type_for_target(item),
                    "log_entry_ids": log_entry_ids,
                    "evidence_ids": evidence_ids,
                    "source_snippets": [
                        {
                            "evidence_id": chunk.evidence_id,
                            "entry_id": chunk.entry_id,
                            "importance": chunk.importance,
                            "content": chunk.content,
                        }
                        for chunk in target_evidence
                    ],
                }
            )
        return catalog

    async def _prepare_entries(self, entries: list[LogEntry]) -> list[LogEntry]:
        prepared: list[LogEntry] = []
        for entry in entries:
            if entry.durability != "durable":
                continue
            if not entry.content.strip():
                continue
            if _is_tool_entry(entry):
                extracted = await self._extract_tool_entry(entry)
                prepared.extend(extracted)
            else:
                prepared.append(entry)
        return prepared

    async def _extract_tool_entry(self, entry: LogEntry) -> list[LogEntry]:
        system, user = prompts.tool_observation_extract_prompt(entry.entry_id, entry.content)
        try:
            response = await self.llm.call_structured(system, user, ToolObservationExtractionOutput)
        except Exception as exc:
            self._preparation_failures[entry.entry_id] = str(exc)
            return []

        facts = response.get("facts", []) if isinstance(response, dict) else []
        durable_facts = []
        topic_hints = []
        confidences = []
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            if fact.get("recommended_memory_scope") != "durable":
                continue
            fact_text = str(fact.get("fact", "")).strip()
            if not fact_text:
                continue
            durable_facts.append(fact_text)
            confidences.append(float(fact.get("confidence", 0.5)))
            for topic in fact.get("suggested_topics", []):
                if isinstance(topic, str) and topic.strip():
                    topic_hints.append(_slugify(topic))

        if not durable_facts:
            return []

        content_lines = [
            "Extracted durable facts from tool observation.",
            f"Source tool entry: {entry.entry_id}",
        ]
        tool_name = response.get("tool_name") if isinstance(response, dict) else None
        query_or_url = response.get("query_or_url") if isinstance(response, dict) else None
        if tool_name:
            content_lines.append(f"Tool: {tool_name}")
        if query_or_url:
            content_lines.append(f"Query or URL: {query_or_url}")
        if topic_hints:
            content_lines.append("Suggested topics: " + ", ".join(sorted(set(topic_hints))))
        content_lines.append("")
        content_lines.extend(f"- {fact}" for fact in durable_facts)

        return [
            LogEntry(
                entry_id=entry.entry_id,
                session_id=entry.session_id,
                timestamp=entry.timestamp,
                content="\n".join(content_lines),
                importance=max([entry.importance, *confidences], default=entry.importance),
                status=entry.status,
                durability="durable",
                consolidated=entry.consolidated,
                decay_score=entry.decay_score,
            )
        ]

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

    def _clean_log_entry_ids(self, raw_ids: list) -> list[str]:
        log_entry_ids = []
        for raw_id in raw_ids:
            if isinstance(raw_id, str):
                cleaned = raw_id.strip("[]'\" ")
                if " — " in cleaned:
                    cleaned = cleaned.split(" — ")[0]
                if " - " in cleaned:
                    cleaned = cleaned.split(" - ")[0]
                cleaned = cleaned.strip()
                if cleaned and cleaned not in log_entry_ids:
                    log_entry_ids.append(cleaned)
        return log_entry_ids

    def _lexical_existing_match(self, slug: str, existing_pages: list[dict]) -> str | None:
        slug_key = _normalize_page_key(slug)
        best_slug = None
        best_score = 0.0
        for page in existing_pages:
            page_slug = str(page.get("slug", ""))
            candidates = [
                _normalize_page_key(page_slug),
                _normalize_page_key(str(page.get("title", ""))),
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                score = SequenceMatcher(None, slug_key, candidate).ratio()
                if score > best_score:
                    best_score = score
                    best_slug = page_slug
        return best_slug if best_score >= 0.88 else None

    def _valid_slugs(self, extra: list[str] | None = None) -> set[str]:
        slugs = set(extra or [])
        try:
            for page in self.wiki.list_all():
                slugs.add(page.slug)
        except Exception:
            pass
        return slugs

    def _is_placeholder_slug(self, slug: str) -> bool:
        return bool(PLACEHOLDER_SLUG_RE.match(slug))

    def _is_low_quality_rewrite(self, slug: str, title: str, content: str) -> bool:
        if not content.strip():
            return True
        if self._is_placeholder_slug(slug):
            return True
        if PLACEHOLDER_TITLE_RE.match(title.strip()):
            return True
        return False

    def _sanitize_wiki_links(self, content: str, valid_slugs: set[str]) -> str:
        def replace(match: re.Match) -> str:
            label = match.group(1).strip()
            slug = _slugify(label)
            if slug in valid_slugs:
                return f"[[{slug}]]"
            return label

        return re.sub(r"\[\[([^\]]+)\]\]", replace, content)

    def _normalized_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def _is_noop_update(
        self,
        page: WikiPage,
        title: str,
        content: str,
        tags: list,
        related_edges: list[Edge],
        source_ids: list[str],
    ) -> bool:
        has_new_sources = any(source_id not in page.source_log_entries for source_id in source_ids)
        return (
            not has_new_sources
            and page.title == title
            and self._normalized_text(page.content) == self._normalized_text(content)
            and sorted(page.tags) == sorted(tags)
            and [(e.target, e.relation, e.weight) for e in page.related]
            == [(e.target, e.relation, e.weight) for e in related_edges]
        )

    def _append_facts_to_page(self, page: WikiPage, append_data: dict) -> bool:
        """Append new facts to an existing page's content sections. Returns True if any facts were added."""
        new_facts = append_data.get("new_facts", [])
        if not new_facts:
            return False

        key_fact_lines = []
        timeline_rows = []
        for fact in new_facts:
            if not isinstance(fact, dict):
                continue
            fact_text = str(fact.get("fact", "")).strip()
            if not fact_text:
                continue
            section = fact.get("section", "key_facts")
            if section == "event_timeline":
                date = fact.get("date") or "Unknown"
                people = fact.get("people") or ""
                source = fact.get("source") or ""
                timeline_rows.append(f"| {date} | {fact_text} | {people} | {source} |")
            else:
                source = fact.get("source")
                if source:
                    key_fact_lines.append(f"- {fact_text} [[log:{source}]]")
                else:
                    key_fact_lines.append(f"- {fact_text}")

        if not key_fact_lines and not timeline_rows:
            return False

        content = page.content

        # Append key facts
        if key_fact_lines:
            key_facts_block = "\n".join(key_fact_lines)
            # Try to find ## Key Facts section and append after it
            import re
            kf_match = re.search(r"(## Key Facts\b.*?)(?=\n## |\Z)", content, re.DOTALL)
            if kf_match:
                insert_pos = kf_match.end()
                content = content[:insert_pos].rstrip() + "\n" + key_facts_block + "\n" + content[insert_pos:]
            else:
                # No Key Facts section exists, add one before Source Logs or at end
                sl_match = re.search(r"\n## Source Logs\b", content)
                rp_match = re.search(r"\n## Related Pages\b", content)
                insert_before = sl_match or rp_match
                if insert_before:
                    pos = insert_before.start()
                    content = content[:pos] + "\n\n## Key Facts\n" + key_facts_block + "\n" + content[pos:]
                else:
                    content = content.rstrip() + "\n\n## Key Facts\n" + key_facts_block + "\n"

        # Append timeline rows
        if timeline_rows:
            timeline_block = "\n".join(timeline_rows)
            import re
            et_match = re.search(r"(## Event Timeline\b.*?)(?=\n## |\Z)", content, re.DOTALL)
            if et_match:
                insert_pos = et_match.end()
                content = content[:insert_pos].rstrip() + "\n" + timeline_block + "\n" + content[insert_pos:]
            else:
                sl_match = re.search(r"\n## Source Logs\b", content)
                rp_match = re.search(r"\n## Related Pages\b", content)
                insert_before = sl_match or rp_match
                if insert_before:
                    pos = insert_before.start()
                    content = content[:pos] + "\n\n## Event Timeline\n| Date / Relative Time | Event | People / Entities | Source |\n| :--- | :--- | :--- | :--- |\n" + timeline_block + "\n" + content[pos:]
                else:
                    content = content.rstrip() + "\n\n## Event Timeline\n| Date / Relative Time | Event | People / Entities | Source |\n| :--- | :--- | :--- | :--- |\n" + timeline_block + "\n"

        page.content = content

        # Apply tag additions
        new_tags = append_data.get("new_tags", [])
        for tag in new_tags:
            if isinstance(tag, str) and tag.strip() and tag not in page.tags:
                page.tags.append(tag)

        return True

    def _save_deterministic_index(
        self,
        changed_pages: dict[str, WikiPage],
        *,
        dry_run: bool,
        now: datetime,
    ) -> None:
        if dry_run:
            return

        pages_by_slug = dict(changed_pages)
        try:
            for page in self.wiki.list_all():
                pages_by_slug[page.slug] = page
        except Exception:
            pass

        def sort_key(page: WikiPage) -> tuple[int, str]:
            return (0 if page.slug == "user-profile" else 1, page.slug)

        lines = [
            "# Wiki Index",
            "",
            f"_last updated: {now.isoformat(timespec='seconds')}_",
            "",
            "## Pages",
        ]
        for page in sorted(pages_by_slug.values(), key=sort_key):
            if self._is_placeholder_slug(page.slug):
                continue
            summary = self._index_summary(page)
            lines.append(f"- [[{page.slug}]]: {summary}")

        self.wiki.save_index("\n".join(lines) + "\n")

    def _index_needs_rebuild(self) -> bool:
        try:
            pages = {page.slug for page in self.wiki.list_all() if not self._is_placeholder_slug(page.slug)}
            index_links = {
                _slugify(match)
                for match in re.findall(r"\[\[([^\]]+)\]\]", self.wiki.get_index())
            }
        except Exception:
            return False

        if not pages:
            return False
        if pages - index_links:
            return True
        if any(self._is_placeholder_slug(link) or link not in pages for link in index_links):
            return True
        return False

    def _index_summary(self, page: WikiPage) -> str:
        title = page.title.strip() or page.slug
        body_lines = [
            line.strip()
            for line in page.content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if body_lines:
            first = re.sub(r"\s+", " ", body_lines[0])
            first = re.sub(r"\[\[([^\]]+)\]\]", r"\1", first)
            if len(first) > 140:
                first = first[:137].rstrip() + "..."
            return f"{title} - {first}"
        return title
