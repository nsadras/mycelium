import shutil
import frontmatter
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from mycelium.models import PAGE_TYPES, WikiPage, LogEntry, Edge, UpdateLogEntry

def _edge_to_dict(edge: Edge) -> dict:
    return {
        "target": edge.target,
        "relation": edge.relation,
        "weight": edge.weight
    }

def _edge_from_dict(d: dict) -> Edge:
    return Edge(
        target=d["target"],
        relation=d["relation"],
        weight=d.get("weight", 1.0)
    )

def _update_log_to_dict(log: UpdateLogEntry) -> dict:
    return {
        "version": log.version,
        "date": log.date.isoformat(),
        "session_id": log.session_id,
        "trigger": log.trigger,
        "reason": log.reason,
        "previous_confidence": log.previous_confidence,
        "new_confidence": log.new_confidence
    }

def _update_log_from_dict(d: dict) -> UpdateLogEntry:
    return UpdateLogEntry(
        version=d["version"],
        date=datetime.fromisoformat(d["date"]) if isinstance(d["date"], str) else d["date"],
        session_id=d["session_id"],
        trigger=d["trigger"],
        reason=d["reason"],
        previous_confidence=d["previous_confidence"],
        new_confidence=d["new_confidence"]
    )

class WikiStore:
    def __init__(self, wiki_dir: Path):
        self.wiki_dir = wiki_dir
        self.archive_dir = wiki_dir / "_archive"
        
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def get(self, slug: str) -> WikiPage:
        path = self.wiki_dir / f"{slug}.md"
        if not path.exists():
            raise FileNotFoundError(f"Wiki page {slug} not found.")
        
        post = frontmatter.load(path)

        if "page_type" not in post.metadata:
            raise ValueError(
                f"Wiki page {slug} uses the pre-taxonomy schema. "
                "Clear and rebuild the wiki from canonical memory artifacts."
            )
        page_type = post.metadata["page_type"]
        if page_type is not None and page_type not in PAGE_TYPES:
            raise ValueError(f"Wiki page {slug} has invalid page_type: {page_type!r}")
        entity_id = str(post.metadata.get("entity_id") or "")
        if not entity_id:
            raise ValueError(
                f"Wiki page {slug} uses the pre-entity schema. "
                "Clear and rebuild the wiki from canonical claims."
            )
        
        related = [_edge_from_dict(r) for r in post.metadata.get("related", [])]
        update_log = [_update_log_from_dict(u) for u in post.metadata.get("update_log", [])]
        
        created = post.metadata.get("created")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
            
        last_updated = post.metadata.get("last_updated")
        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated)

        now = datetime.now()
        created = created or now
        last_updated = last_updated or created
            
        return WikiPage(
            slug=post.metadata.get("id", slug),
            title=post.metadata.get("title", slug),
            content=post.content,
            created=created,
            last_updated=last_updated,
            version=post.metadata.get("version", 1),
            confidence=post.metadata.get("confidence", 0.0),
            importance=post.metadata.get("importance", 0.5),
            page_type=page_type,
            tags=post.metadata.get("tags", []),
            related=related,
            source_log_entries=post.metadata.get("source_log_entries", []),
            update_log=update_log,
            entity_id=entity_id,
            entity_status=post.metadata.get("entity_status", "active"),
            aliases=post.metadata.get("aliases", []),
            sections=post.metadata.get("sections", []),
        )

    def save(self, page: WikiPage) -> None:
        path = self.wiki_dir / f"{page.slug}.md"
        
        post = frontmatter.Post(page.content)
        post.metadata["id"] = page.slug
        post.metadata["title"] = page.title
        post.metadata["created"] = page.created.isoformat() if page.created else None
        post.metadata["last_updated"] = page.last_updated.isoformat() if page.last_updated else None
        post.metadata["version"] = page.version
        post.metadata["confidence"] = page.confidence
        post.metadata["importance"] = page.importance
        post.metadata["page_type"] = page.page_type
        post.metadata["tags"] = page.tags
        post.metadata["related"] = [_edge_to_dict(r) for r in page.related]
        post.metadata["source_log_entries"] = page.source_log_entries
        post.metadata["update_log"] = [_update_log_to_dict(u) for u in page.update_log]
        post.metadata["entity_id"] = page.entity_id
        post.metadata["entity_status"] = page.entity_status
        post.metadata["aliases"] = page.aliases
        post.metadata["sections"] = page.sections
        
        with open(path, "wb") as f:
            frontmatter.dump(post, f)

    def history(self, slug: str) -> List[UpdateLogEntry]:
        page = self.get(slug)
        return page.update_log

    def list(self, tag: Optional[str] = None, min_confidence: float = 0.0) -> List[WikiPage]:
        pages = self.list_all()
        filtered = []
        for p in pages:
            if tag and tag not in p.tags:
                continue
            if p.confidence < min_confidence:
                continue
            filtered.append(p)
        return filtered

    def list_all(self) -> List[WikiPage]:
        pages = []
        for path in self.wiki_dir.glob("*.md"):
            if path.name == "_index.md":
                continue
            pages.append(self.get(path.stem))
        return pages

    def get_index(self) -> str:
        path = self.wiki_dir / "_index.md"
        if not path.exists():
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def save_index(self, content: str) -> None:
        path = self.wiki_dir / "_index.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def archive(self, slug: str) -> None:
        src = self.wiki_dir / f"{slug}.md"
        dst = self.archive_dir / f"{slug}.md"
        if src.exists():
            shutil.move(str(src), str(dst))

    def delete(self, slug: str) -> None:
        path = self.wiki_dir / f"{slug}.md"
        if path.exists():
            path.unlink()

    def exists(self, slug: str) -> bool:
        return (self.wiki_dir / f"{slug}.md").exists()

