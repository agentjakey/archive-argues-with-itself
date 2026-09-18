import { useMemo, useState } from "react";
import { formatInt, windowNote } from "../../lib/format";
import { outOfWindowCount, timelineBars, type PeriodBar } from "../../lib/timeline";
import type { Period, ScopeInfo } from "../../types";
import { Page } from "./Page";

interface Props {
  scope: ScopeInfo | null;
  initialQuestion: string;
  onDrillDecade: (period: Period, question: string) => void;
  onCompareDecades: (question: string, a: Period, b: Period) => void;
}

/** The thematic timeline: how the record changes across the decades for the active corpus. A
 *  histogram of real document counts per period (from the live /scopes composition, never
 *  hardcoded), with undated as its own bar. Clicking a decade reaches that decade's passages for
 *  the question; picking two decades opens the existing compare view. */
export function TimelinePage({ scope, initialQuestion, onDrillDecade, onCompareDecades }: Props) {
  const byPeriod = scope?.composition?.by_period;
  return (
    <Page title="How the record changes across the decades">
      <p>
        The record was not written all at once, and it does not say the same thing across the years.
        This is the browsable form of that: for the corpus you are exploring
        {scope ? (
          <>
            {" "}
            (<span className="text-ink">{scope.label}</span>)
          </>
        ) : null}
        , each bar is how many documents the corpus actually holds from that period. Open a decade to
        read its passages, or pick two decades to see them side by side in the compare view.
      </p>
      {!byPeriod ? (
        <p className="text-muted" aria-live="polite">
          Loading the timeline.
        </p>
      ) : (
        <TimelineBody
          scope={scope!}
          byPeriod={byPeriod}
          initialQuestion={initialQuestion}
          onDrillDecade={onDrillDecade}
          onCompareDecades={onCompareDecades}
        />
      )}
    </Page>
  );
}

// SVG layout. A plain bar chart: one measure (document count) over an ordered period axis, count
// printed on every bar so it reads without colour, undated set apart by a gap and a hatch so it
// never looks like a decade.
const SLOT = 74;
const BAR_W = 46;
const PLOT_H = 200;
const TOP = 30;
const BOT = 40;
const GAP = 30;
const MIN_BAR = 3;

