"""禁用 LangSmith 网络追踪的兼容函数。"""

from __future__ import annotations


class LangSmithError(Exception):
    pass


def tracing_is_enabled() -> bool:
    return False


def get_tracer_project() -> str:
    return "default"
