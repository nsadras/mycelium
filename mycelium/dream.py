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
    DerivedClaimsOutput,
)
from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    ClaimReconciler,
    DERIVATION_OPERATIONS,
    MemoryClaim,
    parse_source_datetime,
)
from mycelium.projection import (
    ProjectedClaim,
    compact_record_qualifiers,
    display_claim_text,
    partition_claims,
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
    claim_ids: tuple[str, ...] = ()
    segment_ids: tuple[str, ...] = ()
    source_id: str | None = None


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
    def __init__(self, llm: OllamaClient, wiki: WikiStore, logs: LogStore, config: Config, artifacts: ArtifactStore | None = None):
        self.llm = llm
        self.wiki = wiki
        self.logs = logs
        self.config = config
        self.artifacts = artifacts
        self.decay_engine = DecayEngine(wiki, logs, config)
        self._identification_failures: dict[str, str] = {}
        self._preparation_failures: dict[str, str] = {}
        self._pending_page_claim_ids: dict[str, set[str]] = {}
        self._stale_projection_slugs: set[str] = set()

    def _uses_claim_evidence(self) -> bool:
        return self.artifacts is not None and self.config.dream.evidence_mode != "raw"

    async def run(
        self,
        strategy: Literal['full', 'new_only', 'association_only'] = 'full',
        dry_run: bool = False,
        conflict_policy: Literal['fork', 'override', 'merge'] = 'override',
    ) -> DreamReport:
        
        raw_entries = self.logs.get_unconsolidated()
        self._preparation_failures = {}
        self._pending_page_claim_ids: dict[str, set[str]] = {}
        self._stale_projection_slugs: set[str] = set()
        entries = await self._prepare_entries(raw_entries)
        evidence = self._build_run_evidence(entries)
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
        
        deterministic_multi_party = (
            self._uses_claim_evidence() and self._is_multi_party_evidence(evidence)
        )
        if deterministic_multi_party:
            all_targets = self._identify_multi_party_claim_targets(evidence)
        else:
            all_targets = []
            identify_batches = self._evidence_batches(
                evidence,
                lambda text: prompts.consolidation_identify_prompt(index_content, text),
                num_predict=2048,
            )
            for chunk in identify_batches:
                all_targets.extend(await self._identify_targets_for_chunk(index_content, chunk))
            
        identification = self._dedupe_identification(all_targets)
        if not deterministic_multi_party:
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
            
            if self._uses_claim_evidence():
                page_evidence = self._materialization_evidence(page_slug, page_evidence)
                page_source_ids = list(dict.fromkeys(chunk.entry_id for chunk in page_evidence))

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
            confidence = max(0.0, min(1.0, float(rewritten.get("confidence", 0.5))))
            importance = max(0.0, min(1.0, float(rewritten.get("importance", 0.5))))
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
            if self._uses_claim_evidence():
                content = self._strip_internal_artifact_ids(content)
                content = self._dedupe_repeated_lines(content)
                content = self._with_main_projection(page_slug, content)
            
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
                    if not self._uses_claim_evidence():
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
                    else:
                        # Claims/hybrid pages are regenerated from their canonical evidence set.
                        append_outputs = []

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
        if self._uses_claim_evidence():
            derived, derived_created, derived_updated = self._build_projection_pages(
                changed_pages, datetime.now()
            )
            changed_pages.update(derived)
            for slug in derived_created:
                created_operations[slug] = 1
            for slug in derived_updated:
                updated_operations[slug] = 1
        pages_created = sum(created_operations.get(slug, 0) for slug in changed_pages)
        pages_updated = sum(updated_operations.get(slug, 0) for slug in changed_pages)

        if not dry_run:
            for page in changed_pages.values():
                self.wiki.save(page)
                if self.artifacts is not None:
                    self.artifacts.assign_pages(
                        self._pending_page_claim_ids.get(page.slug, set()), page.slug
                    )
            for stale_slug in sorted(self._stale_projection_slugs):
                self.wiki.archive(stale_slug)

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
        pages_created = 0
        changed_pages: dict[str, WikiPage] = {}
        projection_parents: dict[str, WikiPage] = {}
        self._pending_page_claim_ids = {}
        self._stale_projection_slugs = set()
        now = datetime.now()

        for page in pages:
            # Projection pages are deterministic outputs. Rebuild them from their
            # parent claims instead of asking the model to summarize a summary.
            if self._is_placeholder_slug(page.slug) or "derived-memory" in page.tags:
                continue

            page_type = self._page_type_for_slug(page.slug, page.tags)
            if self._uses_claim_evidence():
                if self.config.dream.derived_insights_enabled and not dry_run:
                    try:
                        await self._refresh_derived_insights(page.slug)
                    except Exception as exc:
                        logger.warning(
                            "Keeping existing derived insights for %s: %s", page.slug, exc
                        )
                claims = self._claims_for_projection(page.slug)
                if not claims:
                    logger.info("Skipping claim compaction for %s: no assigned claims", page.slug)
                    continue
                source_evidence = [
                    self._claim_evidence(claim, include_spans=False) for claim in claims
                ]
            else:
                source_entries = []
                if page.source_log_entries:
                    try:
                        source_entries = self.logs.get_many(page.source_log_entries)
                    except Exception:
                        pass
                source_evidence = self._build_evidence(source_entries)

            try:
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
            content = self._sanitize_wiki_links(content, self._valid_slugs(extra=[page.slug]))
            if self._uses_claim_evidence():
                content = self._strip_internal_artifact_ids(content)
                content = self._dedupe_repeated_lines(content)
                content = self._with_main_projection(page.slug, content)
                projection_parents[page.slug] = page
            if self._normalized_text(content) == self._normalized_text(page.content):
                continue

            page.title = title
            page.content = content
            page.tags = self._typed_tags(
                rewritten.get("tags", page.tags), page_type
            )
            page.version += 1
            page.last_updated = now

            confidence = max(0.0, min(
                1.0, float(rewritten.get("confidence", page.confidence))
            ))
            importance = max(0.0, min(
                1.0, float(rewritten.get("importance", page.importance))
            ))
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

            changed_pages[page.slug] = page
            pages_updated += 1

        if self._uses_claim_evidence() and projection_parents:
            derived, created, updated = self._build_projection_pages(projection_parents, now)
            # Projection may add or remove child links even when the overview text
            # itself was already current.
            for slug, parent in projection_parents.items():
                changed_pages.setdefault(slug, parent)
            changed_pages.update(derived)
            pages_created += len(created)
            pages_updated += len(updated)

        if changed_pages and not dry_run:
            # Parents are saved after projection so their child links are included.
            for page in changed_pages.values():
                self.wiki.save(page)
            for stale_slug in sorted(self._stale_projection_slugs):
                self.wiki.archive(stale_slug)
            self._save_deterministic_index(changed_pages, dry_run=False, now=now)

        return DreamReport(
            pages_updated=pages_updated,
            pages_created=pages_created,
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
            target_slug = _slugify(str(target.get("page", "")))
            if target_slug == "user-profile" and self._benchmark_evidence(evidence):
                # Multi-party benchmark/meeting participants are not implicitly the system user.
                continue
            target["evidence_ids"] = list(dict.fromkeys(evidence_ids))
            target["log_entry_ids"] = list(
                dict.fromkeys(
                    item.entry_id for item in evidence if item.evidence_id in target["evidence_ids"]
                )
            )
            if target["evidence_ids"] or target.get("action") == "none":
                validated.append(target)
        return validated

    def _benchmark_evidence(self, evidence: list[EvidenceChunk]) -> bool:
        if self.artifacts is None:
            return False
        source_ids = {chunk.source_id for chunk in evidence if chunk.source_id}
        for source_id in source_ids:
            try:
                if self.artifacts.get_source(source_id).source_type in {"benchmark_conversation", "meeting_transcript"}:
                    return True
            except FileNotFoundError:
                continue
        return False

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

    def _build_run_evidence(self, entries: list[LogEntry]) -> list[EvidenceChunk]:
        mode = self.config.dream.evidence_mode
        if mode == "raw" or self.artifacts is None:
            return self._build_evidence(entries)
        entry_ids = {entry.entry_id for entry in entries}
        source_by_id = {source.source_id: source for source in self.artifacts.list_sources()}
        for episode in self.artifacts.list_episodes():
            source = source_by_id.get(episode.source_id)
            if (
                mode == "claims"
                and source
                and source.raw_log_entry_id in entry_ids
                and episode.extraction_status in {"failed", "partial"}
            ):
                self._preparation_failures[source.raw_log_entry_id] = (
                    episode.extraction_error or "claim extraction failed"
                )
        claims = [
            claim for claim in self.artifacts.list_claims(status="active")
            if any(prov.raw_log_entry_id in entry_ids for prov in claim.provenance)
        ]
        evidence = [self._claim_evidence(claim, include_spans=mode == "hybrid") for claim in claims]
        if mode == "hybrid":
            claimed_segments = {
                segment_id for claim in claims for prov in claim.provenance for segment_id in prov.segment_ids
            }
            for source in self.artifacts.list_sources():
                if source.raw_log_entry_id not in entry_ids:
                    continue
                for segment in source.segments:
                    if segment.segment_id in claimed_segments or not segment.content.strip():
                        continue
                    evidence.append(EvidenceChunk(
                        evidence_id=f"{segment.segment_id}::unassigned",
                        entry_id=source.raw_log_entry_id or source.source_id,
                        session_id=source.session_id,
                        timestamp=self._source_timestamp(source.recorded_at),
                        content=(
                            "UNASSIGNED SOURCE SPAN (no extracted claim; retain if useful)\n"
                            f"speaker={segment.speaker or 'unknown'}; time={segment.timestamp or 'unknown'}\n"
                            f"{segment.content}"
                        ),
                        importance=0.65, durability="durable", chunk_index=1, chunk_count=1,
                        segment_ids=(segment.segment_id,), source_id=source.source_id,
                    ))
        # If extraction failed, hybrid must degrade visibly and losslessly to raw evidence.
        covered_entries = {
            prov.raw_log_entry_id for claim in claims for prov in claim.provenance if prov.raw_log_entry_id
        }
        sources_with_segments = {source.raw_log_entry_id for source in source_by_id.values() if source.segments}
        missing_entries = entry_ids - covered_entries - sources_with_segments
        if mode == "hybrid" and missing_entries:
            evidence.extend(self._build_evidence([entry for entry in entries if entry.entry_id in missing_entries]))
        return evidence

    @staticmethod
    def _source_timestamp(value: str) -> datetime:
        return parse_source_datetime(value) or datetime.now()

    def _is_multi_party_evidence(self, evidence: list[EvidenceChunk]) -> bool:
        if self.artifacts is None:
            return False
        source_ids = {chunk.source_id for chunk in evidence if chunk.source_id}
        if not source_ids:
            return False
        for source_id in source_ids:
            try:
                if self.artifacts.get_source(source_id).source_type != "benchmark_conversation":
                    return False
            except FileNotFoundError:
                return False
        return True

    def _identify_multi_party_claim_targets(self, evidence: list[EvidenceChunk]) -> list[dict]:
        """Route conversation facts to real participant pages, never synthetic speaker labels."""
        if self.artifacts is None:
            return []
        targets: dict[str, dict] = {}
        for chunk in evidence:
            source = None
            participant_names: dict[str, str] = {}
            if chunk.source_id:
                try:
                    source = self.artifacts.get_source(chunk.source_id)
                    for name in [
                        *source.participants,
                        *(segment.speaker for segment in source.segments if segment.speaker),
                    ]:
                        if name:
                            participant_names.setdefault(name.strip().lower(), name.strip())
                except FileNotFoundError:
                    pass
            speakers: set[str] = set()
            for claim_id in chunk.claim_ids:
                try:
                    claim = self.artifacts.get_claim(claim_id)
                except FileNotFoundError:
                    continue
                about_participants = {
                    participant_names[str(item.get("entity", "")).strip().lower()]
                    for item in claim.about
                    if str(item.get("entity", "")).strip().lower() in participant_names
                }
                if about_participants:
                    speakers.update(about_participants)
                    continue
                speakers.update(
                    participant_names[prov.speaker.strip().lower()]
                    for prov in claim.provenance
                    if prov.speaker and prov.speaker.strip().lower() in participant_names
                )
            if not speakers and source is not None and chunk.segment_ids:
                wanted = set(chunk.segment_ids)
                speakers.update(
                    segment.speaker for segment in source.segments
                    if segment.segment_id in wanted and segment.speaker
                )
            for speaker in sorted(speakers):
                if speaker.strip().lower() in {"user", "assistant", "system", "unknown"}:
                    continue
                slug = f"person-{_slugify(speaker)}"
                target = targets.setdefault(slug, {
                    "page": slug,
                    "action": "update" if self.wiki.exists(slug) else "create",
                    "page_type": "entity", "log_entry_ids": [], "evidence_ids": [],
                })
                if chunk.entry_id not in target["log_entry_ids"]:
                    target["log_entry_ids"].append(chunk.entry_id)
                if chunk.evidence_id not in target["evidence_ids"]:
                    target["evidence_ids"].append(chunk.evidence_id)
        return list(targets.values())

    @staticmethod
    def _dedupe_repeated_lines(content: str) -> str:
        seen: set[str] = set()
        result = []
        for line in content.splitlines():
            normalized = re.sub(r"\s+", " ", line.strip()).lower()
            is_content = len(normalized) >= 24 and not normalized.startswith(("#", "|", "---"))
            if is_content and normalized in seen:
                continue
            if is_content:
                seen.add(normalized)
            result.append(line)
        return "\n".join(result).strip()

    @staticmethod
    def _strip_internal_artifact_ids(content: str) -> str:
        content = re.sub(r"\[+\s*claim-[a-f0-9-]+\s*\]+", "", content, flags=re.I)
        content = re.sub(r"\bclaim-[a-f0-9-]+\b", "", content, flags=re.I)
        content = re.sub(r"[ \t]+([,.;])", r"\1", content)
        content = re.sub(r"[ \t]{2,}", " ", content)
        return content.strip()

    def _claim_evidence(self, claim: MemoryClaim, *, include_spans: bool) -> EvidenceChunk:
        provenance = claim.provenance[0]
        source = self.artifacts.get_source(provenance.source_id) if self.artifacts else None
        about = ", ".join(
            f"{item.get('entity')} ({item.get('role')})" if item.get("role") else str(item.get("entity"))
            for item in claim.about if item.get("entity")
        ) or "unspecified"
        lines = [
            f"CANONICAL CLAIM: {claim.text}",
            f"type={claim.claim_type}; predicate={claim.predicate or 'unknown'}; "
            f"modality={claim.evidence_modality}; temporal={claim.temporal_status}; "
            f"kind={claim.kind}; about={about}; confidence={claim.confidence:.2f}; "
            f"status={claim.status}; facets={json.dumps(claim.facets, ensure_ascii=False, sort_keys=True)}",
        ]
        if include_spans and source is not None:
            wanted = {segment_id for prov in claim.provenance for segment_id in prov.segment_ids}
            spans = [segment for segment in source.segments if segment.segment_id in wanted]
            if spans:
                lines.append("EXACT SUPPORTING SPANS:")
                lines.extend(
                    f"[{segment.segment_id}] {segment.speaker or segment.role or 'unknown'}"
                    f" ({segment.timestamp or 'time unknown'}): {segment.content}"
                    for segment in spans
                )
        raw_entry = provenance.raw_log_entry_id or provenance.source_id
        return EvidenceChunk(
            evidence_id=f"{claim.claim_id}::claim",
            entry_id=raw_entry,
            session_id=source.session_id if source else "",
            timestamp=self._source_timestamp(source.recorded_at) if source else datetime.now(),
            content="\n".join(lines), importance=max(0.5, claim.confidence), durability="durable",
            chunk_index=1, chunk_count=1, claim_ids=(claim.claim_id,),
            segment_ids=tuple(segment_id for prov in claim.provenance for segment_id in prov.segment_ids),
            source_id=provenance.source_id,
        )

    def _materialization_evidence(self, page_slug: str, current: list[EvidenceChunk]) -> list[EvidenceChunk]:
        if self.artifacts is None:
            return current
        current_claim_ids = {claim_id for chunk in current for claim_id in chunk.claim_ids}
        existing_claims = self.artifacts.claims_for_page(page_slug)
        # Exact spans validate/expose extraction and unclaimed spans stay lossless, but
        # repeating every quote during final materialization wastes the context window.
        merged = []
        for chunk in current:
            if chunk.claim_ids:
                for claim_id in chunk.claim_ids:
                    try:
                        merged.append(self._claim_evidence(self.artifacts.get_claim(claim_id), include_spans=False))
                    except FileNotFoundError:
                        continue
            else:
                merged.append(chunk)
        present_ids = {chunk.evidence_id for chunk in merged}
        for claim in existing_claims:
            chunk = self._claim_evidence(claim, include_spans=False)
            if chunk.evidence_id not in present_ids:
                merged.append(chunk)
                present_ids.add(chunk.evidence_id)
        # Persist assignment only after identification; failed rewrites remain auditable as unmaterialized.
        self._pending_page_claim_ids = getattr(self, "_pending_page_claim_ids", {})
        self._pending_page_claim_ids.setdefault(page_slug, set()).update(current_claim_ids)
        return merged

    def _claims_for_projection(self, page_slug: str) -> list[MemoryClaim]:
        if self.artifacts is None:
            return []
        claim_ids = set(getattr(self, "_pending_page_claim_ids", {}).get(page_slug, set()))
        claims = {claim.claim_id: claim for claim in self.artifacts.claims_for_page(page_slug)}
        for claim_id in claim_ids:
            try:
                claims[claim_id] = self.artifacts.get_claim(claim_id)
            except FileNotFoundError:
                continue
        return [claim for claim in claims.values() if claim.status == "active"]

    def _with_main_projection(self, page_slug: str, overview: str) -> str:
        """Render a bounded primary page; complete detail lives in derived views."""
        active = self._claims_for_projection(page_slug)
        if not active:
            return overview
        projected = partition_claims(
            active, main_claim_limit=self.config.dream.main_page_claim_limit
        )
        groups: dict[str, list[ProjectedClaim]] = {}
        for item in projected["main"]:
            groups.setdefault(item.bucket, []).append(item)
        # The generated overview and deterministic claim list largely repeated
        # one another. Claims-mode pages use one authoritative compact view;
        # the model output remains useful for title, tags, and importance.
        lines = ["## Memory"]
        for label in sorted(groups):
            lines.extend(["", f"### {label}"])
            for item in groups[label]:
                qualifiers = compact_record_qualifiers(item, include_date=True)
                suffix = f" _({'; '.join(qualifiers)})_" if qualifiers else ""
                lines.append(f"- {display_claim_text(item.claim)}{suffix}")
        child_links = []
        if projected["timeline"]:
            child_links.append(f"- [[{page_slug}-timeline]]: dated events and changes")
        if projected["details"]:
            child_links.append(f"- [[{page_slug}-details]]: supporting durable facts")
        if projected["insights"]:
            child_links.append(f"- [[{page_slug}-insights]]: traceable derived conclusions")
        if projected["interaction_archive"]:
            child_links.append(f"- [[{page_slug}-interactions]]: conversational and relationship history")
        if child_links:
            lines.extend(["", "## Memory Sections", *child_links])
        return "\n".join(lines).strip()

    def _build_projection_pages(
        self,
        parent_pages: dict[str, WikiPage],
        now: datetime,
    ) -> tuple[dict[str, WikiPage], set[str], set[str]]:
        derived: dict[str, WikiPage] = {}
        created: set[str] = set()
        updated: set[str] = set()
        for parent_slug, parent in list(parent_pages.items()):
            if "derived-memory" in parent.tags:
                continue
            claims = self._claims_for_projection(parent_slug)
            if not claims:
                continue
            projected = partition_claims(
                claims, main_claim_limit=self.config.dream.main_page_claim_limit
            )
            specs = []
            specs.extend(self._projection_shards(parent, "timeline", "Timeline", projected["timeline"]))
            specs.extend(self._projection_shards(parent, "details", "Detailed Facts", projected["details"]))
            specs.extend(self._projection_shards(parent, "insights", "Derived Insights", projected["insights"]))
            specs.extend(self._projection_shards(parent, "interactions", "Interaction Archive", projected["interaction_archive"]))
            child_slugs = []
            for slug, title, content, items in specs:
                child_slugs.append(slug)
                projection_kind = slug.removeprefix(f"{parent_slug}-").split("-")[0]
                sources = list(dict.fromkeys(
                    provenance.raw_log_entry_id
                    for item in items for claim in item.members
                    for provenance in claim.provenance
                    if provenance.raw_log_entry_id
                ))
                if self.wiki.exists(slug):
                    page = self.wiki.get(slug)
                    if (
                        self._normalized_text(page.content) == self._normalized_text(content)
                        and page.source_log_entries == sources
                    ):
                        continue
                    page.title = title
                    page.content = content
                    page.source_log_entries = sources
                    page.version += 1
                    page.last_updated = now
                    page.update_log.append(UpdateLogEntry(
                        page.version, now, "system", "projection", 0.0,
                        "Regenerated deterministic claim projection",
                        page.confidence, 1.0,
                    ))
                    page.confidence = 1.0
                    updated.add(slug)
                else:
                    page = WikiPage(
                        slug=slug, title=title, content=content,
                        created=now, last_updated=now, version=1,
                        confidence=1.0, importance=max(0.4, parent.importance - 0.1),
                        tags=["derived-memory", projection_kind, f"parent:{parent_slug}"],
                        related=[Edge(parent_slug, "informs", 1.0)],
                        source_log_entries=sources,
                        update_log=[UpdateLogEntry(
                            1, now, "system", "projection", 0.0,
                            "Initial deterministic claim projection", 0.0, 1.0,
                        )],
                    )
                    created.add(slug)
                record_memory_event(page, "dream_updated", now=now)
                derived[slug] = page
            existing_targets = {edge.target for edge in parent.related}
            for child_slug in child_slugs:
                if child_slug not in existing_targets:
                    parent.related.append(Edge(child_slug, "informs", 1.0))
            for existing in self.wiki.list_all():
                if (
                    existing.slug not in child_slugs
                    and "derived-memory" in existing.tags
                    and f"parent:{parent_slug}" in existing.tags
                ):
                    self._stale_projection_slugs.add(existing.slug)
            parent.related = [
                edge for edge in parent.related if edge.target not in self._stale_projection_slugs
            ]
        return derived, created, updated

    def _projection_shards(
        self,
        parent: WikiPage,
        suffix: str,
        title_suffix: str,
        items: list[ProjectedClaim],
        *,
        max_chars: int | None = None,
        max_records: int | None = None,
    ) -> list[tuple[str, str, str, list[ProjectedClaim]]]:
        if not items:
            return []
        max_chars = max_chars or self.config.dream.projection_page_max_chars
        max_records = max_records or self.config.dream.projection_page_max_records
        date_grouped = suffix in {"timeline", "interactions"}
        grouped: dict[str, list[ProjectedClaim]] = {}
        for item in items:
            heading = (
                "Repeated interactions"
                if suffix == "interactions" and len(item.members) > 1
                else item.date_key if date_grouped else item.bucket
            )
            grouped.setdefault(heading, []).append(item)
        shards: list[tuple[list[str], list[ProjectedClaim]]] = []
        lines = [f"# {parent.title}: {title_suffix}", "", f"Parent: [[{parent.slug}]]"]
        if suffix == "insights":
            lines.extend([
                "",
                "These conclusions are derived from multiple explicit memories; each remains traceable to its supporting claims.",
            ])
        shard_items: list[ProjectedClaim] = []
        seen_text: set[str] = set()
        for heading in sorted(grouped):
            heading_added = False
            for item in grouped[heading]:
                rendered_text = display_claim_text(item.claim)
                normalized = self._normalized_text(rendered_text)
                if normalized in seen_text:
                    continue
                seen_text.add(normalized)
                qualifiers = compact_record_qualifiers(item, include_date=not date_grouped)
                suffix_text = f" _({'; '.join(qualifiers)})_" if qualifiers else ""
                bullet = f"- {rendered_text}{suffix_text}"
                heading_lines = ["", f"## {heading}"] if not heading_added else []
                addition = "\n".join([*heading_lines, bullet])
                if shard_items and (
                    len("\n".join(lines)) + len(addition) > max_chars
                    or len(shard_items) >= max_records
                ):
                    shards.append((lines, shard_items))
                    lines = [f"# {parent.title}: {title_suffix}", "", f"Parent: [[{parent.slug}]]", "", f"## {heading}"]
                    shard_items = []
                    heading_added = True
                else:
                    lines.extend(heading_lines)
                    heading_added = True
                lines.append(bullet)
                shard_items.append(item)
        if shard_items:
            shards.append((lines, shard_items))
        result = []
        shard_slugs = [
            f"{parent.slug}-{suffix}" if index == 1 else f"{parent.slug}-{suffix}-{index}"
            for index in range(1, len(shards) + 1)
        ]
        for index, (shard_lines, included) in enumerate(shards, start=1):
            number = "" if index == 1 else f"-{index}"
            slug = f"{parent.slug}-{suffix}{number}"
            title = f"{parent.title}: {title_suffix}" + (f" {index}" if len(shards) > 1 else "")
            shard_lines[0] = f"# {title}"
            if len(shard_slugs) > 1:
                shard_lines[3:3] = ["", "Parts: " + " · ".join(f"[[{part}]]" for part in shard_slugs)]
            result.append((slug, title, "\n".join(shard_lines).strip(), included))
        return result

    async def _refresh_derived_insights(self, page_slug: str) -> list[MemoryClaim]:
        """Replace cross-claim conclusions only after a successful, grounded synthesis."""
        if self.artifacts is None:
            return []
        page_claims = self.artifacts.claims_for_page(page_slug)
        explicit = [claim for claim in page_claims if claim.status == "active" and not claim.inferred]
        if len(explicit) < 2:
            return []
        allowed = {claim.claim_id: claim for claim in explicit}
        lines = [self._render_derivation_claim(claim) for claim in sorted(
            explicit, key=lambda item: (item.recorded_at, item.claim_id)
        )]
        batches: list[list[str]] = []
        current: list[str] = []
        current_chars = 0
        for line in lines:
            if current and current_chars + len(line) > 70000:
                batches.append(current)
                current = []
                current_chars = 0
            current.append(line)
            current_chars += len(line) + 1
        if current:
            batches.append(current)

        raw_candidates: list[dict] = []
        for batch_index, batch in enumerate(batches, start=1):
            batch_header = (
                f"PARTIAL CLAIM BATCH {batch_index}/{len(batches)}. "
                "Do not derive a total count from a partial batch.\n"
                if len(batches) > 1 else ""
            )
            system, user = prompts.derived_claims_prompt(
                page_slug, batch_header + "\n".join(batch)
            )
            response = await self.llm.call_structured(
                system,
                user,
                DerivedClaimsOutput,
                num_predict=4096,
                dump_success=True,
                debug_label=f"derived-insights-{page_slug}-batch-{batch_index}",
            )
            if not isinstance(response, dict):
                raise ValueError("derived insight synthesis did not return an object")
            raw_candidates.extend(
                item for item in response.get("claims", []) if isinstance(item, dict)
            )

        reconciler = ClaimReconciler(self.artifacts)
        refreshed: list[MemoryClaim] = []
        for raw in raw_candidates:
            text = " ".join(str(raw.get("text", "")).split())
            inference_basis = " ".join(str(raw.get("inference_basis", "")).split())
            operation = str(raw.get("derivation_operation") or "").strip().lower()
            if operation not in DERIVATION_OPERATIONS:
                continue
            supplied_basis_ids = [
                *raw.get("basis_claim_ids", []),
                *re.findall(r"\bclaim-[a-z0-9]+\b", inference_basis, re.I),
            ]
            basis_ids = list(dict.fromkeys(
                claim_id for claim_id in supplied_basis_ids
                if claim_id in allowed
            ))
            about = [item for item in raw.get("about", []) if isinstance(item, dict) and item.get("entity")]
            if not text or not basis_ids or not inference_basis:
                continue
            basis = [allowed[claim_id] for claim_id in basis_ids]
            if not self._valid_derivation_basis(operation, basis):
                continue
            if not about:
                candidate_entities = {
                    str(item.get("entity", "")).strip()
                    for claim in basis for item in claim.about if item.get("entity")
                }
                normalized_text_for_about = re.sub(
                    r"[^a-z0-9]+", " ", text.lower()
                ).strip()
                normalized_candidate_entities = [
                    (entity, re.sub(r"[^a-z0-9]+", " ", entity.lower()).strip())
                    for entity in sorted(candidate_entities)
                ]
                about = [
                    {"entity": entity}
                    for entity, normalized_entity in normalized_candidate_entities
                    if re.search(
                        rf"(?:^|\s){re.escape(normalized_entity)}(?:\s|$)",
                        normalized_text_for_about,
                    )
                ]
            if not about:
                continue
            basis_entity_names = {
                str(item.get("entity", "")).strip().lower()
                for claim in basis for item in claim.about if item.get("entity")
            }
            if any(
                str(item.get("entity", "")).strip().lower() not in basis_entity_names
                for item in about
            ):
                continue
            normalized_text = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
            normalized_entities = [
                re.sub(r"[^a-z0-9]+", " ", str(item["entity"]).lower()).strip()
                for item in about if str(item.get("entity", "")).strip()
            ]
            if not any(
                re.search(rf"(?:^|\s){re.escape(entity)}(?:\s|$)", normalized_text)
                for entity in normalized_entities
            ):
                continue
            if any(claim_id in text for claim_id in basis_ids):
                continue
            provenance: list[ClaimProvenance] = []
            seen_provenance: set[tuple[str, tuple[str, ...]]] = set()
            for claim in basis:
                for item in claim.provenance:
                    key = (item.source_id, tuple(item.segment_ids))
                    if key in seen_provenance:
                        continue
                    seen_provenance.add(key)
                    provenance.append(ClaimProvenance(
                        source_id=item.source_id,
                        segment_ids=list(item.segment_ids),
                        raw_log_entry_id=item.raw_log_entry_id,
                        speaker=item.speaker,
                        evidence_type="inferred",
                    ))
            facets = dict(raw.get("facets", {}) or {})
            facets.update({
                "inference_basis": inference_basis,
                "basis_claim_ids": basis_ids,
                "derivation_method": "cross_claim_synthesis",
                "derivation_operation": operation,
            })
            incoming = MemoryClaim(
                claim_id=f"claim-{uuid.uuid4().hex[:12]}",
                text=text,
                kind=str(raw.get("kind") or "derived insight").strip().lower(),
                about=about,
                provenance=provenance,
                recorded_at=max(claim.recorded_at for claim in basis),
                confidence=max(0.0, min(0.7, float(raw.get("confidence", 0.6)))),
                inferred=True,
                facets=facets,
                page_slugs=[page_slug],
                salience=0.65,
                display_scope="details",
                claim_type="state",
                predicate=str(raw["predicate"]) if raw.get("predicate") else None,
                evidence_modality="inference",
                temporal_status=str(raw.get("temporal_status") or "unknown"),
                derivation_operation=operation,
            )
            canonical = reconciler.reconcile(incoming)
            if page_slug not in canonical.page_slugs:
                canonical.page_slugs.append(page_slug)
                self.artifacts.save_claim(canonical)
            refreshed.append(canonical)

        refreshed_ids = {claim.claim_id for claim in refreshed}
        for claim in page_claims:
            if (
                claim.status == "active"
                and claim.inferred
                and claim.facets.get("derivation_method") == "cross_claim_synthesis"
                and claim.claim_id not in refreshed_ids
            ):
                claim.status = "superseded"
                self.artifacts.save_claim(claim)
        return refreshed

    @staticmethod
    def _valid_derivation_basis(operation: str, basis: list[MemoryClaim]) -> bool:
        """Validate reasoning prerequisites from structured claims, never conclusion wording."""
        if not basis:
            return False
        if operation == "temporal_arithmetic":
            if len(basis) == 1:
                facets = basis[0].facets
                return bool(facets.get("duration") and facets.get("observed_at"))
            anchors = [claim.facets.get("normalized_date") for claim in basis]
            return len(basis) <= 3 and all(anchors) and len(set(anchors)) >= 2
        if operation == "event_count":
            if len(basis) < 2 or any(claim.claim_type != "event" for claim in basis):
                return False
            occurrence_keys = [
                claim.facets.get("occurrence_id") or claim.facets.get("normalized_date")
                for claim in basis
            ]
            return all(occurrence_keys) and len(set(occurrence_keys)) == len(occurrence_keys)
        if operation == "recurring_pattern":
            dates = [claim.facets.get("normalized_date") for claim in basis]
            source_ids = {
                provenance.source_id for claim in basis for provenance in claim.provenance
            }
            return (
                len(basis) >= 3
                and all(dates)
                and len(set(dates)) >= 3
                and len(source_ids) >= 3
            )
        if operation == "cross_fact_relationship":
            predicates = {claim.predicate for claim in basis if claim.predicate}
            return len(basis) >= 2 and len(predicates) >= 2
        return False

    @staticmethod
    def _render_derivation_claim(claim: MemoryClaim) -> str:
        useful_facet_keys = (
            "normalized_date", "date_precision", "when", "observed_at",
            "duration", "quantity", "location", "object", "reason",
        )
        useful_facets = {
            key: claim.facets[key] for key in useful_facet_keys
            if key in claim.facets and claim.facets[key] not in (None, "", [], {})
        }
        facet_text = (
            f"; facets={json.dumps(useful_facets, ensure_ascii=False, sort_keys=True)}"
            if useful_facets else ""
        )
        return (
            f"[{claim.claim_id}] type={claim.claim_type}; predicate={claim.predicate or 'unknown'}; "
            f"modality={claim.evidence_modality}; temporal={claim.temporal_status}; "
            f"recorded={claim.recorded_at}{facet_text}; {claim.text}"
        )

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
        # Claims-mode pages are projections of canonical evidence. Starting from old
        # prose both consumes context and lets stale/duplicated prose survive.
        working_content = "" if self._uses_claim_evidence() else existing_content
        rendered_batches: list[str] = []
        latest: dict = {}
        while remaining:
            def prompt_factory(text: str) -> tuple[str, str]:
                if self._uses_claim_evidence():
                    return prompts.claim_materialization_prompt(
                        working_content, text, page_slug=page_slug, page_type=page_type,
                    )
                return prompts.consolidation_rewrite_prompt(
                    working_content, text, page_slug=page_slug, page_type=page_type,
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
