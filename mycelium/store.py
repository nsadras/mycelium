from dataclasses import asdict
from mycelium.database import database
import frontmatter
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from mycelium.models import Edge, LogEntry, UpdateLogEntry, WikiPage
from mycelium.ontology import ENTITY_TYPES


def _edge_to_dict(edge: Edge) -> dict:
    return {"target": edge.target, "relation": edge.relation, "weight": edge.weight}


def _edge_from_dict(d: dict) -> Edge:
    return Edge(target=d["target"], relation=d["relation"], weight=d.get("weight", 1.0))


def _update_log_to_dict(log: UpdateLogEntry) -> dict:
    return {
        "version": log.version,
        "date": log.date.isoformat(),
        "session_id": log.session_id,
        "trigger": log.trigger,
        "reason": log.reason,
    }


def _update_log_from_dict(d: dict) -> UpdateLogEntry:
    return UpdateLogEntry(
        version=d["version"],
        date=datetime.fromisoformat(d["date"])
        if isinstance(d["date"], str)
        else d["date"],
        session_id=d["session_id"],
        trigger=d["trigger"],
        reason=d["reason"],
    )


class WikiStore:
    def __init__(self, wiki_dir: Path, *, db=None):
        self.wiki_dir = wiki_dir
        self.archive_dir = wiki_dir / "_archive"
        self.db = db if db is not None else database(wiki_dir.parent)

    def get(self, slug: str) -> WikiPage:
        post = frontmatter.loads(self.db.get("wiki", slug)["content"])

        if "page_type" not in post.metadata:
            raise ValueError(
                f"Wiki page {slug} uses the pre-taxonomy schema. "
                "Clear and rebuild the wiki from canonical memory artifacts."
            )
        page_type = post.metadata["page_type"]
        if page_type is not None and page_type not in ENTITY_TYPES:
            raise ValueError(f"Wiki page {slug} has invalid page_type: {page_type!r}")
        entity_id = str(post.metadata.get("entity_id") or "")
        if not entity_id:
            raise ValueError(
                f"Wiki page {slug} uses the pre-entity schema. "
                "Clear and rebuild the wiki from canonical claims."
            )

        related = [_edge_from_dict(r) for r in post.metadata.get("related", [])]
        update_log = [
            _update_log_from_dict(u) for u in post.metadata.get("update_log", [])
        ]

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

        post = frontmatter.Post(page.content)
        post.metadata["id"] = page.slug
        post.metadata["title"] = page.title
        post.metadata["created"] = page.created.isoformat() if page.created else None
        post.metadata["last_updated"] = (
            page.last_updated.isoformat() if page.last_updated else None
        )
        post.metadata["version"] = page.version
        post.metadata["page_type"] = page.page_type
        post.metadata["tags"] = page.tags
        post.metadata["related"] = [_edge_to_dict(r) for r in page.related]
        post.metadata["source_log_entries"] = page.source_log_entries
        post.metadata["update_log"] = [_update_log_to_dict(u) for u in page.update_log]
        post.metadata["entity_id"] = page.entity_id
        post.metadata["entity_status"] = page.entity_status
        post.metadata["aliases"] = page.aliases
        post.metadata["sections"] = page.sections

        self._write(page.slug, frontmatter.dumps(post))

    def _write(self, slug, content):
        with self.db.transaction():
            self.db.put("wiki", slug, {"content": content})
            self.db.project(f"wiki/{slug}.md", content)
        self.db.publish()

    def history(self, slug: str) -> List[UpdateLogEntry]:
        page = self.get(slug)
        return page.update_log

    def list(self, tag: Optional[str] = None) -> List[WikiPage]:
        pages = self.list_all()
        filtered = []
        for p in pages:
            if tag and tag not in p.tags:
                continue
            filtered.append(p)
        return filtered

    def list_all(self) -> List[WikiPage]:
        return [self.get(slug) for slug in self.db.ids("wiki") if slug != "_index"]

    def get_index(self) -> str:
        try:
            return self.db.get("wiki", "_index")["content"]
        except FileNotFoundError:
            return ""

    def save_index(self, content: str) -> None:
        self._write("_index", content)

    def archive(self, slug: str) -> None:
        if self.exists(slug):
            with self.db.transaction():
                self.db.put("wiki-archive", slug, self.db.get("wiki", slug))
                self.db.project(
                    f"wiki/_archive/{slug}.md", self.db.get("wiki", slug)["content"]
                )
                self.delete(slug)
            self.db.publish()

    def delete(self, slug: str) -> None:
        with self.db.transaction():
            self.db.delete("wiki", slug)
            self.db.project(f"wiki/{slug}.md", None)
        self.db.publish()

    def exists(self, slug: str) -> bool:
        try:
            self.db.get("wiki", slug)
            return True
        except FileNotFoundError:
            return False


