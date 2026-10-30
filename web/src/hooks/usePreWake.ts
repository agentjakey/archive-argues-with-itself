import { useCallback, useRef } from "react";
import * as api from "../lib/api";
import { staticMode } from "../lib/config";

const AGAIN_AFTER_MS = 5 * 60 * 1000;   // the engine sleeps after 15 minutes idle; 5 is well inside it

/** Start the engine when someone shows they are about to ask: the question box gets focus. Never
 *  on page load, so reading the stories never wakes it. The Ask button needs no separate call: the
 *  question it sends wakes the engine itself. Only in a static release (locally the engine is
 *  always on). Each wake carries a Turnstile token and is rate limited by the Worker. */
export function usePreWake(enabled: boolean): () => void {
  const last = useRef(0);

  return useCallback(() => {
    if (!enabled || !staticMode()) return;
    const now = Date.now();
    if (now - last.current < AGAIN_AFTER_MS) return;
    last.current = now;
    void api.wake();
  }, [enabled]);
}
