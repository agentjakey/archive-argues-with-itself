import { useState } from "react";
import { useEscape } from "../hooks/useKeyboard";
import { highlight } from "../lib/highlight";
import { shortTitle, yearLabel } from "../lib/format";
import { ocrUncertain } from "../lib/sensitivity";
import { OcrBadge } from "./OcrBadge";
import type { EvidenceRow } from "../types";

interface Props {
  a: EvidenceRow;
  b: EvidenceRow;
  salientTerms: string[];
  caption?: string;                 // a story's "what changed" narrative, when opened from a story
  onOpen: (row: EvidenceRow) => void;   // open the offline-safe PageDrawer for a column
  onUnpin: (row: EvidenceRow) => void;
  onClose: () => void;
}

const EXCERPT_MAX = 220;

/** One legible cited line: the passage's own OCR text, trimmed to a scannable excerpt
 *  at a word boundary. The full page is one tap away in the drawer. Never invented. */
function excerpt(text: string): string {
  const s = (text ?? "").replace(/\s+/g, " ").trim();
  if (s.length <= EXCERPT_MAX) return s;
  const cut = s.slice(0, EXCERPT_MAX);
  const sp = cut.lastIndexOf(" ");
  return `${(sp > 80 ? cut.slice(0, sp) : cut).trimEnd()}...`;
}

/** Two eras side by side, the change legible at a glance: big years, a "then / later"
 *  tag, one cited excerpt each with the query terms marked, and the scanned page one tap
 *  away via the existing (offline-safe) PageDrawer. The excerpt is the source text
 *  verbatim; the caption, when present, is the author's framing, not a generated claim. */
export function CompareView({ a, b, salientTerms, caption, onOpen, onUnpin, onClose }: Props) {
  useEscape(true, onClose);
  const [copied, setCopied] = useState(false);
  const title = `${yearLabel(a.year)} vs ${yearLabel(b.year)}`;
  const bothDated = a.year != null && b.year != null && a.year !== b.year;

  const eraTag = (row: EvidenceRow, other: EvidenceRow): string | null => {
    if (!bothDated) return null;
    return (row.year as number) < (other.year as number) ? "Then" : "Later";
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const columns: [EvidenceRow, EvidenceRow] = [a, b];

  return (
    <section className="card mt-6" aria-labelledby="compare-title">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <p className="font-sans text-xs uppercase tracking-wide text-muted">What the record said, then and later</p>
          <h2 id="compare-title" className="font-serif text-3xl">
            {title}
          </h2>
        </div>
        <div className="flex gap-2">
          <button type="button" className="chip" onClick={copyLink} aria-live="polite">
            {copied ? "Link copied" : "Copy link"}
          </button>
          <button type="button" className="chip" onClick={onClose} aria-label="Close compare view">
            Close
          </button>
        </div>
      </div>

      {caption && (
        <div className="mt-3 border-l-2 border-ink pl-3 max-w-prose">
          <p className="font-sans text-xs uppercase tracking-wide text-muted">What changed</p>
          <p className="mt-1 leading-relaxed">{caption}</p>
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-6">
        {columns.map((row, i) => {
          const tag = eraTag(row, columns[1 - i]);
          return (
            <div key={row.passage_id} className="min-w-0">
              <div className="flex items-baseline gap-2 border-b border-rule pb-1">
                {tag && <span className="tag">{tag}</span>}
                <span className="font-serif text-2xl">{yearLabel(row.year)}</span>
                <span className="text-sm text-muted">{row.jurisdiction ?? "unknown"}</span>
                {row.offline && (
                  <span className="tag ml-auto" title="Served from the local scan pack, no network">
                    local scan
                  </span>
                )}
              </div>
              <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
                {shortTitle(row.title, 96)}
                {ocrUncertain(row.ocr_quality) && <OcrBadge />}
              </p>
              <blockquote className="excerpt mt-3 border-l-2 border-rule pl-3">
                {highlight(excerpt(row.snippet), salientTerms).map((s, j) =>
                  s.hit ? <mark key={j}>{s.text}</mark> : <span key={j}>{s.text}</span>,
                )}
              </blockquote>
              <button
                type="button"
                className="mt-3 block w-full cursor-pointer border-0 bg-transparent p-0 text-left"
                onClick={() => onOpen(row)}
                aria-label={`View the scanned page for ${yearLabel(row.year)}`}
              >
                <img
                  src={row.page_image}
                  alt={`Page image, ${shortTitle(row.title)}, leaf ${row.leaf_index}`}
                  loading="lazy"
                  className="w-full border border-rule bg-paper hover:border-ink"
                />
              </button>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" className="chip border-ink bg-ink text-paper" onClick={() => onOpen(row)}>
                  View the scanned page
                </button>
                <a className="chip" href={row.deep_link} target="_blank" rel="noopener noreferrer">
                  archive.org
                </a>
                <button type="button" className="chip" onClick={() => onUnpin(row)}>
                  Remove
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
