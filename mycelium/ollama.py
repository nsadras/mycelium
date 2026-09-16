from mycelium.telemetry import trace_metadata, trace_operation
import json
import inspect
import logging
import os
import time
import re
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any, Union, Optional

from dotenv import load_dotenv
from httpx import TimeoutException
from ollama import AsyncClient, RequestError, ResponseError, web_fetch, web_search
from pydantic import BaseModel, ValidationError
from ollama._utils import convert_function_to_tool
from mycelium.budget import require_request_budget, output_contract
from mycelium.decision_cache import DecisionCache

logger = logging.getLogger(__name__)
LLM_DEBUG_DIR_ENV = "MYCELIUM_LLM_DEBUG_DIR"
LLM_CALL_LOG_LIMIT = 100


@dataclass
class ToolEvent:
    tool_name: str
    arguments: dict[str, Any]
    result: str
    failed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolExecutionResult:
    """Separate an inspectable tool result from its bounded model presentation."""

    result: str
    model_result: str
    supersession_key: str | None = None
    superseded_result: str = "Tool result superseded by the latest state."
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentExecutionStep:
    """One model decision and any tool observations produced from it."""

    attempt_index: int
    round_index: int
    thinking: str
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_events: list[ToolEvent] = field(default_factory=list)
    outcome: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    content: str
    tool_events: list[ToolEvent] = field(default_factory=list)
    execution_trace: list[AgentExecutionStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class OllamaClient:
    def __init__(
        self,
        url: str,
        model: str,
        temperature: float = 1.0,
        timeout: int = 900,
        context_window_tokens: int = 32768,
        trace_path: Path | None = None,
        top_p: float = 0.95,
        top_k: int = 64,
        reasoning_enabled: bool = True,
        reasoning_output_tokens: int = 16384,
        reasoning_format: str = "prompt",
    ) -> None:
        load_dotenv()
        self.url = url.rstrip('/')
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.reasoning_enabled = reasoning_enabled
        self.reasoning_output_tokens = reasoning_output_tokens
        if reasoning_output_tokens <= 0 or reasoning_format not in {"prompt", "native"}:
            raise ValueError("Reasoning requires a positive token reserve and prompt/native format")
        self.reasoning_format = reasoning_format
        self.timeout = timeout
        self.context_window_tokens = context_window_tokens
        self.trace_path = trace_path
        self.client = AsyncClient(host=self.url, timeout=self.timeout)
        self._call_log: deque[dict[str, Any]] = deque(maxlen=LLM_CALL_LOG_LIMIT)

    def output_budget(self, requested: int, *, think: bool) -> int:
        """Reserve generation space for reasoning as well as the final answer."""
        return max(requested, self.reasoning_output_tokens) if think and self.reasoning_enabled else requested

    def _extract_json(self, content: str) -> Union[dict, list]:
        """
        Extracts JSON from a string, handling potential markdown fences.
        """
        content = content.strip()
        
        # Remove markdown code fences if present
        if content.startswith("```"):
            # Find the end of the first line (e.g., ```json)
            first_line_end = content.find("\n")
            if first_line_end != -1:
                content = content[first_line_end:].strip()
            
            # Remove the closing fences
            if content.endswith("```"):
                content = content[:-3].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # If standard parsing fails, try a simple regex for the first { or [ to the last } or ]
            # as a last resort fallback for models that still add preambles.
            match = re.search(r'([\[{].*[\]}])', content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            raise

    async def call_messages(
        self,
        messages: list[dict[str, Any]],
        max_retries: int = 3,
        temperature: Optional[float] = None,
        enable_tools: bool = True,
        max_tool_rounds: int = 5,
        num_ctx: int | None = None,
        num_predict: int | None = None,
        think: bool | None = None,
        tool_definitions: list[Any] | None = None,
        tool_runner: Callable[
            [str, dict[str, Any]],
            str
            | ToolExecutionResult
            | None
            | Awaitable[str | ToolExecutionResult | None],
        ] | None = None,
        replaceable_context_message_index: int | None = None,
        replacement_context_content: str | None = None,
    ) -> ChatResponse:
        """
        Makes a chat completion call using an explicit message history.
        """
        call_id = str(uuid.uuid4())[:8]
        temp = temperature if temperature is not None else self.temperature
        think = self.reasoning_enabled and (bool(enable_tools) if think is None else think)
        options = {"temperature": temp, "top_p": self.top_p, "top_k": self.top_k,
                   "num_ctx": self.context_window_tokens,
                   "num_predict": self.output_budget(num_predict if num_predict is not None else 4096, think=think)}
        if num_ctx is not None:
            options["num_ctx"] = num_ctx
        endpoint = f"{self.url}/api/chat"
        working_messages = [dict(message) for message in messages]
        tool_events: list[ToolEvent] = []
        execution_trace: list[AgentExecutionStep] = []

        for attempt in range(max_retries):
            start_time = time.time()
            self._log_request(
                call_id=call_id,
                attempt=attempt + 1,
                max_retries=max_retries,
                endpoint=endpoint,
                model=self.model,
                messages=working_messages,
                output_format=None,
                options=options,
            )
            try:
                content, metadata = await self._chat_with_optional_tools(
                    call_id=call_id,
                    attempt_index=attempt + 1,
                    messages=working_messages,
                    options=options,
                    enable_tools=enable_tools,
                    max_tool_rounds=max_tool_rounds,
                    tool_events=tool_events,
                    execution_trace=execution_trace,
                    think=think,
                    tool_definitions=tool_definitions,
                    tool_runner=tool_runner,
                    replaceable_context_message_index=(
                        replaceable_context_message_index
                    ),
                    replacement_context_content=replacement_context_content,
                )
                metadata = dict(metadata)
                for key in ("total_duration", "load_duration", "prompt_eval_count",
                            "prompt_eval_duration", "eval_count", "eval_duration"):
                    values = [step.metadata[key] for step in execution_trace if key in step.metadata]
                    if values:
                        metadata[key] = sum(values)
                metadata["inference_rounds"] = len(execution_trace)
                latency_ms = int((time.time() - start_time) * 1000)
                self._log_call(
                    call_id,
                    attempt + 1,
                    self._first_message_content(working_messages, "system"),
                    self._last_message_content(working_messages, "user"),
                    content,
                    latency_ms,
                    True,
                    metadata,
                )
                return ChatResponse(
                    content=content,
                    tool_events=tool_events,
                    execution_trace=execution_trace,
                    metadata=metadata,
                )

            except (RequestError, ResponseError, TimeoutException) as e:
                latency_ms = int((time.time() - start_time) * 1000)
                self._log_call(
                    call_id,
                    attempt + 1,
                    self._first_message_content(working_messages, "system"),
                    self._last_message_content(working_messages, "user"),
                    str(e),
                    latency_ms,
                    False,
                )
                if attempt == max_retries - 1 or (
                    isinstance(e, ResponseError) and e.status_code is not None
                    and 400 <= e.status_code < 500 and e.status_code not in {408, 429}
                ):
                    raise

        raise ValueError("Failed to get chat response from Ollama")

    async def _chat_with_optional_tools(
        self,
        call_id: str,
        attempt_index: int,
        messages: list[dict[str, Any]],
        options: dict[str, Any],
        enable_tools: bool,
        max_tool_rounds: int,
        tool_events: list[ToolEvent],
        execution_trace: list[AgentExecutionStep],
        think: bool | None,
        tool_definitions: list[Any] | None,
        tool_runner: Callable[
            [str, dict[str, Any]],
            str
            | ToolExecutionResult
            | None
            | Awaitable[str | ToolExecutionResult | None],
        ] | None,
        replaceable_context_message_index: int | None,
        replacement_context_content: str | None,
    ) -> tuple[str, dict[str, Any]]:
        tools = (
            tool_definitions
            if enable_tools and tool_definitions is not None
            else [web_search, web_fetch] if enable_tools else None
        )
        tools = [convert_function_to_tool(t).model_dump(exclude_none=True)
                 if callable(t) else t for t in tools] if tools else None
        think_enabled = think if think is not None else bool(enable_tools)
        current_result_message_by_key: dict[str, int] = {}
        context_replaced = False
        for round_idx in range(max_tool_rounds + 1):
            require_request_budget(messages, context_window=options["num_ctx"],
                                   output_tokens=options["num_predict"], tools=tools)
            round_started = time.monotonic()
            try:
                with trace_operation("llm_attempt", llm_call_id=call_id, llm_attempt=attempt_index, llm_round=round_idx + 1):
                    response = await self.client.chat(  # type: ignore[call-overload]  # SDK overload rejects equivalent mappings
                        model=self.model,
                        messages=messages,
                        tools=tools,
                        think=think_enabled,
                        stream=False,
                        format=None,
                        options=options,
                    )
            except (RequestError, ResponseError, TimeoutException):
                self._log_call(call_id, attempt_index, "", "", "",
                               int((time.monotonic() - round_started) * 1000), False,
                               stage=f"chat-round-{round_idx + 1}")
                raise
            metadata = self._response_metadata(response)
            metadata.update(think=think_enabled, output_token_limit=options["num_predict"],
                            context_window_tokens=options["num_ctx"])
            self._log_call(call_id, attempt_index, "", "", "",
                           int((time.monotonic() - round_started) * 1000), metadata.get("done_reason") != "length", metadata,
                           stage=f"chat-round-{round_idx + 1}")
            if metadata.get("done_reason") == "length":
                raise ValueError("Generation exhausted its token allowance; increase the output reserve before retrying")
            assistant_message = self._assistant_message_dict(response)
            content = assistant_message.get("content", "").strip()
            tool_calls = assistant_message.get("tool_calls", [])
            step = AgentExecutionStep(
                attempt_index=attempt_index,
                round_index=round_idx + 1,
                thinking=str(assistant_message.get("thinking", "") or ""),
                content=content,
                tool_calls=[self._tool_call_dict(tool_call) for tool_call in tool_calls],
                metadata=metadata,
            )
            execution_trace.append(step)
            messages.append(assistant_message)
            if not tool_calls:
                step.outcome = "final_response"
                return content, metadata
            if round_idx >= max_tool_rounds:
                step.outcome = "tool_round_limit"
                return content, metadata
            for tool_call in tool_calls:
                tool_name, tool_args = self._tool_call_name_args(tool_call)
                custom_result = (
                    tool_runner(tool_name, tool_args)
                    if tool_runner is not None
                    else None
                )
                executed = (
                    await custom_result
                    if inspect.isawaitable(custom_result)
                    else custom_result
                )
                if executed is None:
                    executed = await self._run_tool(tool_name, tool_args)
                if isinstance(executed, ToolExecutionResult):
                    result = executed.result
                    model_result = executed.model_result
                    result_metadata = dict(executed.metadata)
                    if executed.supersession_key:
                        prior_index = current_result_message_by_key.get(
                            executed.supersession_key
                        )
                        if prior_index is not None:
                            messages[prior_index]["content"] = (
                                executed.superseded_result
                            )
                        if not context_replaced:
                            self._replace_context_message(
                                messages,
                                replaceable_context_message_index,
                                replacement_context_content,
                            )
                            context_replaced = True
                else:
                    result = executed
                    model_result = result
                    result_metadata = {}
                failed = (
                    result.startswith(f"Tool {tool_name} failed:")
                    or result == f"Tool {tool_name} not found"
                    or result.startswith("<memory-tool-error>")
                )
                tool_event = ToolEvent(
                    tool_name=tool_name,
                    arguments=tool_args,
                    result=result,
                    failed=failed,
                    metadata=result_metadata,
                )
                tool_events.append(tool_event)
                step.tool_events.append(tool_event)
                logger.info(
                    "LLM tool call %s",
                    json.dumps(
                        {
                            "call_id": call_id,
                            "tool_name": tool_name,
                            "argument_keys": sorted(tool_args),
                            "result_chars": len(result),
                            "failed": failed,
                        },
                        ensure_ascii=False,
                    ),
                )
                messages.append({
                    "role": "tool",
                    "content": model_result,
                    "tool_name": tool_name,
                })
                if (
                    isinstance(executed, ToolExecutionResult)
                    and executed.supersession_key
                ):
                    current_result_message_by_key[executed.supersession_key] = (
                        len(messages) - 1
                    )
            step.outcome = "tools_executed"
        return "", {}

    @staticmethod
    def _replace_context_message(
        messages: list[dict[str, Any]],
        message_index: int | None,
        replacement_content: str | None,
    ) -> None:
        if message_index is None or replacement_content is None:
            return
        if message_index < 0 or message_index >= len(messages):
            raise ValueError("Replaceable context message index is out of range")
        messages[message_index]["content"] = replacement_content

    def _assistant_message_dict(self, response: Any) -> dict[str, Any]:
        message = getattr(response, "message", None)
        if isinstance(message, dict):
            return dict(message)
        if message is None:
            return {"role": "assistant", "content": ""}

        assistant_message: dict[str, Any] = {
            "role": getattr(message, "role", "assistant") or "assistant",
            "content": getattr(message, "content", "") or "",
        }
        thinking = getattr(message, "thinking", None)
        if thinking:
            assistant_message["thinking"] = thinking
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            assistant_message["tool_calls"] = tool_calls
        return assistant_message

    def _tool_call_name_args(self, tool_call: Any) -> tuple[str, dict[str, Any]]:
        function = tool_call.get("function") if isinstance(tool_call, dict) else getattr(tool_call, "function", None)
        if isinstance(function, dict):
            return str(function.get("name", "")), dict(function.get("arguments", {}) or {})
        if function is None:
            return "", {}
        return str(getattr(function, "name", "")), dict(getattr(function, "arguments", {}) or {})

    def _tool_call_dict(self, tool_call: Any) -> dict[str, Any]:
        tool_name, tool_args = self._tool_call_name_args(tool_call)
        return {"tool_name": tool_name, "arguments": tool_args}

    async def _run_tool(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        try:
            if tool_name == "web_search":
                return self._format_web_search_result(
                    await self.client.web_search(**tool_args)
                )
            if tool_name == "web_fetch":
                return self._format_web_fetch_result(
                    await self.client.web_fetch(**tool_args)
                )
            return f"Tool {tool_name} not found"
        except Exception as exc:
            return f"Tool {tool_name} failed: {exc}"

    def _format_web_search_result(self, response: Any) -> str:
        results = getattr(response, "results", None)
        if results is None and isinstance(response, dict):
            results = response.get("results")
        if not results:
            return "No search results."

        formatted = []
        for index, result in enumerate(results, start=1):
            title = self._field(result, "title") or "Untitled result"
            url = self._field(result, "url")
            content = self._field(result, "content")
            parts = [f"{index}. {title}"]
            if url:
                parts.append(str(url))
            if content:
                parts.append(str(content).replace("\\n", "\n"))
            formatted.append("\n".join(parts))
        return "\n\n---\n\n".join(formatted)

    def _format_web_fetch_result(self, response: Any) -> str:
        title = self._field(response, "title")
        content = self._field(response, "content")
        links = self._field(response, "links")
        parts = []
        if title:
            parts.append(f"# {title}")
        if content:
            parts.append(str(content).replace("\\n", "\n"))
        if links:
            parts.append("Links:\n" + "\n".join(f"- {link}" for link in links))
        return "\n\n".join(parts) if parts else "No fetched content."

    def _field(self, value: Any, field: str) -> Any:
        if isinstance(value, dict):
            return value.get(field)
        return getattr(value, field, None)

    def _first_message_content(self, messages: list[dict[str, Any]], role: str) -> str:
        for message in messages:
            if message.get("role") == role:
                return message.get("content", "")
        return ""

    def _last_message_content(self, messages: list[dict[str, Any]], role: str) -> str:
        for message in reversed(messages):
            if message.get("role") == role:
                return message.get("content", "")
        return ""

    def _response_metadata(self, response: Any) -> dict[str, Any]:
        fields = (
            "done",
            "done_reason",
            "total_duration",
            "load_duration",
            "prompt_eval_count",
            "prompt_eval_duration",
            "eval_count",
            "eval_duration",
        )
        metadata: dict[str, Any] = {}
        for metadata_field in fields:
            value = self._field(response, metadata_field)
            if value is not None:
                metadata[metadata_field] = value
        return metadata

    def _parse_structured_response(
        self,
        content: str,
        response_model: type[BaseModel] | None,
    ) -> Union[dict, list]:
        if response_model is None:
            parsed = self._extract_json(content)
            if not isinstance(parsed, (dict, list)):
                raise ValueError("Structured response was not a JSON object or array")
            return parsed

        stripped = content.strip()
        try:
            parsed_model = response_model.model_validate_json(stripped)
        except ValidationError:
            extracted = self._extract_json(stripped)
            parsed_model = response_model.model_validate(extracted)

        if getattr(parsed_model, "__pydantic_root_model__", False):
            return parsed_model.model_dump()
        return parsed_model.model_dump()
                    
    async def call_structured(
        self,
        system: str,
        user: str,
        schema: Union[dict, type[BaseModel]],
        max_retries: int = 3,
        num_predict: int = 4096,
        dump_success: bool = False,
        debug_label: str | None = None,
        think: bool = False,
        *,
        cache_store=None,
    ) -> Union[dict, list]:
        """Reuse only validated results under the same complete inference contract."""
        arguments = dict(max_retries=max_retries, num_predict=num_predict,
                         dump_success=dump_success, debug_label=debug_label, think=think)
        if cache_store is None:
            return await self._call_structured(system, user, schema, **arguments)
        output_format, response_model = self._structured_format(schema)
        if response_model is None:
            raise ValueError("Cached structured decisions require a validating response model")
        started = time.perf_counter()
        # A configured tag can point at new weights during the process lifetime.
        # Verify the digest on every lookup rather than reusing a stale identity.
        digest = await self._decision_model_digest()
        enabled = bool(think and self.reasoning_enabled)
        request = {
            "version": 1, "system": system, "user": output_contract(user, output_format), "schema": output_format,
            "endpoint": self.url, "model": self.model, "digest": digest,
            "stage": debug_label, "temperature": self.temperature, "top_p": self.top_p,
            "top_k": self.top_k, "context_window": self.context_window_tokens,
            "think": enabled, "reasoning_format": self.reasoning_format,
            "output_tokens": self.output_budget(num_predict, think=enabled), "max_retries": max_retries,
        }
        cache = DecisionCache(cache_store, request)
        async with cache.lock:
            prior = cache.get()
            if prior is not None:
                parsed = response_model.model_validate(prior["response"]).model_dump()
                self._log_call(str(uuid.uuid4())[:8], 1, system, user,
                    json.dumps(parsed, ensure_ascii=False), int((time.perf_counter()-started)*1000), True,
                    {"cache_hit": True, "request_digest": cache.key, "model_digest": digest},
                    stage=debug_label or "structured")
                return parsed
            result = await self._call_structured(system, user, schema, **arguments)
            if await self._decision_model_digest() != digest:
                raise ValueError("Configured model weights changed during inference; decision was not cached")
            cache.save(result, model_digest=digest, stage=debug_label or "structured")
            return result

    async def _decision_model_digest(self):
        inventory = await self.client.list()
        model_name = self.model if ":" in self.model else self.model + ":latest"
        matching = [row for row in self._field(inventory, "models") or []
                    if self._field(row, "model") in {self.model, model_name}]
        digest = self._field(matching[0], "digest") if len(matching) == 1 else None
        if not isinstance(digest, str) or not digest:
            raise ValueError(f"Cannot identify configured model weights for decision reuse: {self.model}")
        return digest

    async def _call_structured(
        self,
        system: str,
        user: str,
        schema: Union[dict, type[BaseModel]],
        max_retries: int = 3,
        num_predict: int = 4096,
        dump_success: bool = False,
        debug_label: str | None = None,
        think: bool = False,
    ) -> Union[dict, list]:
        """
        Validate one structured decision. Reasoning uses a schema-grounded,
        uninterrupted generation by default, avoiding Ollama's format restart.
        Native constrained reasoning is an explicit configuration choice.
        """
        call_id = str(uuid.uuid4())[:8]
        output_format, response_model = self._structured_format(schema)
        think = think and self.reasoning_enabled
        if think and response_model is None and self.reasoning_format == "prompt":
            raise ValueError("Prompt-constrained reasoning requires a Pydantic response model")
        num_predict = self.output_budget(num_predict, think=think)
        user = output_contract(user, output_format)
        api_format = None if think and self.reasoning_format == "prompt" else output_format
        options = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "num_ctx": self.context_window_tokens,
            "num_predict": num_predict,
        }
        endpoint = f"{self.url}/api/chat"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        for attempt in range(max_retries):
            require_request_budget(messages, context_window=self.context_window_tokens,
                                   output_tokens=num_predict)
            start_time = time.time()
            self._log_request(
                call_id=call_id,
                attempt=attempt + 1,
                max_retries=max_retries,
                endpoint=endpoint,
                model=self.model,
                messages=messages,
                output_format=api_format,
                options=options,
            )
            try:
                with trace_operation("llm_attempt", llm_call_id=call_id, llm_attempt=attempt + 1):
                    response = await self.client.chat(  # type: ignore[call-overload]  # SDK overload rejects equivalent mappings
                        model=self.model,
                        messages=messages,
                        think=think,
                        stream=False,
                        format=api_format,
                        options=options,
                    )
                assistant_message = self._assistant_message_dict(response)
                content = str(assistant_message.get("content", "")).strip()
                metadata = self._response_metadata(response)
                metadata.update(
                    think=think,
                    structured_output_mode="native" if api_format is not None else "prompt",
                    output_token_limit=num_predict,
                    context_window_tokens=self.context_window_tokens,
                    thinking_chars=len(str(assistant_message.get("thinking", "") or "")),
                    content_chars=len(content),
                )
                latency_ms = int((time.time() - start_time) * 1000)

                try:
                    if metadata.get("done_reason") == "length":
                        raise ValueError("Generation exhausted its token allowance; increase the output reserve before retrying")
                    parsed = self._parse_structured_response(content, response_model)
                    self._log_call(call_id, attempt + 1, system, user, content, latency_ms, True, metadata, stage=debug_label or "structured")
                    if dump_success:
                        self._dump_structured_success(
                            call_id=call_id,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            endpoint=endpoint,
                            model=self.model,
                            messages=messages,
                            output_format=output_format,
                            options=options,
                            assistant_message=assistant_message,
                            response=content,
                            parsed=parsed,
                            metadata=metadata,
                            debug_label=debug_label,
                        )
                    return parsed
                except (json.JSONDecodeError, ValidationError, ValueError) as parse_exc:
                    self._log_call(call_id, attempt + 1, system, user, content, latency_ms, False, metadata, stage=debug_label or "structured")
                    debug_dump_path = self._dump_structured_failure(
                        call_id=call_id,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        endpoint=endpoint,
                        model=self.model,
                        messages=messages,
                        output_format=output_format,
                        options=options,
                        assistant_message=assistant_message,
                        response=content,
                        metadata=metadata,
                        error=parse_exc,
                    )
                    if attempt == max_retries - 1 or metadata.get("done_reason") == "length":
                        metadata_text = f"; metadata={metadata}" if metadata else ""
                        debug_text = (
                            f"; debug_dump={debug_dump_path}"
                            if debug_dump_path
                            else f"; debug_dump disabled, set {LLM_DEBUG_DIR_ENV}=.llm-debug"
                        )
                        raise ValueError(
                            "Structured response did not satisfy its contract after "
                            f"{attempt + 1} attempts; final_error="
                            f"{type(parse_exc).__name__}: {parse_exc}"
                            f"{metadata_text}{debug_text}"
                        ) from parse_exc
                    messages = [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": (
                                "The response did not satisfy the supplied structured "
                                "output contract. Correct the response and return the "
                                "complete JSON value only. Contract error: "
                                f"{type(parse_exc).__name__}: {parse_exc}"
                            ),
                        },
                    ]
                    continue

            except (RequestError, ResponseError, TimeoutException) as e:
                latency_ms = int((time.time() - start_time) * 1000)
                self._log_call(call_id, attempt + 1, system, user, str(e), latency_ms, False, stage=debug_label or "structured")
                if attempt == max_retries - 1 or (
                    isinstance(e, ResponseError) and e.status_code is not None
                    and 400 <= e.status_code < 500 and e.status_code not in {408, 429}
                ):
                    raise

        raise ValueError("Failed to get structured response from Ollama")

    def _structured_format(
        self,
        schema: Union[dict, type[BaseModel]],
    ) -> tuple[Union[str, dict[str, Any]], type[BaseModel] | None]:
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            return schema.model_json_schema(), schema
        return schema, None

    def _dump_structured_failure(
        self,
        *,
        call_id: str,
        attempt: int,
        max_retries: int,
        endpoint: str,
        model: str,
        messages: list[dict[str, Any]],
        output_format: Union[str, dict[str, Any]],
        options: dict[str, Any],
        assistant_message: dict[str, Any],
        response: str,
        metadata: dict[str, Any],
        error: Exception,
    ) -> str | None:
        debug_dir = os.getenv(LLM_DEBUG_DIR_ENV) or (str(self.trace_path.parent / "failures") if self.trace_path else None)
        if not debug_dir:
            return None

        payload = {
            "trace": trace_metadata(),
            "call_id": call_id,
            "attempt": attempt,
            "max_retries": max_retries,
            "endpoint": endpoint,
            "model": model,
            "messages": messages,
            "format": None if metadata.get("structured_output_mode") == "prompt" else output_format,
            "validation_schema": output_format,
            "options": options,
            "metadata": metadata,
            "assistant_message": assistant_message,
            "response": response,
            "response_chars": len(response),
            "error_type": type(error).__name__,
            "error": str(error),
        }

        try:
            path = Path(debug_dir).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            filename = f"structured-failure-{call_id}-attempt-{attempt}.json"
            dump_path = path / filename
            dump_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            return str(dump_path)
        except Exception as dump_exc:
            logger.warning("Failed to write structured LLM debug dump: %s", dump_exc)
            return None

    def _dump_structured_success(
        self,
        *,
        call_id: str,
        attempt: int,
        max_retries: int,
        endpoint: str,
        model: str,
        messages: list[dict[str, Any]],
        output_format: Union[str, dict[str, Any]],
        options: dict[str, Any],
        assistant_message: dict[str, Any],
        response: str,
        parsed: Union[dict, list],
        metadata: dict[str, Any],
        debug_label: str | None = None,
    ) -> str | None:
        debug_dir = os.getenv(LLM_DEBUG_DIR_ENV)
        if not debug_dir:
            return None

        payload = {
            "trace": trace_metadata(),
            "call_id": call_id,
            "attempt": attempt,
            "max_retries": max_retries,
            "endpoint": endpoint,
            "model": model,
            "messages": messages,
            "format": None if metadata.get("structured_output_mode") == "prompt" else output_format,
            "validation_schema": output_format,
            "options": options,
            "metadata": metadata,
            "assistant_message": assistant_message,
            "response": response,
            "response_chars": len(response),
            "parsed": parsed,
            "debug_label": debug_label,
        }

        try:
            path = Path(debug_dir).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            label = self._debug_filename_part(debug_label or "structured")
            filename = f"structured-success-{label}-{call_id}-attempt-{attempt}.json"
            dump_path = path / filename
            dump_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            return str(dump_path)
        except Exception as dump_exc:
            logger.warning("Failed to write structured LLM debug dump: %s", dump_exc)
            return None

    def _debug_filename_part(self, value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-._")
        return normalized[:80] or "structured"

    def _log_request(
        self,
        call_id: str,
        attempt: int,
        max_retries: int,
        endpoint: str,
        model: str,
        messages: list[dict[str, Any]] | None,
        output_format: Union[str, dict[str, Any], None],
        options: dict[str, Any],
        prompt: str | None = None,
        system: str | None = None,
    ) -> None:
        message_chars = sum(
            len(str(message.get("content", ""))) for message in (messages or [])
        )
        logger.info(
            "LLM request %s",
            json.dumps(
                {
                    "call_id": call_id,
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "endpoint": endpoint,
                    "model": model,
                    "format": "schema" if isinstance(output_format, dict) else output_format,
                    "options": options,
                    "message_count": len(messages or []),
                    "request_chars": message_chars + len(system or "") + len(prompt or ""),
                },
                ensure_ascii=False,
                default=str,
            ),
        )

    def _log_call(
        self,
        call_id: str,
        attempt: int,
        system: str,
        user: str,
        response: str,
        latency_ms: int,
        success: bool,
        metadata: dict[str, Any] | None = None,
        *,
        stage: str | None = None,
    ) -> None:
        entry = {
            "trace": trace_metadata(),
            "timestamp": time.time(),
            "stage": stage or "chat",
            "model": self.model,
            "call_id": call_id,
            "attempt": attempt,
            "system_chars": len(system),
            "user_chars": len(user),
            "response_chars": len(response),
            "latency_ms": latency_ms,
            "success": success,
            "metadata": metadata or {},
        }
        # The UI keeps operation summaries; the durable trace counts actual inference attempts.
        if not (stage or "").startswith("chat-round-"):
            self._call_log.append(entry)
        if self.trace_path is not None and stage is not None:
            try:
                self.trace_path.parent.mkdir(parents=True, exist_ok=True)
                with self.trace_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError:
                # Diagnostic I/O must not discard a completed model response.
                logger.warning("Could not persist LLM timing record", exc_info=True)
        logger.info("LLM response %s", json.dumps(entry, ensure_ascii=False))
