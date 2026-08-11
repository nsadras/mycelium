from __future__ import annotations

import re

from mycelium.models import WikiPage

RECALL_SECTION_NAMES = ("Key Facts", "Event Timeline", "Source Logs")


def extract_recall_sections(content: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {name: [] for name in RECALL_SECTION_NAMES}
    current: str | None = None

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        heading = re.match(r"^(#{2,6})\s+(.+?)\s*$", line)
        if heading:
            level = len(heading.group(1))
            title = _normalize_heading(heading.group(2))
            recall_section = next(
                (
                    name
                    for name in RECALL_SECTION_NAMES
                    if _normalize_heading(name) == title
                ),
                None,
            )
            if recall_section is not None:
                current = recall_section
            elif level <= 2:
                current = None
            continue
        if current is None:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if _is_recall_line(stripped):
            sections[current].append(stripped)

    return {name: rows for name, rows in sections.items() if rows}


def page_recall_context(page: WikiPage, *, max_lines: int = 24) -> str:
    sections = extract_recall_sections(page.content)
    if not sections:
        return ""

    lines = [f"RECALL DETAILS FOR [[{page.slug}]]:"]
    remaining = max_lines
    for section_name in RECALL_SECTION_NAMES:
        rows = sections.get(section_name, [])
        if not rows or remaining <= 0:
            continue
        lines.append(f"{section_name}:")
        for row in rows[:remaining]:
            lines.append(row)
            remaining -= 1
            if remaining <= 0:
                break
    return "\n".join(lines)


def routing_recall_index(pages: list[WikiPage], *, max_lines_per_page: int = 10) -> str:
    blocks = []
    for page in pages:
        context = page_recall_context(page, max_lines=max_lines_per_page)
        if context:
            blocks.append(context)
    if not blocks:
        return ""
    return "## Recall Facts And Timelines\n" + "\n\n".join(blocks)


def _normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _is_recall_line(line: str) -> bool:
    if re.match(r"^\|[\s:\-|]+\|?$", line):
        return False
    if line.startswith(("-", "*", "|")):
        return True
    if re.match(r"^\d+[.)]\s+", line):
        return True
    return False
