import { shortTitle, yearLabel } from "../lib/format";
import type { Story } from "../types";

interface Props {
  stories: Story[];
  loading: boolean;                 // /stories still settling: hold a stable placeholder, no pop-in
  onOpen: (story: Story) => void;   // the EXISTING story-open path (cached, instant, no model call)
}

/** The featured-arguments gallery: the active scope's curated stories as cards. The strongest
 *  (stories[0]) is the large lead card; the rest are a responsive grid below it, one column on mobile,
 *  lead first. Each card is a single button (one action: open the full cited answer via the existing
 *  story-open path) showing the story's two scanned pages side by side, its question, and its one-line
 *  caption. While /stories loads it holds a stable skeleton; with no stories it renders nothing, so the
 *  landing falls back to its framing lines and the ask box. Rules, not boxes: framed scans, a bottom
 *  hairline per card, one accent reserved elsewhere. */
export function StoryGallery({ stories, loading, onOpen }: Props) {
  if (loading && stories.length === 0) {
    return (
      <section className="mt-6" aria-hidden="true">
        <div className="sk-page" style={{ maxWidth: "none", height: "300px" }} />
        <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-3">
          <div className="sk-page" style={{ maxWidth: "none", height: "170px" }} />
          <div className="sk-page" style={{ maxWidth: "none", height: "170px" }} />
          <div className="sk-page" style={{ maxWidth: "none", height: "170px" }} />
        </div>
      </section>
    );
  }
  if (!stories.length) return null;
  const [lead, ...rest] = stories;
  return (
    <section className="mt-6" aria-labelledby="gallery-heading">
      <h2 id="gallery-heading" className="sr-only">
        Featured arguments from the record
      </h2>
      <ArgumentCard story={lead} lead onOpen={onOpen} />
      {rest.length > 0 && (
        <ul className="mt-6 grid list-none grid-cols-1 gap-x-8 gap-y-6 p-0 sm:grid-cols-3">
          {rest.map((s) => (
            <li key={s.id} className="m-0">
              <ArgumentCard story={s} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** One card. A single button (one action, opens the story), holding the two scanned pages, the
 *  question, the caption, and a "See the full answer" cue that underlines when the card is hovered.
 *  Phrasing spans only (no headings inside a button); the button's label carries the question, and
 *  each scan carries alt text. */
function ArgumentCard({ story, lead = false, onOpen }: { story: Story; lead?: boolean; onOpen: (s: Story) => void }) {
  const [a, b] = story.pins;
  return (
    <button
      type="button"
      onClick={() => onOpen(story)}
      aria-label={`See the full answer: ${story.question}`}
      className="group block w-full cursor-pointer border-0 border-b border-rule bg-transparent p-0 pb-5 text-left"
    >
      <span className={`grid grid-cols-2 ${lead ? "gap-3" : "gap-2"}`}>
        {[a, b].map((p, i) => (
          <img
            key={p.passage_id}
            src={p.page_image}
            alt={`Scanned page ${i + 1}: ${shortTitle(p.title)}, ${yearLabel(p.year)}`}
            loading="lazy"
            decoding="async"
            className={`w-full ${lead ? "max-h-[420px]" : "max-h-[200px]"} border border-rule bg-paper object-cover object-top group-hover:border-ink`}
          />
        ))}
      </span>
      <span className="mt-2 block text-sm text-muted">
        {yearLabel(a.year)} to {yearLabel(b.year)}
      </span>
      <span className={`mt-1 block font-serif leading-snug ${lead ? "max-w-prose text-2xl" : "text-lg"}`}>
        {story.question}
      </span>
      <span className={`mt-1 block text-sm text-muted ${lead ? "max-w-prose" : ""}`}>{story.caption}</span>
      <span className="mt-2 block font-sans text-sm text-ink underline decoration-transparent underline-offset-2 group-hover:decoration-current">
        See the full answer
      </span>
    </button>
  );
}
