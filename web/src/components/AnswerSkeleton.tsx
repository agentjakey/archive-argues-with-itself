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

/** The shared waiting body: one heading, three shimmer lines, a modest page placeholder, and one
 *  honest caption line, inside a region that reserves its height so nothing shifts when the real
 *  content lands. Both the main ask and the two-decade compare fill use it, so a two-phase wait
 *  reads as one coherent process. The shimmer is decorative and is quieted by prefers-reduced-motion. */
export function SkeletonBody({ heading, caption }: { heading: string; caption: string }) {
  return (
    <section className="rule-left answer-region mt-4" role="status" aria-busy="true">
      <h2 className="font-serif text-lg text-muted">{heading}</h2>
      <div className="mt-3 max-w-prose space-y-3" aria-hidden="true">
        <span className="sk-line" style={{ width: "97%" }} />
        <span className="sk-line" style={{ width: "90%" }} />
        <span className="sk-line" style={{ width: "72%" }} />
      </div>
      <div className="sk-page mt-4 w-full" aria-hidden="true" />
      <p className="mt-3 text-sm text-muted">{caption}</p>
    </section>
  );
}

/** The answer-shaped placeholder for the main ask. It appears only after a short delay, so a cached
 *  question renders instantly with no spinner. Streaming is not used: the pipeline verifies each
 *  drafted sentence and drops the ones that fail, so only the final verified answer is ever shown. */
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
    <SkeletonBody
      heading="Answer from the record"
      caption={`Searching ${scope} and composing the cited answer. ${elapsed} s.`}
    />
  );
}
