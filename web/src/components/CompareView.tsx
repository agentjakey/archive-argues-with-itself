import { useState } from "react";
import { useEscape } from "../hooks/useKeyboard";
import { highlight } from "../lib/highlight";
import { shortTitle, yearLabel } from "../lib/format";
import type { EvidenceRow } from "../types";

interface Props {
  a: EvidenceRow;
  b: EvidenceRow;
  salientTerms: string[];
  onUnpin: (row: EvidenceRow) => void;
  onClose: () => void;
}

/** Two pinned passages side by side: year and jurisdiction as the column header,
 *  excerpt on top, page image below, deep link under each. Title "1972 vs 1998". */
export function CompareView({ a, b, salientTerms, onUnpin, onClose }: Props) {
  useEscape(true, onClose);
  const [copied, setCopied] = useState(false);
  const title = `${yearLabel(a.year)} vs ${yearLabel(b.year)}`;

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className="card mt-6" aria-labelledby="compare-title">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="compare-title" className="font-serif text-2xl">
          {title}
        </h2>
        <div className="flex gap-2">
          <button type="button" className="chip" onClick={copyLink} aria-live="polite">
            {copied ? "Link copied" : "Copy link"}
          </button>
          <button type="button" className="chip" onClick={onClose} aria-label="Close compare view">
            Close
          </button>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-6">
        {[a, b].map((row) => (
          <div key={row.passage_id} className="min-w-0">
            <h3 className="font-sans font-semibold border-b border-rule pb-1">
              {yearLabel(row.year)} <span className="text-muted font-normal">{row.jurisdiction ?? "unknown"}</span>
            </h3>
            <p className="text-sm text-muted mt-1">{shortTitle(row.title, 96)}</p>
            <p className="excerpt mt-3">
              {highlight(row.snippet, salientTerms).map((s, i) =>
                s.hit ? <mark key={i}>{s.text}</mark> : <span key={i}>{s.text}</span>,
              )}
            </p>
            <img
              src={row.page_image}
              alt={`Page image, ${shortTitle(row.title)}, leaf ${row.leaf_index}`}
              loading="lazy"
              className="mt-3 w-full border border-rule bg-paper"
            />
            <div className="mt-3 flex flex-wrap gap-2">
              <a className="chip" href={row.deep_link} target="_blank" rel="noopener noreferrer">
                Open on archive.org
              </a>
              <button type="button" className="chip" onClick={() => onUnpin(row)}>
                Unpin
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
