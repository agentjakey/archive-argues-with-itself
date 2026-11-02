// The evidence card: a receipt with the quote, the date, the verdict and a QR code to the original
// page on archive.org. The chronicle shows it on screen; printing uses the browser's own print (the
// kiosk prints silently to its receipt printer) and the print stylesheet keeps only the card, sized
// for 80 mm paper. The QR is a static SVG path made when the deck was built, so it needs no library
// and no network.
import type { Page, Quote } from "../lib/deck";
import type { Strings } from "../lib/strings";

type Props = { page: Page; quote: Quote | undefined; verdict: string; status: string; t: Strings };

export function EvidenceCard({ page, quote, verdict, status, t }: Props) {
  const year = page.catalogue_date.year;
  return (
    <article className="evidence-card" aria-label={t.card.heading}>
      <h3 className="card-title">{t.card.heading}</h3>
      {quote && <p className="card-quote">"{quote.text}"</p>}
      <dl className="card-rows">
        <div>
          <dt>{t.card.verdict}</dt>
          <dd>{verdict}</dd>
        </div>
        <div>
          <dt>{t.card.source}</dt>
          <dd>
            {page.title}
            {page.issuer && page.issuer !== "unknown" ? `, ${page.issuer}` : ""}
          </dd>
        </div>
        {year !== null && (
          <div>
            <dt>{t.card.date}</dt>
            <dd>{year}</dd>
          </div>
        )}
      </dl>
      {page.qr && (
        <svg className="card-qr" viewBox={`0 0 ${page.qr.size} ${page.qr.size}`} role="img" aria-label={t.card.scan}>
          <rect width={page.qr.size} height={page.qr.size} fill="#fff" />
          <path d={page.qr.path} fill="#000" />
        </svg>
      )}
      <p className="card-small">{t.card.scan}</p>
      <p className="card-small card-url">{page.details_url}</p>
      <p className="card-small">{status}</p>
      <p className="card-small">{t.privacy}</p>
      <p className="card-small">{t.card.footer}</p>
    </article>
  );
}
