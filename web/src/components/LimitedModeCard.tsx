import type { Answer, Degraded } from "../types";

interface Props {
  answer: Answer;
  degraded: Degraded;
}

/** Shown when the server could not generate a written answer (offline, model
 *  unreachable, or rate-limited) and returned the retrieved record instead. Kept
 *  visually distinct from AbstentionCard: this is "the answer service is not running
 *  here," not "the archive does not cover this." The evidence trail renders below. */
export function LimitedModeCard({ answer, degraded }: Props) {
  return (
    <article className="rule-left" role="status" aria-labelledby="limited-heading">
      <h2 id="limited-heading" className="font-serif text-2xl">
        Showing the record, not a written answer
      </h2>
      <p className="mt-3 max-w-prose leading-relaxed">{answer.abstention_text}</p>
      <p className="mt-3 max-w-prose text-sm text-muted">
        The passages below are the real record for your question. Read them and follow each one to its
        scanned page. A written, cited answer is generated on the live version, which needs the network.
      </p>
      {degraded.live_url && (
        <a className="chip mt-3" href={degraded.live_url} target="_blank" rel="noopener noreferrer">
          Open the live version
        </a>
      )}
    </article>
  );
}
