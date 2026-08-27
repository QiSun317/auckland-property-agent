import { z } from "zod";

import { ZONES, findSuburb, type Cell, type Dataset, type FactMap } from "./dataset";

const wantsSchema = z.enum([
  "invest", "quiet", "land", "apartment", "commute", "coastal", "growth", "liquid", "cheap",
]);

const criteriaSchema = z.object({
  budget: z.number().finite().nullable().optional(),
  beds: z.number().int().min(1).max(5).nullable().optional(),
  maxKm: z.number().finite().nonnegative().nullable().optional(),
  zones: z.array(z.enum(ZONES)).max(7).optional(),
  wants: z.array(wantsSchema).max(9).optional(),
});

export const agentResponseSchema = z.object({
  on_topic: z.boolean().describe("是否属于本项目可服务的奥克兰 suburb/住宅数据问题"),
  answer: z.string().min(1).max(4000).describe("直接、自然地回答用户，语言跟随用户；不能写项目数据之外的事实"),
  picks: z.array(z.object({
    name: z.string().min(1).max(100),
    why: z.string().min(1).max(700),
  })).max(6).default([]),
  criteria: criteriaSchema.optional(),
  citations: z.array(z.string().min(1).max(180)).max(40).default([])
    .describe("逐字复制所用工具 facts 中的 label；值由服务端按 label 读取，不得杜撰"),
  limitations: z.array(z.string().min(1).max(500)).max(5).default([]),
});

export type AgentResponse = z.infer<typeof agentResponseSchema>;

export interface GroundedResponse {
  on_topic: boolean;
  answer: string;
  lead: string;
  picks: Array<{ name: string; why: string }>;
  criteria?: z.infer<typeof criteriaSchema>;
  evidence: Array<{ label: string; value: Cell }>;
  limitations: string[];
}

interface NumericClaim {
  raw: string;
  value: number;
}

function numericClaims(text: string): NumericClaim[] {
  const claims: NumericClaim[] = [];
  const pattern = /(?:NZ\$|\$)?\s*(-?\d[\d,]*(?:\.\d+)?)\s*(m²|sqm|km|%|k|m|万|百万)?/gi;
  for (const match of text.matchAll(pattern)) {
    const rawNumber = match[1].replaceAll(",", "");
    let value = Number(rawNumber);
    if (!Number.isFinite(value)) continue;
    const suffix = (match[2] ?? "").toLowerCase();
    if (suffix === "k") value *= 1_000;
    if (suffix === "m" || suffix === "百万") value *= 1_000_000;
    if (suffix === "万") value *= 10_000;
    const hasCurrency = /NZ\$|\$/.test(match[0]);
    const isSignificant = hasCurrency || suffix !== "" || Math.abs(value) >= 100;
    const isLikelyYear = suffix === "" && value >= 1900 && value <= 2100;
    if (isSignificant && !isLikelyYear) claims.push({ raw: match[0].trim(), value });
  }
  return claims;
}

function valueSupportsClaim(value: Cell, claim: NumericClaim): boolean {
  if (typeof value === "number") {
    const tolerance = Math.max(0.011, Math.abs(value) * 0.001);
    return Math.abs(value - claim.value) <= tolerance;
  }
  if (typeof value !== "string") return false;
  return numericClaims(value).some((candidate) => {
    const tolerance = Math.max(0.011, Math.abs(candidate.value) * 0.001);
    return Math.abs(candidate.value - claim.value) <= tolerance;
  });
}

function assertNumericClaimsAreCited(text: string, citedValues: Cell[]): void {
  for (const claim of numericClaims(text)) {
    if (!citedValues.some((value) => valueSupportsClaim(value, claim))) {
      throw new Error(`Uncited numeric claim: ${claim.raw}`);
    }
  }
}

function readerText(text: string): string {
  return text
    .replace(/\[(?:suburb|summary|constant):[^\]\n]+\]/g, "")
    .replace(/\*\*|`/g, "")
    .replace(/[ \t]+([，。,.!?！？])/g, "$1")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

export function groundAgentResponse(raw: unknown, dataset: Dataset, toolFacts: FactMap): GroundedResponse {
  const response = agentResponseSchema.parse(raw);
  const answer = readerText(response.answer);
  const evidence: Array<{ label: string; value: Cell }> = [];
  const addEvidence = (label: string) => {
    if (evidence.some((item) => item.label === label)) return;
    evidence.push({ label, value: toolFacts[label] });
  };
  for (const label of response.citations) {
    if (!(label in toolFacts)) {
      throw new Error(`Citation was not returned by a tool: ${label}`);
    }
    addEvidence(label);
  }
  const picks = response.picks.filter((pick, index, all) => {
    return Boolean(findSuburb(dataset, pick.name)) && all.findIndex((item) => item.name === pick.name) === index;
  }).map((pick) => ({ ...pick, why: readerText(pick.why) }));

  if (picks.length !== response.picks.length) throw new Error("Response contained an unknown or duplicate suburb");
  for (const pick of picks) {
    if (!evidence.some((item) => item.label.startsWith(`suburb:${pick.name}:`))) {
      const label = Object.keys(toolFacts).find((key) => key.startsWith(`suburb:${pick.name}:`));
      if (!label) throw new Error(`Pick was not returned by a tool: ${pick.name}`);
      addEvidence(label);
    }
  }

  // Citation transcription is not a task the model needs to be trusted with.
  // When a written number exactly matches a project fact, attach that fact in
  // code; a number with no matching tool/project fact remains a hard failure.
  const claimTexts = [answer, ...picks.map((pick) => pick.why)];
  for (const claim of claimTexts.flatMap(numericClaims)) {
    if (evidence.some((item) => valueSupportsClaim(item.value, claim))) continue;
    const match = Object.entries(toolFacts).find(([, value]) => valueSupportsClaim(value, claim));
    if (match) addEvidence(match[0]);
  }

  if (response.on_topic && !evidence.length && !response.limitations.length) {
    throw new Error("On-topic response had neither tool evidence nor an explicit limitation");
  }
  const citedValues = evidence.map((citation) => citation.value);
  assertNumericClaimsAreCited(answer, citedValues);
  for (const pick of picks) assertNumericClaimsAreCited(pick.why, citedValues);

  return {
    on_topic: response.on_topic,
    answer,
    lead: answer,
    picks,
    criteria: response.criteria,
    evidence,
    limitations: response.limitations,
  };
}
