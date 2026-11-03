import { useEffect, useState } from "react";

export interface CatalogueSummary {
  documents: number;
  coverage: { known?: number; text_fetched?: number; indexed?: number };
  built_at?: string;
}

let pending: Promise<CatalogueSummary | null> | null = null;

/** The catalogue's own totals (/catalogue/data/summary.json, published with each site release), so
 *  the landing states the catalogue's size from the release, never from a number typed into the
 *  code. Null while loading, or when the release has no catalogue (development, tests). */
export function useCatalogueSummary(): CatalogueSummary | null {
  const [summary, setSummary] = useState<CatalogueSummary | null>(null);
  useEffect(() => {
    let alive = true;
    if (!pending) {
      pending = fetch("/catalogue/data/summary.json", { headers: { accept: "application/json" } })
        .then((r) => (r.ok ? r.json() : null))
        .then((s) => (s && typeof s.documents === "number" ? (s as CatalogueSummary) : null))
        .catch(() => null);
    }
    pending.then((s) => {
      if (alive) setSummary(s);
    });
    return () => {
      alive = false;
    };
  }, []);
  return summary;
}
