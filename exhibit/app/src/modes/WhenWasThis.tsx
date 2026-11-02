// When Was This?: every year on the page is hidden; the visitor sets the dial and locks in a guess.
// Points go by closeness, and only for cards whose date is verified (the builder refuses any other).
// The reveal is paced: the year on a timeline with the guess, then the clue lines, then how the
// year is known (the catalogue and the document agree), then the review status and the way on.
import { useState } from "react";
import type { Lang, WhenRound } from "../lib/deck";
import { quoteById } from "../lib/deck";
import { useDial } from "../lib/input";
import { SOLO_PACE, useStaged } from "../lib/pace";
import { useSettings } from "../lib/settings";
import { score } from "../lib/text";
import type { Strings } from "../lib/strings";
import { Dial } from "../components/Dial";
import { PageView } from "../components/PageView";
import { StatusNote } from "../components/StatusNote";
import { Timeline } from "../components/Timeline";

type Props = {
  round: WhenRound;
  lang: Lang;
  t: Strings;
  first: number;
  last: number;
  progress: string;
  nextLabel: string;
  onEvent: (e: string) => void;
  onNext: (guess: number, points: number | null) => void;
};

export function WhenWasThis({ round, lang, t, first, last, progress, nextLabel, onEvent, onNext }: Props) {
  const { reducedMotion } = useSettings();
  const mid = Math.round((first + last) / 2);
  const [year, setYear] = useState(mid);
  const [locked, setLocked] = useState<number | null>(null);
  const [howOpen, setHowOpen] = useState(false);
  const shown = useStaged(SOLO_PACE.slice(0, 4), reducedMotion, round.id, locked !== null);
  useDial((step) => {
    if (locked === null) setYear((y) => Math.min(last, Math.max(first, y + step)));
  });
  const page = round.pages[0];
  const actual = round.play.year;
  const scored = page.date_verified;
  const points = locked === null ? null : scored ? score(locked, actual) : null;
  const lock = () => {
    if (locked !== null) return;
    setLocked(year);
    onEvent("when_was_this:guess");
  };
  const clues = round.play.clues.map((id) => quoteById(round, id)).filter((q): q is NonNullable<typeof q> => Boolean(q));
  const where = page.page_date.method === "read_from_page" ? t.when.thisPage : t.when.titlePage;
  return (
    <section className="round round-when" data-step="when_was_this" aria-labelledby="wwt-heading">
      <header className="round-head">
        <p className="kicker">{progress}</p>
        <h2 id="wwt-heading">{t.when.prompt}</h2>
      </header>
      <div className="round-side">
        {locked === null ? (
          <>
            <p className="lede">{t.when.lede}</p>
            <Dial year={year} first={first} last={last} onChange={setYear} t={t} />
            <button type="button" className="btn btn-primary" data-primary onClick={lock}>
              {t.when.guess}
            </button>
          </>
        ) : (
          <div className="reveal" aria-live="polite">
            {shown >= 1 && (
              <div className="beat">
                <p className="verdict">{t.when.actual(actual)}</p>
                <Timeline
                  guess={locked}
                  actual={actual}
                  first={first}
                  last={last}
                  youLabel={t.when.you}
                  publishedLabel={t.when.published}
                  label={t.when.timeline(locked, actual)}
                />
                <p className="verdict-sub">
                  {t.when.yourGuess(locked)}. {t.when.off(Math.abs(locked - actual))} {points !== null ? t.when.points(points) + "." : ""}
                </p>
              </div>
            )}
            {shown >= 2 && (
              <div className="beat">
                <h3>{t.when.clues}</h3>
                <ul className="quote-list">
                  {clues.map((q) => (
                    <li key={q.id}>
                      <blockquote>"{q.text}"</blockquote>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {shown >= 3 && (
              <div className="beat">
                <button type="button" className="btn btn-quiet" aria-expanded={howOpen} onClick={() => setHowOpen(!howOpen)}>
                  {t.when.howWeKnow}
                </button>
                {howOpen && (
                  <div className="how">
                    <p>{t.when.howVerified(actual, page.page_date.line ?? "", where)}</p>
                    <p>{round.explanation[lang]}</p>
                  </div>
              )}
              </div>
            )}
            {shown >= 4 && (
              <div className="beat">
                <StatusNote round={round} t={t} />
              </div>
            )}
            {shown >= 4 && (
              <div className="next-bar">
                <button type="button" className="btn btn-primary" data-primary onClick={() => onNext(locked, points)}>
                  {nextLabel}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="round-main">
        <PageView
          page={page}
          label={round.play.label[lang] || page.title}
          t={t}
          masks={locked === null ? round.play.masked_text : []}
          hideTitleYears={locked === null ? round.play.masked_title : undefined}
          marks={locked === null ? [] : clues.map((q) => ({ id: q.id, quote: q.text }))}
        />
      </div>
    </section>
  );
}
