import { useCallback } from "react";
import { groupByDecade } from "../lib/format";
import type { EvidenceRow } from "../types";
import { DecadeRail } from "./DecadeRail";
import { EvidenceCard } from "./EvidenceCard";

interface Props {
  rows: EvidenceRow[];
  salientTerms: string[];
  pinned: string[];
  heading: string;
  onOpen: (row: EvidenceRow) => void;
  onPin: (row: EvidenceRow) => void;
}

const laneId = (key: string) => `lane-${key.replace(/[^a-z0-9]/gi, "-")}`;

/** Vertical timeline grouped by decade; fixed lanes always render (empty ones
 *  greyed) so absence is visible; the undated lane is always last. */
export function EvidenceTrail({ rows, salientTerms, pinned, heading, onOpen, onPin }: Props) {
  const lanes = groupByDecade(rows);
  const jump = useCallback((key: string) => {
    document.getElementById(laneId(key))?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);
  return (
    <section aria-labelledby="trail-heading" className="mt-8">
      <h2 id="trail-heading" className="font-sans text-sm uppercase tracking-wide text-muted">
        {heading}
      </h2>
      <DecadeRail lanes={[...lanes.entries()].map(([key, list]) => ({ key, count: list.length }))} onJump={jump} />
      <ol className="mt-3 border-l border-rule pl-5 space-y-8" data-testid="lanes">
        {[...lanes.entries()].map(([decade, list]) => (
          <li key={decade} id={laneId(decade)} className={list.length ? "" : "text-muted"} data-empty={list.length === 0}>
            <h3 className="font-sans font-semibold -ml-5 pl-5 relative scroll-mt-16">
              <span
                className={`absolute -left-[5px] top-2 h-2 w-2 rounded-full ${list.length ? "bg-ink" : "border border-rule bg-paper"}`}
                aria-hidden="true"
              />
              {decade}
              <span className="ml-2 font-mono text-xs text-muted">({list.length})</span>
            </h3>
            {list.length === 0 ? (
              <p className="mt-2 text-sm">no passages retrieved for this lane</p>
            ) : (
              <div className="mt-3 space-y-3">
                {list.map((row) => (
                  <EvidenceCard
                    key={row.passage_id}
                    row={row}
                    salientTerms={salientTerms}
                    pinned={pinned.includes(row.passage_id)}
                    onOpen={onOpen}
                    onPin={onPin}
                  />
                ))}
              </div>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
