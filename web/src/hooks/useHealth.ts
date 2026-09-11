import { useEffect, useState } from "react";
import * as api from "../lib/api";
import type { Health } from "../types";

/** Corpus facts for the header strip and the waiting label; fetched once. */
export function useHealth(): Health | null {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    let alive = true;
    api
      .health()
      .then((h) => {
        if (alive) setHealth(h);
      })
      .catch(() => {
        if (alive) setHealth(null);
      });
    return () => {
      alive = false;
    };
  }, []);
  return health;
}
