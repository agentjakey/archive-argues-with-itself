import { formatInt, formatShare, windowLabel } from "../lib/format";
import type { ScopeInfo, YearWindow } from "../types";

interface Props {
  scope: ScopeInfo | null;
}

/** Per-scope corpus facts for the header strip. Every figure is read from the ACTIVE scope
 *  (GET /scopes) -- the same source the subtitle uses -- so the band and the subtitle can never
 *  disagree, and no pilot value can render under another corpus. When the active scope has not
 *  loaded, nothing is shown (never another scope's number as a fallback). */
export function CorpusStrip({ scope }: Props) {
  const c = scope?.composition ?? null;
  const cov = scope?.coverage_window ?? null;
  const hasWindow = !!cov && cov.min_year != null && cov.max_year != null;
  return (
    <div className="mt-4 border-t border-b border-rule py-3">
      {scope && c ? (
        <>
          <dl className="flex flex-wrap gap-x-8 gap-y-2" aria-label="Corpus facts">
            <Figure value={formatInt(scope.item_count)} label="items" />
            <Figure value={formatInt(c.passages)} label="passages" />
            <Figure
              value={hasWindow ? windowLabel({ window: cov! }) : windowLabel({ window: c.dated_span })}
              label="coverage window"
            />
            <Figure value={formatShare(c.undated.item_share)} label="of items undated" />
            <Figure value={formatShare(c.jurisdiction_unknown_share)} label="jurisdiction unknown" />
          </dl>
          <p className="mt-2 text-sm text-muted">{spanNote(hasWindow ? cov : null, c.dated_span)}</p>
          {c.jurisdiction_is_floor && (
            <p className="mt-1 text-sm text-muted">
              Jurisdiction is an issuer-derived proxy, a floor, not per-province coverage.
            </p>
          )}
        </>
      ) : (
        <p className="text-sm text-muted" aria-live="polite">
          Loading corpus facts.
        </p>
      )}
      <p className="mt-2 text-sm text-muted">
        <span className="cited mr-2">Cited</span>= the passage exists, was retrieved for this question, and resolves
        to a page on archive.org
      </p>
    </div>
  );
}

/** The one honest date-span line, per scope: when the displayed window is clamped inside the true
 *  dated span (the pilot, shown 1960-2009 though catalog dates run wider), disclose the true span;
 *  otherwise (microlog, shown unclamped) just state it. Never restates another scope's numbers. */
function spanNote(cov: YearWindow | null, span: YearWindow): string {
  const base = "Early and late dates are catalog metadata and may not equal the publication year.";
  if (span.min_year == null || span.max_year == null) return base;
  const spanStr = `${span.min_year} to ${span.max_year}`;
  if (cov && cov.min_year != null && cov.max_year != null && (span.min_year < cov.min_year || span.max_year > cov.max_year)) {
    return `Shown clamped to ${cov.min_year}-${cov.max_year}; dated items actually span ${spanStr}. ${base}`;
  }
  return `Dated items span ${spanStr}. ${base}`;
}

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col">
      <dd className="font-serif text-xl m-0">{value}</dd>
      <dt className="text-sm text-muted">{label}</dt>
    </div>
  );
}
