"""项目 suburb 数据的清洗、查询、聚合与可追溯事实生成。"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import median
from typing import Any

CANONICAL_FIELDS = (
    "name",
    "zone",
    "entry_price",
    "median_cv",
    "avg_value",
    "cbd_km",
    "change_1y_pct",
    "long_term_growth_pct",
    "gross_yield_pct",
    "median_rent_wk",
    "days_to_sell",
    "sold_12m",
    "population",
    "renter_pct",
    "own_section_pct",
    "median_section_m2",
    "bedroom_mix_1_to_5_pct",
    "traits_from_intro",
    "about",
)

NUMERIC_FIELDS = (
    "entry_price",
    "median_cv",
    "avg_value",
    "cbd_km",
    "change_1y_pct",
    "long_term_growth_pct",
    "gross_yield_pct",
    "median_rent_wk",
    "days_to_sell",
    "sold_12m",
    "population",
    "renter_pct",
    "own_section_pct",
    "median_section_m2",
)

ZONES = ("北岸", "西区", "中区", "东区", "南区", "北部乡村", "海岛")
TRAITS = (
    "coastal",
    "bush",
    "rural",
    "volcanic",
    "town_centre",
    "historic",
    "industrial",
)

FIELD_DESCRIPTIONS = {
    "name": "LINZ suburb/locality name",
    "zone": "project-defined Auckland area: 北岸, 西区, 中区, 东区, 南区, 北部乡村 or 海岛",
    "entry_price": "25th-percentile 2024 council CV; one quarter of rating units are below it; not a sale price",
    "median_cv": "median 2024 Auckland Council capital value across rating units; not a sale price",
    "avg_value": "average automated house value from the project's market source; not a sale price",
    "cbd_km": "straight-line kilometres from the suburb centroid to Auckland CBD",
    "change_1y_pct": "one-year change in the market source's average house value, percent",
    "long_term_growth_pct": "long-term annualised growth in average house value, percent",
    "gross_yield_pct": "estimated gross rental yield, percent",
    "median_rent_wk": "median weekly asking rent in NZD",
    "days_to_sell": "median days to sell",
    "sold_12m": "market-source sales count in the latest 12 months",
    "population": "resident population attached to the suburb in the project dataset",
    "renter_pct": "share of occupied dwellings rented, percent",
    "own_section_pct": "share of homes on their own section, percent",
    "median_section_m2": "median land area in square metres where available",
    "bedroom_mix_1_to_5_pct": "slash-separated shares for 1, 2, 3, 4 and 5+ bedrooms",
    "traits_from_intro": "conservative traits extracted from the project's Wikipedia introduction",
    "about": "English Wikipedia opening paragraph stored by the project; use only what this text explicitly supports",
}

ZONE_ALIASES = {
    "north shore": "北岸",
    "west": "西区",
    "central": "中区",
    "east": "东区",
    "south": "南区",
    "rodney / rural north": "北部乡村",
    "gulf islands": "海岛",
}

Cell = str | int | float | None
SuburbRecord = dict[str, Cell]
FactMap = dict[str, Cell]


@dataclass(frozen=True)
class Dataset:
    rows: list[SuburbRecord]
    by_name: dict[str, SuburbRecord]


def _clean_string(value: Any, maximum: int) -> str | None:
    if value is None:
        return None
    result = str(value).strip()[:maximum]
    return result or None


def _clean_cell(field: str, value: Any) -> Cell:
    if value is None:
        return None
    if field in NUMERIC_FIELDS:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return value if isfinite(float(value)) else None
    text = _clean_string(value, 700 if field == "about" else 120)
    if field == "zone" and text:
        return ZONE_ALIASES.get(text.casefold(), text)
    return text


def clean_dataset(raw_input: Any) -> Dataset:
    body = raw_input if isinstance(raw_input, dict) else {}
    raw_fields = body.get("fields")
    fields = raw_fields[:30] if isinstance(raw_fields, list) else []
    indices: dict[str, int] = {}
    for index, value in enumerate(fields):
        field = str(value)[:40]
        if field in CANONICAL_FIELDS and field not in indices:
            indices[field] = index

    rows: list[SuburbRecord] = []
    by_name: dict[str, SuburbRecord] = {}
    raw_rows = body.get("rows")
    for raw in raw_rows[:400] if isinstance(raw_rows, list) else []:
        if not isinstance(raw, list):
            continue
        record = {
            field: _clean_cell(
                field,
                raw[indices[field]]
                if field in indices and indices[field] < len(raw)
                else None,
            )
            for field in CANONICAL_FIELDS
        }
        name = record["name"]
        if not isinstance(name, str):
            continue
        key = name.casefold()
        if key in by_name:
            continue
        rows.append(record)
        by_name[key] = record
    return Dataset(rows=rows, by_name=by_name)


def find_suburb(dataset: Dataset, name: str) -> SuburbRecord | None:
    return dataset.by_name.get(name.strip().casefold())


def _numeric_value(row: SuburbRecord, field: str) -> float | int | None:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if isfinite(float(value)) else None


def _bedroom_share(row: SuburbRecord, bedrooms: Any) -> float | None:
    raw = row.get("bedroom_mix_1_to_5_pct")
    if not isinstance(raw, str) or not isinstance(bedrooms, (int, float)):
        return None
    try:
        shares = [float(value) for value in raw.split("/")]
    except ValueError:
        return None
    index = max(0, min(4, round(bedrooms) - 1))
    return shares[index] if index < len(shares) and isfinite(shares[index]) else None


def _normalise_constraint(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "model_dump"):
        return raw.model_dump(exclude_none=True)
    return {}


def _matches(row: SuburbRecord, query: dict[str, Any]) -> bool:
    zones = query.get("zones") or []
    if zones and row.get("zone") not in zones:
        return False
    names = query.get("names") or []
    if names:
        allowed = {str(name).casefold() for name in names}
        if (
            not isinstance(row.get("name"), str)
            or row["name"].casefold() not in allowed
        ):
            return False
    traits = query.get("traits") or []
    if traits:
        row_traits = set(str(row.get("traits_from_intro") or "").split("/"))
        if not all(trait in row_traits for trait in traits):
            return False
    for raw_constraint in query.get("numeric") or []:
        constraint = _normalise_constraint(raw_constraint)
        field = constraint.get("field")
        value = _numeric_value(row, field) if field in NUMERIC_FIELDS else None
        if value is None:
            return False
        if constraint.get("min") is not None and value < constraint["min"]:
            return False
        if constraint.get("max") is not None and value > constraint["max"]:
            return False
    if query.get("bedrooms") is not None:
        share = _bedroom_share(row, query["bedrooms"])
        if share is None or share < (query.get("minBedroomSharePct") or 0):
            return False
    return True


def filtered_rows(
    dataset: Dataset, query: dict[str, Any] | None = None
) -> list[SuburbRecord]:
    filters = query or {}
    return [row for row in dataset.rows if _matches(row, filters)]


def query_rows(dataset: Dataset, query: dict[str, Any]) -> dict[str, Any]:
    matched = filtered_rows(dataset, query)
    sort_by = query.get("sortBy")
    if sort_by in NUMERIC_FIELDS:
        reverse = query.get("direction") != "asc"
        present = [row for row in matched if _numeric_value(row, sort_by) is not None]
        missing = [row for row in matched if _numeric_value(row, sort_by) is None]
        present.sort(
            key=lambda row: float(_numeric_value(row, sort_by)), reverse=reverse
        )
        matched = present + missing
    limit = min(20, max(1, int(query.get("limit") or 8)))
    return {"total": len(matched), "rows": matched[:limit]}


def facts_for_rows(rows: list[SuburbRecord]) -> FactMap:
    facts: FactMap = {}
    for row in rows:
        name = row.get("name")
        if not isinstance(name, str):
            continue
        for field in CANONICAL_FIELDS:
            if row.get(field) is not None:
                facts[f"suburb:{name}:{field}"] = row[field]
    return facts


def _rounded(value: float) -> float:
    return round(value + 0.0, 2)


def aggregate_rows(
    dataset: Dataset,
    filters: dict[str, Any],
    metric: str,
    operation: str,
    group_by_zone: bool,
) -> dict[str, Any]:
    rows = filtered_rows(dataset, filters)
    groups: dict[str, list[SuburbRecord]] = {}
    if group_by_zone:
        for row in rows:
            zone = row.get("zone")
            if isinstance(zone, str):
                groups.setdefault(zone, []).append(row)
    else:
        groups["all"] = rows

    facts: FactMap = {}
    data: list[dict[str, Cell]] = []
    for group, group_rows in groups.items():
        values = [
            (row, value)
            for row in group_rows
            if (value := _numeric_value(row, metric)) is not None
        ]
        value: Cell = None
        suburb: Cell = None
        if values:
            if operation == "count":
                value = len(values)
            elif operation == "mean":
                value = _rounded(sum(item[1] for item in values) / len(values))
            elif operation == "median":
                value = _rounded(float(median(item[1] for item in values)))
            else:
                selected = (
                    min(values, key=lambda item: item[1])
                    if operation == "min"
                    else max(values, key=lambda item: item[1])
                )
                suburb, value = selected[0].get("name"), selected[1]
        prefix = f"summary:{group}:{metric}:{operation}"
        facts[f"{prefix}:matched"] = len(group_rows)
        if value is not None:
            facts[f"{prefix}:value"] = value
        if suburb is not None:
            facts[f"{prefix}:suburb"] = suburb
        data.append(
            {
                "group": group,
                "matched": len(group_rows),
                "value": value,
                "suburb": suburb,
            }
        )
    return {"data": data, "facts": facts}


def dataset_definition_facts(dataset: Dataset) -> FactMap:
    facts: FactMap = {
        "constant:dataset:row_count": len(dataset.rows),
        "constant:dataset:scope": "Only the suburb table supplied by the Auckland Property Intelligence project for this request.",
        "constant:entry_price:percentile": 25,
    }
    for field, description in FIELD_DESCRIPTIONS.items():
        facts[f"constant:field:{field}:definition"] = description
    return facts


def calculate_project_numbers(operation: str, values: list[float]) -> float:
    if len(values) < 2:
        raise ValueError("At least two values are required")
    if operation == "add":
        value = sum(values)
    elif operation == "subtract":
        if len(values) != 2:
            raise ValueError("subtract requires exactly two values")
        value = values[0] - values[1]
    elif operation == "multiply":
        value = 1.0
        for item in values:
            value *= item
    elif operation == "divide":
        if len(values) != 2:
            raise ValueError("divide requires exactly two values")
        if values[1] == 0:
            raise ValueError("Cannot divide by zero")
        value = values[0] / values[1]
    elif operation == "mean":
        value = sum(values) / len(values)
    elif operation == "percent_change":
        if len(values) != 2:
            raise ValueError("percent_change requires exactly two values")
        if values[0] == 0:
            raise ValueError("Cannot calculate percentage change from zero")
        value = (values[1] - values[0]) / abs(values[0]) * 100
    else:
        raise ValueError(f"Unknown calculation operation: {operation}")
    return _rounded(value)
