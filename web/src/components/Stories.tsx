import { shortTitle, yearLabel } from "../lib/format";
import type { Story } from "../types";

interface Props {
  stories: Story[];
  loading: boolean;                 // /stories still settling: hold a stable placeholder, no pop-in
  onOpen: (story: Story) => void;   // the EXISTING story-open path (cached, instant, no model call)
}

// One line above the grid, from the final copy.
const GALLERY_LEAD_IN =
  "Each one is a single question answered from two pages of the record, years apart. Open one to " +
  "see the pages and the answer they support.";

/** The featured-arguments gallery: the active scope's curated stories as one uniform grid of compact
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
        Featured arguments from the record
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

/** One card, uniform with every other. A single button (one action, opens the story), holding the
 *  two scanned pages, the question, the caption, and a "See the full answer" cue that underlines on
 *  hover. Phrasing spans only (no headings inside a button); the button's label carries the question,
 *  and each scan carries alt text. */
function ArgumentCard({ story, onOpen }: { story: Story; onOpen: (s: Story) => void }) {
  const [a, b] = story.pins;
  return (
    <button
      type="button"
      onClick={() => onOpen(story)}
      aria-label={`See the full answer: ${story.question}`}
      className="group block w-full cursor-pointer border-0 border-b border-rule bg-transparent p-0 pb-4 text-left"
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
      <span className="mt-2 block font-sans text-sm text-ink underline decoration-transparent underline-offset-2 group-hover:decoration-current">
        See the full answer
      </span>
    </button>
  );
}
