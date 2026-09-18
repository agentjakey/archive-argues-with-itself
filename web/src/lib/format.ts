import type { CorpusFacts, EvidenceRow, YearWindow } from "../types";

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

/** The one honest span story, shown wherever a date range or an out-of-window period appears: the
 *  nominal collection window, how many dated items carry metadata dates outside it, and that these
 *  are catalog-metadata dates that may not equal the publication year. The real count is passed in
 *  (from by_period on composition surfaces, or corpus_facts.items_out_of_window on the header), so
 *  the same number reads across surfaces. Nothing here is inferred; the true dated span is shown
 *  unclamped elsewhere. */
export function windowNote(pilotWindow: YearWindow, outOfWindow: number): string {
  const w = windowLabel({ window: pilotWindow });
  const base = "Early and late dates are catalog metadata and may not equal the publication year.";
  if (!outOfWindow) return `The nominal collection window is ${w}. ${base}`;
  const items =
    outOfWindow === 1 ? "1 item carries a metadata date" : `${formatInt(outOfWindow)} items carry metadata dates`;
  return `The nominal collection window is ${w}; ${items} outside it. ${base}`;
}

/** Honest short label for how an item's date was resolved. exact = catalogue metadata,
 *  title_extracted = the document's own title (both recorded, not inferred); undated when there
 *  is no date. "estimated" is supported for completeness but no scope contains estimated dates. */
export function dateMethodLabel(row: Pick<EvidenceRow, "year" | "date_method">): string {
  if (row.year == null || row.date_method === "unknown") return "undated";
  switch (row.date_method) {
    case "exact":
      return "date from metadata";
    case "title_extracted":
      return "date from the title";
    case "estimated":
      return "estimated date";
    default:
      return "dated";
  }
}

/** The one-line explanation shown on hover and in the page drawer. */
export function dateMethodDetail(row: Pick<EvidenceRow, "year" | "date_method">): string {
  if (row.year == null || row.date_method === "unknown")
    return "This item carries no date in the record; it is shown as undated.";
  switch (row.date_method) {
    case "exact":
      return `Dated ${row.year}, from the catalogue metadata (recorded).`;
    case "title_extracted":
      return `Dated ${row.year}, read from the document's own title (recorded, not inferred).`;
    case "estimated":
      return `Estimated ${row.year} (inferred, not recorded).`;
    default:
      return `Dated ${row.year}.`;
  }
}
