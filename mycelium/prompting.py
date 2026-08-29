"""Strict Jinja rendering for all model-facing prompts."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, Template


TEMPLATE_ROOT = Path(__file__).with_name("prompt_templates")


@lru_cache(maxsize=1)
def prompt_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_ROOT),
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=False,
    )


def prompt_template(name: str) -> Template:
    """Load a prompt template by its path relative to ``prompt_templates``."""
    return prompt_environment().get_template(name)


def render_prompt(name: str, /, **context: Any) -> str:
    """Render one prompt and fail when any declared variable is missing."""
    return prompt_template(name).render(**context)


def render_prompt_pair(name: str, /, **context: Any) -> tuple[str, str]:
    """Render the conventional system/user pair for one prompt family."""
    return (
        render_prompt(f"{name}.system.jinja", **context),
        render_prompt(f"{name}.user.jinja", **context),
    )
