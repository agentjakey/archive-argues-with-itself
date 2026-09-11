import { formatInt, formatShare, windowLabel } from "../lib/format";
import type { CorpusFacts } from "../types";

interface Props {
  corpus: CorpusFacts | null;
}

/** Four labeled figures from /health plus the one-line meaning of "Cited". */
export function CorpusStrip({ corpus }: Props) {
  return (
    <div className="mt-4 border-t border-b border-rule py-3">
      {corpus ? (
        <dl className="flex flex-wrap gap-x-8 gap-y-2" aria-label="Corpus facts">
          <Figure value={formatInt(corpus.items)} label="items" />
          <Figure value={formatInt(corpus.passages)} label="passages" />
          <Figure
            value={`${windowLabel({ window: corpus.pilot_window })} pilot window`}
            label={`dated items span ${windowLabel({ window: corpus.window })}`}
          />
          <Figure value={formatShare(corpus.undated_share)} label="of passages undated" />
        </dl>
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

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col">
      <dd className="font-serif text-xl m-0">{value}</dd>
      <dt className="text-sm text-muted">{label}</dt>
    </div>
  );
}
