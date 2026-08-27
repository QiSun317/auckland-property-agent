import { describe, expect, it } from "vitest";

import { cleanDataset } from "../src/dataset";
import { groundAgentResponse } from "../src/grounding";
import { fields, rows } from "./fixtures";

const dataset = cleanDataset({ fields, rows });
const facts = {
  "suburb:Alpha Bay:entry_price": 800000,
  "suburb:Alpha Bay:zone": "北岸",
};

describe("answer grounding gate", () => {
  it("accepts exact tool citations and compatible picks", () => {
    const result = groundAgentResponse({
      on_topic: true,
      answer: "Alpha Bay 的项目入门值是 **$800,000** [suburb:Alpha Bay:entry_price]。",
      picks: [{ name: "Alpha Bay", why: "项目把它归在北岸。" }],
      citations: ["suburb:Alpha Bay:entry_price", "suburb:Alpha Bay:zone"],
      limitations: [],
    }, dataset, facts);
    expect(result.picks[0].name).toBe("Alpha Bay");
    expect(result.evidence).toHaveLength(2);
    expect(result.answer).toBe("Alpha Bay 的项目入门值是 $800,000。");
  });

  it("rejects an uncited number", () => {
    expect(() => groundAgentResponse({
      on_topic: true,
      answer: "Alpha Bay 距离市中心 9km。",
      picks: [],
      citations: ["suburb:Alpha Bay:zone"],
      limitations: [],
    }, dataset, facts)).toThrow(/Uncited numeric claim/);
  });

  it("attaches exact project evidence when the formatter omits a label", () => {
    const result = groundAgentResponse({
      on_topic: true,
      answer: "项目的入门值口径是 25%。",
      picks: [],
      citations: [],
      limitations: [],
    }, dataset, { "constant:entry_price:percentile": 25 });
    expect(result.evidence).toEqual([{ label: "constant:entry_price:percentile", value: 25 }]);
  });

  it("allows an explicit data limitation without invented evidence", () => {
    const result = groundAgentResponse({
      on_topic: true,
      answer: "项目数据没有学校质量字段，因此不能据此比较。",
      picks: [],
      citations: [],
      limitations: ["项目数据不含学校质量"],
    }, dataset, {});
    expect(result.limitations).toHaveLength(1);
  });
});
