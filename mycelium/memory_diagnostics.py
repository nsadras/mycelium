"""Failure location is observable; semantic correctness still needs source review."""

from asyncio import CancelledError

from httpx import TimeoutException
from ollama import RequestError, ResponseError

from mycelium.budget import ContextBudgetError
from mycelium.ollama import StructuredOutputError


def failure(stage, source_id, error):
    category = (error.category if isinstance(error, StructuredOutputError) else
                "cancelled" if isinstance(error, CancelledError) else
                "input_capacity" if isinstance(error, ContextBudgetError) else
                "transport" if isinstance(error, (RequestError, ResponseError, TimeoutException)) else
                "pipeline")
    return {"stage": stage, "source_id": source_id, "category": category,
            "reason": f"{type(error).__name__}: {error}"}
