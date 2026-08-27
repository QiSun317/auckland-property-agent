"""HTTP 边界可复用的输入、CORS、话题与错误清洗规则。"""

from __future__ import annotations

import re
from typing import Any

MAX_BODY_BYTES = 750_000
MAX_TEXT_CHARS = 1_200
MAX_CONTEXT_CHARS = 2_400
MAX_HISTORY_TURNS = 8

PROPERTY_WORDS = (
    "房",
    "屋",
    "住",
    "买",
    "購",
    "租",
    "预算",
    "預算",
    "地段",
    "区",
    "區",
    "郊区",
    "通勤",
    "投资",
    "回报",
    "公寓",
    "地块",
    "房价",
    "估价",
    "奥克兰",
    "奧克蘭",
    "数据",
    "比较",
    "推荐",
    "suburb",
    "house",
    "home",
    "apartment",
    "property",
    "buy",
    "rent",
    "budget",
    "yield",
    "invest",
    "auckland",
    "area",
    "commute",
    "section",
    "land",
    "bedroom",
    "value",
    "price",
    "dataset",
    "compare",
)
EXPLICIT_OFF_TOPIC = (
    re.compile(
        r"写(一?[首篇段]|个|下).*(诗|故事|代码|程序|作文|歌词)|翻译|食谱|菜谱|笑话|简历"
    ),
    re.compile(
        r"\b(write|translate|code|program|debug|script|poem|story|joke|recipe|essay|resume)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"python|javascript|typescript|sql|正则|regex|天气|新闻|股票|怎么做菜",
        re.IGNORECASE,
    ),
)


def cors_headers(origin: str | None, allowed: str) -> dict[str, str]:
    allow_list = [item.strip() for item in allowed.split(",") if item.strip()]
    permitted = allowed == "*" or bool(origin and origin in allow_list)
    return {
        "access-control-allow-origin": (origin or "*") if permitted else "null",
        "access-control-allow-headers": "content-type",
        "access-control-allow-methods": "POST, OPTIONS",
        "access-control-max-age": "86400",
        "vary": "Origin",
    }


def clean_text(value: Any, maximum: int) -> str:
    return value.strip()[:maximum] if isinstance(value, str) else ""


def clean_history(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value[-MAX_HISTORY_TURNS:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = clean_text(item.get("content"), 800)
        if content:
            result.append({"role": item["role"], "content": content})
    return result


def is_obviously_off_topic(text: str) -> bool:
    lowered = text.casefold()
    has_property_signal = any(word in lowered for word in PROPERTY_WORDS) or bool(
        re.search(r"\$|\d", lowered)
    )
    return not has_property_signal and any(
        pattern.search(text) for pattern in EXPLICIT_OFF_TOPIC
    )


def safe_error(error: Exception) -> str:
    message = str(error) or "unknown error"
    message = re.sub(r"AIza[0-9A-Za-z_-]{10,}", "[redacted]", message)
    message = re.sub(
        r"key=[^&\s]+",
        "key=[redacted]",
        message,
        flags=re.IGNORECASE,
    )
    return message[:300]
