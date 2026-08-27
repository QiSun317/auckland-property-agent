"""将模型结构化输出约束到本轮项目工具提供的事实。"""

from __future__ import annotations

import math
import re
from typing import Any

from dataset import ZONES, Cell, Dataset, FactMap, find_suburb

WANTS = {
    "invest",
    "quiet",
    "land",
    "apartment",
    "commute",
    "coastal",
    "growth",
    "liquid",
    "cheap",
}

AGENT_RESPONSE_SCHEMA = {
    "title": "grounded_response",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "on_topic": {
            "type": "boolean",
            "description": "是否属于本项目可服务的奥克兰 suburb/住宅数据问题",
        },
        "answer": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000,
            "description": "直接、自然地回答用户，语言跟随用户；不能写项目数据之外的事实",
        },
        "picks": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 100},
                    "why": {"type": "string", "minLength": 1, "maxLength": 700},
                },
                "required": ["name", "why"],
            },
        },
        "criteria": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "budget": {"type": ["number", "null"]},
                "beds": {"type": ["integer", "null"], "minimum": 1, "maximum": 5},
                "maxKm": {"type": ["number", "null"], "minimum": 0},
                "zones": {
                    "type": "array",
                    "maxItems": 7,
                    "items": {"type": "string", "enum": list(ZONES)},
                },
                "wants": {
                    "type": "array",
                    "maxItems": 9,
                    "items": {"type": "string", "enum": sorted(WANTS)},
                },
            },
        },
        "citations": {
            "type": "array",
            "maxItems": 40,
            "items": {"type": "string", "minLength": 1, "maxLength": 180},
            "description": "逐字复制所用工具 facts 中的 label；值由服务端按 label 读取，不得杜撰",
        },
        "limitations": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string", "minLength": 1, "maxLength": 500},
        },
    },
    "required": ["on_topic", "answer", "picks", "citations", "limitations"],
}

_NUMBER_PATTERN = re.compile(
    r"(?:NZ\$|\$)?\s*(-?\d[\d,]*(?:\.\d+)?)\s*(m²|sqm|km|%|k|m|万|百万)?",
    re.IGNORECASE,
)


