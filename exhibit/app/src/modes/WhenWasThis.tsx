// When Was This?: every year on the page is hidden; the visitor sets the dial and locks in a guess.
// Points go by closeness, and only for cards whose date is verified (the builder refuses any other).
// The reveal shows the clue lines and how the year is known: the catalogue and the document agree.
import { useState } from "react";
import type { Lang, WhenRound } from "../lib/deck";
import { quoteById } from "../lib/deck";
import { useDial } from "../lib/input";
import { score } from "../lib/text";
import type { Strings } from "../lib/strings";
import { Dial } from "../components/Dial";
import { PageView } from "../components/PageView";
import { StatusNote } from "../components/StatusNote";
import { EvidenceCard } from "../components/EvidenceCard";

type Props = { rounds: WhenRound[]; lang: Lang; t: Strings; first: number; last: number; canPrint: boolean; onEvent: (e: string) => void; onDone: () => void };

export function WhenWasThis({ rounds, lang, t, first, last, canPrint, onEvent, onDone }: Props) {
  const [index, setIndex] = useState(0);
  const mid = Math.round((first + last) / 2);
  const [year, setYear] = useState(mid);
  const [locked, setLocked] = useState<number | null>(null);
  const [total, setTotal] = useState(0);
  const round = rounds[index];
  useDial((step) => {
    if (locked === null) setYear((y) => Math.min(last, Math.max(first, y + step)));
  });
  if (!round) return null;
  const page = round.pages[0];
  const actual = round.play.year;
  const scored = page.date_verified;
  const lock = () => {
    if (locked !== null) return;
    setLocked(year);
    const pts = scored ? score(year, actual) : 0;
    setTotal(total + pts);
    onEvent("when_was_this:guess");
    if (index === rounds.length - 1) onEvent("when_was_this:finish");
  };
  const clues = round.play.clues.map((id) => quoteById(round, id)).filter(Boolean);
  const where = page.page_date.method === "read_from_page" ? t.when.thisPage : t.when.titlePage;
  return (
    <section className="mode" aria-labelledby="wwt-heading">
      <p className="kicker">
        {t.same.round(index + 1, rounds.length)} . {t.when.points(total)}
      </p>
      <h2 id="wwt-heading">{t.when.prompt}</h2>
      <p className="lede">{round.play.label[lang]}</p>
      <Dial year={locked ?? year} first={first} last={last} onChange={(y) => locked === null && setYear(y)} t={t} />
      {locked === null ? (
        <button type="button" className="btn btn-big" data-primary onClick={lock}>
          {t.when.guess}
        </button>
      ) : (
        <div className="reveal" role="status" aria-live="polite">
          <p className="reveal-head">
            {t.when.actual(actual)} {t.when.yourGuess(locked)}. {t.when.off(Math.abs(locked - actual))}{" "}
            {scored ? t.when.points(score(locked, actual)) : ""}
          </p>
          <h3>{t.when.clues}</h3>
          <ul className="quote-list">
            {clues.map((q) => (
              <li key={q!.id}>
                <blockquote>"{q!.text}"</blockquote>
              </li>
            ))}
          </ul>
          <p>{round.explanation[lang]}</p>
          <h3>{t.when.howWeKnow}</h3>
          <p>{t.when.howVerified(actual, page.page_date.line ?? "", where)}</p>
          <StatusNote round={round} t={t} />
          <EvidenceCard page={page} quote={clues[0]} verdict={t.when.actual(actual)} t={t} canPrint={canPrint} onPrint={() => onEvent("card:print")} />
          <button
            type="button"
            className="btn btn-big"
            data-primary
            onClick={() => {
              setLocked(null);
              setYear(mid);
              if (index + 1 < rounds.length) setIndex(index + 1);
              else onDone();
            }}
          >
            {index + 1 < rounds.length ? t.next : t.home}
          </button>
        </div>
      )}
      <PageView
        page={page}
        label={round.play.label[lang] || page.title}
        t={t}
        masks={locked === null ? round.play.masked_text : []}
        hideTitleYears={locked === null ? round.play.masked_title : undefined}
        marks={locked === null ? [] : clues.map((q) => ({ id: q!.id, quote: q!.text }))}
      />
    </section>
  );
}
