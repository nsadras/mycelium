import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Optional, Union

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from mycelium.ollama import ChatResponse, LLM_DEBUG_DIR_ENV, ToolEvent

logger = logging.getLogger(__name__)


class OpenAICompatibleClient:
    def __init__(self, url: str, model: str, temperature: float = 0.1, timeout: int = 120) -> None:
        load_dotenv()
        self.url = url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self._call_log: list[dict] = []

        api_key = os.getenv("MYCELIUM_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = httpx.AsyncClient(timeout=self.timeout, headers=headers)

    def _chat_endpoint(self) -> str:
        if self.url.endswith("/chat/completions"):
            return self.url
        return f"{self.url}/chat/completions"

    async def call(
        self,
        system: str,
        user: str,
        expect_json: Union[bool, dict, type[BaseModel]] = False,
        max_retries: int = 3,
        temperature: Optional[float] = None,
    ) -> Union[str, dict, list]:
        output_format: dict[str, Any] | None = None
        response_model: type[BaseModel] | None = None
        if expect_json:
            if isinstance(expect_json, type) and issubclass(expect_json, BaseModel):
                output_format = self._response_format(expect_json.model_json_schema())
                response_model = expect_json
            elif isinstance(expect_json, dict):
                output_format = self._response_format(expect_json)
            else:
                output_format = {"type": "json_object"}

        response = await self._chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_retries=max_retries,
            temperature=temperature,
            response_format=output_format,
        )

        if not expect_json:
            return response.content
        return self._parse_structured_response(response.content, response_model)

    async def call_messages(
        self,
        messages: list[dict[str, Any]],
        max_retries: int = 3,
        temperature: Optional[float] = None,
        enable_tools: bool = True,
        max_tool_rounds: int = 5,
        tool_result_chars: int = 8000,
        num_ctx: int | None = None,
        num_predict: int | None = None,
        think: bool | None = None,
    ) -> ChatResponse:
        del num_ctx, think

        call_id = str(uuid.uuid4())[:8]
        working_messages = list(messages)
        tool_events: list[ToolEvent] = []
        metadata: dict[str, Any] = {}

        for round_idx in range(max_tool_rounds + 1):
            response = await self._chat_completion(
                messages=working_messages,
                max_retries=max_retries,
                temperature=temperature,
                tools=self._tool_schemas() if enable_tools else None,
                max_tokens=num_predict,
                call_id=call_id,
            )
            metadata = response.metadata
            assistant_message = response.metadata.get("message", {})
            content = response.content.strip()
            tool_calls = assistant_message.get("tool_calls") or []
            working_messages.append(self._assistant_message_for_history(assistant_message, content, tool_calls))

            if not tool_calls:
                return ChatResponse(content=content, tool_events=tool_events, metadata=metadata)
            if round_idx >= max_tool_rounds:
                return ChatResponse(content=content, tool_events=tool_events, metadata=metadata)

            for tool_call in tool_calls:
                tool_call_id = str(tool_call.get("id", ""))
                tool_name, tool_args = self._tool_call_name_args(tool_call)
                result = self._run_tool(tool_name, tool_args)
                truncated = result[:tool_result_chars]
                failed = result.startswith(f"Tool {tool_name} failed:") or result == f"Tool {tool_name} not found"
                tool_events.append(
                    ToolEvent(
                        tool_name=tool_name,
                        arguments=tool_args,
                        result=truncated,
                        failed=failed,
                        truncated=len(result) > len(truncated),
                    )
                )
                working_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": tool_name,
                        "content": truncated,
                    }
                )

        return ChatResponse(content="", tool_events=tool_events, metadata=metadata)

    async def call_structured(
        self,
        system: str,
        user: str,
        schema: Union[dict, type[BaseModel]],
        max_retries: int = 3,
        num_predict: int = 4096,
        dump_success: bool = False,
        debug_label: str | None = None,
    ) -> Union[dict, list]:
        call_id = str(uuid.uuid4())[:8]
        output_schema, response_model = self._structured_format(schema)
        response_format = self._response_format(output_schema)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        for attempt in range(max_retries):
            start_time = time.time()
            try:
                response = await self._chat_completion(
                    messages=messages,
                    max_retries=1,
                    temperature=0.0,
                    response_format=response_format,
                    max_tokens=num_predict,
                    call_id=call_id,
                    attempt=attempt + 1,
                    max_retries_for_log=max_retries,
                    log_success=False,
                )
                content = response.content.strip()
                latency_ms = int((time.time() - start_time) * 1000)
                try:
                    parsed = self._parse_structured_response(content, response_model)
                    self._log_call(call_id, attempt + 1, system, user, content, latency_ms, True, response.metadata)
                    if dump_success:
                        self._dump_structured_success(
                            call_id=call_id,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            endpoint=self._chat_endpoint(),
                            model=self.model,
                            messages=messages,
                            output_format=response_format,
                            options={"temperature": 0.0, "max_tokens": num_predict},
                            assistant_message=response.metadata.get("message", {}),
                            response=content,
                            parsed=parsed,
                            metadata=response.metadata,
                            debug_label=debug_label,
                        )
                    return parsed
                except (json.JSONDecodeError, ValidationError, ValueError) as parse_exc:
                    self._log_call(call_id, attempt + 1, system, user, content, latency_ms, False, response.metadata)
                    debug_dump_path = self._dump_structured_failure(
                        call_id=call_id,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        endpoint=self._chat_endpoint(),
                        model=self.model,
                        messages=messages,
                        output_format=response_format,
                        options={"temperature": 0.0, "max_tokens": num_predict},
                        assistant_message=response.metadata.get("message", {}),
                        response=content,
                        metadata=response.metadata,
                        error=parse_exc,
                    )
                    if attempt == max_retries - 1:
                        debug_text = (
                            f"; debug_dump={debug_dump_path}"
                            if debug_dump_path
                            else f"; debug_dump disabled, set {LLM_DEBUG_DIR_ENV}=.llm-debug"
                        )
                        raise ValueError(
                            f"Failed to parse JSON response from OpenAI-compatible endpoint after {max_retries} attempts"
                            f"{debug_text}: {content}"
                        ) from parse_exc
                    continue
            except httpx.HTTPError:
                if attempt == max_retries - 1:
                    raise

        raise ValueError("Failed to get structured response from OpenAI-compatible endpoint")

    async def _chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        max_retries: int,
        temperature: Optional[float],
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        call_id: str | None = None,
        attempt: int | None = None,
        max_retries_for_log: int | None = None,
        log_success: bool = True,
    ) -> ChatResponse:
        call_id = call_id or str(uuid.uuid4())[:8]
        temp = temperature if temperature is not None else self.temperature
        endpoint = self._chat_endpoint()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
            "stream": False,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if tools is not None:
            payload["tools"] = tools
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        for retry_idx in range(max_retries):
            current_attempt = attempt or retry_idx + 1
            start_time = time.time()
            self._log_request(
                call_id=call_id,
                attempt=current_attempt,
                max_retries=max_retries_for_log or max_retries,
                endpoint=endpoint,
                model=self.model,
                messages=messages,
                output_format=response_format,
                options={k: payload[k] for k in ("temperature", "max_tokens") if k in payload},
            )
            try:
                response = await self.client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
                message = data.get("choices", [{}])[0].get("message", {})
                content = str(message.get("content") or "")
                metadata = self._response_metadata(data, message)
                latency_ms = int((time.time() - start_time) * 1000)
                if log_success:
                    self._log_call(
                        call_id,
                        current_attempt,
                        self._first_message_content(messages, "system"),
                        self._last_message_content(messages, "user"),
                        content,
                        latency_ms,
                        True,
                        metadata,
                    )
                return ChatResponse(content=content, metadata=metadata)
            except httpx.HTTPError as exc:
                latency_ms = int((time.time() - start_time) * 1000)
                self._log_call(
                    call_id,
                    current_attempt,
                    self._first_message_content(messages, "system"),
                    self._last_message_content(messages, "user"),
                    str(exc),
                    latency_ms,
                    False,
                )
                if retry_idx == max_retries - 1:
                    raise

        raise ValueError("Failed to get response from OpenAI-compatible endpoint")

    def _assistant_message_for_history(
        self,
        message: dict[str, Any],
        content: str,
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        assistant_message: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_message["tool_calls"] = tool_calls
        if message.get("reasoning_content"):
            assistant_message["reasoning_content"] = message["reasoning_content"]
        return assistant_message

    def _response_format(self, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "mycelium_response",
                "schema": schema,
                "strict": True,
            },
        }

    def _structured_format(
        self,
        schema: Union[dict, type[BaseModel]],
    ) -> tuple[dict[str, Any], type[BaseModel] | None]:
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            return schema.model_json_schema(), schema
        return schema, None

    def _extract_json(self, content: str) -> Union[dict, list]:
        content = content.strip()
        if content.startswith("```"):
            first_line_end = content.find("\n")
            if first_line_end != -1:
                content = content[first_line_end:].strip()
            if content.endswith("```"):
                content = content[:-3].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"([\[{].*[\]}])", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            raise

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
            return parsed_model.model_dump(exclude_none=True)
        return parsed_model.model_dump(exclude_none=True)

    def _tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for current information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "max_results": {"type": "integer", "default": 3},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "web_fetch",
                    "description": "Fetch the contents of a web page by URL.",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                },
            },
        ]

    def _tool_call_name_args(self, tool_call: Any) -> tuple[str, dict[str, Any]]:
        function = tool_call.get("function") if isinstance(tool_call, dict) else {}
        name = str(function.get("name", ""))
        raw_args = function.get("arguments", {}) or {}
        if isinstance(raw_args, str):
            try:
                return name, dict(json.loads(raw_args))
            except json.JSONDecodeError:
                return name, {}
        return name, dict(raw_args)

    def _run_tool(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        try:
            if tool_name == "web_search":
                from ollama import Client

                return self._format_web_search_result(Client().web_search(**tool_args))
            if tool_name == "web_fetch":
                from ollama import Client

                return self._format_web_fetch_result(Client().web_fetch(**tool_args))
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
                return str(message.get("content", ""))
        return ""

    def _last_message_content(self, messages: list[dict[str, Any]], role: str) -> str:
        for message in reversed(messages):
            if message.get("role") == role:
                return str(message.get("content", ""))
        return ""

    def _response_metadata(self, data: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
        metadata = {
            "id": data.get("id"),
            "object": data.get("object"),
            "created": data.get("created"),
            "usage": data.get("usage", {}),
            "message": message,
        }
        choices = data.get("choices") or []
        if choices:
            metadata["finish_reason"] = choices[0].get("finish_reason")
        return {k: v for k, v in metadata.items() if v is not None}

    def _dump_structured_failure(
        self,
        *,
        call_id: str,
        attempt: int,
        max_retries: int,
        endpoint: str,
        model: str,
        messages: list[dict[str, Any]],
        output_format: dict[str, Any],
        options: dict[str, Any],
        assistant_message: dict[str, Any],
        response: str,
        metadata: dict[str, Any],
        error: Exception,
    ) -> str | None:
        debug_dir = os.getenv(LLM_DEBUG_DIR_ENV)
        if not debug_dir:
            return None

        payload = {
            "call_id": call_id,
            "attempt": attempt,
            "max_retries": max_retries,
            "endpoint": endpoint,
            "model": model,
            "messages": messages,
            "format": output_format,
            "options": options,
            "metadata": metadata,
            "assistant_message": assistant_message,
            "response": response,
            "response_chars": len(response),
            "error_type": type(error).__name__,
            "error": str(error),
        }
        return self._write_debug_dump(payload, f"structured-failure-{call_id}-attempt-{attempt}.json")

    def _dump_structured_success(
        self,
        *,
        call_id: str,
        attempt: int,
        max_retries: int,
        endpoint: str,
        model: str,
        messages: list[dict[str, Any]],
        output_format: dict[str, Any],
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
            "call_id": call_id,
            "attempt": attempt,
            "max_retries": max_retries,
            "endpoint": endpoint,
            "model": model,
            "messages": messages,
            "format": output_format,
            "options": options,
            "metadata": metadata,
            "assistant_message": assistant_message,
            "response": response,
            "response_chars": len(response),
            "parsed": parsed,
            "debug_label": debug_label,
        }
        label = self._debug_filename_part(debug_label or "structured")
        return self._write_debug_dump(payload, f"structured-success-{label}-{call_id}-attempt-{attempt}.json")

    def _write_debug_dump(self, payload: dict[str, Any], filename: str) -> str | None:
        debug_dir = os.getenv(LLM_DEBUG_DIR_ENV)
        if not debug_dir:
            return None
        try:
            path = Path(debug_dir).expanduser()
            path.mkdir(parents=True, exist_ok=True)
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
    ) -> None:
        logger.info(
            "LLM request\n%s",
            json.dumps(
                {
                    "call_id": call_id,
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "endpoint": endpoint,
                    "model": model,
                    "format": output_format,
                    "options": options,
                    "messages": messages,
                },
                indent=2,
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
    ) -> None:
        entry = {
            "timestamp": time.time(),
            "call_id": call_id,
            "attempt": attempt,
            "system": system,
            "user": user,
            "response": response,
            "latency_ms": latency_ms,
            "success": success,
            "metadata": metadata or {},
        }
        self._call_log.append(entry)
        logger.info("LLM response\n%s", json.dumps(entry, indent=2, ensure_ascii=False))
