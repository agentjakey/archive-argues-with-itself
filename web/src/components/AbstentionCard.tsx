import type { Answer } from "../types";
import { UnsupportedRow } from "./UnsupportedRow";

interface Props {
  answer: Answer;
}

/** Same visual weight as the answer card, neutral tone, never error styling. */
export function AbstentionCard({ answer }: Props) {
  const terms = answer.coverage.uncovered_terms;
  return (
    <article className="card" role="status" aria-labelledby="abstain-heading">
      <h2 id="abstain-heading" className="font-sans text-sm uppercase tracking-wide text-muted">
        No answer from the record
      </h2>
      <p className="mt-3 max-w-prose leading-relaxed">{answer.abstention_text}</p>
      {terms.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2" aria-label="Terms no passage mentions">
          {terms.map((t) => (
            <span key={t} className="chip cursor-default font-mono text-xs">
              {t}
            </span>
          ))}
        </div>
      )}
      <p className="mt-3 text-sm text-muted">
        {answer.coverage.n_passages} nearest passages from {answer.coverage.n_items}{" "}
        {answer.coverage.n_items === 1 ? "item" : "items"}, {answer.coverage.n_undated} undated
        {answer.coverage.single_source && <span className="badge ml-2">single source</span>}
      </p>
      <UnsupportedRow items={answer.unsupported} />
    </article>
  );
}
