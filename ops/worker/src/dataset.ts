export const CANONICAL_FIELDS = [
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
] as const;

export const NUMERIC_FIELDS = [
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
] as const;

export const ZONES = ["北岸", "西区", "中区", "东区", "南区", "北部乡村", "海岛"] as const;
export const TRAITS = [
  "coastal",
  "bush",
  "rural",
  "volcanic",
  "town_centre",
  "historic",
  "industrial",
] as const;

export const FIELD_DESCRIPTIONS: Record<Field, string> = {
  name: "LINZ suburb/locality name",
  zone: "project-defined Auckland area: 北岸, 西区, 中区, 东区, 南区, 北部乡村 or 海岛",
  entry_price: "25th-percentile 2024 council CV; one quarter of rating units are below it; not a sale price",
  median_cv: "median 2024 Auckland Council capital value across rating units; not a sale price",
  avg_value: "average automated house value from the project's market source; not a sale price",
  cbd_km: "straight-line kilometres from the suburb centroid to Auckland CBD",
  change_1y_pct: "one-year change in the market source's average house value, percent",
  long_term_growth_pct: "long-term annualised growth in average house value, percent",
  gross_yield_pct: "estimated gross rental yield, percent",
  median_rent_wk: "median weekly asking rent in NZD",
  days_to_sell: "median days to sell",
  sold_12m: "market-source sales count in the latest 12 months",
  population: "resident population attached to the suburb in the project dataset",
  renter_pct: "share of occupied dwellings rented, percent",
  own_section_pct: "share of homes on their own section, percent",
  median_section_m2: "median land area in square metres where available",
  bedroom_mix_1_to_5_pct: "slash-separated shares for 1, 2, 3, 4 and 5+ bedrooms",
  traits_from_intro: "conservative traits extracted from the project's Wikipedia introduction",
  about: "English Wikipedia opening paragraph stored by the project; use only what this text explicitly supports",
};

export type Field = (typeof CANONICAL_FIELDS)[number];
export type NumericField = (typeof NUMERIC_FIELDS)[number];
export type Zone = (typeof ZONES)[number];
export type Trait = (typeof TRAITS)[number];
export type Cell = string | number | null;
export type SuburbRecord = Record<Field, Cell>;
export type FactMap = Record<string, Cell>;

export interface Dataset {
  rows: SuburbRecord[];
  byName: Map<string, SuburbRecord>;
}

export interface NumericConstraint {
  field: NumericField;
  min?: number;
  max?: number;
}

export interface DatasetFilter {
  zones?: Zone[];
  names?: string[];
  traits?: Trait[];
  numeric?: NumericConstraint[];
  bedrooms?: number;
  minBedroomSharePct?: number;
}

export interface FilterQuery extends DatasetFilter {
  sortBy?: NumericField;
  direction?: "asc" | "desc";
  limit?: number;
}

const NUMERIC_SET = new Set<string>(NUMERIC_FIELDS);
const FIELD_SET = new Set<string>(CANONICAL_FIELDS);
const ZONE_ALIASES: Record<string, Zone> = {
  "north shore": "北岸",
  west: "西区",
  central: "中区",
  east: "东区",
  south: "南区",
  "rodney / rural north": "北部乡村",
  "gulf islands": "海岛",
};

function cleanString(value: unknown, max: number): string | null {
  if (value === null || value === undefined) return null;
  const result = String(value).trim().slice(0, max);
  return result || null;
}

function cleanCell(field: Field, value: unknown): Cell {
  if (value === null || value === undefined) return null;
  if (NUMERIC_SET.has(field)) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  }
  const text = cleanString(value, field === "about" ? 700 : 120);
  if (field === "zone" && text) return ZONE_ALIASES[text.toLowerCase()] ?? text;
  return text;
}

export function cleanDataset(input: unknown): Dataset {
  const body = input && typeof input === "object" ? input as Record<string, unknown> : {};
  const rawFields = Array.isArray(body.fields) ? body.fields.slice(0, 30) : [];
  const indices = new Map<Field, number>();
  rawFields.forEach((value, index) => {
    const field = String(value).slice(0, 40);
    if (FIELD_SET.has(field) && !indices.has(field as Field)) indices.set(field as Field, index);
  });

  const rows: SuburbRecord[] = [];
  const byName = new Map<string, SuburbRecord>();
  const rawRows = Array.isArray(body.rows) ? body.rows.slice(0, 400) : [];
  for (const raw of rawRows) {
    if (!Array.isArray(raw)) continue;
    const record = Object.fromEntries(CANONICAL_FIELDS.map((field) => {
      const index = indices.get(field);
      return [field, cleanCell(field, index === undefined ? null : raw[index])];
    })) as SuburbRecord;
    if (typeof record.name !== "string") continue;
    const key = record.name.toLocaleLowerCase("en-NZ");
    if (byName.has(key)) continue;
    rows.push(record);
    byName.set(key, record);
  }
  return { rows, byName };
}

export function findSuburb(dataset: Dataset, name: string): SuburbRecord | undefined {
  return dataset.byName.get(name.trim().toLocaleLowerCase("en-NZ"));
}

