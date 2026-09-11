import { formatInt, formatShare } from "../lib/format";
import type { CoverageResponse } from "../types";

interface Props {
  coverage: CoverageResponse | null;
  undatedShare: number | null;
  explanation?: boolean;
}

/** Term-by-decade grid of lexical passage counts (zeros shown), a baseline row,
 *  a jurisdiction row, and the fixed line on what this cannot tell you. */
export function CoveragePanel({ coverage, undatedShare, explanation }: Props) {
  const share = undatedShare == null ? "45%" : formatShare(undatedShare);
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
        What this cannot tell you: post-2009 OCR is effectively absent; {share} of passages carry no date; counts are
        lexical matches, not relevance.
      </p>
    </section>
  );
}
