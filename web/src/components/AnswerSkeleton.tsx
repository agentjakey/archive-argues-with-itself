import { useEffect, useState } from "react";
import { formatInt } from "../lib/format";
import type { AskStatus } from "../hooks/useAsk";

interface Props {
  status: AskStatus;
  elapsed: number;
  passages: number | null;
}

// Cached and other fast answers arrive before this, so the skeleton never flashes for them.
const SHOW_AFTER_MS = 350;

/** An answer-shaped placeholder that fills when the verified answer arrives, in place of a static
 *  "about 10 s" line. It appears only after a short delay, so a cached question renders instantly
 *  with no spinner. The honest elapsed time stays as a small secondary line. Streaming is not used:
 *  the pipeline verifies each drafted sentence and drops the ones that fail, so only the final
 *  verified answer is ever shown; streaming raw output would surface sentences that then vanish.
 *  The shimmer is decorative and is quieted by the prefers-reduced-motion rule. */
export function AnswerSkeleton({ status, elapsed, passages }: Props) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (status !== "waiting") {
      setShow(false);
      return;
    }
    const t = window.setTimeout(() => setShow(true), SHOW_AFTER_MS);
    return () => window.clearTimeout(t);
  }, [status]);

  if (status !== "waiting" || !show) return null;
  const scope = passages != null ? `${formatInt(passages)} passages` : "the record";
  return (
    <section className="rule-left mt-4" role="status" aria-busy="true">
      <h2 className="font-serif text-2xl text-muted">Answer from the record</h2>
      <div className="mt-3 max-w-prose space-y-3" aria-hidden="true">
        <span className="sk-line" style={{ width: "97%" }} />
        <span className="sk-line" style={{ width: "90%" }} />
        <span className="sk-line" style={{ width: "72%" }} />
      </div>
      <div className="sk-page mt-4 w-full" aria-hidden="true" />
      <p className="mt-3 text-sm text-muted">
        Searching {scope} and composing the cited answer. {elapsed} s.
      </p>
    </section>
  );
}
