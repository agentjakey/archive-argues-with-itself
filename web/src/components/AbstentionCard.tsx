import type { Answer } from "../types";
import { UnsupportedRow } from "./UnsupportedRow";

interface Props {
  answer: Answer;
}

/** Same weight and styling as the answer: a left rule and a serif heading, neutral tone. */
export function AbstentionCard({ answer }: Props) {
  const terms = answer.coverage.uncovered_terms;
  return (
    <article className="rule-left" role="status" aria-labelledby="abstain-heading">
      <h2 id="abstain-heading" className="font-serif text-2xl">
        No answer from the record
      </h2>
      <p className="mt-3 max-w-prose leading-relaxed">{answer.abstention_text}</p>
      {terms.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2" aria-label="Terms no passage mentions">
          {terms.map((t) => (
            <span key={t} className="chip cursor-default font-mono text-sm">
              {t}
            </span>
          ))}
        </div>
      )}
      <p className="mt-3 text-sm text-muted">
        {answer.coverage.n_passages} nearest passages from {answer.coverage.n_items}{" "}
        {answer.coverage.n_items === 1 ? "item" : "items"}, {answer.coverage.n_undated} undated
        {answer.coverage.single_source && <span className="tag ml-2">single source</span>}
      </p>
      {answer.cached && <p className="mt-1 text-sm text-muted">served from cache, generated {answer.cached.created_at.slice(0, 10)}</p>}
      <UnsupportedRow items={answer.unsupported} />
    </article>
  );
}
