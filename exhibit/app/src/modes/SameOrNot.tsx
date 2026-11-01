// Same or Not?: two real pages, two claims, four choices. The reveal names the answer in words,
// marks the decisive lines on the pages, and shows what was compared (period, place, population,
// program, measure). Right and wrong are said in words and shapes, never by colour alone.
import { useState } from "react";
import type { Choice, Lang, SameOrNotRound } from "../lib/deck";
import { CHOICES, pageByRef, quoteById } from "../lib/deck";
import type { Strings } from "../lib/strings";
import { PageView } from "../components/PageView";
import { StatusNote } from "../components/StatusNote";
import { EvidenceCard } from "../components/EvidenceCard";

type Props = { rounds: SameOrNotRound[]; lang: Lang; t: Strings; canPrint: boolean; onEvent: (e: string) => void; onDone: () => void };

export function SameOrNot({ rounds, lang, t, canPrint, onEvent, onDone }: Props) {
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<Choice | null>(null);
  const round = rounds[index];
  if (!round) return null;
  const [pa, pb] = round.pages;
  const revealed = picked !== null;
  const right = picked === round.play.answer;
  const decisive = round.play.decisive.map((id) => quoteById(round, id)).filter(Boolean);
  const marksFor = (ref: string) =>
    revealed ? round.quotes.filter((q) => q.page_ref === ref && (q.role === "decisive" || q.role === "claim")).map((q) => ({ id: q.id, quote: q.text })) : [];
  const choose = (c: Choice) => {
    if (revealed) return;
    setPicked(c);
    onEvent(`same_or_not:${c}`);
    if (index === rounds.length - 1) onEvent("same_or_not:finish");
  };
  return (
    <section className="mode" aria-labelledby="son-heading">
      <p className="kicker">
        {t.same.level(round.level)} . {t.same.round(index + 1, rounds.length)}
      </p>
      <h2 id="son-heading">{t.same.prompt}</h2>
      {round.level === 1 && <p className="note level-one">{t.same.levelOneNote}</p>}
      <div className="claims">
        <div className="claim">
          <p className="claim-label">{t.same.claimA}</p>
          <p className="claim-text">{round.play.claims[0].text[lang]}</p>
        </div>
        <div className="claim">
          <p className="claim-label">{t.same.claimB}</p>
          <p className="claim-text">{round.play.claims[1].text[lang]}</p>
        </div>
      </div>
      <div className="choices" role="radiogroup" aria-label={t.same.prompt}>
        {CHOICES.map((c, i) => {
          const isAnswer = revealed && c === round.play.answer;
          const isPicked = picked === c;
          return (
            <button
              key={c}
              type="button"
              role="radio"
              aria-checked={isPicked}
              className={`choice${isAnswer ? " choice-answer" : ""}${isPicked && !isAnswer ? " choice-wrong" : ""}`}
              onClick={() => choose(c)}
              onKeyDown={(e) => {
                if (revealed) return;
                const next = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
                if (next !== 0) {
                  e.preventDefault();
                  const target = (e.currentTarget.parentElement?.children[(i + next + CHOICES.length) % CHOICES.length] as HTMLElement | undefined);
                  target?.focus();
                }
              }}
              disabled={revealed && !isAnswer && !isPicked}
            >
              <span className="choice-key" aria-hidden="true">
                {String.fromCharCode(65 + i)}
              </span>
              <span className="choice-name">{t.same.choices[c]}</span>
              <span className="choice-help">{t.same.choiceHelp[c]}</span>
              {isAnswer && <span className="choice-mark">{"\u2713"} {t.same.right.replace(".", "")}</span>}
              {isPicked && !isAnswer && <span className="choice-mark">{"\u2717"}</span>}
            </button>
          );
        })}
      </div>
      {revealed && (
        <div className="reveal" role="status" aria-live="polite">
          <p className="reveal-head">
            {right ? t.same.right : t.same.notQuite} {t.same.answerWas(t.same.choices[round.play.answer])}
          </p>
          <p>{round.explanation[lang]}</p>
          <h3>{t.same.decisive}</h3>
          <ul className="quote-list">
            {decisive.map((q) => (
              <li key={q!.id}>
                <blockquote>"{q!.text}"</blockquote>
                <span className="note">{q!.page_ref === pa.ref ? t.same.pageA : t.same.pageB}</span>
              </li>
            ))}
          </ul>
          <h3>{t.same.compared}</h3>
          <dl className="constraints">
            {Object.entries(round.play.constraints).map(([k, v]) => (
              <div key={k} className={`constraint constraint-${v}`}>
                <dt>{t.same.constraint[k] ?? k}</dt>
                <dd>
                  <span aria-hidden="true">{v === "same" ? "=" : v === "differs" ? "\u2260" : "?"}</span> {t.same.constraintValue[v] ?? v}
                </dd>
              </div>
            ))}
          </dl>
          <StatusNote round={round} t={t} />
          <EvidenceCard
            page={pageByRef(round, decisive[0]?.page_ref ?? pa.ref) ?? pa}
            quote={decisive[0]}
            verdict={t.same.choices[round.play.answer]}
            t={t}
            canPrint={canPrint}
            onPrint={() => onEvent("card:print")}
          />
          <button
            type="button"
            className="btn btn-big"
            onClick={() => {
              setPicked(null);
              if (index + 1 < rounds.length) setIndex(index + 1);
              else onDone();
            }}
          >
            {index + 1 < rounds.length ? t.next : t.home}
          </button>
        </div>
      )}
      <div className="pair">
        <PageView page={pa} label={t.same.pageA} t={t} marks={marksFor(pa.ref)} />
        <PageView page={pb} label={t.same.pageB} t={t} marks={marksFor(pb.ref)} />
      </div>
    </section>
  );
}
