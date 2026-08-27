"""禁用远程追踪时供 LangChain Core 导入的最小 LangSmith 兼容层。"""

from __future__ import annotations

from typing import Any

from .run_helpers import get_tracing_context


class Client:
    """仅满足 LangChain 的惰性追踪类型引用。"""

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(f"LangSmith tracing is disabled: {name}")


class RunTree:
    """未启用追踪时不会实例化的占位类型。"""


__all__ = ["Client", "RunTree", "get_tracing_context"]
