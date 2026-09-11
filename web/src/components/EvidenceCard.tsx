import { cardId } from "../lib/citations";
import { highlight } from "../lib/highlight";
import { shortTitle, yearLabel } from "../lib/format";
import type { EvidenceRow } from "../types";

interface Props {
  row: EvidenceRow;
  salientTerms: string[];
  pinned: boolean;
  onOpen: (row: EvidenceRow) => void;
  onPin: (row: EvidenceRow) => void;
}

/** Rules, not boxes: a bottom hairline, a 120px scan with a soft shadow, small-caps
 *  tags, Cited as accent text with a short underline, actions as text links. */
export function EvidenceCard({ row, salientTerms, pinned, onOpen, onPin }: Props) {
  const segments = highlight(row.snippet, salientTerms);
  return (
    <article id={cardId(row.passage_id)} className="evidence">
      <button
        type="button"
        className="thumb"
        onClick={() => onOpen(row)}
        aria-label={`Open page scan: ${shortTitle(row.title)}, leaf ${row.leaf_index}`}
      >
        <img
          src={row.page_thumb}
          alt={`Page scan, ${shortTitle(row.title)}, leaf ${row.leaf_index}`}
          loading="lazy"
          decoding="async"
        />
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
          <span className="font-semibold">{yearLabel(row.year)}</span>
          <span className="tag">{row.jurisdiction ?? "unknown"}</span>
          <span className="tag">{(row.doc_type ?? "unknown").replace(/_/g, " ")}</span>
          {row.bm25_rank != null && <span className="tag">lexical</span>}
          {row.dense_rank != null && <span className="tag">semantic</span>}
          {row.cited && <span className="cited">Cited</span>}
        </div>
        <h4 className="mt-1 font-serif text-lg leading-snug">{shortTitle(row.title, 96)}</h4>
        <p className="font-mono text-xs text-muted">
          {row.item_id} leaf {row.leaf_index}
          {row.printed_page ? `, p. ${row.printed_page}` : ""}
        </p>
        <p className="excerpt mt-2">
          {segments.map((s, i) => (s.hit ? <mark key={i}>{s.text}</mark> : <span key={i}>{s.text}</span>))}
        </p>
        <p className="mt-2 text-sm actions">
          <button type="button" className="linkish" onClick={() => onOpen(row)}>
            View page
          </button>
          <span aria-hidden="true"> &middot; </span>
          <button type="button" className="linkish" aria-pressed={pinned} onClick={() => onPin(row)}>
            {pinned ? "Pinned" : "Pin to compare"}
          </button>
          <span aria-hidden="true"> &middot; </span>
          <a className="linkish" href={row.deep_link} target="_blank" rel="noopener noreferrer">
            archive.org
          </a>
        </p>
      </div>
    </article>
  );
}
