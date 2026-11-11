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

// When Was This?'s dial never starts on the answer. It starts at least DIAL_START_GAP years away,
// which scores nothing (points fall by 10 a year), so leaving the dial alone never earns points.
// The start sits in the middle three fifths of the range, where it anchors a guess least, and is
// chosen per card from the card's id, so it is the same on every visit but differs between cards
// and does not point at the answer the way a fixed midpoint with an exception would.
export const DIAL_START_GAP = 10;

function hashKey(key: string): number {
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function dialStart(first: number, last: number, answer: number, key: string): number {
  const margin = Math.round((last - first) / 5);
  const pick = (lo: number, hi: number, ok: (y: number) => boolean): number[] => {
    const out: number[] = [];
    for (let y = lo; y <= hi; y++) if (ok(y)) out.push(y);
    return out;
  };
  let choices = pick(first + margin, last - margin, (y) => Math.abs(y - answer) >= DIAL_START_GAP);
  if (choices.length === 0) choices = pick(first, last, (y) => Math.abs(y - answer) >= DIAL_START_GAP);
  if (choices.length === 0) choices = pick(first, last, (y) => y !== answer);
  if (choices.length === 0) return first;
  return choices[hashKey(key) % choices.length];
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

// The dial's press sends Enter. When nothing is focused (the visitor has only turned the dial), Enter
// presses the screen's main action: the button marked data-primary. A focused control keeps its own
// Enter.
export function usePrimaryEnter(): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Enter") return;
      const active = document.activeElement;
      if (active && active !== document.body && active.tagName !== "MAIN") return;
      const primary = document.querySelector<HTMLButtonElement>("[data-primary]:not(:disabled)");
      if (primary) {
        e.preventDefault();
        primary.click();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
