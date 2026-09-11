import { useEffect, useRef } from "react";
import type { Story } from "../types";

export const IDLE_MS = 60_000;
export const STEP_MS = 20_000;
const EVENTS: (keyof WindowEventMap)[] = ["pointerdown", "keydown", "touchstart", "wheel"];

interface Options {
  enabled: boolean;               // kiosk mode only
  stories: Story[];
  onShow: (story: Story) => void; // open a story (question + two pins)
  onHome: () => void;             // a touch during the loop returns to the home screen
  idleMs?: number;
  stepMs?: number;
}

/** Kiosk attract loop: after idleMs with no input, cycle through the stories every
 *  stepMs; any input while cycling stops the loop and calls onHome. Any input while
 *  idle-but-not-cycling just resets the idle timer. */
export function useAttractLoop({ enabled, stories, onShow, onHome, idleMs = IDLE_MS, stepMs = STEP_MS }: Options) {
  const looping = useRef(false);
  const index = useRef(0);
  const show = useRef(onShow);
  const home = useRef(onHome);
  show.current = onShow;
  home.current = onHome;

  useEffect(() => {
    if (!enabled || stories.length === 0) return;
    let idleTimer: number | null = null;
    let stepTimer: number | null = null;

    const step = () => {
      show.current(stories[index.current % stories.length]);
      index.current += 1;
    };
    const startLoop = () => {
      looping.current = true;
      step();
      stepTimer = window.setInterval(step, stepMs);
    };
    const armIdle = () => {
      if (idleTimer !== null) window.clearTimeout(idleTimer);
      idleTimer = window.setTimeout(startLoop, idleMs);
    };
    const onInput = () => {
      if (looping.current) {
        looping.current = false;
        if (stepTimer !== null) window.clearInterval(stepTimer);
        stepTimer = null;
        home.current();
      }
      armIdle();
    };

    EVENTS.forEach((e) => window.addEventListener(e, onInput, { passive: true }));
    armIdle();
    return () => {
      EVENTS.forEach((e) => window.removeEventListener(e, onInput));
      if (idleTimer !== null) window.clearTimeout(idleTimer);
      if (stepTimer !== null) window.clearInterval(stepTimer);
      looping.current = false;
    };
  }, [enabled, stories, idleMs, stepMs]);
}
