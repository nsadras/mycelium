import tiktoken
import json


class ContextBudgetError(ValueError):
    """The complete request cannot fit without dropping evidence."""


def output_contract(user: str, schema) -> str:
    return (
        user
        + "\n\nOUTPUT CONTRACT (JSON Schema)\n"
        + json.dumps(schema, ensure_ascii=False)
        + "\n\nReturn the completed result for the supplied evidence as one JSON value matching this contract."
    )


def request_tokens(messages, schema=None, tools=None) -> int:
    """Estimate the actual envelopes, structured schema, and tool definitions."""
    if schema:
        messages = [dict(message) for message in messages]
        if not messages or messages[-1].get("role") != "user":
            raise ValueError(
                "Structured prompt estimation requires a final user message"
            )
        messages[-1]["content"] = output_contract(messages[-1]["content"], schema)
    payload = {"messages": messages}
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


def count_message_tokens(messages: list[dict[str, str]]) -> int:
    """Conservative content-plus-envelope estimate for one chat prompt."""
    return 3 + sum(
        4
        + count_tokens(message.get("role", ""))
        + count_tokens(message.get("content", ""))
        for message in messages
    )
