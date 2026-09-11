import type { CorpusFacts, EvidenceRow } from "../types";

export function shortTitle(title: string | null, max = 48): string {
  const s = (title ?? "untitled").replace(/\s+/g, " ").trim();
  return s.length > max ? `${s.slice(0, max - 3).trimEnd()}...` : s;
}

export function yearLabel(year: number | null): string {
  return year == null ? "undated" : String(year);
}

/** "short title, year, p. N (leaf L)"; without a printed page: "short title, year, leaf L". */
export function chipLabel(row: EvidenceRow): string {
  const page = row.printed_page ? `p. ${row.printed_page} (leaf ${row.leaf_index})` : `leaf ${row.leaf_index}`;
  return `${shortTitle(row.title)}, ${yearLabel(row.year)}, ${page}`;
}

export function decadeKey(row: Pick<EvidenceRow, "year" | "decade">): string {
  if (row.year == null) return "undated";
  return row.decade ?? `${Math.floor(row.year / 10) * 10}s`;
}

/** Decade lanes ascending, with "undated" forced last. */
export function laneOrder(keys: Iterable<string>): string[] {
  const set = new Set(keys);
  const dated = [...set].filter((k) => k !== "undated").sort();
  return set.has("undated") ? [...dated, "undated"] : dated;
}

/** The lanes the rail always shows, so absence is visible. */
export const FIXED_LANES = ["1960s", "1970s", "1980s", "1990s", "2000s", "undated"];

/** Every lane to render: the fixed set plus any decade actually present, ordered. */
export function allLanes(rows: Pick<EvidenceRow, "year" | "decade">[]): string[] {
  return laneOrder([...FIXED_LANES, ...rows.map(decadeKey)]);
}

export function groupByDecade(rows: EvidenceRow[]): Map<string, EvidenceRow[]> {
  const groups = new Map<string, EvidenceRow[]>();
  for (const k of allLanes(rows)) groups.set(k, []);
  for (const r of rows) groups.get(decadeKey(r))!.push(r);
  return groups;
}

export function formatElapsed(seconds: number): string {
  return `${seconds} s elapsed`;
}

export function formatInt(n: number): string {
  return n.toLocaleString("en-CA");
}

export function formatShare(share: number): string {
  return `${Math.round(share * 100)}%`;
}

export function windowLabel(c: Pick<CorpusFacts, "window">): string {
  const { min_year, max_year } = c.window;
  if (min_year == null || max_year == null) return "undated only";
  return `${min_year} to ${max_year}`;
}
