import { formatElapsed, formatInt } from "../lib/format";
import type { AskStatus } from "../hooks/useAsk";

interface Props {
  status: AskStatus;
  elapsed: number;
  completion: string | null;
  passages: number | null;
}

/** One honest status line: a real waiting message with an elapsed counter while
 *  the request is in flight, then the real completion label from the response.
 *  Errors are rendered by ErrorCard, not here. */
export function WaitingLabel({ status, elapsed, completion, passages }: Props) {
  let text = "";
  if (status === "waiting") {
    const scope = passages != null ? `${formatInt(passages)} passages` : "the corpus";
    text = `Searching ${scope} and composing, about 10 s. ${formatElapsed(elapsed)}.`;
  } else if (status === "done" && completion) {
    text = completion;
  }
  return (
    <p className="mt-3 min-h-[1.5rem] text-sm text-muted" aria-live="polite" role="status">
      {text}
    </p>
  );
}
