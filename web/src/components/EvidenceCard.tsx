import { highlight } from "../lib/highlight";
import { shortTitle, yearLabel } from "../lib/format";
import type { EvidenceRow } from "../types";
import { LegTags } from "./LegTags";

interface Props {
  row: EvidenceRow;
  salientTerms: string[];
  pinned: boolean;
  onOpen: (row: EvidenceRow) => void;
  onPin: (row: EvidenceRow) => void;
  compact?: boolean;
}

/** The page scan is the hero; the excerpt is set in serif; ids and leaves in mono. */
export function EvidenceCard({ row, salientTerms, pinned, onOpen, onPin, compact }: Props) {
  const segments = highlight(row.snippet, salientTerms);
  return (
    <article className={`card flex gap-4 ${row.cited ? "card--cited" : ""} ${compact ? "p-3" : ""}`}>
      <button
        type="button"
        className={`shrink-0 border border-rule bg-paper ${compact ? "w-24" : "w-32 sm:w-40"}`}
        onClick={() => onOpen(row)}
        aria-label={`Open page scan: ${shortTitle(row.title)}, leaf ${row.leaf_index}`}
      >
        <img
          src={row.page_thumb}
          alt={`Page scan, ${shortTitle(row.title)}, leaf ${row.leaf_index}`}
          loading="lazy"
          decoding="async"
          className="block w-full h-auto"
        />
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
          <span className="font-sans font-semibold">{yearLabel(row.year)}</span>
          <span className="text-muted">{row.jurisdiction ?? "unknown"}</span>
          <span className="text-muted">{(row.doc_type ?? "unknown").replace(/_/g, " ")}</span>
          {row.cited && <span className="badge badge--cited">Cited</span>}
          <LegTags row={row} />
        </div>
        <h4 className="mt-1 font-sans">{shortTitle(row.title, 96)}</h4>
        <p className="font-mono text-xs text-muted">
          {row.item_id} leaf {row.leaf_index}
          {row.printed_page ? `, p. ${row.printed_page}` : ""}
        </p>
        {!compact && (
          <p className="excerpt mt-2 text-[0.95em]">
            {segments.map((s, i) => (s.hit ? <mark key={i}>{s.text}</mark> : <span key={i}>{s.text}</span>))}
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className="chip" onClick={() => onOpen(row)}>
            View page
          </button>
          <button type="button" className="chip" aria-pressed={pinned} onClick={() => onPin(row)}>
            {pinned ? "Pinned" : "Pin to compare"}
          </button>
          <a className="chip" href={row.deep_link} target="_blank" rel="noopener noreferrer">
            Open on archive.org
          </a>
        </div>
      </div>
    </article>
  );
}
