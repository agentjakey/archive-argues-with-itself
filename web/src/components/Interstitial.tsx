import type { Flagged } from "../types";
import { INTERSTITIAL_COPY, contextualNote } from "../lib/sensitivity";
import { CrisisLines } from "./CrisisLines";

interface Props {
  flagged: Flagged;
  onContinue: () => void;
  onBack: () => void;
}

/** A gentle tap-through screen shown before the heaviest flagged results (never a blur, never
 *  a wall). It carries the same note and support lines, then Continue / Go back. Shown only
 *  for configured topics and only for flagged results; the caller never mounts it otherwise.
 *  Static, works offline (N6). */
export function Interstitial({ flagged, onContinue, onBack }: Props) {
  return (
    <main>
      <section className="card mt-6" role="group" aria-labelledby="interstitial-heading">
        <p className="font-sans text-xs uppercase tracking-wide text-muted">{INTERSTITIAL_COPY.eyebrow}</p>
        <h2 id="interstitial-heading" className="font-serif text-2xl">
          {INTERSTITIAL_COPY.heading}
        </h2>
        <p className="mt-3 max-w-prose leading-relaxed">{INTERSTITIAL_COPY.body}</p>
        <p className="mt-3 max-w-prose leading-relaxed">{contextualNote(flagged)}</p>
        <CrisisLines lines={flagged.crisis_lines} />
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" className="chip border-ink bg-ink text-paper" onClick={onContinue}>
            {INTERSTITIAL_COPY.continueLabel}
          </button>
          <button type="button" className="chip" onClick={onBack}>
            {INTERSTITIAL_COPY.backLabel}
          </button>
        </div>
      </section>
    </main>
  );
}
