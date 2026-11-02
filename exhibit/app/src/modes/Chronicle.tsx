// The chronicle: the end of a visit, one line per round with what the visitor said beside what the
// record says, and the evidence card to take home. It is built from the visit held in memory and is
// gone when the visit resets; nothing here is stored or sent.
import { useState } from "react";
import type { Lang, Page, Quote, Round } from "../lib/deck";
import { pageByRef, quoteById } from "../lib/deck";
import type { Result } from "../lib/arc";
import { totalPoints } from "../lib/arc";
import type { Strings } from "../lib/strings";
import { EvidenceCard } from "../components/EvidenceCard";
import { MiniSplit } from "../components/SplitBar";

type Props = {
  results: Result[];
  lang: Lang;
  t: Strings;
  canPrint: boolean;
  onEvent: (e: string) => void;
  onAgain: () => void;
  onDone: () => void;
};

function statusLine(round: Round, t: Strings): string {
  return round.status === "author-reviewed" ? t.status.authorReviewed : t.status.short;
}

function cardFor(result: Result, t: Strings, lang: Lang): { page: Page; quote: Quote | undefined; verdict: string } {
  const round = result.round;
  if (result.kind === "when_was_this") {
    const quote = quoteById(round, result.round.play.clues[0] ?? "");
    return { page: round.pages[0], quote, verdict: t.when.actual(result.round.play.year) };
  }
  if (result.kind === "same_or_not") {
    const quote = quoteById(round, result.round.play.decisive[0] ?? "");
    const page = (quote && pageByRef(round, quote.page_ref)) || round.pages[0];
    return { page, quote, verdict: t.same.choices[result.round.play.answer] };
  }
  const step = [...result.round.play.epochs].reverse().find((e) => e.year <= result.year);
  const quote = step ? quoteById(round, step.quotes[0] ?? "") : undefined;
  const page = (quote && pageByRef(round, quote.page_ref)) || round.pages[0];
  return { page, quote, verdict: `${result.round.play.question[lang]} (${result.year})` };
}

function Row({ result, t, lang }: { result: Result; t: Strings; lang: Lang }) {
  if (result.kind === "when_was_this") {
    return (
      <>
        <p className="row-title">{result.round.play.label[lang]}</p>
        <p>
          <span className="row-who">{t.chronicle.you}:</span> {result.guess}. <span className="row-who">{t.chronicle.record}:</span> {result.round.play.year}.
          {result.points !== null ? ` ${t.when.points(result.points)}.` : ""}
        </p>
      </>
    );
  }
  if (result.kind === "same_or_not") {
    const answer = result.round.play.answer;
    return (
      <>
        <p className="row-title">{result.round.play.claims[0].text[lang]}</p>
        <p>
          {result.picks.length > 1 ? (
            <MiniSplit picks={result.picks} answer={answer} t={t} />
          ) : (
            <>
              <span className="row-who">{t.chronicle.you}:</span> {t.same.choices[result.picks[0]]}.{" "}
            </>
          )}{" "}
          <span className="row-who">{t.chronicle.record}:</span> {t.same.choices[answer]}.
        </p>
      </>
    );
  }
  return (
    <>
      <p className="row-title">{result.round.play.question[lang]}</p>
      <p>{t.chronicle.dialRow(result.year)}.</p>
    </>
  );
}

export function Chronicle({ results, lang, t, canPrint, onEvent, onAgain, onDone }: Props) {
  const [chosen, setChosen] = useState(0);
  const card = results[chosen] ? cardFor(results[chosen], t, lang) : null;
  return (
    <section className="round round-chronicle" data-step="chronicle" aria-labelledby="chronicle-heading">
      <div className="chronicle-list">
        <h2 id="chronicle-heading">{t.chronicle.heading}</h2>
        <p className="lede">{t.chronicle.summary(results.length, totalPoints(results))}</p>
        <ol className="chronicle-rows">
          {results.map((r, i) => (
            <li key={r.round.id + i} className={i === chosen ? "row row-chosen" : "row"}>
              <p className="kicker">{t.modes[r.kind].name}</p>
              <Row result={r} t={t} lang={lang} />
              <button type="button" className="btn btn-quiet" aria-pressed={i === chosen} onClick={() => setChosen(i)}>
                {i === chosen ? t.chronicle.cardFor : t.chronicle.useCard}
              </button>
            </li>
          ))}
        </ol>
        <p className="status-note">
          {results.some((r) => r.round.status !== "author-reviewed") ? t.status.short : t.status.authorReviewed}
          {results.some((r) => r.round.explanation_status === "model-drafted") ? " " + t.status.drafted : ""}
        </p>
        <div className="actions next-bar">
          <button type="button" className="btn btn-primary" data-primary onClick={onAgain}>
            {t.again}
          </button>
          <button type="button" className="btn btn-quiet" onClick={onDone}>
            {t.done}
          </button>
        </div>
      </div>
      {card && (
        <div className="chronicle-card">
          <h3>{t.chronicle.cardHeading}</h3>
          <p className="note">{t.chronicle.cardLede}</p>
          {canPrint && (
            <button
              type="button"
              className="btn btn-print"
              onClick={() => {
                onEvent("card:print");
                window.print();
              }}
            >
              {t.card.print}
            </button>
          )}
          <EvidenceCard page={card.page} quote={card.quote} verdict={card.verdict} status={statusLine(results[chosen].round, t)} t={t} />
        </div>
      )}
    </section>
  );
}
