import { tool } from "langchain";
import { ToolMessage } from "@langchain/core/messages";
import { z } from "zod";

import {
  FIELD_DESCRIPTIONS,
  NUMERIC_FIELDS,
  TRAITS,
  ZONES,
  aggregateRows,
  factsForRows,
  findSuburb,
  queryRows,
  type Dataset,
  type FactMap,
  type FilterQuery,
} from "./dataset";

const numericFieldSchema = z.enum(NUMERIC_FIELDS);
const zoneSchema = z.enum(ZONES);
const traitSchema = z.enum(TRAITS);

const filterShape = {
  zones: z.array(zoneSchema).max(7).optional().describe("只保留指定项目区域"),
  names: z.array(z.string().min(1).max(80)).max(12).optional().describe("只保留指定 suburb 名称"),
  traits: z.array(traitSchema).max(7).optional().describe("必须同时具备的项目简介标签"),
  numeric: z.array(z.object({
    field: numericFieldSchema,
    min: z.number().finite().optional(),
    max: z.number().finite().optional(),
  })).max(10).optional().describe("数值字段过滤条件，min/max 均为包含边界"),
  bedrooms: z.number().int().min(1).max(5).optional().describe("卧室数，5 代表 5+"),
  minBedroomSharePct: z.number().min(0).max(100).optional().describe("该卧室户型在 suburb 中的最低占比"),
};

const filterSchema = z.object({
  ...filterShape,
  sortBy: numericFieldSchema.optional(),
  direction: z.enum(["asc", "desc"]).optional(),
  limit: z.number().int().min(1).max(20).default(8),
});

function serialise(data: unknown, facts: FactMap): string {
  return JSON.stringify({ data, facts });
}

export function datasetDefinitionFacts(dataset: Dataset): FactMap {
  const facts: FactMap = {
    "constant:dataset:row_count": dataset.rows.length,
    "constant:dataset:scope": "Only the suburb table supplied by the Auckland Property Intelligence project for this request.",
    "constant:entry_price:percentile": 25,
  };
  for (const [field, description] of Object.entries(FIELD_DESCRIPTIONS)) {
    facts[`constant:field:${field}:definition`] = description;
  }
  return facts;
}

export type CalculationOperation = "add" | "subtract" | "multiply" | "divide" | "mean" | "percent_change";

export function calculateProjectNumbers(operation: CalculationOperation, values: number[]): number {
  let value: number;
  if (operation === "add") value = values.reduce((sum, item) => sum + item, 0);
  else if (operation === "subtract") value = values[0] - values[1];
  else if (operation === "multiply") value = values.reduce((product, item) => product * item, 1);
  else if (operation === "divide") {
    if (values[1] === 0) throw new Error("Cannot divide by zero");
    value = values[0] / values[1];
  } else if (operation === "mean") {
    value = values.reduce((sum, item) => sum + item, 0) / values.length;
  } else {
    if (values[0] === 0) throw new Error("Cannot calculate percentage change from zero");
    value = (values[1] - values[0]) / Math.abs(values[0]) * 100;
  }
  return Math.round(value * 100) / 100;
}

