// Period bars for the thematic timeline, built from the scope composition's real per-period
// document counts (Composition.by_period, item counts). The decade axis is contiguous from the
// first to the last decade actually present, so an interior decade with no documents shows as a
// zero bar (sparse stays visibly sparse); pre-1960 and post-2009 appear only when the corpus has
// documents there (no fabricated tail beyond the record). Undated is returned separately as its
// own bar and is never folded into a decade. This is the browsable form of the "argues with
// itself" span, feeding the existing compare view rather than duplicating it.

import type { Period } from "../types";

export interface PeriodBar {
  key: Period;
  label: string;
  count: number;
  kind: "dated" | "undated";
}

const DECADE_RE = /^(\d{4})s$/;

function decadeStart(key: string): number | null {
  const m = DECADE_RE.exec(key);
  return m ? Number(m[1]) : null;
}

/** Ordered dated bars plus the separate undated bar, from real per-period document counts.
 *  by_period['undated'] equals the sources view's undated item count (same basis, single source),
 *  so the undated bar and the sources view never disagree. */
export function timelineBars(byPeriod: Record<string, number>): { dated: PeriodBar[]; undated: PeriodBar } {
  const decades = Object.keys(byPeriod)
    .map(decadeStart)
    .filter((n): n is number => n != null);
  const dated: PeriodBar[] = [];
  if ((byPeriod["pre-1960"] ?? 0) > 0) {
    dated.push({ key: "pre-1960", label: "pre-1960", count: byPeriod["pre-1960"], kind: "dated" });
  }
  if (decades.length) {
    const lo = Math.min(...decades);
    const hi = Math.max(...decades);
    for (let d = lo; d <= hi; d += 10) {
      const key = `${d}s` as Period;
      dated.push({ key, label: `${d}s`, count: byPeriod[key] ?? 0, kind: "dated" });
    }
  }
  if ((byPeriod["post-2009"] ?? 0) > 0) {
    dated.push({ key: "post-2009", label: "post-2009", count: byPeriod["post-2009"], kind: "dated" });
  }
  const undated: PeriodBar = {
    key: "undated",
    label: "undated",
    count: byPeriod["undated"] ?? 0,
    kind: "undated",
  };
  return { dated, undated };
}

/** The period bucket an evidence row falls in, matching ingest.normalize.period_of and the
 *  backend _PERIOD_CASE exactly. Used to pick one pool passage per decade for the compare view,
 *  so a compare draws from the same period definition the histogram is built on. */
export function periodOfRow(row: { year: number | null }): Period {
  if (row.year == null) return "undated";
  if (row.year < 1960) return "pre-1960";
  if (row.year > 2009) return "post-2009";
  return `${Math.floor(row.year / 10) * 10}s` as Period;
}

/** A readable label for a period key, for compare captions and controls. */
export function periodLabel(key: Period): string {
  return key;
}
