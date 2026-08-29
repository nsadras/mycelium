import tiktoken

# Use cl100k_base encoding for all models (close enough for budgeting)
_enc = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_enc.encode(text))
