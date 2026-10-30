// Waiting for a waking engine: poll the engine Worker's /health with backoff until the engine is
// ready, reporting each step for the waking screen. Pure timing logic, so it can be tested without
// a browser clock.
import type { EngineStage, EngineStatus } from "../types";

export type WakePhase = "waking" | "slow" | "down";

export interface WakeProgress {
  phase: WakePhase;
  elapsed: number;              // seconds since the question was asked
  stage: EngineStage | null;
}

export const SLOW_AFTER_S = 60;           // past this, say plainly that it is slow and point to the stories
export const DOWN_AFTER_S = 300;          // past this, or on a failed start, say it is down
const MAX_FAILED_POLLS = 5;               // consecutive unreachable polls that mean down
const DELAYS_S = [2, 2, 3, 3, 4, 5];     // then every 5 s

export function delayFor(attempt: number): number {
  return DELAYS_S[Math.min(attempt, DELAYS_S.length - 1)];
}

/** The most informative stage among the engines a status reports. */
export function stageOf(status: EngineStatus): EngineStage | null {
  if (status.stage) return status.stage;
  const waking = (status.engines ?? []).find((e) => e.status !== "ready" && e.stage);
  return waking?.stage ?? null;
}

export class EngineDown extends Error {
  constructor(reason: string) {
    super(reason);
    this.name = "EngineDown";
  }
}

export interface WaitDeps {
  status: () => Promise<EngineStatus>;
  sleep: (seconds: number) => Promise<void>;
  now: () => number;            // milliseconds
}

/** Resolve once the engine reports ready; report progress along the way. Throws EngineDown when it
 *  fails to start, stays unreachable, or takes longer than DOWN_AFTER_S. The caller's abort signal
 *  stops the wait (a new question, or leaving the page). */
export async function waitForEngine(
  startedAt: number,
  deps: WaitDeps,
  onProgress: (p: WakeProgress) => void,
  signal: AbortSignal,
): Promise<void> {
  let failed = 0;
  for (let attempt = 0; ; attempt++) {
    if (signal.aborted) throw new DOMException("aborted", "AbortError");
    const elapsed = Math.round((deps.now() - startedAt) / 1000);
    if (elapsed >= DOWN_AFTER_S) throw new EngineDown("the engine did not become ready in time");
    let status: EngineStatus | null = null;
    try {
      status = await deps.status();
      failed = 0;
    } catch {
      failed += 1;
      if (failed >= MAX_FAILED_POLLS) throw new EngineDown("the engine could not be reached");
    }
    if (status?.status === "ready") return;
    if (status?.status === "failed") throw new EngineDown(status.error ?? "the engine failed to start");
    onProgress({ phase: elapsed >= SLOW_AFTER_S ? "slow" : "waking", elapsed, stage: status ? stageOf(status) : null });
    await deps.sleep(delayFor(attempt));
  }
}
