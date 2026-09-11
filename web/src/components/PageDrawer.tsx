import { useEffect, useRef } from "react";
import { useEscape } from "../hooks/useKeyboard";
import { chipLabel, shortTitle } from "../lib/format";
import type { EvidenceRow } from "../types";

interface Props {
  row: EvidenceRow | null;
  onClose: () => void;
}

/** Right-side overlay drawer: the page image, the archive.org viewer with a plain
 *  fallback, and an outbound link. Escape or the backdrop closes; focus returns. */
export function PageDrawer({ row, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(null);
  useEscape(row !== null, onClose);

  useEffect(() => {
    if (row) {
      opener.current = document.activeElement;
      closeRef.current?.focus();
    } else if (opener.current instanceof HTMLElement) {
      opener.current.focus();
      opener.current = null;
    }
  }, [row]);

  if (!row) return null;
  return (
    <>
      <div className="backdrop" onClick={onClose} aria-hidden="true" />
      <aside className="drawer p-5" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="drawer-title" className="font-sans font-semibold">
              {shortTitle(row.title, 96)}
            </h2>
            <p className="text-sm text-muted">{chipLabel(row)}</p>
            <p className="font-mono text-xs text-muted">
              {row.item_id} leaf {row.leaf_index}
            </p>
          </div>
          <button ref={closeRef} type="button" className="chip" onClick={onClose} aria-label="Close page drawer">
            Close
          </button>
        </div>
        <img
          src={row.page_image}
          alt={`Page image, ${shortTitle(row.title)}, leaf ${row.leaf_index}`}
          className="mt-4 w-full border border-rule bg-paper"
          loading="eager"
        />
        <div className="mt-4">
          <iframe
            src={row.embed_url}
            title="archive.org page viewer"
            className="w-full h-[60vh] border border-rule bg-paper"
            loading="lazy"
          />
          <p className="mt-2 text-sm text-muted">If the viewer above does not load, the page is available on archive.org.</p>
        </div>
        <a className="chip mt-4" href={row.deep_link} target="_blank" rel="noopener noreferrer">
          Open on archive.org
        </a>
      </aside>
    </>
  );
}
