import { useMemo, useState } from "react";
import { numberCitations } from "../lib/citations";
import { plural, shortTitle, yearLabel } from "../lib/format";
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
  const [scanFailed, setScanFailed] = useState(false);
  // The top cited page, surfaced under the answer so the scanned proof is visible without scrolling
  // to the trail. One already-loaded image, no extra network; opens the existing drawer on click.
  const topCite = answer.verified_citations[0];
  const topRow = topCite ? byId.get(topCite.passage_id) : undefined;
  const topN = topCite ? numbered.get(topCite.passage_id) ?? 0 : 0;
  return (
    <article className="rule-left" aria-labelledby="answer-heading">
      <h2 id="answer-heading" className="font-serif text-xl">
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
        {plural(answer.verified_citations.length, "citation")} verified against{" "}
        {plural(answer.coverage.n_passages, "retrieved passage")} from {plural(answer.coverage.n_items, "item")}
        {answer.coverage.single_source && <span className="tag ml-2">single source</span>}
      </p>
      {cached && <p className="mt-1 text-sm text-muted">{cached}</p>}
      {topRow?.page_image && !scanFailed && (
        <figure className="mt-4 m-0 max-w-[420px]">
          <button
            type="button"
            className="block w-full cursor-pointer border-0 bg-transparent p-0 text-left"
            onClick={() => onOpen(topRow)}
            aria-label={`Open the scanned page behind citation ${topN}: ${shortTitle(topRow.title)}`}
          >
            <img
              src={topRow.page_image}
              alt={`Scanned page behind citation ${topN}, ${shortTitle(topRow.title)}, leaf ${topRow.leaf_index}`}
              loading="eager"
              className="w-full border border-rule bg-paper hover:border-ink"
              onError={() => setScanFailed(true)}
            />
          </button>
          <figcaption className="mt-1 text-sm text-muted">
            The page behind citation [{topN}]: {shortTitle(topRow.title, 70)} ({yearLabel(topRow.year)}).{" "}
            <button type="button" className="linkish" onClick={() => onOpen(topRow)}>
              View full page
            </button>
          </figcaption>
        </figure>
      )}
      <Sources numbered={numbered} byId={byId} />
      <UnsupportedRow items={answer.unsupported} />
    </article>
  );
}
