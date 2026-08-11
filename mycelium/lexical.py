from __future__ import annotations

import math
import re


def terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9'-]{2,}", text.lower())
        if token not in STOPWORDS
    }


def query_term_weights(documents: list[str], query: str) -> dict[str, float]:
    query_terms = terms(query)
    document_terms = [terms(document) for document in documents]
    document_count = max(len(document_terms), 1)
    entity_terms = {
        token.lower()
        for token in re.findall(r"\b[A-Z][A-Za-z0-9'-]{2,}\b", query)
        if token.lower() in query_terms
    }
    weights = {}
    for term in query_terms:
        document_frequency = sum(term in item_terms for item_terms in document_terms)
        idf = math.log(
            1.0
            + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
        )
        weights[term] = idf * (2.0 if term in entity_terms else 1.0)
    return weights


STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "because",
    "but",
    "can",
    "did",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "her",
    "him",
    "his",
    "how",
    "into",
    "not",
    "that",
    "the",
    "their",
    "then",
    "there",
    "they",
    "this",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "you",
    "your",
}
