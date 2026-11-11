// One real page: the scanned image from archive.org's image service when the screen is online, and
// always the page's own text with quoted lines marked (and years hidden on a When Was This? card).
// The image is never re-hosted; when it cannot load, the text stands on its own and says why.
import { useState } from "react";
import type { Page } from "../lib/deck";
import { segment } from "../lib/text";
import type { Strings } from "../lib/strings";

type Props = {
  page: Page;
  label: string;
  t: Strings;
  marks?: { id: string; quote: string }[];
  masks?: [number, number][];
  hideTitleYears?: [number, number][];
  showImage?: boolean;
  activeMark?: string | null;
};

export function PageView({ page, label, t, marks = [], masks = [], hideTitleYears, showImage = true, activeMark }: Props) {
  const [imageFailed, setImageFailed] = useState(false);
  const [imageOpen, setImageOpen] = useState(false);
  const segments = segment(page.text, marks, masks);
  const title = hideTitleYears ? segment(page.title, [], hideTitleYears) : null;
  // The scan's alt text names the page too, so it hides the same years as the title (a screen reader
  // would otherwise read the answer out before the guess).
  const altTitle = title ? title.map((s) => (s.kind === "mask" ? t.when.hidden : s.text)).join("") : page.title;
  return (
    <section className="page" aria-label={label}>
      <header className="page-head">
        <span className="page-label">{label}</span>
        <h3 className="page-title">
          {title
            ? title.map((s, i) => (s.kind === "mask" ? <span key={i} className="mask" role="img" aria-label={t.when.hidden}>{"\u2588\u2588\u2588\u2588"}</span> : <span key={i}>{s.text}</span>))
            : page.title}
        </h3>
        {page.issuer && <p className="page-issuer">{page.issuer}</p>}
      </header>
      {showImage && (
        <div className="page-image-row">
          <button type="button" className="btn btn-quiet" aria-expanded={imageOpen} onClick={() => setImageOpen(!imageOpen)}>
            {imageOpen ? t.hidePage : t.showPage}
          </button>
          {imageOpen && !imageFailed && (
            <img
              className="page-image"
              src={page.image_url}
              alt={t.imageAlt(altTitle, page.leaf)}
              loading="lazy"
              referrerPolicy="no-referrer"
              onError={() => setImageFailed(true)}
            />
          )}
          {imageOpen && imageFailed && <p className="note" role="status">{t.imageOffline}</p>}
        </div>
      )}
      <div
        className="page-text"
        lang={page.language?.startsWith("fr") ? "fr" : "en"}
        tabIndex={0}
        role="region"
        aria-label={`${label}: ${t.pageText}`}
      >
        {segments.map((s, i) => {
          if (s.kind === "mask") return <span key={i} className="mask" role="img" aria-label={t.when.hidden}>{"\u2588\u2588\u2588\u2588"}</span>;
          if (s.kind === "mark")
            return (
              <mark key={i} className={s.quoteId === activeMark ? "mark mark-active" : "mark"} data-quote={s.quoteId}>
                {s.text}
              </mark>
            );
          return <span key={i}>{s.text}</span>;
        })}
      </div>
      <p className="note">
        {t.textNote} {page.text_cut ? t.textCut : null}
      </p>
    </section>
  );
}
