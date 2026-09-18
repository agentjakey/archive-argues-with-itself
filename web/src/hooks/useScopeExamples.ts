import { useEffect, useState } from "react";
import * as api from "../lib/api";
import type { Example } from "../types";

/** Seed questions for every served scope, keyed by scope name, for the explorer. Each scope's
 *  examples are fetched independently; a scope with no seed file returns an empty list. */
export function useScopeExamples(names: string[]): Record<string, Example[]> {
  const [byScope, setByScope] = useState<Record<string, Example[]>>({});
  const key = names.join(",");
  useEffect(() => {
    let alive = true;
    const list = key ? key.split(",") : [];
    Promise.all(
      list.map((n) =>
        api
          .examplesForScope(n)
          .then((ex) => [n, ex] as const)
          .catch(() => [n, [] as Example[]] as const),
      ),
    ).then((pairs) => {
      if (alive) setByScope(Object.fromEntries(pairs));
    });
    return () => {
      alive = false;
    };
  }, [key]);
  return byScope;
}
