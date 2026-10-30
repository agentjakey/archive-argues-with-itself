import type { Answer, Degraded } from "../types";

interface Props {
  answer: Answer;
  degraded: Degraded;
}

// A slow first/cold query (the retrieval deadline or the per-request budget) is the service still
// getting ready after a fresh load or an idle spell, not a failure. It reads differently from a
// genuine offline / no-key / rate-limited limited mode, where the answer service simply is not
// running here.
const WARMING_REASONS = new Set(["retrieval_slow", "budget", "starting"]);
// Limited on purpose by this deployment (the day's answer budget is spent, or a collection's index
// did not load): the live version is the one being read, so there is nothing else to open.
const HELD_BACK_REASONS = new Set(["daily_budget", "index_unavailable"]);

/** Shown when the server returned the retrieved record instead of a written answer. Three framings:
 *  a cold/slow first load reads as "still getting ready, worth retrying"; a deliberate hold (the
 *  daily budget, an index that did not load) says what happened; a true offline / model limited
 *  mode reads as "the answer service is not running here." The evidence trail renders below. */
export function LimitedModeCard({ answer, degraded }: Props) {
  const warming = WARMING_REASONS.has(degraded.reason);
  const heldBack = HELD_BACK_REASONS.has(degraded.reason);
  let detail: string;
  if (warming) {
    detail =
      "The service was still warming up after a fresh load or a quiet spell, so this first " +
      "question ran long. Your question was not lost. Ask it again in a moment and it should " +
      "answer; meanwhile the passages below are the real record for it.";
  } else if (heldBack) {
    detail =
      "The passages below are the real record for your question. Read them and follow each one to its " +
      "scanned page. The stories and example questions are recorded answers and still work.";
  } else {
    detail =
      "The passages below are the real record for your question. Read them and follow each one to its " +
      "scanned page. A written, cited answer is generated on the live version, which needs the network.";
  }
  return (
    <article className="settle rule-left" role="status" aria-labelledby="limited-heading">
      <h2 id="limited-heading" className="screen-title">
        {warming ? "Still getting ready" : "Showing the record, not a written answer"}
      </h2>
      <p className="mt-3 max-w-prose leading-relaxed">{answer.abstention_text}</p>
      <p className="mt-3 max-w-prose text-sm text-muted">{detail}</p>
      {!warming && !heldBack && degraded.live_url && (
        <a className="chip mt-3" href={degraded.live_url} target="_blank" rel="noopener noreferrer">
          Open the live version
        </a>
      )}
    </article>
  );
}