def _numeric_claims(text: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for match in _NUMBER_PATTERN.finditer(text):
        value = float(match.group(1).replace(",", ""))
        if not math.isfinite(value):
            continue
        suffix = (match.group(2) or "").casefold()
        if suffix == "k":
            value *= 1_000
        elif suffix in {"m", "百万"}:
            value *= 1_000_000
        elif suffix == "万":
            value *= 10_000
        raw = match.group(0).strip()
        has_currency = "NZ$" in raw.upper() or "$" in raw
        significant = has_currency or bool(suffix) or abs(value) >= 100
        likely_year = not suffix and 1900 <= value <= 2100
        if significant and not likely_year:
            claims.append({"raw": raw, "value": value})
    return claims


def _value_supports_claim(value: Cell, claim: dict[str, Any]) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        tolerance = max(0.011, abs(float(value)) * 0.001)
        return abs(float(value) - claim["value"]) <= tolerance
    if not isinstance(value, str):
        return False
    return any(
        _value_supports_claim(candidate["value"], claim)
        for candidate in _numeric_claims(value)
    )


def _reader_text(text: str) -> str:
    text = re.sub(r"\[(?:suburb|summary|constant):[^\]\n]+\]", "", text)
    text = text.replace("**", "").replace(chr(96), "")
    text = re.sub(r"[ \t]+([，。,.!?！？])", r"\1", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def _strings(value: Any, maximum: int, item_maximum: int) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError("Invalid response string list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > item_maximum:
            raise ValueError("Invalid response string")
        result.append(item)
    return result


def _validate_criteria(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError("Invalid criteria")
    allowed = {"budget", "beds", "maxKm", "zones", "wants"}
    if set(value) - allowed:
        raise ValueError("Unknown criteria field")
    result: dict[str, Any] = {}
    for field in ("budget", "maxKm"):
        item = value.get(field)
        if item is not None:
            if (
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not math.isfinite(float(item))
            ):
                raise ValueError(f"Invalid {field}")
            if field == "maxKm" and item < 0:
                raise ValueError("Invalid maxKm")
        if field in value:
            result[field] = item
    beds = value.get("beds")
    if beds is not None and (
        isinstance(beds, bool) or not isinstance(beds, int) or not 1 <= beds <= 5
    ):
        raise ValueError("Invalid beds")
    if "beds" in value:
        result["beds"] = beds
    zones = value.get("zones", [])
    if (
        not isinstance(zones, list)
        or len(zones) > 7
        or any(zone not in ZONES for zone in zones)
    ):
        raise ValueError("Invalid zones")
    wants = value.get("wants", [])
    if (
        not isinstance(wants, list)
        or len(wants) > 9
        or any(want not in WANTS for want in wants)
    ):
        raise ValueError("Invalid wants")
    if "zones" in value:
        result["zones"] = zones
    if "wants" in value:
        result["wants"] = wants
    return result


def _validate_response(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError("Agent response must be an object")
    on_topic = raw.get("on_topic")
    answer = raw.get("answer")
    if not isinstance(on_topic, bool):
        raise TypeError("Invalid on_topic")
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 4000:
        raise ValueError("Invalid answer")
    raw_picks = raw.get("picks", [])
    if not isinstance(raw_picks, list) or len(raw_picks) > 6:
        raise ValueError("Invalid picks")
    picks: list[dict[str, str]] = []
    for pick in raw_picks:
        if not isinstance(pick, dict) or set(pick) != {"name", "why"}:
            raise ValueError("Invalid pick")
        name, why = pick["name"], pick["why"]
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ValueError("Invalid pick name")
        if not isinstance(why, str) or not why.strip() or len(why) > 700:
            raise ValueError("Invalid pick reason")
        picks.append({"name": name, "why": why})
    return {
        "on_topic": on_topic,
        "answer": answer,
        "picks": picks,
        "criteria": _validate_criteria(raw.get("criteria")),
        "citations": _strings(raw.get("citations", []), 40, 180),
        "limitations": _strings(raw.get("limitations", []), 5, 500),
    }


def ground_agent_response(
    raw: Any, dataset: Dataset, tool_facts: FactMap
) -> dict[str, Any]:
    response = _validate_response(raw)
    answer = _reader_text(response["answer"])
    evidence: list[dict[str, Cell]] = []

    def add_evidence(label: str) -> None:
        if not any(item["label"] == label for item in evidence):
            evidence.append({"label": label, "value": tool_facts[label]})

    for label in response["citations"]:
        if label not in tool_facts:
            raise ValueError(f"Citation was not returned by a tool: {label}")
        add_evidence(label)

    seen_names: set[str] = set()
    picks: list[dict[str, str]] = []
    for pick in response["picks"]:
        key = pick["name"].casefold()
        if not find_suburb(dataset, pick["name"]) or key in seen_names:
            raise ValueError("Response contained an unknown or duplicate suburb")
        seen_names.add(key)
        picks.append({"name": pick["name"], "why": _reader_text(pick["why"])})
    for pick in picks:
        if not any(
            item["label"].startswith(f"suburb:{pick['name']}:") for item in evidence
        ):
            label = next(
                (
                    key
                    for key in tool_facts
                    if key.startswith(f"suburb:{pick['name']}:")
                ),
                None,
            )
            if label is None:
                raise ValueError(f"Pick was not returned by a tool: {pick['name']}")
            add_evidence(label)

    claim_texts = [answer, *(pick["why"] for pick in picks)]
    for claim in (claim for text in claim_texts for claim in _numeric_claims(text)):
        if any(_value_supports_claim(item["value"], claim) for item in evidence):
            continue
        match = next(
            (
                label
                for label, value in tool_facts.items()
                if _value_supports_claim(value, claim)
            ),
            None,
        )
        if match:
            add_evidence(match)

    if response["on_topic"] and not evidence and not response["limitations"]:
        raise ValueError(
            "On-topic response had neither tool evidence nor an explicit limitation"
        )
    cited_values = [item["value"] for item in evidence]
    for text in claim_texts:
        for claim in _numeric_claims(text):
            if not any(_value_supports_claim(value, claim) for value in cited_values):
                raise ValueError(f"Uncited numeric claim: {claim['raw']}")

    result = {
        "on_topic": response["on_topic"],
        "answer": answer,
        "lead": answer,
        "picks": picks,
        "evidence": evidence,
        "limitations": response["limitations"],
    }
    if response["criteria"] is not None:
        result["criteria"] = response["criteria"]
    return result