class LogStore:
    def __init__(self, logs_dir: Path, *, db=None):
        self.logs_dir = logs_dir
        self.db = db if db is not None else database(logs_dir.parent)

    def append(self, entry: LogEntry) -> None:
        with self.db.transaction():
            try:
                self.get(entry.entry_id)
                return
            except FileNotFoundError:
                pass
            self._save(entry)
        self.db.publish()

    def _save(self, entry):
        data = asdict(entry)
        data["timestamp"] = entry.timestamp.isoformat()
        data["date"] = entry.entry_id.split("#")[0]
        try:
            data["log_order"] = self.db.get("logs", entry.entry_id)["log_order"]
        except FileNotFoundError:
            data["log_order"] = self.db.revision("logs") + 1
        self.db.put("logs", entry.entry_id, data)
        self._project(data["date"])

    def _project(self, date):
        entries = [
            self.get(identifier) for identifier in self.db.ids("logs", "date", date)
        ]
        entries.sort(key=lambda entry: self.db.get("logs", entry.entry_id)["log_order"])
        text = f"# Log: {date}\n\n"
        for entry in entries:
            text += (
                f"## {entry.entry_id.split('#')[-1]} — {entry.timestamp:%H:%M}\n\n"
                f"**session_id:** {entry.session_id}  \n"
                f"**durability:** {entry.durability}  \n"
                f"**consolidated:** {str(entry.consolidated).lower()}  \n\n"
                f"{entry.content.strip()}\n\n---\n\n"
            )
        self.db.project(f"logs/{date}.md", text if entries else None)

    def get(self, entry_id: str) -> LogEntry:
        data = self.db.get("logs", entry_id)
        data.pop("date")
        data.pop("log_order")
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return LogEntry(**data)

    def get_many(self, entry_ids: List[str]) -> List[LogEntry]:
        result = []
        for identifier in entry_ids:
            try:
                result.append(self.get(identifier))
            except FileNotFoundError:
                pass
        return result

    def list_entries(self, days: int | None = 7) -> List[LogEntry]:
        entries = [self.get(identifier) for identifier in self.db.ids("logs")]
        dates = sorted(
            {entry.entry_id.split("#")[0] for entry in entries}, reverse=True
        )
        selected = set(dates if days is None else dates[:days])
        date_rank = {date: index for index, date in enumerate(dates)}
        return sorted(
            (entry for entry in entries if entry.entry_id.split("#")[0] in selected),
            key=lambda entry: (
                date_rank[entry.entry_id.split("#")[0]],
                self.db.get("logs", entry.entry_id)["log_order"],
            ),
        )

    def get_unconsolidated(self, days: int | None = 7) -> List[LogEntry]:
        return [entry for entry in self.list_entries(days) if not entry.consolidated]

    def mark_consolidated(self, entry_ids: List[str]) -> None:
        with self.db.transaction():
            for entry in self.get_many(entry_ids):
                entry.consolidated = True
                self._save(entry)
        self.db.publish()

    def mark_unconsolidated(self, date_str: str) -> None:
        with self.db.transaction():
            for identifier in self.db.ids("logs", "date", date_str):
                entry = self.get(identifier)
                entry.consolidated = False
                self._save(entry)
        self.db.publish()

    def mark_all_unconsolidated(self) -> None:
        for date in {entry.entry_id.split("#")[0] for entry in self.list_entries(None)}:
            self.mark_unconsolidated(date)
