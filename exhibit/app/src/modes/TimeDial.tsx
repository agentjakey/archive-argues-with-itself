// Time Dial: pick a question, turn the dial, and the answer is rebuilt from only the pages published
// by that year. Every step was drafted offline from exactly those pages and checked before release.
// Around the steps, each year says whether the indexed record is quiet, recorded, or not indexed.
import { useMemo, useState } from "react";
import type { DialRound, Lang } from "../lib/deck";
import { pageByRef, quoteById } from "../lib/deck";
import { useDial } from "../lib/input";
import type { Strings } from "../lib/strings";
import { Dial } from "../components/Dial";
import { PageView } from "../components/PageView";
import { StatusNote } from "../components/StatusNote";

type Props = { rounds: DialRound[]; lang: Lang; t: Strings; first: number; last: number; onEvent: (e: string) => void };

export function TimeDial({ rounds, lang, t, first, last, onEvent }: Props) {
  const [chosen, setChosen] = useState<DialRound | null>(null);
  if (!chosen) {
    return (
      <section className="mode" aria-labelledby="dial-heading">
        <h2 id="dial-heading">{t.modes.time_dial.name}</h2>
        <p className="lede">{t.dial.pickQuestion}</p>
        <ul className="choice-list">
          {rounds.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                className="btn btn-big"
                onClick={() => {
                  onEvent("time_dial:start");
                  setChosen(r);
                }}
              >
                {r.play.question[lang]}
              </button>
            </li>
          ))}
        </ul>
      </section>
    );
  }
  return <DialQuestion round={chosen} lang={lang} t={t} first={first} last={last} onBack={() => setChosen(null)} />;
}

function DialQuestion({ round, lang, t, first, last, onBack }: { round: DialRound; lang: Lang; t: Strings; first: number; last: number; onBack: () => void }) {
  const steps = round.play.epochs;
  const [year, setYear] = useState(steps.length ? steps[0].year : first);
  const [openPage, setOpenPage] = useState<string | null>(null);
  useDial((step) => setYear((y) => Math.min(last, Math.max(first, y + step))));
  const step = useMemo(() => [...steps].reverse().find((e) => e.year <= year) ?? null, [steps, year]);
  const yearInfo = round.play.years.find((y) => y.year === year);
  const pagesByThen = round.pages.filter((p) => (p.catalogue_date.year ?? 9999) <= year);
  const yearLine = !yearInfo
    ? ""
    : yearInfo.state === "not_indexed"
      ? t.dial.notIndexed(year)
      : yearInfo.state === "quiet"
        ? t.dial.quiet(year)
        : t.dial.recorded(year, yearInfo.items ?? 0);
  const maxItems = Math.max(1, ...round.play.years.map((y) => y.items ?? 0));
  return (
    <section className="mode" aria-labelledby="dialq-heading">
      <button type="button" className="btn btn-quiet" onClick={onBack}>
        {t.back}
      </button>
      <h2 id="dialq-heading">{round.play.question[lang]}</h2>
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
        <span className={`state-chip chip-${yearInfo?.state ?? "quiet"}`}>{yearInfo ? (yearInfo.state === "not_indexed" ? "N/A" : yearInfo.state === "quiet" ? "0" : String(yearInfo.items)) : ""}</span>{" "}
        {yearLine}
      </p>
      <div className="answer" aria-live="polite">
        {step === null ? (
          <p>{t.dial.nothingYet(year)}</p>
        ) : (
          <>
            <p className="answer-text">{step.state === "insufficient" ? t.dial.insufficient + " " : ""}{step.answer[lang]}</p>
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
      </div>
      {openPage && pageByRef(round, openPage) && (
        <PageView
          page={pageByRef(round, openPage)!}
          label={pageByRef(round, openPage)!.title}
          t={t}
          marks={round.quotes.filter((q) => q.page_ref === openPage).map((q) => ({ id: q.id, quote: q.text }))}
        />
      )}
      <details className="pages-so-far">
        <summary>
          {t.dial.pagesSoFar} ({pagesByThen.length})
        </summary>
        <ul>
          {pagesByThen.map((p) => (
            <li key={p.ref}>
              {p.catalogue_date.year}: {p.title}
            </li>
          ))}
        </ul>
      </details>
      <StatusNote round={round} t={t} />
    </section>
  );
}
