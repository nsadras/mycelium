"""Compact display of exact source references; original citation lists stay intact."""

from html import escape


def segment_references(source_id: str, segment_ids: tuple[str, ...]) -> str:
    """Abbreviate only exact consecutive canonical IDs, never fill citation gaps."""
    ranges: list[tuple[str, str, int | None]] = []
    for identifier in segment_ids:
        source, separator, number = identifier.rpartition("#seg-")
        ordinal = int(number) if separator and source == source_id and number.isascii() and number.isdecimal() else None
        if ordinal is not None and identifier != f"{source_id}#seg-{ordinal:04d}":
            ordinal = None
        if ranges and ordinal is not None and ranges[-1][2] is not None and ordinal == ranges[-1][2] + 1:
            ranges[-1] = (ranges[-1][0], identifier, ordinal)
        else:
            ranges.append((identifier, identifier, ordinal))
    return " · ".join(
        f"`{escape(start, quote=False)}`" if start == end
        else f"`{escape(start, quote=False)}`–`{escape(end, quote=False)}`"
        for start, end, _ in ranges)
