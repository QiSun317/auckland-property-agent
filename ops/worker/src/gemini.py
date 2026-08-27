"""面向 Cloudflare Python Workers 的 LangChain Gemini ChatModel。"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field, PrivateAttr

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    texts: list[str] = []
    for block in content:
        if isinstance(block, str):
            texts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            texts.append(block["text"])
    return "\n".join(texts)


def _tool_result(content: Any) -> Any:
    text = _message_text(content)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, (dict, list, str, int, float, bool)) or parsed is None:
            return parsed
    except (TypeError, ValueError):
        pass
    return text


def _schema_copy(schema: dict[str, Any]) -> dict[str, Any]:
    """生成可序列化副本，并展开本地 JSON Schema 引用。"""

    cloned = json.loads(json.dumps(schema))
    definitions = cloned.get("$defs") or cloned.get("definitions") or {}

    def expand(value: Any) -> Any:
        if isinstance(value, list):
            return [expand(item) for item in value]
        if not isinstance(value, dict):
            return value
        if isinstance(value.get("$ref"), str):
            name = value["$ref"].split("/")[-1]
            target = definitions.get(name)
            if isinstance(target, dict):
                merged = {
                    **target,
                    **{key: item for key, item in value.items() if key != "$ref"},
                }
                return expand(merged)
        return {
            key: expand(item)
            for key, item in value.items()
            if key not in {"$defs", "definitions"}
        }

    return expand(cloned)


def _tool_declaration(tool: dict[str, Any] | type | Any | BaseTool) -> dict[str, Any]:
    converted = convert_to_openai_tool(tool)
    function = converted.get("function", converted)
    declaration = {
        "name": function["name"],
        "description": function.get("description") or function["name"],
    }
    parameters = function.get("parameters")
    if isinstance(parameters, dict):
        declaration["parametersJsonSchema"] = _schema_copy(parameters)
    return declaration


def _messages_to_gemini(
    messages: list[BaseMessage],
) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    tool_names: dict[str, str] = {}
    pending_tool_parts: list[dict[str, Any]] = []

    def flush_tool_parts() -> None:
        if pending_tool_parts:
            contents.append({"role": "user", "parts": [*pending_tool_parts]})
            pending_tool_parts.clear()

    for message in messages:
        if isinstance(message, SystemMessage):
            flush_tool_parts()
            text = _message_text(message.content)
            if text:
                system_parts.append(text)
            continue
        if isinstance(message, AIMessage):
            flush_tool_parts()
            for call in message.tool_calls:
                if call.get("id") and call.get("name"):
                    tool_names[str(call["id"])] = str(call["name"])
            raw_parts = message.additional_kwargs.get("gemini_parts")
            if isinstance(raw_parts, list) and raw_parts:
                parts = raw_parts
            else:
                parts = []
                text = _message_text(message.content)
                if text:
                    parts.append({"text": text})
                for call in message.tool_calls:
                    function_call = {
                        "id": call.get("id"),
                        "name": call["name"],
                        "args": call.get("args") or {},
                    }
                    parts.append({"functionCall": function_call})
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue
        if isinstance(message, ToolMessage):
            name = (
                message.name
                or tool_names.get(str(message.tool_call_id))
                or "unknown_tool"
            )
            function_response = {
                "id": message.tool_call_id,
                "name": name,
                "response": {"result": _tool_result(message.content)},
            }
            pending_tool_parts.append({"functionResponse": function_response})
            continue

        flush_tool_parts()
        text = _message_text(message.content)
        if text:
            contents.append({"role": "user", "parts": [{"text": text}]})

    flush_tool_parts()
    return "\n\n".join(system_parts), contents


def _tool_config(tool_choice: Any) -> dict[str, Any] | None:
    if tool_choice is None:
        return None
    mode = "AUTO"
    allowed: list[str] | None = None
    if isinstance(tool_choice, str):
        lowered = tool_choice.casefold()
        if lowered in {"any", "required"}:
            mode = "ANY"
        elif lowered == "none":
            mode = "NONE"
        elif lowered != "auto":
            mode = "ANY"
            allowed = [tool_choice]
    elif isinstance(tool_choice, dict):
        function = tool_choice.get("function")
        if isinstance(function, dict) and function.get("name"):
            mode = "ANY"
            allowed = [str(function["name"])]
    config: dict[str, Any] = {"mode": mode}
    if allowed:
        config["allowedFunctionNames"] = allowed
    return {"functionCallingConfig": config}


class GeminiWorkerChatModel(BaseChatModel):
    """通过异步 HTTP 调用 Gemini，同时实现 LangChain 原生工具调用。"""

    api_key: str = Field(repr=False)
    model_name: str
    temperature: float = 0.0
    max_output_tokens: int = 2_500
    timeout_seconds: float = 45.0
    max_model_calls: int = 5
    _model_calls: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "cloudflare-python-gemini"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name, "temperature": self.temperature}

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Any:
        declarations = [_tool_declaration(tool) for tool in tools]
        return self.bind(
            gemini_tools=declarations,
            gemini_tool_choice=tool_choice,
            **kwargs,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError("GeminiWorkerChatModel is async-only")

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        from js import Object, fetch
        from pyodide.ffi import to_js

        endpoint = f"{GEMINI_API_BASE}/{self.model_name}:generateContent"
        headers = {
            "content-type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        options = to_js(
            {
                "method": "POST",
                "headers": headers,
                "body": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            },
            dict_converter=Object.fromEntries,
        )
        last_status = 0
        last_error: Exception | None = None
        last_detail = ""
        for attempt in range(2):
            try:
                response = await asyncio.wait_for(
                    fetch(endpoint, options), timeout=self.timeout_seconds
                )
                last_status = int(response.status)
                response_text = str(await response.text())
                if last_status < 400:
                    data = json.loads(response_text)
                    if not isinstance(data, dict):
                        raise RuntimeError("Gemini returned a non-object response")
                    return data
                try:
                    error_body = json.loads(response_text)
                    error_value = (
                        error_body.get("error", {}).get("message")
                        if isinstance(error_body, dict)
                        else None
                    )
                    if isinstance(error_value, str):
                        last_detail = error_value[:300]
                except (TypeError, ValueError):
                    last_detail = ""
                if last_status not in {429, 500, 502, 503, 504} or attempt == 1:
                    break
            except Exception as error:  # noqa: BLE001 - retry one transient fetch failure.
                last_error = error
                if attempt == 1:
                    break
            if attempt == 0:
                await asyncio.sleep(0.25)
        detail = f"status {last_status}" if last_status else "network error"
        if last_detail:
            detail = f"{detail}: {last_detail}"
        raise RuntimeError(f"Gemini request failed with {detail}") from last_error

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        gemini_tools: list[dict[str, Any]] | None = None,
        gemini_tool_choice: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self._model_calls >= self.max_model_calls:
            raise RuntimeError("Agent model call limit reached")
        self._model_calls += 1

        system_instruction, contents = _messages_to_gemini(messages)
        if not contents:
            raise ValueError("Gemini requires at least one non-system message")
        generation_config: dict[str, Any] = {
            "temperature": self.temperature,
            "maxOutputTokens": self.max_output_tokens,
        }
        if stop:
            generation_config["stopSequences"] = stop
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if gemini_tools:
            payload["tools"] = [{"functionDeclarations": gemini_tools}]
            config = _tool_config(gemini_tool_choice)
            if config:
                payload["toolConfig"] = config

        data = await self._post(payload)
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            reason = data.get("promptFeedback", {}).get("blockReason", "no candidate")
            raise RuntimeError(f"Gemini returned no candidate: {reason}")
        candidate = candidates[0]
        content = candidate.get("content") if isinstance(candidate, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            parts = []

        texts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            if isinstance(part.get("text"), str) and not part.get("thought"):
                texts.append(part["text"])
            function_call = part.get("functionCall")
            if not isinstance(function_call, dict) or not function_call.get("name"):
                continue
            call_id = str(function_call.get("id") or f"call_{uuid.uuid4().hex}")
            args = function_call.get("args")
            tool_calls.append(
                {
                    "name": str(function_call["name"]),
                    "args": args if isinstance(args, dict) else {},
                    "id": call_id,
                    "type": "tool_call",
                }
            )

        message = AIMessage(
            content="\n".join(texts),
            tool_calls=tool_calls,
            additional_kwargs={"gemini_parts": parts},
            response_metadata={
                "finish_reason": candidate.get("finishReason")
                if isinstance(candidate, dict)
                else None,
                "model_version": data.get("modelVersion"),
            },
        )
        usage = data.get("usageMetadata")
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output={"usage": usage if isinstance(usage, dict) else {}},
        )
