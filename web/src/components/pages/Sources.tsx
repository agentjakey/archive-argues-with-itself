import { formatInt, windowNote } from "../../lib/format";
import { outOfWindowCount } from "../../lib/timeline";
import type { ScopeInfo, YearWindow } from "../../types";
import { Page } from "./Page";

function pct(n: number, total: number): string {
  return total ? `${Math.round((n / total) * 100)}%` : "0%";
}

function spanLabel(w: YearWindow): string {
  if (w.min_year == null || w.max_year == null) return "undated only";
  return `${w.min_year} to ${w.max_year}`;
}

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col">
      <dd className="font-serif text-xl m-0">{value}</dd>
      <dt className="text-sm text-muted">{label}</dt>
    </div>
  );
}

/** One corpus's composition, every figure read live from that corpus's own databases via
 *  /scopes (never hardcoded). The jurisdiction breakdown is shown as a floor, never as full
 *  provincial coverage. */
function ScopeComposition({ scope }: { scope: ScopeInfo }) {
  const c = scope.composition;
  if (!c) return null;
  const ocrTotal = c.ocr.high + c.ocr.medium + c.ocr.low;
  return (
    <section className="mt-8 border-t border-rule pt-5" aria-label={`${scope.label} composition`}>
      <h3 className="font-serif text-xl">{scope.label}</h3>
      {scope.blurb && <p className="mt-1 text-sm text-muted">{scope.blurb}</p>}
      <p className="mt-2">
        Source:{" "}
        {scope.collection && scope.collection_url ? (
          <a className="linkish" href={scope.collection_url} target="_blank" rel="noopener noreferrer">
            {scope.collection} on archive.org
          </a>
        ) : (
          "unknown"
        )}
        {scope.collections.length > 1 && (
          <span className="text-muted"> (plus {scope.collections.length - 1} sibling collections)</span>
        )}
      </p>

      <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-2">
        <Figure value={formatInt(scope.item_count)} label="items" />
        <Figure value={formatInt(c.passages)} label="passages" />
        <Figure value={spanLabel(c.dated_span)} label="dated items span" />
        <Figure value={pct(c.undated.items, scope.item_count)} label="of items undated" />
      </dl>
      <p className="mt-2 text-sm text-muted">{windowNote(c.window, outOfWindowCount(c.by_period))}</p>
      <p className="mt-1 text-sm text-muted">
        Undated: {formatInt(c.undated.items)} of {formatInt(scope.item_count)} items (
        {pct(c.undated.items, scope.item_count)}); the same documents are{" "}
        {pct(c.undated.passages, c.passages)} of passages. The headline undated share is item-weighted; the
        passage figure is labelled as such and is never the headline.
      </p>

      <h4 className="mt-4 tag">OCR quality, passage-weighted</h4>
      <p className="text-sm">
        high {pct(c.ocr.high, ocrTotal)} &middot; medium {pct(c.ocr.medium, ocrTotal)} &middot; low{" "}
        {pct(c.ocr.low, ocrTotal)}
      </p>
      <div className="mt-1 flex h-3 w-full max-w-md overflow-hidden border border-rule" aria-hidden="true">
        <span style={{ width: pct(c.ocr.high, ocrTotal) }} className="bg-ink" />
        <span style={{ width: pct(c.ocr.medium, ocrTotal) }} className="bg-muted" />
        <span style={{ width: pct(c.ocr.low, ocrTotal) }} className="bg-rule" />
      </div>
      <p className="mt-1 text-sm text-muted">
        A surface proxy (dictionary hits, character ratios), the same one retrieval down-weights by, not a
        semantic-correctness measure.
      </p>

      <h4 className="mt-4 tag">Jurisdiction, an issuer proxy and a floor</h4>
      <ul className="mt-1 text-sm space-y-0.5">
        {c.jurisdictions.map((j) => (
          <li key={j.name}>
            {j.name}: {pct(j.items, scope.item_count)} ({formatInt(j.items)} items)
          </li>
        ))}
      </ul>
      <p className="mt-1 text-sm text-muted">
        Jurisdiction is derived from the issuer, so it is a floor, not full coverage:{" "}
        {Math.round(c.jurisdiction_unknown_share * 100)}% of items are unknown.
        {c.jurisdiction_is_floor
          ? " These per-province counts are a floor: an item is attributed only when its issuer metadata names the jurisdiction, so a body that does not name its province stays unknown rather than being guessed. Not verified per-province coverage."
          : ""}
      </p>

      <h4 className="mt-4 tag">How dates were resolved</h4>
      <p className="text-sm">
        {formatInt(c.date_method.exact ?? 0)} from catalogue metadata, {formatInt(c.date_method.title_extracted ?? 0)}{" "}
        from the document title, {formatInt(c.date_method.unknown ?? 0)} undated. No date here is estimated or
        inferred; a title-read date is the year printed on the document itself.
      </p>
    </section>
  );
}

/** The sources and provenance view: per served corpus, its real composition, with working
 *  archive.org links. Reads /scopes; renders nothing scope-specific until it loads. */
export function SourcesPage({ scopes }: { scopes: ScopeInfo[] | null }) {
  return (
    <Page title="Sources and provenance">
      <p>
        Each corpus here is built from existing Internet Archive scans and their OCR. Every figure below is
        read live from that corpus's own databases through the app, not hardcoded. Every answer and every
        citation links to the page on archive.org, so you can read the source for yourself.
      </p>
      {scopes && scopes.length > 0 ? (
        scopes.map((s) => <ScopeComposition key={s.name} scope={s} />)
      ) : (
        <p className="text-muted" aria-live="polite">
          Loading corpus composition.
        </p>
      )}
    </Page>
  );
}
