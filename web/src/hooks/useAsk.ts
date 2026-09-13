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
  const inFlight = useRef(false);

  const stopTimer = () => {
    if (timer.current !== null) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
  };

  const run = useCallback(async (req: AskRequest) => {
    if (inFlight.current) return;   // ignore a second tap while a request is already running
    inFlight.current = true;
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
      // api.ts maps network faults and timeouts to friendly copy; anything else gets a
      // neutral line. A raw exception message never reaches the screen (N6).
      setError(e instanceof api.ApiError ? e.detail : "Something went wrong reaching the archive. The record and examples below still work.");
      setStatus("error");
    } finally {
      stopTimer();
      inFlight.current = false;
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
