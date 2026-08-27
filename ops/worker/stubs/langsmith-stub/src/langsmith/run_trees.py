"""LangSmith 追踪关闭时的惰性占位。"""

from __future__ import annotations

from . import Client, RunTree

_CLIENT: Client | None = None


def get_cached_client() -> Client:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = Client()
    return _CLIENT


__all__ = ["RunTree", "get_cached_client"]
