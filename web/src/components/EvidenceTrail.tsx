import { useCallback, useState } from "react";
import { groupByDecade } from "../lib/format";
import type { EvidenceRow } from "../types";
import { DecadeTimeline } from "./DecadeTimeline";
import { EvidenceCard } from "./EvidenceCard";

interface Props {
  rows: EvidenceRow[];
  salientTerms: string[];
  pinned: string[];
  heading: string;
  matched: Record<string, number> | null;   // corpus passages matching the question's terms, by decade
  onOpen: (row: EvidenceRow) => void;
  onPin: (row: EvidenceRow) => void;
}

const laneId = (key: string) => `lane-${key.replace(/[^a-z0-9]/gi, "-")}`;

/** Vertical timeline grouped by decade; fixed lanes always render (empty ones as
 *  one muted line) so absence is visible; the undated lane is always last. */
export function EvidenceTrail({ rows, salientTerms, pinned, heading, matched, onOpen, onPin }: Props) {
  const lanes = groupByDecade(rows);
  const [active, setActive] = useState<string | null>(null);
  const jump = useCallback((key: string) => {
    setActive(key);
    document.getElementById(laneId(key))?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);
  return (
    <section aria-labelledby="trail-heading" className="mt-10">
      <h2 id="trail-heading" className="font-serif text-2xl">
        {heading}
      </h2>
      <DecadeTimeline
        lanes={[...lanes.entries()].map(([key, list]) => ({
          key,
          retrieved: list.length,
          matched: matched ? matched[key] ?? 0 : null,
        }))}
        active={active}
        onJump={jump}
      />
      <ol className="mt-4" data-testid="lanes">
        {[...lanes.entries()].map(([decade, list]) => (
          <li key={decade} id={laneId(decade)} className="lane" data-empty={list.length === 0}>
            {list.length === 0 ? (
              <h3 className="lane-heading text-muted scroll-mt-24">
                {decade} <span className="font-mono text-xs">(0)</span> no passages retrieved
              </h3>
            ) : (
              <>
                <h3 className="lane-heading scroll-mt-24">
                  {decade} <span className="font-mono text-xs text-muted">({list.length})</span>
                </h3>
                <div>
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
              </>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
