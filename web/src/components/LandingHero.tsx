import { useState } from "react";
import { ATTRACT_HOOK, ATTRACT_SUBHOOK } from "../lib/attract";
import { shortTitle, yearLabel } from "../lib/format";
import type { EvidenceRow, Story } from "../types";

interface Props {
  stories: Story[];
  loading: boolean;                      // /stories still settling: hold a stable placeholder, no flash
  canAsk: boolean;                       // false offline/kiosk-without-box: the ask entry is hidden
  busy: boolean;
  onAsk: () => void;                     // the one primary action: focus the ask box
  onOpenStory: (story: Story) => void;   // open the cached full answer for this example (no model call)
  onOpen: (row: EvidenceRow) => void;    // open a page scan in the drawer
}

/** A plain page pointer [n]: it jumps to one of the two pages shown above. Deliberately NOT the
 *  live answer's verified citation mark (.mark, a superscript). This block is a curated example,
 *  so its marks are pointers to the two pages on display, not a claim of machine-verified support. */
function PagePointer({ n, onClick }: { n: number; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mx-0.5 cursor-pointer border-0 bg-transparent p-0 font-sans font-semibold text-ink underline-offset-2 hover:underline"
      style={{ minHeight: 0 }}
      aria-label={`Go to page ${n}, shown above`}
    >
      [{n}]
    </button>
  );
}

/** The landing hero: show before you tell. One real curated comparison from the record, clearly
 *  labelled a curated example so it is never mistaken for a live verified answer: the question, the
 *  two scanned pages it draws on (numbered [1] and [2]), the author's one-line framing with those
 *  numbers as pointers to the pages, and a single primary call to action. Built from /stories (pins
 *  plus caption), so it makes no model call and cannot fail on stage. While /stories settles it holds
 *  a stable skeleton (no hook-to-example flash); a scope that ships no stories falls back to the
 *  static hook so the landing still states plainly what this is. */
export function LandingHero({ stories, loading, canAsk, busy, onAsk, onOpenStory, onOpen }: Props) {
  const pool = stories.filter((s) => !s.flagged);   // the hero never opens behind an interstitial
  const heroes = pool.length ? pool : stories;
  const [i, setI] = useState(0);

  if (loading && !heroes.length) {
    // Stable, hero-shaped placeholder so first paint does not jump or flash the hook.
    return (
      <section className="my-4" aria-hidden="true">
        <div className="sk-line" style={{ width: "45%" }} />
        <div className="sk-line mt-3" style={{ width: "80%", height: "1.75rem" }} />
        <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-2">
          <div className="sk-page" style={{ maxWidth: "none", height: "460px" }} />
          <div className="sk-page" style={{ maxWidth: "none", height: "460px" }} />
        </div>
        <div className="sk-line mt-4" style={{ width: "95%" }} />
        <div className="sk-line mt-2" style={{ width: "60%" }} />
      </section>
    );
  }

  if (!heroes.length) {
    return (
      <section className="rule-left my-4" aria-label="What this is">
        <h2 className="font-serif text-3xl leading-tight">{ATTRACT_HOOK}</h2>
        <p className="mt-2 max-w-prose text-lg">{ATTRACT_SUBHOOK}</p>
        {canAsk && (
          <button type="button" className="chip chip-primary mt-4" onClick={onAsk} disabled={busy}>
            Ask your own question
          </button>
        )}
      </section>
    );
  }

  const story = heroes[i % heroes.length];

  return (
    <section className="my-4" aria-labelledby="hero-question">
      <p className="font-sans text-xs uppercase tracking-wide text-muted">A curated example from the record</p>
      <h2 id="hero-question" className="mt-1 max-w-prose font-serif text-3xl leading-tight">
        {story.question}
      </h2>

      <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-2">
        {story.pins.map((pin, n) => (
          <figure key={pin.passage_id} className="m-0 min-w-0">
            <figcaption className="flex items-baseline gap-2 border-b border-rule pb-1">
              <span className="font-semibold">[{n + 1}]</span>
              <span className="font-serif text-2xl">{yearLabel(pin.year)}</span>
              <span className="text-sm text-muted">{pin.jurisdiction ?? "unknown"}</span>
            </figcaption>
            <button
              type="button"
              className="mt-3 block w-full cursor-pointer border-0 bg-transparent p-0 text-left"
              onClick={() => onOpen(pin)}
              aria-label={`View the scanned page, source ${n + 1}: ${shortTitle(pin.title)}, ${yearLabel(pin.year)}`}
            >
              <img
                src={pin.page_image}
                alt={`Page scan, source ${n + 1}, ${shortTitle(pin.title)}, leaf ${pin.leaf_index}`}
                loading="eager"
                className="w-full max-h-[460px] object-cover object-top border border-rule bg-paper hover:border-ink"
              />
            </button>
            <p className="mt-2 text-sm text-muted">{shortTitle(pin.title, 96)}</p>
          </figure>
        ))}
      </div>

      <p className="mt-4 max-w-prose leading-relaxed">
        {story.caption}
        <PagePointer n={1} onClick={() => onOpen(story.pins[0])} />
        <PagePointer n={2} onClick={() => onOpen(story.pins[1])} />
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        {canAsk ? (
          <>
            <button type="button" className="chip chip-primary" onClick={onAsk} disabled={busy}>
              Ask your own question
            </button>
            <button type="button" className="linkish" onClick={() => onOpenStory(story)}>
              See the full answer
            </button>
          </>
        ) : (
          <button type="button" className="chip chip-primary" onClick={() => onOpenStory(story)}>
            See the full answer
          </button>
        )}
        {heroes.length > 1 && (
          <button type="button" className="linkish" onClick={() => setI((k) => (k + 1) % heroes.length)}>
            Show another example
          </button>
        )}
      </div>

      <p className="mt-3 max-w-prose text-sm text-muted">
        A curated pairing of two real pages. Ask your own question for a live answer, where each sentence links to
        the page it cites and the tool declines when the record is too thin.
      </p>
    </section>
  );
}
