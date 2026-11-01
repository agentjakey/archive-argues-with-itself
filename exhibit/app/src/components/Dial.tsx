// The year dial on screen: a slider that the physical dial, the arrow keys, a wheel, the two large
// buttons and a drag all move. It is a real ARIA slider, so a screen reader announces the year.
import { useRef } from "react";
import { clampYear, wheelAccumulator } from "../lib/input";
import type { Strings } from "../lib/strings";

type Props = {
  year: number;
  first: number;
  last: number;
  onChange: (year: number) => void;
  t: Strings;
  valueText?: string;
  hideValue?: boolean;
};

export function Dial({ year, first, last, onChange, t, valueText, hideValue }: Props) {
  const wheel = useRef(wheelAccumulator());
  const track = useRef<HTMLDivElement>(null);
  const set = (y: number) => onChange(clampYear(y, first, last));
  const fromPointer = (clientX: number) => {
    const box = track.current?.getBoundingClientRect();
    if (!box || box.width === 0) return;
    const share = Math.min(1, Math.max(0, (clientX - box.left) / box.width));
    set(Math.round(first + share * (last - first)));
  };
  const share = (year - first) / Math.max(1, last - first);
  return (
    <div className="dial">
      <button type="button" className="btn dial-step" onClick={() => set(year - 1)} aria-label={t.dial.earlier}>
        <span aria-hidden="true">{"<"}</span> {t.dial.earlier}
      </button>
      <div
        className="dial-track"
        ref={track}
        role="slider"
        tabIndex={0}
        aria-label={t.dial.label}
        aria-valuemin={first}
        aria-valuemax={last}
        aria-valuenow={year}
        aria-valuetext={valueText ?? String(year)}
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
          const steps = wheel.current(e.deltaY);
          if (steps !== 0) set(year + steps);
        }}
        onPointerDown={(e) => {
          (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          fromPointer(e.clientX);
        }}
        onPointerMove={(e) => {
          if (e.buttons === 1) fromPointer(e.clientX);
        }}
      >
        <div className="dial-rail" aria-hidden="true">
          <div className="dial-fill" style={{ width: `${share * 100}%` }} />
          <div className="dial-knob" style={{ left: `${share * 100}%` }} />
        </div>
        <div className="dial-ends" aria-hidden="true">
          <span>{first}</span>
          <span>{last}</span>
        </div>
      </div>
      <button type="button" className="btn dial-step" onClick={() => set(year + 1)} aria-label={t.dial.later}>
        {t.dial.later} <span aria-hidden="true">{">"}</span>
      </button>
      {!hideValue && (
        <output className="dial-year" aria-live="polite">
          {year}
        </output>
      )}
    </div>
  );
}
