import tiktoken
import json


class ContextBudgetError(ValueError):
    """The complete request cannot fit without dropping evidence."""


def request_tokens(messages, schema=None, tools=None) -> int:
    """Estimate the actual envelopes, structured schema, and tool definitions."""
    payload = {"messages": messages}
    if schema:
        payload["format"] = schema
    if tools:
        payload["tools"] = tools
    return count_tokens(json.dumps(payload, ensure_ascii=False, default=str))


def require_request_budget(
    messages, *, context_window, output_tokens, schema=None, tools=None
):
    if output_tokens <= 0:
        raise ContextBudgetError(
            "Generation requires a positive, bounded output reserve"
        )
    available = context_window - output_tokens - 2048
    used = request_tokens(messages, schema, tools)
    if available <= 0 or used > available:
        raise ContextBudgetError(
            f"Complete LLM input exceeds its budget ({used} > {available}); "
            "split complete evidence units before requesting inference"
        )
    return used


# Estimates use cl100k; request budgeting reserves headroom for tokenizer differences.
_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def truncate_text_tokens(text: str, max_tokens: int, *, keep_end: bool = False) -> str:
    if max_tokens <= 0:
        return ""
    encoded = _enc.encode(text)
    if len(encoded) <= max_tokens:
        return text
    selected = encoded[-max_tokens:] if keep_end else encoded[:max_tokens]
    return _enc.decode(selected)


def count_message_tokens(messages: list[dict[str, str]]) -> int:
    """Conservative content-plus-envelope estimate for one chat prompt."""
    return 3 + sum(
        4
        + count_tokens(message.get("role", ""))
        + count_tokens(message.get("content", ""))
        for message in messages
    )
