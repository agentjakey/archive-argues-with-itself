// The year dial: a tape of years that slides under a fixed needle, with a tick for every year and a
// labelled tick for every decade. It always settles on a whole year (a detent), and every way of
// turning it gives the same steps: the physical USB knob and the arrow keys, a drag along the tape,
// a mouse wheel, and the two large buttons. It is a real ARIA slider, so a screen reader announces
// the year. With sound switched on, each detent ticks.
import { useEffect, useRef } from "react";
import type { CSSProperties } from "react";
import { clampYear, wheelAccumulator } from "../lib/input";
import { useSettings } from "../lib/settings";
import { tick } from "../lib/sound";
import type { Strings } from "../lib/strings";

type Props = {
  year: number;
  first: number;
  last: number;
  onChange: (year: number) => void;
  t: Strings;
  valueText?: string;
  locked?: boolean;
};

export function Dial({ year, first, last, onChange, t, valueText, locked = false }: Props) {
  const { sound } = useSettings();
  const wheel = useRef(wheelAccumulator());
  const tape = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; year: number; px: number } | null>(null);
  const previous = useRef(year);
  useEffect(() => {
    if (previous.current !== year && sound) tick(year % 10 === 0);
    previous.current = year;
  }, [year, sound]);
  const set = (y: number) => {
    if (!locked) onChange(clampYear(y, first, last));
  };
  const tickPx = () => {
    const ticks = tape.current?.children;
    if (!ticks || ticks.length < 2) return 20;
    return Math.max(4, (ticks[1] as HTMLElement).offsetLeft - (ticks[0] as HTMLElement).offsetLeft);
  };
  const years: number[] = [];
  for (let y = first; y <= last; y++) years.push(y);
  const style = { "--at": year - first } as CSSProperties;
  return (
    <div className={`dial${locked ? " dial-locked" : ""}`}>
      <output className="dial-year" aria-hidden="true">
        {year}
      </output>
      <div className="dial-row">
        <button type="button" className="dial-step" onClick={() => set(year - 1)} aria-label={t.dial.earlier} disabled={locked || year <= first}>
          <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
            <polygon points="14,2 14,18 4,10" />
          </svg>
        </button>
        <div
          className="dial-window"
          role="slider"
          tabIndex={0}
          aria-label={t.dial.label}
          aria-valuemin={first}
          aria-valuemax={last}
          aria-valuenow={year}
          aria-valuetext={valueText ?? String(year)}
          aria-disabled={locked || undefined}
          onKeyDown={(e) => {
            const step = e.key === "ArrowRight" || e.key === "ArrowUp" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowDown" ? -1 : 0;
            if (e.key === "Home") set(first);
            else if (e.key === "End") set(last);
            else if (e.key === "PageUp") set(year + 10);
            else if (e.key === "PageDown") set(year - 10);
            else if (step !== 0) set(year + step);
            else return;
            e.preventDefault();
          }}
          onWheel={(e) => {
            const steps = wheel.current(Math.abs(e.deltaX) > Math.abs(e.deltaY) ? -e.deltaX : e.deltaY);
            if (steps !== 0) set(year + steps);
          }}
          onPointerDown={(e) => {
            if (locked) return;
            (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
            drag.current = { x: e.clientX, year, px: tickPx() };
          }}
          onPointerMove={(e) => {
            const d = drag.current;
            if (!d) return;
            set(d.year + Math.round((d.x - e.clientX) / d.px));
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
          onPointerCancel={() => {
            drag.current = null;
          }}
        >
          <div className="dial-tape" ref={tape} style={style} aria-hidden="true">
            {years.map((y) => (
              <span
                key={y}
                className={`dial-tick${y % 10 === 0 ? " dial-tick-decade" : y % 5 === 0 ? " dial-tick-five" : ""}`}
                style={{ "--i": y - first } as CSSProperties}
              >
                {y % 10 === 0 && <span className="dial-tick-label">{y}</span>}
              </span>
            ))}
          </div>
          <span className="dial-needle" aria-hidden="true" />
        </div>
        <button type="button" className="dial-step" onClick={() => set(year + 1)} aria-label={t.dial.later} disabled={locked || year >= last}>
          <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
            <polygon points="6,2 6,18 16,10" />
          </svg>
        </button>
      </div>
      <p className="dial-hint">{t.dial.turn}</p>
    </div>
  );
}
