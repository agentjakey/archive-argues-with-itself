import { formatInt, formatShare, windowLabel } from "../lib/format";
import type { CorpusFacts } from "../types";

interface Props {
  corpus: CorpusFacts | null;
}

/** Four labeled figures from /health plus the one-line meaning of "Cited". */
export function CorpusStrip({ corpus }: Props) {
  const figures = corpus
    ? [
        { label: "items", value: formatInt(corpus.items) },
        { label: "passages", value: formatInt(corpus.passages) },
        { label: "window", value: windowLabel(corpus) },
        { label: "of passages undated", value: formatShare(corpus.undated_share) },
      ]
    : [];
  return (
    <div className="mt-4 border-t border-b border-rule py-3">
      {corpus ? (
        <dl className="flex flex-wrap gap-x-8 gap-y-2" aria-label="Corpus facts">
          {figures.map((f) => (
            <div key={f.label} className="flex items-baseline gap-2">
              <dd className="font-serif text-xl m-0">{f.value}</dd>
              <dt className="text-sm text-muted">{f.label}</dt>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-sm text-muted" aria-live="polite">
          Loading corpus facts.
        </p>
      )}
      <p className="mt-2 text-sm text-muted">
        <span className="badge badge--cited mr-2">Cited</span>= the passage exists, was retrieved for this question,
        and resolves to a page on archive.org
      </p>
    </div>
  );
}
