import { describe, expect, it } from "vitest";

import { aggregateRows, cleanDataset, queryRows } from "../src/dataset";
import { calculateProjectNumbers, datasetDefinitionFacts } from "../src/tools";
import { fields, rows } from "./fixtures";

describe("project dataset tools", () => {
  it("allow-lists fields, normalises zones and filters deterministically", () => {
    const dataset = cleanDataset({ fields: [...fields, "secret"], rows });
    const result = queryRows(dataset, {
      numeric: [{ field: "entry_price", max: 700000 }],
      sortBy: "gross_yield_pct",
      direction: "desc",
      limit: 5,
    });
    expect(dataset.rows).toHaveLength(2);
    expect(dataset.rows[0].zone).toBe("北岸");
    expect(result.total).toBe(1);
    expect(result.rows[0].name).toBe("Beta Hills");
    expect("secret" in result.rows[0]).toBe(false);
  });

  it("returns traceable aggregate facts", () => {
    const result = aggregateRows(cleanDataset({ fields, rows }), {}, "entry_price", "median", false);
    expect(result.data).toEqual([{ group: "all", matched: 2, value: 725000, suburb: null }]);
    expect(result.facts["summary:all:entry_price:median:value"]).toBe(725000);
  });

  it("reuses field definitions as grounding facts", () => {
    const facts = datasetDefinitionFacts(cleanDataset({ fields, rows }));
    expect(facts["constant:entry_price:percentile"]).toBe(25);
    expect(facts["constant:field:entry_price:definition"]).toContain("25th-percentile");
  });

  it("computes reusable derived project values deterministically", () => {
    expect(calculateProjectNumbers("subtract", [800000, 650000])).toBe(150000);
    expect(calculateProjectNumbers("percent_change", [650000, 800000])).toBe(23.08);
    expect(() => calculateProjectNumbers("divide", [1, 0])).toThrow(/zero/);
  });
});
