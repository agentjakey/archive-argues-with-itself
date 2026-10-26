import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { glossaryEntry } from "../lib/glossary";

// Term toggletip. The term is a real <button> in the tab order (native Enter/Space activation, a
// visible focus ring), and activating it reveals a small bubble whose text sits in a role="status"
// live region, so a screen reader hears the definition on open while focus stays on the button and is
// never trapped in the bubble. This is the WAI-ARIA "toggletip" pattern (a button that toggles a
// live-region bubble), with mouse hover added on top: hover opens after a short delay, the bubble is
// itself hoverable with a close delay, and a click pins it open, so it meets WCAG 1.4.13 content on
// hover (dismissible with Escape, hoverable, persistent). The bubble is portaled to <body> and placed
// with fixed coordinates clamped to the viewport, so no overflow/clip ancestor can cut it off and it
// never forces horizontal scroll. Only one is open at a time. No external dependency.

// Module-level handoff so only one toggletip is open across the whole app. The token is the per
// instance identity; the closer closes that instance. Reset by whichever instance currently owns it.
let activeToken: object | null = null;
let activeClose: (() => void) | null = null;

const OPEN_DELAY = 120; // ms before hover opens, so a cursor passing over a term does not flash it
const CLOSE_DELAY = 150; // ms grace to let the pointer travel from the term into the bubble
const GAP = 6; // px between the term and the bubble
const MARGIN = 8; // px minimum gap from any viewport edge

function isCoarsePointer(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(hover: none), (pointer: coarse)").matches
  );
}

interface Props {
  /** Glossary key (lib/glossary.ts). An unknown key renders the text as plain, non-interactive text. */
  def: string;
  /** Visible text; defaults to the glossary term. A plain string, never backend content. */
  children?: string;
}

export function Term({ def, children }: Props) {
  const entry = glossaryEntry(def);
  const bubbleId = useId();
  const token = useRef<object>({}).current;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const bubbleRef = useRef<HTMLSpanElement>(null);
  const timers = useRef<{ open?: number; close?: number }>({});
  const pinnedRef = useRef(false);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  const label = typeof children === "string" ? children : entry?.term ?? def;

  const clearTimers = useCallback(() => {
    if (timers.current.open) window.clearTimeout(timers.current.open);
    if (timers.current.close) window.clearTimeout(timers.current.close);
    timers.current = {};
  }, []);

  const close = useCallback(() => {
    clearTimers();
    pinnedRef.current = false;
    setOpen(false);
    setPos(null);
    if (activeToken === token) {
      activeToken = null;
      activeClose = null;
    }
  }, [clearTimers, token]);

  const show = useCallback(() => {
    if (!entry) return;
    clearTimers();
    if (activeToken && activeToken !== token && activeClose) activeClose();
    activeToken = token;
    activeClose = close;
    setOpen(true);
  }, [clearTimers, close, entry, token]);

  // A pointer click (or native Enter/Space on the button) toggles and pins: once pinned it stays open
  // until a click, Escape, or an outside click, ignoring the hover close.
  const onClick = useCallback(() => {
    if (open && pinnedRef.current) {
      close();
    } else {
      pinnedRef.current = true;
      show();
    }
  }, [open, close, show]);

  const onEnterTrigger = useCallback(() => {
    if (isCoarsePointer()) return; // touch uses tap-to-toggle, never hover
    clearTimers();
    timers.current.open = window.setTimeout(show, OPEN_DELAY);
  }, [clearTimers, show]);

  const onLeaveTrigger = useCallback(() => {
    if (isCoarsePointer()) return;
    if (timers.current.open) {
      window.clearTimeout(timers.current.open);
      timers.current.open = undefined;
    }
    if (!pinnedRef.current) timers.current.close = window.setTimeout(close, CLOSE_DELAY);
  }, [clearTimers, close]);

  const onEnterBubble = useCallback(() => {
    if (timers.current.close) {
      window.clearTimeout(timers.current.close);
      timers.current.close = undefined;
    }
  }, []);

  const onLeaveBubble = useCallback(() => {
    if (!pinnedRef.current) timers.current.close = window.setTimeout(close, CLOSE_DELAY);
  }, [close]);

  // Place the bubble under the term (flipping above when there is no room below), clamped so it never
  // crosses a viewport edge, never clipped by an ancestor (it is portaled and fixed), and never a
  // cause of horizontal scroll. Recomputed on scroll and resize while open.
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const t = triggerRef.current?.getBoundingClientRect();
      if (!t) return;
      const bw = bubbleRef.current?.offsetWidth ?? 0;
      const bh = bubbleRef.current?.offsetHeight ?? 0;
      const vw = window.innerWidth || 0;
      const vh = window.innerHeight || 0;
      let left = Math.min(t.left, vw - bw - MARGIN);
      left = Math.max(MARGIN, Number.isFinite(left) ? left : MARGIN);
      let top = t.bottom + GAP;
      if (top + bh + MARGIN > vh && t.top - bh - GAP >= MARGIN) top = t.top - bh - GAP;
      setPos({ left, top });
    };
    place();
    let raf = 0;
    const onScrollResize = () => {
      if (raf) return;
      raf = window.requestAnimationFrame(() => {
        raf = 0;
        place();
      });
    };
    window.addEventListener("scroll", onScrollResize, true);
    window.addEventListener("resize", onScrollResize);
    return () => {
      window.removeEventListener("scroll", onScrollResize, true);
      window.removeEventListener("resize", onScrollResize);
      if (raf) window.cancelAnimationFrame(raf);
    };
  }, [open]);

  // Escape closes and returns focus to the term; a pointer press outside the term and the bubble
  // closes. Both are bound only while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close();
        triggerRef.current?.focus();
      }
    };
    const onDown = (e: Event) => {
      const target = e.target as Node | null;
      if (!target) return;
      if (triggerRef.current?.contains(target) || bubbleRef.current?.contains(target)) return;
      close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown, true);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown, true);
    };
  }, [open, close]);

  // Release timers and the shared open-slot if this instance unmounts while owning it.
  useEffect(
    () => () => {
      clearTimers();
      if (activeToken === token) {
        activeToken = null;
        activeClose = null;
      }
    },
    [clearTimers, token],
  );

  // Defensive: an unknown key is not interactive, just the plain word.
  if (!entry) return <>{label}</>;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="term"
        aria-expanded={open}
        aria-controls={open ? bubbleId : undefined}
        aria-label={`${label}: what this means`}
        onClick={onClick}
        onMouseEnter={onEnterTrigger}
        onMouseLeave={onLeaveTrigger}
      >
        {label}
      </button>
      {open &&
        createPortal(
          <span
            id={bubbleId}
            ref={bubbleRef}
            role="status"
            className="toggletip-bubble"
            style={{
              left: pos ? pos.left : -9999,
              top: pos ? pos.top : -9999,
              visibility: pos ? "visible" : "hidden",
            }}
            onMouseEnter={onEnterBubble}
            onMouseLeave={onLeaveBubble}
          >
            {entry.definition}
          </span>,
          document.body,
        )}
    </>
  );
}
