import { shortTitle, yearLabel } from "../lib/format";
import type { Story } from "../types";

interface Props {
  stories: Story[];
  loading: boolean;                 // /stories still settling: hold a stable placeholder, no pop-in
  onOpen: (story: Story) => void;   // the EXISTING story-open path (cached, instant, no model call)
}

// One line above the grid, from the final copy.
const GALLERY_LEAD_IN =
  "Each one pairs two pages of the record, years apart, on a single question. Open one to see the " +
  "pages, the answer they support, and the limits of the comparison.";

/** The featured-pairs gallery: the active scope's curated stories as one uniform grid of compact
 *  cards (no oversized lead card). Each card is a single button (one action: open the full cited
 *  answer via the existing story-open path) showing the story's two scanned pages side by side, its
 *  question, and its one-line caption. While /stories loads it holds a stable skeleton; with no
 *  stories it renders nothing, so the landing falls back to its framing lines and the ask box. */
export function StoryGallery({ stories, loading, onOpen }: Props) {
  if (loading && stories.length === 0) {
    return (
      <section className="mt-6" aria-hidden="true">
        <div className="grid grid-cols-1 gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="sk-page" style={{ maxWidth: "none", height: "150px" }} />
          ))}
        </div>
      </section>
    );
  }
  if (!stories.length) return null;
  return (
    <section className="mt-6" aria-labelledby="gallery-heading">
      <h2 id="gallery-heading" className="sr-only">
        Featured pairs from the record
      </h2>
      <p className="max-w-prose text-sm text-muted">{GALLERY_LEAD_IN}</p>
      <ul className="mt-4 grid list-none grid-cols-1 gap-x-8 gap-y-6 p-0 sm:grid-cols-2 lg:grid-cols-3">
        {stories.map((s) => (
          <li key={s.id} className="m-0">
            <ArgumentCard story={s} onOpen={onOpen} />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** One card, uniform with every other: the two scanned pages, the question, the caption, and one
 *  button, "See the full answer", whose accessible name adds the question. The whole card also opens
 *  the story on a mouse click; keyboard and screen-reader users have the button. Each scan carries
 *  alt text. */
function ArgumentCard({ story, onOpen }: { story: Story; onOpen: (s: Story) => void }) {
  const [a, b] = story.pins;
  return (
    <div
      onClick={() => onOpen(story)}
      className="group block w-full cursor-pointer border-b border-rule pb-4 text-left"
    >
      <span className="grid grid-cols-2 gap-2">
        {[a, b].map((p, i) => (
          <img
            key={p.passage_id}
            src={p.page_image}
            alt={`Scanned page ${i + 1}: ${shortTitle(p.title)}, ${yearLabel(p.year)}`}
            loading="lazy"
            decoding="async"
            className="w-full max-h-[150px] border border-rule bg-paper object-cover object-top group-hover:border-ink"
          />
        ))}
      </span>
      <span className="mt-2 block text-sm text-muted">
        {yearLabel(a.year)} to {yearLabel(b.year)}
      </span>
      <span className="mt-1 block font-serif text-base leading-snug">{story.question}</span>
      <span className="mt-1 block line-clamp-2 text-sm text-muted">{story.caption}</span>
      {story.comparability && (
        <span className="mt-1 block text-xs text-muted">{story.comparability.label}</span>
      )}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onOpen(story);
        }}
        aria-label={`See the full answer: ${story.question}`}
        className="mt-2 block cursor-pointer border-0 bg-transparent p-0 font-sans text-sm text-ink underline decoration-transparent underline-offset-2 group-hover:decoration-current"
      >
        See the full answer
      </button>
    </div>
  );
}