export function createDatasetTools(dataset: Dataset) {
  const availableNumbers = new Set<number>();
  const recordResult = (data: unknown, facts: FactMap): string => {
    for (const value of Object.values(facts)) if (typeof value === "number") availableNumbers.add(value);
    return serialise(data, facts);
  };

  const lookupSuburbs = tool(
    async ({ names }) => {
      console.log(JSON.stringify({ event: "agent.tool", tool: "lookup_suburbs" }));
      const found = names.flatMap((name) => {
        const row = findSuburb(dataset, name);
        return row ? [row] : [];
      });
      const foundNames = new Set(found.flatMap((row) => typeof row.name === "string"
        ? [row.name.toLocaleLowerCase("en-NZ")] : []));
      const missing = names.filter((name) => !foundNames.has(name.toLocaleLowerCase("en-NZ")));
      return recordResult({ found, missing }, factsForRows(found));
    },
    {
      name: "lookup_suburbs",
      description: "按项目中的精确 suburb 名称读取全部可用字段。回答某个或多个具体地区的问题前必须调用。",
      schema: z.object({ names: z.array(z.string().min(1).max(80)).min(1).max(12) }),
    },
  );

  const filterSuburbs = tool(
    async (query) => {
      console.log(JSON.stringify({ event: "agent.tool", tool: "filter_suburbs" }));
      const result = queryRows(dataset, query as FilterQuery);
      return recordResult({ total_matches: result.total, rows: result.rows }, factsForRows(result.rows));
    },
    {
      name: "filter_suburbs",
      description: "用项目字段筛选、排序 suburb。适合推荐、排名、预算、距离、收益、涨幅、户型、区域和简介标签问题。",
      schema: filterSchema,
    },
  );

  const summarizeSuburbs = tool(
    async ({ metric, operation, groupBy, ...filter }) => {
      console.log(JSON.stringify({ event: "agent.tool", tool: "summarize_suburbs" }));
      const aggregated = aggregateRows(
        dataset,
        filter as FilterQuery,
        metric,
        operation,
        groupBy === "zone",
      );
      return recordResult(aggregated.data, aggregated.facts);
    },
    {
      name: "summarize_suburbs",
      description: "对筛选后的项目数值字段做 count/mean/median/min/max 统计，可按项目区域分组。",
      schema: z.object({
        ...filterShape,
        metric: numericFieldSchema,
        operation: z.enum(["count", "mean", "median", "min", "max"]),
        groupBy: z.enum(["all", "zone"]).default("all"),
      }),
    },
  );

  const describeDataset = tool(
    async () => {
      console.log(JSON.stringify({ event: "agent.tool", tool: "describe_dataset" }));
      const facts = datasetDefinitionFacts(dataset);
      return recordResult({
        row_count: dataset.rows.length,
        fields: FIELD_DESCRIPTIONS,
        zones: ZONES,
        traits: TRAITS,
        scope: facts["constant:dataset:scope"],
      }, facts);
    },
    {
      name: "describe_dataset",
      description: "解释项目数据覆盖范围、字段定义、区域和简介标签。遇到口径、数据来源能力或可回答范围问题时调用。",
      schema: z.object({}),
    },
  );

  const calculateProjectValues = tool(
    async ({ operation, values }) => {
      console.log(JSON.stringify({ event: "agent.tool", tool: "calculate_project_values" }));
      if (!values.every((value) => availableNumbers.has(value))) {
        throw new Error("Every input must come from an earlier project-data tool result in this turn");
      }
      const rounded = calculateProjectNumbers(operation, values);
      const label = `calculation:${operation}:${values.join(",")}:value`;
      return recordResult({ operation, inputs: values, value: rounded }, { [label]: rounded });
    },
    {
      name: "calculate_project_values",
      description: "对本轮其他项目数据工具已经返回过的数值做受控算术，用于差额、比率、均值或百分比变化。不得输入用户自报或猜测的数字。",
      schema: z.object({
        operation: z.enum(["add", "subtract", "multiply", "divide", "mean", "percent_change"]),
        values: z.array(z.number().finite()).min(2).max(10),
      }).superRefine((input, ctx) => {
        if (["subtract", "divide", "percent_change"].includes(input.operation) && input.values.length !== 2) {
          ctx.addIssue({ code: "custom", message: `${input.operation} requires exactly two values` });
        }
      }),
    },
  );

  return [lookupSuburbs, filterSuburbs, summarizeSuburbs, describeDataset, calculateProjectValues];
}

export function collectToolFacts(messages: unknown[]): FactMap {
  const facts: FactMap = {};
  for (const message of messages) {
    if (!(message instanceof ToolMessage)) continue;
    const content = typeof message.content === "string" ? message.content : "";
    try {
      const parsed = JSON.parse(content) as { facts?: unknown };
      if (!parsed.facts || typeof parsed.facts !== "object" || Array.isArray(parsed.facts)) continue;
      for (const [label, value] of Object.entries(parsed.facts)) {
        if (typeof value === "string" || typeof value === "number" || value === null) facts[label] = value;
      }
    } catch {
      // A malformed tool result is ignored and therefore cannot ground a claim.
    }
  }
  return facts;
}
