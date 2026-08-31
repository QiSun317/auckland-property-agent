"""只读 LangChain 项目数据工具。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from dataset import (
    FIELD_DESCRIPTIONS,
    NUMERIC_FIELDS,
    TRAITS,
    ZONES,
    Dataset,
    FactMap,
    aggregate_rows,
    calculate_project_numbers,
    dataset_definition_facts,
    facts_for_rows,
    find_suburb,
    query_rows,
)
from planning import (
    PlanningRetriever,
    explicit_plan_scope,
    facts_for_plan_hits,
    planning_scope_facts,
    planning_zones_for_tool,
)

NumericField = Literal[
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
]
Zone = Literal["北岸", "西区", "中区", "东区", "南区", "北部乡村", "海岛"]
Trait = Literal[
    "coastal",
    "bush",
    "rural",
    "volcanic",
    "town_centre",
    "historic",
    "industrial",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NumericConstraint(StrictModel):
    field: NumericField
    min: float | None = None
    max: float | None = None


class FilterFields(StrictModel):
    zones: list[Zone] | None = Field(default=None, max_length=7)
    names: list[str] | None = Field(default=None, max_length=12)
    traits: list[Trait] | None = Field(default=None, max_length=7)
    numeric: list[NumericConstraint] | None = Field(default=None, max_length=10)
    bedrooms: int | None = Field(default=None, ge=1, le=5)
    minBedroomSharePct: float | None = Field(default=None, ge=0, le=100)


class LookupInput(StrictModel):
    names: list[str] = Field(min_length=1, max_length=12)


class FilterInput(FilterFields):
    sortBy: NumericField | None = None
    direction: Literal["asc", "desc"] | None = None
    limit: int = Field(default=8, ge=1, le=20)


class SummaryInput(FilterFields):
    metric: NumericField
    operation: Literal["count", "mean", "median", "min", "max"]
    groupBy: Literal["all", "zone"] = "all"


class DescribeInput(StrictModel):
    pass


class CalculationInput(StrictModel):
    operation: Literal[
        "add", "subtract", "multiply", "divide", "mean", "percent_change"
    ]
    values: list[float] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def exact_binary_arity(self) -> CalculationInput:
        if (
            self.operation in {"subtract", "divide", "percent_change"}
            and len(self.values) != 2
        ):
            raise ValueError(f"{self.operation} requires exactly two values")
        return self


class PlanSearchInput(StrictModel):
    question: str = Field(min_length=2, max_length=800)
    limit: int = Field(default=5, ge=1, le=8)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _filters(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _jsonable(value)
        for key, value in values.items()
        if value is not None
        and key
        in {
            "zones",
            "names",
            "traits",
            "numeric",
            "bedrooms",
            "minBedroomSharePct",
        }
    }


@dataclass
class ToolSession:
    dataset: Dataset
    max_calls: int = 8
    call_count: int = 0
    available_numbers: set[float] = field(default_factory=set)
    seen_calls: set[str] = field(default_factory=set)

    def begin(self, name: str, payload: dict[str, Any]) -> None:
        fingerprint = json.dumps(
            {"tool": name, "input": _jsonable(payload)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if fingerprint in self.seen_calls:
            raise ValueError(
                "A tool cannot be repeated with the same arguments in one turn"
            )
        if self.call_count >= self.max_calls:
            raise ValueError("Project-data tool call limit reached")
        self.seen_calls.add(fingerprint)
        self.call_count += 1
        print(json.dumps({"event": "agent.tool", "tool": name}, separators=(",", ":")))

    def result(self, data: Any, facts: FactMap) -> str:
        for value in facts.values():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self.available_numbers.add(float(value))
        return json.dumps(
            {"data": data, "facts": facts},
            ensure_ascii=False,
            separators=(",", ":"),
        )


def create_dataset_tools(
    dataset: Dataset,
    planning_retriever: PlanningRetriever | None = None,
    *,
    current_question: str = "",
) -> tuple[list[StructuredTool], ToolSession]:
    session = ToolSession(dataset)

    async def lookup_suburbs(names: list[str]) -> str:
        session.begin("lookup_suburbs", {"names": names})
        found = [
            row for name in names if (row := find_suburb(dataset, name)) is not None
        ]
        found_names = {
            row["name"].casefold() for row in found if isinstance(row.get("name"), str)
        }
        missing = [name for name in names if name.casefold() not in found_names]
        return session.result(
            {"found": found, "missing": missing}, facts_for_rows(found)
        )

    async def filter_suburbs(
        zones: list[Zone] | None = None,
        names: list[str] | None = None,
        traits: list[Trait] | None = None,
        numeric: list[NumericConstraint] | None = None,
        bedrooms: int | None = None,
        minBedroomSharePct: float | None = None,
        sortBy: NumericField | None = None,
        direction: Literal["asc", "desc"] | None = None,
        limit: int = 8,
    ) -> str:
        values = locals()
        query = {
            **_filters(values),
            "sortBy": sortBy,
            "direction": direction,
            "limit": limit,
        }
        session.begin("filter_suburbs", query)
        result = query_rows(dataset, query)
        return session.result(
            {"total_matches": result["total"], "rows": result["rows"]},
            facts_for_rows(result["rows"]),
        )

    async def summarize_suburbs(
        metric: NumericField,
        operation: Literal["count", "mean", "median", "min", "max"],
        groupBy: Literal["all", "zone"] = "all",
        zones: list[Zone] | None = None,
        names: list[str] | None = None,
        traits: list[Trait] | None = None,
        numeric: list[NumericConstraint] | None = None,
        bedrooms: int | None = None,
        minBedroomSharePct: float | None = None,
    ) -> str:
        values = locals()
        filters = _filters(values)
        payload = {
            **filters,
            "metric": metric,
            "operation": operation,
            "groupBy": groupBy,
        }
        session.begin("summarize_suburbs", payload)
        aggregated = aggregate_rows(
            dataset, filters, metric, operation, groupBy == "zone"
        )
        return session.result(aggregated["data"], aggregated["facts"])

    async def describe_dataset() -> str:
        session.begin("describe_dataset", {})
        facts = dataset_definition_facts(dataset)
        return session.result(
            {
                "row_count": len(dataset.rows),
                "fields": FIELD_DESCRIPTIONS,
                "zones": ZONES,
                "traits": TRAITS,
                "scope": facts["constant:dataset:scope"],
            },
            facts,
        )

    async def calculate_project_values(
        operation: Literal[
            "add", "subtract", "multiply", "divide", "mean", "percent_change"
        ],
        values: list[float],
    ) -> str:
        payload = {"operation": operation, "values": values}
        session.begin("calculate_project_values", payload)
        if not all(float(value) in session.available_numbers for value in values):
            raise ValueError(
                "Every input must come from an earlier project-data tool result in this turn"
            )
        rounded = calculate_project_numbers(operation, values)
        label = (
            f"calculation:{operation}:{','.join(str(value) for value in values)}:value"
        )
        return session.result(
            {"operation": operation, "inputs": values, "value": rounded},
            {label: rounded},
        )

    async def describe_unitary_plan_scope() -> str:
        session.begin("describe_unitary_plan_scope", {})
        facts = planning_scope_facts()
        return session.result(
            {
                "source": facts["constant:plan:source"],
                "exact_zone_required": facts[
                    "constant:plan:exact_zone_required"
                ],
                "planning_zones": planning_zones_for_tool(),
            },
            facts,
        )

    async def search_unitary_plan(question: str, limit: int = 5) -> str:
        if planning_retriever is None:
            raise RuntimeError("Unitary Plan retrieval is unavailable")
        scope = explicit_plan_scope(current_question)
        if scope is None:
            raise ValueError(
                "The current user question does not state an exact planning zone "
                "name, zone code, or chapter. Do not infer one from a suburb; call "
                "describe_unitary_plan_scope and ask the user for the exact zone."
            )
        payload = {"question": question, "limit": limit, "scope": scope.as_dict()}
        session.begin("search_unitary_plan", payload)
        hits = await planning_retriever.search(question, scope.chapters, limit)
        facts = facts_for_plan_hits(hits)
        facts[f"constant:plan:scope:{scope.name}"] = ", ".join(scope.chapters)
        return session.result(
            {
                "scope": scope.as_dict(),
                "hits": [
                    {
                        "clause_key": hit.get("clause_key") or hit.get("id"),
                        "chapter": hit.get("chapter"),
                        "clause_id": hit.get("clause_id"),
                        "title": hit.get("title"),
                        "score": hit.get("score"),
                        "fact_prefix": (
                            f"plan:{hit.get('clause_key') or hit.get('id')}"
                        ),
                    }
                    for hit in hits
                ],
            },
            facts,
        )

    tools = [
        StructuredTool.from_function(
            coroutine=lookup_suburbs,
            name="lookup_suburbs",
            description="按项目中的精确 suburb 名称读取全部可用字段。回答某个或多个具体地区的问题前必须调用。",
            args_schema=LookupInput,
        ),
        StructuredTool.from_function(
            coroutine=filter_suburbs,
            name="filter_suburbs",
            description="用项目字段筛选、排序 suburb。适合推荐、排名、预算、距离、收益、涨幅、户型、区域和简介标签问题。",
            args_schema=FilterInput,
        ),
        StructuredTool.from_function(
            coroutine=summarize_suburbs,
            name="summarize_suburbs",
            description="对筛选后的项目数值字段做 count/mean/median/min/max 统计，可按项目区域分组。",
            args_schema=SummaryInput,
        ),
        StructuredTool.from_function(
            coroutine=describe_dataset,
            name="describe_dataset",
            description="解释项目数据覆盖范围、字段定义、区域和简介标签。遇到口径、数据来源能力或可回答范围问题时调用。",
            args_schema=DescribeInput,
        ),
        StructuredTool.from_function(
            coroutine=calculate_project_values,
            name="calculate_project_values",
            description="对本轮其他项目数据工具已经返回过的数值做受控算术，用于差额、比率、均值或百分比变化。不得输入用户自报或猜测的数字。",
            args_schema=CalculationInput,
        ),
    ]
    if planning_retriever is not None:
        tools.extend(
            [
                StructuredTool.from_function(
                    coroutine=describe_unitary_plan_scope,
                    name="describe_unitary_plan_scope",
                    description=(
                        "解释项目中的 Auckland Unitary Plan 资料、可接受的精确规划区名称/代码/章节，"
                        "以及为什么不能从 suburb 推断单个房产的规划区。当前问题没有明确规划区时调用。"
                    ),
                    args_schema=DescribeInput,
                ),
                StructuredTool.from_function(
                    coroutine=search_unitary_plan,
                    name="search_unitary_plan",
                    description=(
                        "只在当前用户问题逐字给出精确 Unitary Plan 规划区名称、zone code 或 H/E 章节时，"
                        "在该范围内检索项目保存的规划条款。服务端会从当前问题独立验证范围；"
                        "绝不能根据 suburb、历史或模型常识猜规划区。"
                    ),
                    args_schema=PlanSearchInput,
                ),
            ]
        )
    return tools, session


def collect_tool_facts(messages: list[Any]) -> FactMap:
    facts: FactMap = {}
    for message in messages:
        if not isinstance(message, ToolMessage) or not isinstance(message.content, str):
            continue
        try:
            parsed = json.loads(message.content)
        except (TypeError, ValueError):
            continue
        raw_facts = parsed.get("facts") if isinstance(parsed, dict) else None
        if not isinstance(raw_facts, dict):
            continue
        for label, value in raw_facts.items():
            if isinstance(value, (str, int, float)) or value is None:
                facts[str(label)] = value
    return facts


assert set(NUMERIC_FIELDS) == set(NumericField.__args__)
assert set(ZONES) == set(Zone.__args__)
assert set(TRAITS) == set(Trait.__args__)
