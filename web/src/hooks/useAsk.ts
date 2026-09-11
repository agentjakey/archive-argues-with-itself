import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import type { AskRequest, AskResponse } from "../types";

export type AskStatus = "idle" | "waiting" | "done" | "error";

/** One real request, one real waiting label with an elapsed counter, one real
 *  completion label derived from the response. No staged theatre. */
export function useAsk() {
  const [status, setStatus] = useState<AskStatus>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [response, setResponse] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const stopTimer = () => {
    if (timer.current !== null) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
  };

  const run = useCallback(async (req: AskRequest) => {
    setStatus("waiting");
    setElapsed(0);
    setResponse(null);
    setError(null);
    stopTimer();
    const t0 = Date.now();
    timer.current = window.setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 1000);
    try {
      const r = await api.ask(req);
      setResponse(r);
      setStatus("done");
    } catch (e) {
      // ApiError carries the server's detail verbatim; anything else is a network fault.
      setError(e instanceof Error ? e.message : String(e));
      setStatus("error");
    } finally {
      stopTimer();
    }
  }, []);

  useEffect(() => stopTimer, []);

  const completion = response
    ? response.answer.abstained
      ? response.answer.abstention_text ?? "abstained"
      : `${response.answer.verified_citations.length} citations verified`
    : null;

  return { status, elapsed, response, error, run, completion };
}
