// Time Dial: turn the dial, and the answer is rebuilt from only the pages published by that year.
// Every step was drafted offline from exactly those pages and checked before release. Around the
// steps, each year says whether the indexed record is quiet, recorded, or not indexed.
import { useMemo, useState } from "react";
import type { DialRound, Lang } from "../lib/deck";
import { pageByRef, quoteById } from "../lib/deck";
import { useDial } from "../lib/input";
import type { Strings } from "../lib/strings";
import { Dial } from "../components/Dial";
import { PageView } from "../components/PageView";
import { StatusNote } from "../components/StatusNote";

// The question picker the "All games" menu shows before a Time Dial run.
export function TimeDialPicker({ rounds, lang, t, onPick }: { rounds: DialRound[]; lang: Lang; t: Strings; onPick: (round: DialRound) => void }) {
  return (
    <section className="round round-picker" aria-labelledby="dial-heading">
      <h2 id="dial-heading">{t.modes.time_dial.name}</h2>
      <p className="lede">{t.dial.pickQuestion}</p>
      <ul className="choice-list">
        {rounds.map((r) => (
          <li key={r.id}>
            <button type="button" className="btn btn-wide" onClick={() => onPick(r)}>
              {r.play.question[lang]}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

type Props = {
  round: DialRound;
  lang: Lang;
  t: Strings;
  first: number;
  last: number;
  progress: string;
  nextLabel: string;
  onNext: (year: number) => void;
};

export function TimeDial({ round, lang, t, first, last, progress, nextLabel, onNext }: Props) {
  const steps = round.play.epochs;
  const [year, setYear] = useState(steps.length ? steps[0].year : first);
  const [openPage, setOpenPage] = useState<string | null>(null);
  useDial((step) => setYear((y) => Math.min(last, Math.max(first, y + step))));
  const step = useMemo(() => [...steps].reverse().find((e) => e.year <= year) ?? null, [steps, year]);
  const yearInfo = round.play.years.find((y) => y.year === year);
  const yearLine = !yearInfo
    ? ""
    : yearInfo.state === "not_indexed"
      ? t.dial.notIndexed(year)
      : yearInfo.state === "quiet"
        ? t.dial.quiet(year)
        : t.dial.recorded(year, yearInfo.items ?? 0);
  const maxItems = Math.max(1, ...round.play.years.map((y) => y.items ?? 0));
  const opened = openPage ? pageByRef(round, openPage) : undefined;
  return (
    <section className="round round-dial" data-step="time_dial" aria-labelledby="dialq-heading">
      <header className="round-head">
        <p className="kicker">{progress}</p>
        <h2 id="dialq-heading">{round.play.question[lang]}</h2>
      </header>
      <div className="round-side">
        <Dial year={year} first={first} last={last} onChange={setYear} t={t} />
        <figure className="years-strip" aria-label={t.dial.yearsStrip}>
          <div className="years-bars" aria-hidden="true">
            {round.play.years.map((y) => (
              <span
                key={y.year}
                className={`bar bar-${y.state}${y.year === year ? " bar-now" : ""}`}
                style={{ height: y.state === "recorded" ? `${Math.max(8, ((y.items ?? 0) / maxItems) * 100)}%` : undefined }}
              />
            ))}
          </div>
          <figcaption className="note">{t.dial.yearsStrip}</figcaption>
        </figure>
        <p className="year-line" aria-live="polite">
          {yearInfo && <span className={`state-chip chip-${yearInfo.state}`}>{t.dial.stateShort[yearInfo.state]}</span>} {yearLine}
        </p>
        <div className="next-bar">
          <button type="button" className="btn btn-primary" data-primary onClick={() => onNext(year)}>
            {nextLabel}
          </button>
        </div>
      </div>
      {/* In kiosk mode this pane may scroll: it takes focus so the keyboard can scroll it too. */}
      <div className="round-main" tabIndex={0} role="region" aria-labelledby="dialq-heading">
        <div className="answer" aria-live="polite">
          {step === null ? (
            <p className="answer-text">{t.dial.nothingYet(year)}</p>
          ) : (
            <>
              {step.state === "insufficient" && <p className="state-chip chip-insufficient">{t.dial.insufficient}</p>}
              <p className="answer-text">{step.answer[lang]}</p>
              <p className="note">{t.dial.builtFrom(step.pages_by_then.length, step.year)}</p>
              <ul className="quote-list">
                {step.quotes.map((qid) => {
                  const q = quoteById(round, qid);
                  const page = q ? pageByRef(round, q.page_ref) : undefined;
                  if (!q || !page) return null;
                  return (
                    <li key={qid}>
                      <blockquote>"{q.text}"</blockquote>
                      <button type="button" className="btn btn-quiet" onClick={() => setOpenPage(openPage === page.ref ? null : page.ref)} aria-expanded={openPage === page.ref}>
                        {page.title} ({page.catalogue_date.year})
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
          <StatusNote round={round} t={t} />
        </div>
        {opened && (
          <PageView page={opened} label={opened.title} t={t} marks={round.quotes.filter((q) => q.page_ref === opened.ref).map((q) => ({ id: q.id, quote: q.text }))} />
        )}
      </div>
    </section>
  );
}
