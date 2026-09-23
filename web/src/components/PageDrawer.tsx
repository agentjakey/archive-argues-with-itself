import { useEffect, useRef, useState } from "react";
import { useEscape } from "../hooks/useKeyboard";
import { chipLabel, dateMethodDetail, shortTitle } from "../lib/format";
import { ocrUncertain } from "../lib/sensitivity";
import { OcrBadge } from "./OcrBadge";
import type { EvidenceRow, ScopeInfo } from "../types";

interface Props {
  row: EvidenceRow | null;
  onClose: () => void;
  source?: ScopeInfo | null;   // the active corpus, for the per-citation source collection
  offline?: boolean;           // kiosk/offline: never fetch a page image live; degrade to a clear state
}

/** Right-side overlay drawer: the page image and provenance. Offline strategy (R1, both scopes):
 *  a page in the local pack shows its scanned image; a page NOT in the pack degrades to a clear
 *  "not on this device" state with the citation and the archive.org deep link -- never a broken
 *  image, an error, or a live fetch. In kiosk/offline mode no page image is fetched from the
 *  network at all; online, a failed load falls back to the same clear state. */
export function PageDrawer({ row, onClose, source, offline = false }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(null);
  const [imgError, setImgError] = useState(false);
  useEscape(row !== null, onClose);

  useEffect(() => {
    setImgError(false);   // a new page starts fresh, so a prior load failure never sticks
  }, [row]);

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
  const inPack = !!row.offline;                          // the page image is in the local offline pack
  const noLiveImage = !inPack && (offline || imgError);  // kiosk/offline, or a failed load: never a broken image
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
            <p className="mt-1 text-sm text-muted">{dateMethodDetail(row)}</p>
            {source?.collection && (
              <p className="text-sm text-muted">
                From the{" "}
                {source.collection_url ? (
                  <a className="linkish" href={source.collection_url} target="_blank" rel="noopener noreferrer">
                    {source.collection}
                  </a>
                ) : (
                  source.collection
                )}{" "}
                collection on archive.org.
              </p>
            )}
            {ocrUncertain(row.ocr_quality) && (
              <p className="mt-1">
                <OcrBadge />
              </p>
            )}
          </div>
          <button ref={closeRef} type="button" className="chip" onClick={onClose} aria-label="Close page drawer">
            Close
          </button>
        </div>

        {inPack ? (
          <>
            <img
              src={row.page_image}
              alt={`Page image, ${shortTitle(row.title)}, leaf ${row.leaf_index}`}
              className="mt-4 w-full border border-rule bg-paper"
              loading="eager"
            />
            <p className="mt-4 text-sm text-muted">
              Showing the scanned page from the local archive. The interactive viewer and the archive.org
              link need the network.
            </p>
          </>
        ) : noLiveImage ? (
          <div className="mt-4 border border-rule bg-paper p-4 text-sm text-muted" role="note">
            The page image is not on this device. The citation above is complete, and the page is available
            on the live site (open it on archive.org below).
          </div>
        ) : (
          <>
            <img
              src={row.page_image}
              alt={`Page image, ${shortTitle(row.title)}, leaf ${row.leaf_index}`}
              className="mt-4 w-full border border-rule bg-paper"
              loading="eager"
              onError={() => setImgError(true)}
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
          </>
        )}
        <a className="chip mt-4" href={row.deep_link} target="_blank" rel="noopener noreferrer">
          Open on archive.org
        </a>
      </aside>
    </>
  );
}
