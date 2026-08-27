"""Cloudflare Python Worker HTTP 入口。"""

from __future__ import annotations

import json
import time
from typing import Any

from js import Object
from pyodide.ffi import to_js as _to_js
from workers import Response, WorkerEntrypoint

from agent import run_dataset_agent
from boundary import (
    MAX_BODY_BYTES,
    MAX_CONTEXT_CHARS,
    MAX_TEXT_CHARS,
    clean_history,
    clean_text,
    cors_headers,
    is_obviously_off_topic,
    safe_error,
)
from dataset import clean_dataset


def _to_js_object(value: dict[str, Any]) -> Any:
    return _to_js(value, dict_converter=Object.fromEntries)


def _json_response(body: Any, status: int, headers: dict[str, str]) -> Response:
    return Response.json(body, status=status, headers=headers)


async def read_bounded_json(request: Any) -> dict[str, Any]:
    raw_content_length = request.headers.get("content-length")
    try:
        content_length = int(str(raw_content_length)) if raw_content_length else 0
    except ValueError:
        content_length = 0
    if content_length > MAX_BODY_BYTES:
        raise ValueError("request too large")
    if request.body is None:
        raise ValueError("empty body")

    reader = request.body.getReader()
    chunks: list[bytes] = []
    size = 0
    while True:
        result = await reader.read()
        if bool(result.done):
            break
        value = result.value
        chunk = bytes(value.to_py())
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            await reader.cancel()
            raise ValueError("request too large")
        chunks.append(chunk)
    try:
        parsed = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("bad json") from error
    if not isinstance(parsed, dict):
        raise TypeError("bad json")
    return parsed


def _env_text(env: Any, name: str, default: str = "") -> str:
    value = getattr(env, name, None)
    return str(value) if value is not None else default


class Default(WorkerEntrypoint):
    """项目唯一公网模型入口。"""

    async def fetch(self, request: Any) -> Response:
        origin_value = request.headers.get("origin")
        origin = str(origin_value) if origin_value is not None else None
        headers = cors_headers(origin, _env_text(self.env, "ALLOWED_ORIGIN", "*"))
        method = str(request.method)
        if method == "OPTIONS":
            return Response(None, status=204, headers=headers)
        if method != "POST":
            return _json_response({"error": "POST only"}, 405, headers)
        if headers["access-control-allow-origin"] == "null":
            return _json_response({"error": "origin not allowed"}, 403, headers)

        try:
            body = await read_bounded_json(request)
        except Exception as error:  # noqa: BLE001 - HTTP boundary returns a safe 400.
            return _json_response({"error": safe_error(error)}, 400, headers)
        text = clean_text(body.get("text"), MAX_TEXT_CHARS)
        context = clean_text(body.get("context"), MAX_CONTEXT_CHARS)
        if not text:
            return _json_response({"error": "empty request"}, 400, headers)
        if is_obviously_off_topic(text):
            return _json_response(
                {
                    "on_topic": False,
                    "answer": "这个问题超出了本项目的奥克兰住宅数据范围。",
                    "picks": [],
                },
                200,
                headers,
            )

        ip_value = request.headers.get("cf-connecting-ip")
        ip = str(ip_value) if ip_value is not None else "anonymous"
        limit_result = await self.env.RATE_LIMIT.limit(_to_js_object({"key": ip}))
        if not bool(limit_result.success):
            return _json_response(
                {"error": "rate limited, try again shortly"},
                429,
                headers,
            )
        api_key = _env_text(self.env, "GEMINI_API_KEY")
        if not api_key:
            return _json_response({"error": "proxy not configured"}, 500, headers)

        dataset = clean_dataset(body)
        if not dataset.rows:
            return _json_response({"error": "no project data supplied"}, 400, headers)

        started = time.monotonic()
        try:
            result = await run_dataset_agent(
                api_key,
                _env_text(self.env, "MODEL", "gemini-3.5-flash-lite"),
                dataset,
                text=text,
                context=context,
                history=clean_history(body.get("history")),
            )
            print(
                json.dumps(
                    {
                        "event": "agent.complete",
                        "rows": len(dataset.rows),
                        "picks": len(result["picks"]),
                        "evidence": len(result["evidence"]),
                        "ms": round((time.monotonic() - started) * 1000),
                    },
                    separators=(",", ":"),
                )
            )
            return _json_response(result, 200, headers)
        except Exception as error:  # noqa: BLE001 - model failures become a safe 502.
            print(
                json.dumps(
                    {
                        "event": "agent.error",
                        "error": safe_error(error),
                        "ms": round((time.monotonic() - started) * 1000),
                    },
                    separators=(",", ":"),
                )
            )
            return _json_response(
                {"error": "grounded model response unavailable"},
                502,
                headers,
            )
