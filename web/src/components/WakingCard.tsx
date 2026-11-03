import type { WakeProgress } from "../lib/waking";
import { listWords, partLabel } from "../lib/parts";
import type { EngineStage, ScopeInfo } from "../types";

interface Props {
  wake: WakeProgress;
  question: string;
  onRetry: () => void;
  scopes?: ScopeInfo[] | null;   // for the parts' plain names
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
export function WakingCard({ wake, question, onRetry, scopes }: Props) {
  const downloading = wake.stage?.stage === "downloading" && !!wake.stage.bytes_total;
  const parts = (wake.parts ?? []).map((p) => partLabel(p, scopes));
  const several = parts.length > 1;
  const heading =
    wake.phase === "down"
      ? "The archive engine is not answering right now"
      : wake.phase === "slow"
        ? "Still waking, slower than usual"
        : several
          ? `Waking ${parts.length} parts of the archive`
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
      {parts.length > 0 && wake.phase !== "down" && (
        <p className="mt-3 max-w-prose leading-relaxed" data-testid="waking-parts">
          {several
            ? `This question needs ${listWords(parts)}. Each part sleeps when nobody is asking and wakes on its own; the answer comes when they are all ready.`
            : `This question needs ${parts[0]}, which sleeps when nobody is asking and is waking now.`}
        </p>
      )}
      {wake.phase === "down" ? (
        <>
          <p className="mt-3 max-w-prose text-sm text-muted">
            The stories and the example questions below are recorded answers, with every page cited, and they
            still work. Try your question again in a few minutes.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className="chip chip-primary" onClick={onRetry}>
              Try again
            </button>
            <CatalogueLink question={question} />
          </div>
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
              className="waking-progress mt-2 w-full max-w-md"
              max={wake.stage!.bytes_total}
              value={wake.stage!.bytes_downloaded ?? 0}
              aria-label="Archive files fetched so far"
            />
          )}
          <p className="mt-2 text-sm text-muted" aria-live="off">
            Waiting {wake.elapsed} s
          </p>
          {wake.phase === "slow" && (
            <p className="mt-3">
              <CatalogueLink question={question} />
            </p>
          )}
        </>
      )}
    </article>
  );
}

/** While the engine is away, the catalogue still works: it searches titles and issuers, not page
 *  text, so it is offered as a different kind of search, carrying the question's words. */
function CatalogueLink({ question }: { question: string }) {
  const href = question ? `/catalogue/?q=${encodeURIComponent(question.slice(0, 120))}` : "/catalogue/";
  return (
    <a className="chip" href={href}>
      Search catalogue titles instead
    </a>
  );
}
