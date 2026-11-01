// The physical dial and the keyboard speak the same standard events. The recommended dial (a
// USB HID knob, docs/EXHIBIT_HARDWARE.md) sends ArrowRight and ArrowLeft for each click of the
// knob and Enter when it is pressed. A mouse wheel or a touchpad scroll on the dial area turns it
// too. Nothing here needs a driver.
import { useEffect, useRef } from "react";

export type DialStep = -1 | 1;

export function stepFromKey(key: string): DialStep | 0 {
  if (key === "ArrowRight" || key === "ArrowUp" || key === "PageUp" || key === "+") return 1;
  if (key === "ArrowLeft" || key === "ArrowDown" || key === "PageDown" || key === "-") return -1;
  return 0;
}

// A wheel gesture arrives as many small deltas; this turns them into whole steps.
export function wheelAccumulator(threshold = 60) {
  let total = 0;
  return (deltaY: number): number => {
    total += deltaY;
    const steps = Math.trunc(total / threshold);
    total -= steps * threshold;
    return steps === 0 ? 0 : -steps;
  };
}

export function clampYear(year: number, first: number, last: number): number {
  return Math.min(last, Math.max(first, year));
}

// Calls onStep for dial clicks anywhere on the page, unless focus is in a control that uses the
// arrow keys itself (a radio group or a slider handles its own keys).
export function useDial(onStep: (step: DialStep) => void, enabled = true): void {
  const handler = useRef(onStep);
  handler.current = onStep;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const role = target?.getAttribute?.("role");
      if (role === "radio" || role === "slider" || target?.tagName === "INPUT") return;
      const step = stepFromKey(e.key);
      if (step !== 0) {
        e.preventDefault();
        handler.current(step);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
