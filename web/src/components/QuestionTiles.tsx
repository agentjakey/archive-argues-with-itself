import { TILE_CALLOUT } from "../lib/attract";
import type { Example } from "../types";

interface Props {
  tiles: Example[];
  onPick: (e: Example) => void;
  disabled?: boolean;
}

/** The primary call to action: four to six tappable question tiles drawn from the cached,
 *  non-flagged exhibit set, each labelled with its payoff. Tapping runs the cached question,
 *  so the result is instant and offline. Free-text stays available but secondary. */
export function QuestionTiles({ tiles, onPick, disabled }: Props) {
  if (!tiles.length) return null;
  return (
    <section className="mt-4" aria-label="Start here">
      <p className="font-sans text-xs uppercase tracking-wide text-muted">Tap a question to begin</p>
      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {tiles.map((t) => (
          <button
            key={t.qid}
            type="button"
            disabled={disabled}
            onClick={() => onPick(t)}
            className="card flex min-h-[104px] flex-col justify-between text-left hover:border-ink disabled:opacity-60"
          >
            <span className="font-serif text-lg leading-snug">{t.text}</span>
            <span className="mt-2 font-sans text-xs uppercase tracking-wide text-muted">{TILE_CALLOUT}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
