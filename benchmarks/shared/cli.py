"""Shared benchmark run naming."""

from datetime import datetime


def default_run_id(benchmark: str, system: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{benchmark}-{system}-{stamp}"
