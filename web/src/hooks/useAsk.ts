import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { plural } from "../lib/format";
import { EngineDown, waitForEngine, type WakeProgress } from "../lib/waking";
import type { AskRequest, AskResponse } from "../types";

export type AskStatus = "idle" | "waiting" | "waking" | "done" | "error";

const sleep = (seconds: number) => new Promise<void>((resolve) => window.setTimeout(resolve, seconds * 1000));

/** One real request, one real waiting label with an elapsed counter, one real completion label
 *  derived from the response. No staged theatre. When the engine is asleep the question is kept:
 *  the hook waits for the engine (status "waking", with its reported stage, then "slow"), asks again
 *  on its own once the engine is ready, and only gives up ("down") after a failed start or a long
 *  wait. A new question cancels the wait. */
export function useAsk() {
  const [status, setStatus] = useState<AskStatus>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [response, setResponse] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [wake, setWake] = useState<WakeProgress | null>(null);
  const timer = useRef<number | null>(null);
  // "request": an /ask is on the wire (a second tap is ignored); "waking": the question is kept while
  // the engine wakes (a new question replaces it); "idle": nothing running.
  const phase = useRef<"idle" | "request" | "waking">("idle");
  const waitAbort = useRef<AbortController | null>(null);
  const lastRequest = useRef<AskRequest | null>(null);

  const stopTimer = () => {
    if (timer.current !== null) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
  };

  const run = useCallback(async (req: AskRequest) => {
    if (phase.current === "request") return;             // ignore a second tap while a request is running
    waitAbort.current?.abort();                           // a new question replaces one that is waiting
    const abort = new AbortController();
    waitAbort.current = abort;
    lastRequest.current = req;
    setStatus("waiting");
    setElapsed(0);
    setResponse(null);
    setError(null);
    setWake(null);
    stopTimer();
    const t0 = Date.now();
    timer.current = window.setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 1000);
    try {
      for (;;) {
        try {
          phase.current = "request";
          const r = await api.ask(req);
          if (abort.signal.aborted) return;
          setResponse(r);
          setWake(null);
          setStatus("done");
          return;
        } catch (e) {
          if (!(e instanceof api.EngineWaking)) throw e;
          phase.current = "waking";
          setStatus("waking");
          setWake({ phase: "waking", elapsed: Math.round((Date.now() - t0) / 1000), stage: e.engine.stage ?? null });
          await waitForEngine(t0, { status: api.engineStatus, sleep, now: Date.now }, (p) => {
            if (!abort.signal.aborted) setWake(p);
          }, abort.signal);
          if (abort.signal.aborted) return;
          setStatus("waiting");                           // ready: ask again, the question kept
        }
      }
    } catch (e) {
      if (abort.signal.aborted || (e instanceof DOMException && e.name === "AbortError")) return;
      if (e instanceof EngineDown) {
        phase.current = "idle";
        setWake((w) => ({ phase: "down", elapsed: Math.round((Date.now() - t0) / 1000), stage: w?.stage ?? null }));
        setStatus("waking");
        return;
      }
      // api.ts maps network faults and timeouts to friendly copy; anything else gets a
      // neutral line. A raw exception message never reaches the screen (N6).
      setError(e instanceof api.ApiError ? e.detail : "Something went wrong reaching the archive. The record and examples below still work.");
      setStatus("error");
    } finally {
      if (waitAbort.current === abort) {
        stopTimer();
        phase.current = "idle";
        waitAbort.current = null;
      }
    }
  }, []);

  /** Ask the kept question again (the "down" state's retry button). */
  const retry = useCallback(() => {
    if (lastRequest.current) void run(lastRequest.current);
  }, [run]);

  useEffect(() => () => {
    stopTimer();
    waitAbort.current?.abort();
  }, []);

  const completion = response
    ? response.answer.abstained
      ? response.answer.abstention_text ?? "abstained"
      : `${plural(response.answer.verified_citations.length, "citation")} verified`
    : null;

  return { status, elapsed, response, error, run, retry, wake, completion };
}
