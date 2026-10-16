import { useEffect, useState } from "react";
import * as api from "../lib/api";
import type { Example } from "../types";

/** Up to `limit` example chips, always including one gold-abstain probe when the seed has one.
 *  The abstain chip carries a "(thin record)" tag in the UI, so it must be a question that
 *  reliably abstains, not merely one the gold marks should-abstain: the frozen rule answers a
 *  few should-abstain questions off-target, and tagging one of those "thin" while it returns an
 *  answer would be dishonest. `preferAbstainQids` names the verified refuse probes (the same ones
 *  the "See it decline" doorway uses); the first of them present in this scope's seed is chosen,
 *  falling back to the first gold-abstain only if none is present. */
export function pickChips(all: Example[], limit = 6, preferAbstainQids: string[] = []): Example[] {
  const abstainable = all.filter((e) => e.gold === "abstain");
  const preferred = preferAbstainQids.map((id) => abstainable.find((e) => e.qid === id)).find(Boolean);
  const abstain = preferred ?? abstainable[0];
  const rest = all.filter((e) => e !== abstain);
  const chosen = rest.slice(0, abstain ? limit - 1 : limit);
  return abstain ? [...chosen, abstain] : chosen;
}

export function useExamples(limit = 6, preferAbstainQids: string[] = []) {
  const [chips, setChips] = useState<Example[]>([]);
  const preferKey = preferAbstainQids.join(",");
  useEffect(() => {
    let alive = true;
    api
      .examples()
      .then((all) => {
        if (alive) setChips(pickChips(all, limit, preferKey ? preferKey.split(",") : []));
      })
      .catch(() => {
        if (alive) setChips([]);
      });
    return () => {
      alive = false;
    };
  }, [limit, preferKey]);
  return chips;
}
