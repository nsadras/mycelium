from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

from mycelium.lexical import terms
from mycelium.models import WikiPage


@dataclass(frozen=True)
class PageSearchHit:
    slug: str
    score: float


class PageSearchIndex:
    """Lazily refreshed SQLite FTS5 projection over human-readable wiki pages."""

    def __init__(self) -> None:
        self._connection = sqlite3.connect(":memory:")
        self._connection.execute(
            """
            CREATE VIRTUAL TABLE page_search USING fts5(
                slug UNINDEXED,
                title,
                page_type,
                body,
                tokenize = 'porter unicode61 remove_diacritics 2'
            )
            """
        )
        self._fingerprint: tuple[tuple[str, int, str], ...] = ()

    def search(
        self, pages: list[WikiPage], query: str, *, limit: int
    ) -> list[PageSearchHit]:
        if limit <= 0:
            return []
        self._refresh_if_needed(pages)
        query_terms = terms(query)
        if not query_terms:
            return []
        match_query = " OR ".join(f'"{term}"' for term in sorted(query_terms))
        rows = self._connection.execute(
            """
            SELECT slug, bm25(page_search, 0.0, 8.0, 2.0, 1.0) AS rank
            FROM page_search
            WHERE page_search MATCH ?
            ORDER BY rank, slug
            LIMIT ?
            """,
            (match_query, limit),
        ).fetchall()
        return [
            PageSearchHit(slug=str(slug), score=-float(rank))
            for slug, rank in rows
        ]

    def _refresh_if_needed(self, pages: list[WikiPage]) -> None:
        fingerprint = tuple(
            sorted(
                (
                    page.slug,
                    page.version,
                    hashlib.sha256(page.content.encode("utf-8")).hexdigest(),
                )
                for page in pages
            )
        )
        if fingerprint == self._fingerprint:
            return
        with self._connection:
            self._connection.execute("DELETE FROM page_search")
            self._connection.executemany(
                """
                INSERT INTO page_search(slug, title, page_type, body)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        page.slug,
                        page.title,
                        page.page_type or "",
                        page.content,
                    )
                    for page in pages
                ],
            )
        self._fingerprint = fingerprint
