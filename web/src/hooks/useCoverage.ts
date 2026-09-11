import { useEffect, useState } from "react";
import * as api from "../lib/api";
import type { CoverageResponse, Filters } from "../types";

/** Lexical coverage for the asked question under the active filters; fetched in
 *  parallel with /ask and independent of its outcome. */
export function useCoverage(question: string, filters: Filters): CoverageResponse | null {
  const [cov, setCov] = useState<CoverageResponse | null>(null);
  const key = JSON.stringify([question, filters]);
  useEffect(() => {
    if (!question) {
      setCov(null);
      return;
    }
    let alive = true;
    setCov(null);
    api
      .coverage(question, filters)
      .then((c) => {
        if (alive) setCov(c);
      })
      .catch(() => {
        if (alive) setCov(null);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return cov;
}
