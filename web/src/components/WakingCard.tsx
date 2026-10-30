import type { WakeProgress } from "../lib/waking";
import type { EngineStage } from "../types";

interface Props {
  wake: WakeProgress;
  question: string;
  onRetry: () => void;
}

const GB = 1_000_000_000;

function gigabytes(bytes: number): string {
  return (bytes / GB).toFixed(1);
}

/** What the engine is doing, in plain words, from the stage it reports. */
export function stageLine(stage: EngineStage | null): string {
  switch (stage?.stage) {
    case "checking":
      return "Checking the archive files it already has.";
    case "downloading":
      if (stage.bytes_total) {
        return (
          `Fetching the archive: ${gigabytes(stage.bytes_downloaded ?? 0)} of ${gigabytes(stage.bytes_total)} GB, ` +
          "each file checked against its published fingerprint as it arrives."
        );
      }
      return "Fetching the archive.";
    case "provisioned":
    case "loading":
      return "Opening the search indexes.";
    case "ready":
      return "Ready. Asking your question now.";
    default:
      return "Starting up.";
  }
}

/** Shown while a live question waits for the engine, which sleeps when nobody is asking. The
 *  question is kept and asked again on its own; the stories below never need the engine. */
export function WakingCard({ wake, question, onRetry }: Props) {
  const downloading = wake.stage?.stage === "downloading" && !!wake.stage.bytes_total;
  const heading =
    wake.phase === "down"
      ? "The archive engine is not answering right now"
      : wake.phase === "slow"
        ? "Still waking, slower than usual"
        : "Waking the archive engine";
  return (
    <article className="settle rule-left mt-6" role="status" aria-live="polite" aria-labelledby="waking-heading">
      <h2 id="waking-heading" className="screen-title">
        {heading}
      </h2>
      {question && (
        <p className="mt-3 max-w-prose leading-relaxed">
          Your question is kept: <q className="italic">{question}</q>
        </p>
      )}
      {wake.phase === "down" ? (
        <>
          <p className="mt-3 max-w-prose text-sm text-muted">
            The stories and the example questions below are recorded answers, with every page cited, and they
            still work. Try your question again in a few minutes.
          </p>
          <button type="button" className="chip mt-3" onClick={onRetry}>
            Try again
          </button>
        </>
      ) : (
        <>
          <p className="mt-3 max-w-prose text-sm text-muted">
            {wake.phase === "slow"
              ? "It will answer as soon as it is ready; you do not need to ask again. While you wait, the stories below are recorded answers and work now."
              : "The engine sleeps when nobody is asking, which keeps the cost close to nothing. It is starting now and will answer as soon as it is ready; you do not need to ask again."}
          </p>
          <p className="mt-3 text-sm">{stageLine(wake.stage)}</p>
          {downloading && (
            <progress
              className="mt-2 w-full max-w-md"
              max={wake.stage!.bytes_total}
              value={wake.stage!.bytes_downloaded ?? 0}
              aria-label="Archive files fetched so far"
            />
          )}
          <p className="mt-2 text-sm text-muted" aria-live="off">
            Waiting {wake.elapsed} s
          </p>
        </>
      )}
    </article>
  );
}
