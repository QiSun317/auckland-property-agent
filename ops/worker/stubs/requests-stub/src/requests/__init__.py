"""LangChain Core 错误格式化所需的最小 requests 类型。"""

from __future__ import annotations

from typing import Any


class HTTPError(Exception):
    pass


class Response:
    status_code = 0
    text = ""

    def json(self) -> Any:
        return {}
