"""LangChain Core 所需的无网络追踪上下文。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_DEFAULT_CONTEXT = {
    "parent": None,
    "project_name": None,
    "tags": None,
    "metadata": None,
    "enabled": False,
    "client": None,
}
_CONTEXT: ContextVar[dict[str, Any]] = ContextVar(
    "disabled_langsmith_context",
    default=_DEFAULT_CONTEXT,
)


def get_tracing_context() -> dict[str, Any]:
    return {**_DEFAULT_CONTEXT, **_CONTEXT.get()}


def _set_tracing_context(context: dict[str, Any]) -> None:
    _CONTEXT.set({**_DEFAULT_CONTEXT, **context, "enabled": False})
