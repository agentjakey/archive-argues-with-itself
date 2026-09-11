import { useEffect, useState } from "react";
import * as api from "../lib/api";
import type { Example } from "../types";

/** Up to `limit` example chips, always including at least one gold-abstain probe
 *  when the seed has one. */
export function pickChips(all: Example[], limit = 6): Example[] {
  const abstain = all.find((e) => e.gold === "abstain");
  const rest = all.filter((e) => e !== abstain);
  const chosen = rest.slice(0, abstain ? limit - 1 : limit);
  return abstain ? [...chosen, abstain] : chosen;
}

export function useExamples(limit = 6) {
  const [chips, setChips] = useState<Example[]>([]);
  useEffect(() => {
    let alive = true;
    api
      .examples()
      .then((all) => {
        if (alive) setChips(pickChips(all, limit));
      })
      .catch(() => {
        if (alive) setChips([]);
      });
    return () => {
      alive = false;
    };
  }, [limit]);
  return chips;
}
