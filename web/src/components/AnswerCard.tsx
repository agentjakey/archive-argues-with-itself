import type { Answer, EvidenceRow } from "../types";
import { CitationChip } from "./CitationChip";
import { UnsupportedRow } from "./UnsupportedRow";

interface Props {
  answer: Answer;
  byId: Map<string, EvidenceRow>;
  onOpen: (row: EvidenceRow) => void;
}

export function AnswerCard({ answer, byId, onOpen }: Props) {
  return (
    <article className="card" aria-labelledby="answer-heading">
      <h2 id="answer-heading" className="font-sans text-sm uppercase tracking-wide text-muted">
        Answer from the record
      </h2>
      <div className="mt-3 max-w-prose leading-relaxed">
        {answer.sentences.map((s, i) => (
          <p key={i} className="mb-3">
            {s.text}
            {s.cited_ids.map((id) => (
              <CitationChip key={id} passageId={id} row={byId.get(id)} onOpen={onOpen} />
            ))}
          </p>
        ))}
      </div>
      <p className="mt-2 text-sm text-muted">
        {answer.verified_citations.length} citations verified against {answer.coverage.n_passages} retrieved passages
        from {answer.coverage.n_items} {answer.coverage.n_items === 1 ? "item" : "items"}
        {answer.coverage.single_source && <span className="badge ml-2">single source</span>}
      </p>
      <UnsupportedRow items={answer.unsupported} />
    </article>
  );
}
