from __future__ import annotations

import re
import string
from collections import Counter, defaultdict
from typing import Any


MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


def _expand_iso_dates(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        year, month, day = match.groups()
        month_index = int(month)
        if not 1 <= month_index <= 12:
            return match.group(0)
        return f"{int(day)} {MONTHS[month_index - 1]} {year}"

    return re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", replace, value)


def _light_stem(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    for suffix in ("ement", "ments", "ment", "ing", "ed"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            token = token[:-len(suffix)]
            break
    if token.endswith("s") and not token.endswith(("ss", "us", "is")) and len(token) > 4:
        token = token[:-1]
    if token.endswith("e") and len(token) >= 5:
        token = token[:-1]
    return token


def normalize_answer(text: Any) -> str:
    value = _expand_iso_dates(str(text).lower()).replace(",", "")
    value = "".join(ch for ch in value if ch not in string.punctuation)
    value = re.sub(r"\b(a|an|the|and)\b", " ", value)
    return " ".join(_light_stem(token) for token in value.split())


def token_f1(prediction: Any, ground_truth: Any) -> float:
    prediction_tokens = normalize_answer(prediction).split()
    truth_tokens = normalize_answer(ground_truth).split()
    if not prediction_tokens or not truth_tokens:
        return float(prediction_tokens == truth_tokens)
    common = Counter(prediction_tokens) & Counter(truth_tokens)
    same = sum(common.values())
    if same == 0:
        return 0.0
    precision = same / len(prediction_tokens)
    recall = same / len(truth_tokens)
    return 2 * precision * recall / (precision + recall)


def locomo_score(prediction: Any, answer: Any, category: int) -> float:
    if category == 3:
        answer = str(answer).split(";")[0].strip()
    if category in {2, 3, 4}:
        return token_f1(prediction, answer)
    if category == 1:
        prediction_parts = [part.strip() for part in str(prediction).split(",") if part.strip()]
        truth_parts = [part.strip() for part in str(answer).split(",") if part.strip()]
        if not prediction_parts or not truth_parts:
            return 0.0
        return sum(max(token_f1(pred, truth) for pred in prediction_parts) for truth in truth_parts) / len(truth_parts)
    if category == 5:
        lower = str(prediction).lower()
        # Handle various phrasing for refusing adversarial or unanswerable queries
        refusal_keywords = [
            "no information",
            "not mentioned",
            "not specify",
            "not contain",
            "not provide",
            "not have enough information",
            "not have access",
            "not available",
            "insufficient information",
            "i do not know",
            "not state",
            "did not",
            "does not have",
            "no details",
            "was not found"
        ]
        return 1.0 if any(kw in lower for kw in refusal_keywords) else 0.0
    return token_f1(prediction, answer)


def summarize_scores(rows: list[dict[str, Any]], score_key: str = "score") -> dict[str, Any]:
    by_category: dict[str, list[float]] = defaultdict(list)
    scores = []
    for row in rows:
        score = float(row.get(score_key, 0.0))
        scores.append(score)
        category = str(row.get("category", "unknown"))
        by_category[category].append(score)

    return {
        "count": len(scores),
        "mean_score": sum(scores) / len(scores) if scores else 0.0,
        "by_category": {
            category: {
                "count": len(values),
                "mean_score": sum(values) / len(values) if values else 0.0,
            }
            for category, values in sorted(by_category.items())
        },
    }