class LogStore:
    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def append(self, entry: LogEntry) -> None:
        # e.g., entry.entry_id = "2026-05-10#entry-1", we want the date part
        date_str = entry.entry_id.split("#")[0]
        path = self.logs_dir / f"{date_str}.md"
        
        is_new = not path.exists()
        
        with open(path, "a", encoding="utf-8") as f:
            if is_new:
                f.write(f"# Log: {date_str}\n\n")
            
            entry_name = entry.entry_id.split("#")[1] if "#" in entry.entry_id else entry.entry_id
            
            f.write(f"## {entry_name} — {entry.timestamp.strftime('%H:%M')}\n\n")
            f.write(f"**session_id:** {entry.session_id}  \n")
            f.write(f"**importance:** {entry.importance}  \n")
            f.write(f"**durability:** {entry.durability}  \n")
            f.write(f"**consolidated:** {str(entry.consolidated).lower()}  \n")
            f.write("\n")
            f.write(entry.content.strip() + "\n\n---\n\n")

    def get_unconsolidated(self, days: int | None = 7) -> List[LogEntry]:
        return [entry for entry in self.list_entries(days=days) if not entry.consolidated]

    def list_entries(self, days: int | None = 7) -> List[LogEntry]:
        import re
        import typing
        from typing import Literal
        entries = []
        
        log_files = sorted(self.logs_dir.glob("*.md"), reverse=True)
        if days is not None:
            log_files = log_files[:days]
        
        for path in log_files:
            date_str = path.stem
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                
            entry_header = re.compile(r"^## (?P<name>.+?) — (?P<time>\d{2}:\d{2})\s*$", re.MULTILINE)
            matches = list(entry_header.finditer(content))
            for idx, match in enumerate(matches):
                section_start = match.end()
                section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
                section = content[section_start:section_end].strip()
                if section.endswith("---"):
                    section = section[:-3].rstrip()

                lines = section.split("\n")
                entry_name = match.group("name").strip()
                time_str = match.group("time").strip()
                
                metadata: dict = {}
                body_lines = []
                in_body = False
                
                for line in lines:
                    m = re.match(r"^\*\*([^*]+):\*\*\s*(.*)", line)
                    if not in_body:
                        if m:
                            key = m.group(1).strip()
                            val = m.group(2).strip()
                            if val.endswith("  "):
                                val = val[:-2]
                            metadata[key] = val
                        elif line.strip() == "" and len(metadata) > 0:
                            # Only transition to body if we've seen at least some metadata
                            in_body = True
                    else:
                        body_lines.append(line)
                
                if "consolidated" not in metadata:
                    continue

                is_consolidated = metadata.get("consolidated", "false").lower() == "true"
                try:
                    timestamp = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                except ValueError:
                    timestamp = datetime.now()
                    
                importance = float(metadata.get("importance", "0.0"))
                durability = typing.cast(
                    Literal['ephemeral', 'session', 'durable'],
                    metadata.get("durability", "durable"),
                )
                
                entry = LogEntry(
                    entry_id=f"{date_str}#{entry_name}",
                    session_id=metadata.get("session_id", ""),
                    timestamp=timestamp,
                    content="\n".join(body_lines).strip(),
                    importance=importance,
                    durability=durability,
                    consolidated=is_consolidated,
                )
                entries.append(entry)
                    
        return entries

    def get(self, entry_id: str) -> LogEntry:
        if "#" not in entry_id:
            raise FileNotFoundError(f"Log entry {entry_id} not found.")

        for entry in self.list_entries(days=None):
            if entry.entry_id == entry_id:
                return entry
        raise FileNotFoundError(f"Log entry {entry_id} not found.")

    def get_many(self, entry_ids: List[str]) -> List[LogEntry]:
        if not entry_ids:
            return []

        wanted = set(entry_ids)
        found: dict[str, LogEntry] = {}
        for entry in self.list_entries(days=None):
            if entry.entry_id in wanted:
                found[entry.entry_id] = entry
        return [found[entry_id] for entry_id in entry_ids if entry_id in found]

    def mark_consolidated(self, entry_ids: List[str]) -> None:
        # Note: This is an expensive operation since we rewrite the file.
        # This is expected for plain-text storage.
        from typing import Dict, Set
        files_to_update: Dict[str, Set[str]] = {}
        for eid in entry_ids:
            if "#" in eid:
                date_str = eid.split("#")[0]
                if date_str not in files_to_update:
                    files_to_update[date_str] = set()
                files_to_update[date_str].add(eid)

        for date_str, eids in files_to_update.items():
            path = self.logs_dir / f"{date_str}.md"
            if not path.exists():
                continue
                
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                
            for eid in eids:
                entry_name = eid.split("#")[1]
                # Look for the specific entry section and replace consolidated: false with true
                import re
                # This regex looks for the specific entry header and its consolidated status
                pattern = re.compile(r"(## " + re.escape(entry_name) + r" — .*?\n(?:.*?\n)*?\*\*consolidated:\*\* )false", re.MULTILINE)
                content = pattern.sub(r"\g<1>true", content)
                
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    def mark_unconsolidated(self, date_str: str) -> None:
        path = self.logs_dir / f"{date_str}.md"
        if not path.exists():
            return
            
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        import re
        # Find all occurrences of **consolidated:** true and rewrite to false
        pattern = re.compile(r"(\*\*consolidated:\*\* )true", re.MULTILINE)
        content = pattern.sub(r"\g<1>false", content)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def mark_all_unconsolidated(self) -> None:
        for path in self.logs_dir.glob("*.md"):
            self.mark_unconsolidated(path.stem)
