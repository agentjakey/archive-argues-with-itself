import { shortTitle, yearLabel } from "../lib/format";
import type { Story } from "../types";

interface Props {
  stories: Story[];
  onOpen: (story: Story) => void;
}

/** Curated question + two pinned pages. Opening a story asks the question and
 *  shows the two pages side by side. */
export function Stories({ stories, onOpen }: Props) {
  if (!stories.length) return null;
  return (
    <section className="mt-8" aria-labelledby="stories-heading">
      <h2 id="stories-heading" className="font-serif text-2xl">
        Stories
      </h2>
      <p className="mt-1 text-sm text-muted max-w-prose">
        Two pages from the record, years apart, on one question. Open one to see them side by side with the
        answer the evidence supports.
      </p>
      <ul className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-x-8">
        {stories.map((s) => (
          <li key={s.id} className="evidence">
            <button type="button" className="flex gap-4 text-left w-full bg-transparent border-0 p-0" onClick={() => onOpen(s)}>
              <span className="flex gap-2 shrink-0">
                {s.pins.map((p) => (
                  <img
                    key={p.passage_id}
                    src={p.page_thumb}
                    alt={`Page scan, ${shortTitle(p.title)}, ${yearLabel(p.year)}`}
                    className="thumb-sm"
                    loading="lazy"
                  />
                ))}
              </span>
              <span className="min-w-0">
                <span className="block font-serif text-lg leading-snug">{s.question}</span>
                <span className="block mt-1 text-sm text-muted">
                  {yearLabel(s.pins[0].year)} and {yearLabel(s.pins[1].year)}
                </span>
                <span className="block mt-2 text-sm">{s.caption}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
