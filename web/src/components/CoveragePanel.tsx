import { formatInt, formatShare } from "../lib/format";
import type { CoverageResponse, ScopeInfo } from "../types";

interface Props {
  coverage: CoverageResponse | null;
  undatedShare: number | null;
  explanation?: boolean;
  scope?: ScopeInfo | null;
}

/** Term-by-decade grid of lexical passage counts (zeros shown), a baseline row,
 *  a jurisdiction row, and the fixed line on what this cannot tell you. The caption is per-scope:
 *  the temporal ceiling comes from the active scope's coverage window and the undated share from
 *  the active scope; a share that has not loaded is omitted, never faked as another scope's number. */
export function CoveragePanel({ coverage, undatedShare, explanation, scope }: Props) {
  const share = undatedShare == null ? null : formatShare(undatedShare);
  const ceiling = scope?.coverage_window?.max_year ?? null;
  const reach = ceiling != null ? `the record is effectively absent past ${ceiling}` : "post-2009 OCR is effectively absent";
  const dateClause = share ? `${share} of passages carry no date` : "some passages carry no date";
  return (
    <section className="mt-8" aria-labelledby="coverage-heading">
      <h2 id="coverage-heading" className="font-serif text-2xl">
        {explanation ? "Why the record is thin here" : "Coverage"}
      </h2>
      {!coverage ? (
        <p className="mt-2 text-sm text-muted" aria-live="polite">
          Counting lexical matches across the corpus.
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="grid-table" data-testid="coverage-grid">
            <thead>
              <tr>
                <th scope="col">passages matching</th>
                {coverage.by_decade.map((d) => (
                  <th key={d.decade} scope="col">
                    {d.decade}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {coverage.salient_terms.map((term) => (
                <tr key={term}>
                  <th scope="row" className="font-mono">
                    {term}
                  </th>
                  {coverage.by_decade.map((d) => (
                    <td key={d.decade} className={d.terms[term] ? "" : "text-muted"}>
                      {formatInt(d.terms[term] ?? 0)}
                    </td>
                  ))}
                </tr>
              ))}
              <tr className="baseline">
                <th scope="row">all passages, current filters</th>
                {coverage.by_decade.map((d) => (
                  <td key={d.decade}>{formatInt(d.passages)}</td>
                ))}
              </tr>
            </tbody>
          </table>
          <p className="mt-3 text-sm">
            <span className="tag">by jurisdiction</span>{" "}
            {coverage.by_jurisdiction.map((j, i) => (
              <span key={j.jurisdiction}>
                {i > 0 && " / "}
                {j.jurisdiction} <span className="font-mono">{formatInt(j.passages)}</span>
              </span>
            ))}
          </p>
        </div>
      )}
      <p className="mt-3 text-sm text-muted max-w-prose">
        What this cannot tell you: {reach}; {dateClause}; counts are lexical matches, not relevance.
      </p>
    </section>
  );
}
