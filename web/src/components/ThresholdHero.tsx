import { jurisdictionLabel, shortTitle, yearLabel } from "../lib/format";
import type { Story } from "../types";

interface Props {
  featured: Story | null;            // the one example shown at the threshold; null -> renders nothing
  onOpen: (story: Story) => void;    // the existing story-open path (cached, instant, no model call)
}

// A neutral label for the featured pair: two real pages from the record, not a claim that the
// record disagrees or that coverage changed. The caption says what the pages do and do not establish.
const KICKER = "Two pages from the public record";

/** The threshold: the single focal thing on the landing, shown before the machinery. One curated
 *  pair from the record, its two pages years apart sized as artifacts, with the caption and the
 *  comparability label saying what the pair can and cannot show. It is one button (one action: open the full cited answer), following the same
 *  accessible pattern as the gallery cards (spans inside the button, the question in the aria-label).
 *  With no featured story it renders nothing, so the landing falls back to its framing and the tool. */
export function ThresholdHero({ featured, onOpen }: Props) {
  if (!featured) return null;
  const [a, b] = featured.pins;
  return (
    <section className="settle mt-6 border-b border-rule pb-10" aria-labelledby="threshold-kicker">
      <button
        type="button"
        onClick={() => onOpen(featured)}
        aria-label={`See the full answer: ${featured.question}`}
        className="group block w-full cursor-pointer border-0 bg-transparent p-0 text-left"
      >
        <span id="threshold-kicker" className="tag block">
          {KICKER}
        </span>
        <span className="screen-title mt-1 block max-w-[24ch]">{featured.question}</span>

        <span className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2">
          {[a, b].map((p, i) => (
            <span key={p.passage_id} className="block min-w-0">
              <span className="flex items-baseline gap-2">
                {a.year != null && b.year != null && a.year !== b.year && (
                  <span className="tag">{i === 0 ? "Then" : "Later"}</span>
                )}
                <span className="era-year">{yearLabel(p.year)}</span>
                {jurisdictionLabel(p.jurisdiction) && (
                  <span className="text-sm text-muted">{jurisdictionLabel(p.jurisdiction)}</span>
                )}
              </span>
              <span className="page-artifact mt-2 block h-[300px] overflow-hidden sm:h-[min(52vh,480px)]">
                <img
                  src={p.page_image}
                  alt={`Scanned page, ${shortTitle(p.title)}, ${yearLabel(p.year)}`}
                  loading="eager"
                  decoding="async"
                  className="h-full w-full object-cover object-top"
                />
              </span>
            </span>
          ))}
        </span>

        {featured.caption && (
          <span className="lead mt-5 block max-w-prose text-ink">{featured.caption}</span>
        )}
        {featured.comparability && (
          <span className="mt-2 block text-sm">
            <span className="tag">{featured.comparability.label}</span>
          </span>
        )}
        <span className="mt-4 inline-block font-sans text-base text-ink underline decoration-transparent underline-offset-4 group-hover:decoration-current">
          See the full answer
        </span>
      </button>
    </section>
  );
}
