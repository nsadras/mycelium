import json
import logging
import os
import time
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union, Optional

from dotenv import load_dotenv
from ollama import AsyncClient, Client, RequestError, ResponseError, web_fetch, web_search
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)
LLM_DEBUG_DIR_ENV = "MYCELIUM_LLM_DEBUG_DIR"


@dataclass
class ToolEvent:
    tool_name: str
    arguments: dict[str, Any]
    result: str
    failed: bool = False
    truncated: bool = False


@dataclass
class ChatResponse:
    content: str
    tool_events: list[ToolEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class OllamaClient:
    def __init__(
        self,
        url: str,
        model: str,
        temperature: float = 0.1,
        timeout: int = 120,
        context_window_tokens: int = 32768,
    ) -> None:
        load_dotenv()
        self.url = url.rstrip('/')
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.context_window_tokens = context_window_tokens
        self.client = AsyncClient(host=self.url, timeout=self.timeout)
        self.web_client = Client()
        self._call_log: list[dict] = []

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

    async def call(
        self,
        system: str,
        user: str,
        expect_json: Union[bool, dict, type[BaseModel]] = False,
        max_retries: int = 3,
        temperature: Optional[float] = None
    ) -> Union[str, dict, list]:
        """
        Makes a chat completion call to Ollama.
        If expect_json is a dict, it is passed as a JSON Schema to constrain output.
        """
        call_id = str(uuid.uuid4())[:8]
        sys_prompt = system
            
        temp = temperature if temperature is not None else self.temperature
            
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user},
        ]
        options = {"temperature": temp}
        output_format: Union[str, dict[str, Any], None] = None
        response_model: type[BaseModel] | None = None
        
        if expect_json:
            if isinstance(expect_json, type) and issubclass(expect_json, BaseModel):
                response_model = expect_json
                output_format = expect_json.model_json_schema()
            elif isinstance(expect_json, dict):
                output_format = expect_json
            else:
                output_format = "json"

        endpoint = f"{self.url}/api/chat"
        
        for attempt in range(max_retries):
            start_time = time.time()
            self._log_request(
                call_id=call_id,
                attempt=attempt + 1,
                max_retries=max_retries,
                endpoint=endpoint,
                model=self.model,
                messages=messages,
                output_format=output_format,
                options=options,
            )
            try:
                response = await self.client.chat(
                    model=self.model,
                    messages=messages,
                    stream=False,
                    format=output_format,
                    options=options,
                )
                content = self._response_content(response)
                
                latency_ms = int((time.time() - start_time) * 1000)
                
                if expect_json:
                    try:
                        parsed = self._parse_structured_response(content, response_model)
                        self._log_call(call_id, attempt + 1, sys_prompt, user, content, latency_ms, True)
                        return parsed
                    except (json.JSONDecodeError, ValidationError, ValueError):
                        self._log_call(call_id, attempt + 1, sys_prompt, user, content, latency_ms, False)
                        if attempt == max_retries - 1:
                            raise ValueError(f"Failed to parse JSON response from Ollama after {max_retries} attempts: {content}")
                        continue # Retry
                        
                self._log_call(call_id, attempt + 1, sys_prompt, user, content, latency_ms, True)
                return content
                
            except (RequestError, ResponseError) as e:
                latency_ms = int((time.time() - start_time) * 1000)
                self._log_call(call_id, attempt + 1, sys_prompt, user, str(e), latency_ms, False)
                if attempt == max_retries - 1:
                    raise

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
        """
        Makes a chat completion call using an explicit message history.
        """
        call_id = str(uuid.uuid4())[:8]
        temp = temperature if temperature is not None else self.temperature
        options = {"temperature": temp}
        if num_ctx is not None:
            options["num_ctx"] = num_ctx
        if num_predict is not None:
            options["num_predict"] = num_predict
        endpoint = f"{self.url}/api/chat"
        working_messages = list(messages)
        tool_events: list[ToolEvent] = []

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
                    messages=working_messages,
                    options=options,
                    enable_tools=enable_tools,
                    max_tool_rounds=max_tool_rounds,
                    tool_result_chars=tool_result_chars,
                    tool_events=tool_events,
                    think=think,
                )
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
                return ChatResponse(content=content, tool_events=tool_events, metadata=metadata)

            except (RequestError, ResponseError) as e:
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
                if attempt == max_retries - 1:
                    raise

        raise ValueError("Failed to get chat response from Ollama")

    async def _chat_with_optional_tools(
        self,
        call_id: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any],
        enable_tools: bool,
        max_tool_rounds: int,
        tool_result_chars: int,
        tool_events: list[ToolEvent],
        think: bool | None,
    ) -> tuple[str, dict[str, Any]]:
        tools = [web_search, web_fetch] if enable_tools else None
        think_enabled = think if think is not None else bool(enable_tools)
        for round_idx in range(max_tool_rounds + 1):
            response = await self.client.chat(
                model=self.model,
                messages=messages,
                tools=tools,
                think=think_enabled,
                stream=False,
                format=None,
                options=options,
            )
            metadata = self._response_metadata(response)
            assistant_message = self._assistant_message_dict(response)
            content = assistant_message.get("content", "").strip()
            tool_calls = assistant_message.get("tool_calls", [])
            if content:
                logger.info("LLM assistant content during tool loop\n%s", content)
            messages.append(assistant_message)
            if not tool_calls:
                return content, metadata
            if round_idx >= max_tool_rounds:
                return content, metadata
            for tool_call in tool_calls:
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
                logger.info(
                    "LLM tool call\n%s",
                    json.dumps(
                        {
                            "call_id": call_id,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "result": truncated,
                            "truncated": len(result) > len(truncated),
                        },
                        indent=2,
                        ensure_ascii=False,
                        default=str,
                    ),
                )
                messages.append({"role": "tool", "content": truncated, "tool_name": tool_name})
        return "", {}

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

    def _run_tool(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        try:
            if tool_name == "web_search":
                return self._format_web_search_result(self.web_client.web_search(**tool_args))
            if tool_name == "web_fetch":
                return self._format_web_fetch_result(self.web_client.web_fetch(**tool_args))
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

    def _response_content(self, response: Any) -> str:
        message = getattr(response, "message", None)
        if isinstance(message, dict):
            return str(message.get("content", "")).strip()
        content = getattr(message, "content", "")
        return str(content).strip()

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
            return parsed_model.model_dump(exclude_none=True)
        return parsed_model.model_dump(exclude_none=True)
                    
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
        """
        Uses Ollama's chat API with native JSON Schema support.
        """
        call_id = str(uuid.uuid4())[:8]
        output_format, response_model = self._structured_format(schema)
        options = {
            "temperature": 0.0,
            "num_ctx": self.context_window_tokens,
            "num_predict": num_predict,
        }
        endpoint = f"{self.url}/api/chat"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        for attempt in range(max_retries):
            start_time = time.time()
            self._log_request(
                call_id=call_id,
                attempt=attempt + 1,
                max_retries=max_retries,
                endpoint=endpoint,
                model=self.model,
                messages=messages,
                output_format=output_format,
                options=options,
            )
            try:
                response = await self.client.chat(
                    model=self.model,
                    messages=messages,
                    think=False,
                    stream=False,
                    format=output_format,
                    options=options,
                )
                assistant_message = self._assistant_message_dict(response)
                content = str(assistant_message.get("content", "")).strip()
                metadata = self._response_metadata(response)
                latency_ms = int((time.time() - start_time) * 1000)

                try:
                    parsed = self._parse_structured_response(content, response_model)
                    self._log_call(call_id, attempt + 1, system, user, content, latency_ms, True, metadata)
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
                    self._log_call(call_id, attempt + 1, system, user, content, latency_ms, False, metadata)
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
                    if attempt == max_retries - 1:
                        metadata_text = f"; metadata={metadata}" if metadata else ""
                        debug_text = (
                            f"; debug_dump={debug_dump_path}"
                            if debug_dump_path
                            else f"; debug_dump disabled, set {LLM_DEBUG_DIR_ENV}=.llm-debug"
                        )
                        raise ValueError(
                            f"Failed to parse JSON response from Ollama after {max_retries} attempts"
                            f"{metadata_text}{debug_text}: {content}"
                        )
                    continue

            except (RequestError, ResponseError) as e:
                latency_ms = int((time.time() - start_time) * 1000)
                self._log_call(call_id, attempt + 1, system, user, str(e), latency_ms, False)
                if attempt == max_retries - 1:
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

    def _generate_response_content(self, response: Any) -> str:
        content = getattr(response, "response", "")
        if content:
            return str(content).strip()
        if isinstance(response, dict):
            return str(response.get("response", "")).strip()
        return ""

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
                    "system": system,
                    "prompt": prompt,
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