function TimelineBody({
  scope,
  byPeriod,
  initialQuestion,
  onDrillDecade,
  onCompareDecades,
}: {
  scope: ScopeInfo;
  byPeriod: Record<string, number>;
  initialQuestion: string;
  onDrillDecade: (period: Period, question: string) => void;
  onCompareDecades: (question: string, a: Period, b: Period) => void;
}) {
  const { dated, undated } = useMemo(() => timelineBars(byPeriod), [byPeriod]);
  const [question, setQuestion] = useState(initialQuestion);
  const [a, setA] = useState<Period | "">(dated.length ? dated[0].key : "");
  const [b, setB] = useState<Period | "">(dated.length ? dated[dated.length - 1].key : "");

  const undatedItems = scope.composition?.undated.items ?? undated.count;
  const maxCount = Math.max(1, ...dated.map((d) => d.count), undated.count);
  const width = dated.length * SLOT + GAP + SLOT;
  const height = TOP + PLOT_H + BOT;
  const baseline = TOP + PLOT_H;
  const q = question.trim();

  const barHeight = (count: number) => (count > 0 ? Math.max(MIN_BAR, (count / maxCount) * PLOT_H) : 0);

  const drill = (bar: PeriodBar) => onDrillDecade(bar.key, q);
  const canCompare = Boolean(q) && a !== "" && b !== "" && a !== b;

  return (
    <>
      <figure className="mt-4 m-0">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full max-w-[640px] h-auto"
          role="group"
          aria-label={`Documents by period for ${scope.label}`}
        >
          <defs>
            <pattern id="tl-undated" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="7" height="7" fill="#fcfaf4" />
              <line x1="0" y1="0" x2="0" y2="7" stroke="#8b2e1f" strokeWidth="2.5" />
            </pattern>
            <style>{".tl-bar{cursor:pointer}.tl-bar:hover rect,.tl-bar:focus rect{stroke:#8b2e1f;stroke-width:3}"}</style>
          </defs>

          <line x1="0" y1={baseline} x2={width} y2={baseline} stroke="#1c1a17" strokeWidth="1.5" />

          {dated.map((bar, i) => (
            <Bar
              key={bar.key}
              bar={bar}
              x={i * SLOT}
              baseline={baseline}
              h={barHeight(bar.count)}
              fill="#1c1a17"
              onDrill={() => drill(bar)}
            />
          ))}

          {/* Undated sits after a gap, hatched, so it reads as outside the decade axis. */}
          <line
            x1={dated.length * SLOT + GAP / 2}
            y1={TOP}
            x2={dated.length * SLOT + GAP / 2}
            y2={baseline}
            stroke="#d9d2c3"
            strokeWidth="1"
            strokeDasharray="3 3"
          />
          <Bar
            bar={undated}
            x={dated.length * SLOT + GAP}
            baseline={baseline}
            h={barHeight(undated.count)}
            fill="url(#tl-undated)"
            onDrill={() => drill(undated)}
          />
        </svg>
        <figcaption className="mt-3 max-w-prose text-sm text-muted">
          Bars are document counts from this corpus, on one scale. Undated documents ({formatInt(undatedItems)}) are
          their own hatched bar, never spread across the decades; see Sources for the undated share of passages. A
          decade with no documents is drawn as a zero bar, so thin periods stay visibly thin. The axis ends where the
          record does; there is no recent tail this corpus does not hold.
        </figcaption>
        <figcaption className="mt-2 max-w-prose text-sm text-muted">
          {windowNote(scope.composition?.window ?? { min_year: null, max_year: null }, outOfWindowCount(byPeriod))}
        </figcaption>
      </figure>

      <div className="mt-6 border-t border-rule pt-4">
        <label className="block text-sm text-muted" htmlFor="tl-q">
          Ask a question of the record, then open a decade or compare two:
        </label>
        <input
          id="tl-q"
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What did the record say about water fluoridation?"
          className="mt-1 w-full max-w-prose border border-rule bg-sheet px-3 py-2 text-ink placeholder:text-muted focus:border-ink focus:outline-none"
        />
      </div>

      <div className="mt-4 flex flex-wrap items-end gap-2">
        <div className="flex flex-col">
          <label className="text-sm text-muted" htmlFor="tl-a">
            From
          </label>
          <PeriodSelect id="tl-a" bars={dated} value={a} onChange={setA} />
        </div>
        <div className="flex flex-col">
          <label className="text-sm text-muted" htmlFor="tl-b">
            to
          </label>
          <PeriodSelect id="tl-b" bars={dated} value={b} onChange={setB} />
        </div>
        <button
          type="button"
          className="chip border-ink bg-ink text-paper disabled:opacity-40"
          disabled={!canCompare}
          onClick={() => canCompare && onCompareDecades(q, a as Period, b as Period)}
        >
          Compare in the record
        </button>
      </div>
      <p className="mt-2 max-w-prose text-sm text-muted">
        Compare pulls one passage the record surfaced for your question from each period and opens them side by side.
        If a period has no passage for the question, it says so rather than inventing one.
      </p>
    </>
  );
}

function PeriodSelect({
  id,
  bars,
  value,
  onChange,
}: {
  id: string;
  bars: PeriodBar[];
  value: Period | "";
  onChange: (p: Period) => void;
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value as Period)}
      className="mt-1 border border-rule bg-sheet px-2 py-1.5 text-ink focus:border-ink focus:outline-none"
    >
      {bars.map((bar) => (
        <option key={bar.key} value={bar.key}>
          {bar.label} ({formatInt(bar.count)})
        </option>
      ))}
    </select>
  );
}

function Bar({
  bar,
  x,
  baseline,
  h,
  fill,
  onDrill,
}: {
  bar: PeriodBar;
  x: number;
  baseline: number;
  h: number;
  fill: string;
  onDrill: () => void;
}) {
  const cx = x + SLOT / 2;
  const barX = x + (SLOT - BAR_W) / 2;
  const label = `${bar.label}: ${formatInt(bar.count)} document${bar.count === 1 ? "" : "s"}`;
  return (
    <g
      className="tl-bar"
      role="button"
      tabIndex={0}
      aria-label={`${label}. Open this period.`}
      onClick={onDrill}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onDrill();
        }
      }}
    >
      <title>{label}</title>
      {/* full-slot hit target so even a zero bar is clickable */}
      <rect x={x} y={TOP} width={SLOT} height={baseline - TOP + BOT} fill="transparent" />
      {h > 0 && <rect x={barX} y={baseline - h} width={BAR_W} height={h} fill={fill} stroke="#1c1a17" strokeWidth="1" rx="2" />}
      <text x={cx} y={baseline - h - 8} textAnchor="middle" fontSize="15" fill="#1c1a17" fontFamily="ui-monospace, monospace">
        {formatInt(bar.count)}
      </text>
      <text x={cx} y={baseline + 20} textAnchor="middle" fontSize="14" fill="#1c1a17" fontFamily="ui-sans-serif, system-ui">
        {bar.label}
      </text>
    </g>
  );
}
