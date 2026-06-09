import json
import logging
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Literal, Optional
import uuid

from mycelium.models import DreamReport, WikiPage, Edge, UpdateLogEntry, LogEntry
from mycelium.store import WikiStore, LogStore
from mycelium.ollama import OllamaClient
from mycelium.config import Config
from mycelium import prompts
from mycelium.decay import DecayEngine, record_memory_event
from mycelium.structured_outputs import (
    CanonicalizationOutput,
    ConsolidationIdentifyOutput,
    ToolObservationExtractionOutput,
    WikiMergeOutput,
    WikiRewriteOutput,
    PredictionErrorOutput,
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
IDENTIFICATION_MAX_CHARS_PER_ENTRY = 3500
IDENTIFICATION_EXCERPT_CHARS = 3000
PAGE_TYPES = {"entity", "event", "topic"}


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

    async def run(
        self,
        strategy: Literal['full', 'new_only', 'association_only'] = 'full',
        dry_run: bool = False,
        conflict_policy: Literal['fork', 'override', 'merge'] = 'override',
    ) -> DreamReport:
        
        raw_entries = self.logs.get_unconsolidated()
        entries = await self._prepare_entries(raw_entries)
        
        if not entries and strategy != 'association_only':
            if not dry_run and raw_entries:
                self.logs.mark_consolidated([e.entry_id for e in raw_entries])
                await self.decay_engine.run_pass()
            if not dry_run and self._index_needs_rebuild():
                self._save_deterministic_index({}, dry_run=False, now=datetime.now())
            return DreamReport(0, 0, len(raw_entries), [], 0, None)
            
        index_content = self.wiki.get_index()
        
        all_targets = []
        for chunk in self._entry_chunks(entries):
            all_targets.extend(await self._identify_targets_for_chunk(index_content, chunk))
            
        identification = self._dedupe_identification(all_targets)
        identification = await self._canonicalize_identification(identification, entries)
            
        pages_updated = 0
        pages_created = 0
        conflicts_found = []
        conflicts_resolved = 0
        title_to_slug = self._existing_title_index()
        changed_pages: dict[str, WikiPage] = {}
        
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

            # Determine relevant logs for this specific page
            log_entry_ids = item.get("log_entry_ids", [])
            if log_entry_ids and isinstance(log_entry_ids, list):
                page_entries = [e for e in entries if e.entry_id in log_entry_ids]
                # Fall back to all unconsolidated logs if none are found in the filtered list
                if not page_entries:
                    page_entries = entries
            else:
                page_entries = entries

            page_entries_str = self._format_entries_for_prompt(
                page_entries,
                max_chars_per_entry=2500,
                max_total_chars=12000,
            )
            page_source_ids = [e.entry_id for e in page_entries]

            page_exists = self.wiki.exists(page_slug)
            if page_exists:
                existing_page = self.wiki.get(page_slug)
                system, user = prompts.consolidation_rewrite_prompt(
                    existing_page.content,
                    page_entries_str,
                    page_slug=page_slug,
                    page_type=page_type,
                )
                is_create = False
            else:
                existing_page = None
                system, user = prompts.consolidation_rewrite_prompt(
                    "",
                    page_entries_str,
                    page_slug=page_slug,
                    page_type=page_type,
                )
                is_create = True
            
            try:
                rewritten = await self.llm.call_structured(system, user, WikiRewriteOutput)
            except Exception as exc:
                logger.warning("Skipping dream rewrite for %s after structured output failure: %s", page_slug, exc)
                continue
            if not isinstance(rewritten, dict):
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
                    changed_pages[existing_page.slug] = existing_page
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
                changed_pages[new_page.slug] = new_page
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
                    changed_pages[existing_page.slug] = existing_page
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
                    changed_pages[fork_page.slug] = fork_page
                    changed_pages[existing_page.slug] = existing_page
                        
                    pages_created += 1
                    pages_updated += 1
                elif conflict_policy == "merge":
                    existing_page = self.wiki.get(page_slug)
                    # Simple merge prompt: synthesis
                    system = "You are a memory synthesis agent. Merge the following two versions of a wiki page into a single, cohesive, abstracted page."
                    user = f"VERSION 1:\n{existing_page.content}\n\nVERSION 2:\n{content}"
                    
                    try:
                        merged = await self.llm.call_structured(system, user, WikiMergeOutput)
                    except Exception as exc:
                        logger.warning("Skipping dream merge for %s after structured output failure: %s", page_slug, exc)
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
                        if not dry_run:
                            self.wiki.save(existing_page)
                        changed_pages[existing_page.slug] = existing_page
                        pages_updated += 1
                        conflicts_resolved += 1

        # 6. Update index
        if pages_updated > 0 or pages_created > 0:
            self._save_deterministic_index(changed_pages, dry_run=dry_run, now=datetime.now())

        # 7. Mark consolidated
        if not dry_run and raw_entries:
            self.logs.mark_consolidated([e.entry_id for e in raw_entries])

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
            entries_consolidated=len(raw_entries),
            conflicts_found=conflicts_found,
            conflicts_resolved=conflicts_resolved,
            git_commit_sha=commit_sha
        )

    async def _identify_targets_for_chunk(
        self,
        index_content: str,
        entries: list[LogEntry],
    ) -> list:
        if not entries:
            return []
        if len(entries) == 1:
            excerpt_entries = self._split_entry_for_identification(entries[0])
            if len(excerpt_entries) > 1:
                all_targets = []
                for excerpt_chunk in self._entry_chunks(excerpt_entries, max_chars=9000):
                    all_targets.extend(await self._identify_targets_for_chunk(index_content, excerpt_chunk))
                return all_targets

        chunk_str = self._format_entries_for_prompt(
            entries,
            max_chars_per_entry=IDENTIFICATION_MAX_CHARS_PER_ENTRY,
        )
        system, user = prompts.consolidation_identify_prompt(index_content, chunk_str)
        try:
            identification_res = await self.llm.call_structured(system, user, ConsolidationIdentifyOutput)
        except Exception as exc:
            if len(entries) <= 1:
                logger.warning(
                    "Skipping dream identification for %s after structured output failure: %s",
                    entries[0].entry_id,
                    exc,
                )
                return []

            midpoint = max(1, len(entries) // 2)
            return [
                *await self._identify_targets_for_chunk(index_content, entries[:midpoint]),
                *await self._identify_targets_for_chunk(index_content, entries[midpoint:]),
            ]

        if isinstance(identification_res, dict):
            return identification_res.get("targets", [])
        if isinstance(identification_res, list):
            return identification_res
        if hasattr(identification_res, "targets"):
            return identification_res.targets
        return []

    def _split_entry_for_identification(self, entry: LogEntry) -> list[LogEntry]:
        content = entry.content.strip()
        if len(content) <= IDENTIFICATION_MAX_CHARS_PER_ENTRY:
            return [entry]

        chunks = self._split_text_for_prompt(content, IDENTIFICATION_EXCERPT_CHARS)
        if len(chunks) <= 1:
            return [entry]

        return [
            LogEntry(
                entry_id=entry.entry_id,
                session_id=entry.session_id,
                timestamp=entry.timestamp,
                content=(
                    f"Excerpt {index + 1}/{len(chunks)} from original log entry {entry.entry_id}. "
                    "When citing this excerpt, use the original log entry ID only.\n\n"
                    f"{chunk}"
                ),
                importance=entry.importance,
                status=entry.status,
                durability=entry.durability,
                consolidated=entry.consolidated,
                decay_score=entry.decay_score,
            )
            for index, chunk in enumerate(chunks)
        ]

    def _split_text_for_prompt(self, text: str, max_chars: int) -> list[str]:
        if len(text) <= max_chars:
            return [text]

        chunks: list[str] = []
        current: list[str] = []
        current_chars = 0
        paragraphs = re.split(r"\n{2,}", text)

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            if len(paragraph) > max_chars:
                if current:
                    chunks.append("\n\n".join(current))
                    current = []
                    current_chars = 0
                chunks.extend(self._split_long_paragraph(paragraph, max_chars))
                continue

            separator_chars = 2 if current else 0
            if current and current_chars + separator_chars + len(paragraph) > max_chars:
                chunks.append("\n\n".join(current))
                current = []
                current_chars = 0

            current.append(paragraph)
            current_chars += separator_chars + len(paragraph)

        if current:
            chunks.append("\n\n".join(current))

        return chunks or [text[:max_chars]]

    def _split_long_paragraph(self, text: str, max_chars: int) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            if end < len(text):
                split_at = text.rfind("\n", start, end)
                if split_at <= start:
                    split_at = text.rfind(" ", start, end)
                if split_at > start:
                    end = split_at
            chunks.append(text[start:end].strip())
            start = end
            while start < len(text) and text[start].isspace():
                start += 1
        return [chunk for chunk in chunks if chunk]

    def _entry_chunks(self, entries: list[LogEntry], *, max_chars: int = 12000) -> list[list[LogEntry]]:
        chunks: list[list[LogEntry]] = []
        current: list[LogEntry] = []
        current_chars = 0

        for entry in entries:
            formatted_len = len(self._format_entry_for_prompt(entry))
            if current and current_chars + formatted_len > max_chars:
                chunks.append(current)
                current = []
                current_chars = 0
            current.append(entry)
            current_chars += formatted_len

        if current:
            chunks.append(current)
        return chunks

    def _format_entries_for_prompt(
        self,
        entries: list[LogEntry],
        *,
        max_chars_per_entry: int | None = None,
        max_total_chars: int | None = None,
    ) -> str:
        formatted_entries = []
        total_chars = 0
        for entry in entries:
            formatted = self._format_entry_for_prompt(entry, max_chars=max_chars_per_entry)
            if max_total_chars is not None and formatted_entries and total_chars + len(formatted) > max_total_chars:
                break
            formatted_entries.append(formatted)
            total_chars += len(formatted)
        return "\n".join(formatted_entries)

    def _format_entry_for_prompt(self, entry: LogEntry, *, max_chars: int | None = None) -> str:
        content = entry.content
        if max_chars is not None and len(content) > max_chars:
            content = content[: max_chars - 32].rstrip() + "\n[entry truncated for prompt]"
        return (
            f"[{entry.entry_id}] "
            f"durability={entry.durability}; importance={entry.importance:.2f}\n{content}"
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
                        
            existing = deduped.get(slug)
            if existing is None:
                deduped[slug] = {
                    "page": slug,
                    "action": action,
                    "page_type": self._page_type_for_target(item),
                    "log_entry_ids": log_entry_ids
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
        return list(deduped.values())

    async def _canonicalize_identification(
        self,
        identification: list[dict],
        entries: list[LogEntry],
    ) -> list[dict]:
        if not identification:
            return []

        existing_pages = self._canonicalization_page_catalog()
        if len(identification) < 2 and not existing_pages:
            return identification

        proposed_targets = self._canonicalization_target_catalog(identification, entries)
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

            log_entry_ids = self._clean_log_entry_ids(mapping.get("log_entry_ids", []))
            if not log_entry_ids:
                log_entry_ids = list(original.get("log_entry_ids", []))
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
            body = self._normalized_text(page.content)
            catalog.append(
                {
                    "slug": page.slug,
                    "title": page.title,
                    "tags": page.tags,
                    "page_type": self._page_type_for_slug(page.slug, page.tags),
                    "summary": self._index_summary(page),
                    "content_preview": body[:500],
                    "confidence": page.confidence,
                    "importance": page.importance,
                    "source_count": len(page.source_log_entries),
                }
            )
        return catalog

    def _canonicalization_target_catalog(
        self,
        identification: list[dict],
        entries: list[LogEntry],
    ) -> list[dict]:
        entries_by_id = {entry.entry_id: entry for entry in entries}
        catalog = []
        for item in identification:
            if not isinstance(item, dict):
                continue
            page_slug = _slugify(str(item.get("page", "")))
            if not page_slug or self._is_placeholder_slug(page_slug):
                continue

            log_entry_ids = list(item.get("log_entry_ids", []))
            target_entries = [entries_by_id[eid] for eid in log_entry_ids if eid in entries_by_id]
            if not target_entries:
                target_entries = entries[:6]

            catalog.append(
                {
                    "page": page_slug,
                    "action": item.get("action"),
                    "page_type": self._page_type_for_target(item),
                    "log_entry_ids": log_entry_ids,
                    "source_snippets": [
                        {
                            "entry_id": entry.entry_id,
                            "importance": entry.importance,
                            "content": self._normalized_text(entry.content)[:500],
                        }
                        for entry in target_entries[:6]
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
        except Exception:
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
