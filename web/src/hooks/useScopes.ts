import { useEffect, useState } from "react";
import * as api from "../lib/api";
import type { ScopesResponse } from "../types";

/** The corpora this server exposes, for the scope switcher. Fetched once. A single-scope
 *  deploy (the festival pilot) returns one scope, and the switcher stays hidden. */
export function useScopes(): ScopesResponse | null {
  const [scopes, setScopes] = useState<ScopesResponse | null>(null);
  useEffect(() => {
    let alive = true;
    api
      .scopes()
      .then((s) => {
        if (alive) setScopes(s);
      })
      .catch(() => {
        if (alive) setScopes(null);
      });
    return () => {
      alive = false;
    };
  }, []);
  return scopes;
}
