import tiktoken

# Use cl100k_base encoding for all models (close enough for budgeting)
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
        4 + count_tokens(message.get("role", ""))
        + count_tokens(message.get("content", ""))
        for message in messages
    )