function numericValue(row: SuburbRecord, field: NumericField): number | null {
  const value = row[field];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function bedroomShare(row: SuburbRecord, bedrooms: number): number | null {
  if (typeof row.bedroom_mix_1_to_5_pct !== "string") return null;
  const shares = row.bedroom_mix_1_to_5_pct.split("/").map(Number);
  const index = Math.max(0, Math.min(4, Math.round(bedrooms) - 1));
  return Number.isFinite(shares[index]) ? shares[index] : null;
}

function matches(row: SuburbRecord, filter: DatasetFilter): boolean {
  if (filter.zones?.length && (!row.zone || !filter.zones.includes(row.zone as Zone))) return false;
  if (filter.names?.length) {
    const names = new Set(filter.names.map((name) => name.toLocaleLowerCase("en-NZ")));
    if (typeof row.name !== "string" || !names.has(row.name.toLocaleLowerCase("en-NZ"))) return false;
  }
  if (filter.traits?.length) {
    const traits = new Set(typeof row.traits_from_intro === "string"
      ? row.traits_from_intro.split("/") : []);
    if (!filter.traits.every((trait) => traits.has(trait))) return false;
  }
  for (const constraint of filter.numeric ?? []) {
    const value = numericValue(row, constraint.field);
    if (value === null) return false;
    if (constraint.min !== undefined && value < constraint.min) return false;
    if (constraint.max !== undefined && value > constraint.max) return false;
  }
  if (filter.bedrooms !== undefined) {
    const share = bedroomShare(row, filter.bedrooms);
    if (share === null || share < (filter.minBedroomSharePct ?? 0)) return false;
  }
  return true;
}

export function filteredRows(dataset: Dataset, filter: DatasetFilter = {}): SuburbRecord[] {
  return dataset.rows.filter((row) => matches(row, filter));
}

export function queryRows(dataset: Dataset, query: FilterQuery): {
  total: number;
  rows: SuburbRecord[];
} {
  const matched = filteredRows(dataset, query);
  if (query.sortBy) {
    const direction = query.direction === "asc" ? 1 : -1;
    matched.sort((a, b) => {
      const av = numericValue(a, query.sortBy!);
      const bv = numericValue(b, query.sortBy!);
      if (av === null) return 1;
      if (bv === null) return -1;
      return (av - bv) * direction;
    });
  }
  return { total: matched.length, rows: matched.slice(0, Math.min(20, query.limit ?? 8)) };
}

export function factsForRows(rows: SuburbRecord[]): FactMap {
  const facts: FactMap = {};
  for (const row of rows) {
    if (typeof row.name !== "string") continue;
    for (const field of CANONICAL_FIELDS) {
      if (row[field] !== null) facts[`suburb:${row.name}:${field}`] = row[field];
    }
  }
  return facts;
}

function rounded(value: number): number {
  return Math.round(value * 100) / 100;
}

function aggregate(values: Array<{ row: SuburbRecord; value: number }>, operation: AggregateOperation) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a.value - b.value);
  if (operation === "count") return { value: values.length, suburb: null };
  if (operation === "mean") {
    return { value: rounded(values.reduce((sum, item) => sum + item.value, 0) / values.length), suburb: null };
  }
  if (operation === "median") {
    const middle = Math.floor(sorted.length / 2);
    const value = sorted.length % 2
      ? sorted[middle].value
      : (sorted[middle - 1].value + sorted[middle].value) / 2;
    return { value: rounded(value), suburb: null };
  }
  const item = operation === "min" ? sorted[0] : sorted[sorted.length - 1];
  return { value: item.value, suburb: item.row.name };
}

export type AggregateOperation = "count" | "mean" | "median" | "min" | "max";

export function aggregateRows(
  dataset: Dataset,
  filter: DatasetFilter,
  metric: NumericField,
  operation: AggregateOperation,
  groupByZone: boolean,
): { data: unknown; facts: FactMap } {
  const rows = filteredRows(dataset, filter);
  const groups = new Map<string, SuburbRecord[]>();
  if (groupByZone) {
    for (const row of rows) {
      if (typeof row.zone !== "string") continue;
      groups.set(row.zone, [...(groups.get(row.zone) ?? []), row]);
    }
  } else {
    groups.set("all", rows);
  }

  const facts: FactMap = {};
  const data: Array<{ group: string; matched: number; value: number | null; suburb: Cell }> = [];
  for (const [group, groupRows] of groups) {
    const values = groupRows.flatMap((row) => {
      const value = numericValue(row, metric);
      return value === null ? [] : [{ row, value }];
    });
    const result = aggregate(values, operation);
    const prefix = `summary:${group}:${metric}:${operation}`;
    facts[`${prefix}:matched`] = groupRows.length;
    if (result) {
      facts[`${prefix}:value`] = result.value;
      if (result.suburb) facts[`${prefix}:suburb`] = result.suburb;
    }
    data.push({ group, matched: groupRows.length, value: result?.value ?? null,
      suburb: result?.suburb ?? null });
  }
  return { data, facts };
}
