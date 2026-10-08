import { useCallback, useState } from "react";
import { groupByDecade } from "../lib/format";
import type { EvidenceRow, ScopeInfo } from "../types";
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
  source?: ScopeInfo | null;   // the active corpus, for per-citation source collection
}

const laneId = (key: string) => `lane-${key.replace(/[^a-z0-9]/gi, "-")}`;

/** Vertical timeline grouped by decade; fixed lanes always render (empty ones as
 *  one muted line) so absence is visible; the undated lane is always last. */
export function EvidenceTrail({ rows, salientTerms, pinned, heading, matched, onOpen, onPin, source }: Props) {
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
      <p className="mt-2 text-sm text-muted">
        Legend: <span className="text-ink">retrieved</span> is passages returned for your question;{" "}
        <span className="text-ink">matched</span> is passages anywhere in the corpus that mention your terms.
      </p>
      <details className="mt-2">
        <summary className="cursor-pointer text-sm text-muted">What these labels mean</summary>
        <ul className="mt-2 space-y-1.5 text-sm leading-snug max-w-prose">
          <li><span className="cited">Cited</span> <span className="text-muted">used in the answer above: the passage exists, was retrieved for this question, and links to a real page on archive.org.</span></li>
          <li><span className="tag-note">not sent to the model</span> <span className="text-muted">retrieved into the pool, but not among the passages the model was given.</span></li>
          <li><span className="tag">date from metadata</span> / <span className="tag">date from the title</span> <span className="text-muted">how the item's date was resolved; recorded, never guessed.</span></li>
          <li><span className="text-muted"><span className="text-ink">jurisdiction</span> the issuer's jurisdiction, a proxy and a floor, not a verified per-item claim; shown only when the issuer was identified.</span></li>
          <li><span className="text-muted"><span className="text-ink">uncertain OCR</span> the scan's text may be garbled; open the page to read it.</span></li>
        </ul>
      </details>
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
                      source={source}
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
