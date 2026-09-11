import { useMemo } from "react";
import { numberCitations } from "../lib/citations";
import type { Answer, EvidenceRow } from "../types";
import { CitationMark } from "./CitationMark";
import { Sources } from "./Sources";
import { UnsupportedRow } from "./UnsupportedRow";

interface Props {
  answer: Answer;
  byId: Map<string, EvidenceRow>;
  onOpen: (row: EvidenceRow) => void;
}

function cachedLine(answer: Answer): string | null {
  if (!answer.cached) return null;
  const d = new Date(answer.cached.created_at);
  return `served from cache, generated ${isNaN(d.getTime()) ? answer.cached.created_at : d.toLocaleDateString("en-CA")}`;
}

/** No box: a left rule, serif heading, marks [n] beside each claim, Sources below. */
export function AnswerCard({ answer, byId, onOpen }: Props) {
  const numbered = useMemo(() => numberCitations(answer.sentences), [answer.sentences]);
  const cached = cachedLine(answer);
  return (
    <article className="rule-left" aria-labelledby="answer-heading">
      <h2 id="answer-heading" className="font-serif text-2xl">
        Answer from the record
      </h2>
      <div className="mt-3 max-w-prose leading-relaxed">
        {answer.sentences.map((s, i) => (
          <p key={i} className="mb-3">
            {s.text}
            {s.cited_ids.map((id) => (
              <CitationMark key={id} n={numbered.get(id) ?? 0} passageId={id} row={byId.get(id)} onOpen={onOpen} />
            ))}
          </p>
        ))}
      </div>
      <p className="mt-2 text-sm text-muted">
        {answer.verified_citations.length} citations verified against {answer.coverage.n_passages} retrieved passages
        from {answer.coverage.n_items} {answer.coverage.n_items === 1 ? "item" : "items"}
        {answer.coverage.single_source && <span className="tag ml-2">single source</span>}
      </p>
      {cached && <p className="mt-1 text-sm text-muted">{cached}</p>}
      <Sources numbered={numbered} byId={byId} />
      <UnsupportedRow items={answer.unsupported} />
    </article>
  );
}
