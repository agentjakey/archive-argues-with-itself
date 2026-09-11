import { formatInt } from "../lib/format";

export interface TimelineLane {
  key: string;
  retrieved: number;
  matched: number | null; // null until /coverage arrives
}

interface Props {
  lanes: TimelineLane[];
  active: string | null;
  onJump: (key: string) => void;
}

/** A drawn timeline: one rule, a tick per decade (then undated), the label above,
 *  two small counts below. Active decade bold, zero decades muted. */
export function DecadeTimeline({ lanes, active, onJump }: Props) {
  return (
    <nav className="timeline" aria-label="Decades">
      <ol className="timeline-track">
        {lanes.map((l) => {
          const zero = l.retrieved === 0;
          const isActive = l.key === active;
          return (
            <li key={l.key} className="timeline-tick">
              <button
                type="button"
                className={`timeline-btn ${zero ? "is-zero" : ""} ${isActive ? "is-active" : ""}`}
                aria-current={isActive ? "true" : undefined}
                onClick={() => onJump(l.key)}
                aria-label={`${l.key}: ${l.retrieved} retrieved, ${l.matched == null ? "matching count pending" : `${l.matched} matching in corpus`}`}
              >
                <span className="timeline-label">{l.key}</span>
                <span className="timeline-mark" aria-hidden="true" />
                <span className="timeline-counts" aria-hidden="true">
                  <span>
                    <b>{l.retrieved}</b> retrieved
                  </span>
                  <span>{l.matched == null ? "..." : formatInt(l.matched)} matched</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
