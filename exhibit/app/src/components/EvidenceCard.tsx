// The evidence card: a receipt with the quote, the date, the verdict and a QR code to the original
// page on archive.org. It is printed with the browser's own print (the kiosk prints silently to its
// receipt printer); the print stylesheet sizes it for 80 mm paper. The QR is a static SVG path made
// when the deck was built, so it needs no library and no network.
import type { Page, Quote } from "../lib/deck";
import type { Strings } from "../lib/strings";

type Props = { page: Page; quote: Quote | undefined; verdict: string; t: Strings; onPrint?: () => void; canPrint: boolean };

export function EvidenceCard({ page, quote, verdict, t, onPrint, canPrint }: Props) {
  const year = page.catalogue_date.year;
  return (
    <>
      {canPrint && (
        <button
          type="button"
          className="btn"
          onClick={() => {
            onPrint?.();
            window.print();
          }}
        >
          {t.card.print}
        </button>
      )}
      <article className="evidence-card" aria-hidden="true">
        <h2>{t.card.heading}</h2>
        <p className="card-row">
          <strong>{t.card.verdict}:</strong> {verdict}
        </p>
        {quote && (
          <p className="card-row">
            <strong>{t.card.quote}:</strong> "{quote.text}"
          </p>
        )}
        <p className="card-row">
          <strong>{t.card.source}:</strong> {page.title}
          {page.issuer ? `, ${page.issuer}` : ""}
        </p>
        {year !== null && (
          <p className="card-row">
            <strong>{t.card.date}:</strong> {year}
          </p>
        )}
        {page.qr && (
          <svg className="card-qr" viewBox={`0 0 ${page.qr.size} ${page.qr.size}`} role="img" aria-label={t.card.scan}>
            <rect width={page.qr.size} height={page.qr.size} fill="#fff" />
            <path d={page.qr.path} fill="#000" />
          </svg>
        )}
        <p className="card-row card-small">{t.card.scan}</p>
        <p className="card-row card-small">{page.details_url}</p>
        <p className="card-row card-small">{t.privacy}</p>
        <p className="card-row card-small">{t.card.footer}</p>
      </article>
    </>
  );
}
