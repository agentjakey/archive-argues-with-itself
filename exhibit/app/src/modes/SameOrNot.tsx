// Same or Not?: two real pages, two claims, four choices. It plays like a document inspection: the
// claims sit side by side, and the reveal fills in the checklist of what has to match (period,
// place, population, program, measure). Choices are told apart by shape, letter and words.
// In group mode each player picks in secret on the one screen, passing it along, and the reveal
// opens with how the room split. Picks live in memory only and leave with the round.
import { useEffect, useRef, useState } from "react";
import type { Choice, Lang, SameOrNotRound } from "../lib/deck";
import { CHOICES, quoteById } from "../lib/deck";
import { GROUP_PACE, SOLO_PACE, useStaged } from "../lib/pace";
import { useSettings } from "../lib/settings";
import type { Strings } from "../lib/strings";
import { PageView } from "../components/PageView";
import { Shape } from "../components/Shape";
import { SplitBar } from "../components/SplitBar";
import { StatusNote } from "../components/StatusNote";

type Props = {
  round: SameOrNotRound;
  lang: Lang;
  t: Strings;
  players: number | null;
  progress: string;
  nextLabel: string;
  onEvent: (e: string) => void;
  onNext: (picks: Choice[]) => void;
};

const CONSTRAINTS = ["period", "jurisdiction", "population", "program", "measure"];
const MARK: Record<string, string> = { same: "=", differs: "\u2260", unclear: "?" };

export function SameOrNot({ round, lang, t, players, progress, nextLabel, onEvent, onNext }: Props) {
  const { reducedMotion } = useSettings();
  const [picks, setPicks] = useState<Choice[]>([]);
  const [passing, setPassing] = useState(false);
  const [reading, setReading] = useState<0 | 1 | null>(null);
  const choiceRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const voters = players ?? 1;
  const revealed = picks.length >= voters;
  const shown = useStaged(players ? GROUP_PACE : SOLO_PACE, reducedMotion, round.id, revealed);
  const revealRef = useRef<HTMLDivElement>(null);
  // The reveal is the screen's one dominant element once everyone has picked: bring it into view.
  const started = revealed && shown > 0;
  useEffect(() => {
    if (!started) return;
    const frame = window.requestAnimationFrame(() => {
      const box = revealRef.current?.getBoundingClientRect();
      if (box) window.scrollTo(0, Math.max(0, window.scrollY + box.top - 16));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [started]);
  const [pa, pb] = round.pages;
  const answer = round.play.answer;
  const decisive = round.play.decisive.map((id) => quoteById(round, id)).filter((q): q is NonNullable<typeof q> => Boolean(q));
  const marksFor = (ref: string) =>
    revealed ? round.quotes.filter((q) => q.page_ref === ref && (q.role === "decisive" || q.role === "claim")).map((q) => ({ id: q.id, quote: q.text })) : [];

  const choose = (c: Choice) => {
    if (revealed || passing) return;
    const next = [...picks, c];
    setPicks(next);
    onEvent(`same_or_not:${c}`);
    if (next.length < voters) setPassing(true);
  };

  if (reading !== null) {
    const page = reading === 0 ? pa : pb;
    const label = reading === 0 ? t.same.pageA : t.same.pageB;
    return (
      <section className="round round-reading" data-step="same_or_not" aria-labelledby="reading-heading">
        <h2 id="reading-heading" className="sr-only">
          {label}
        </h2>
        <button type="button" className="btn btn-quiet" onClick={() => setReading(null)} autoFocus>
          {t.same.backToClaims}
        </button>
        <PageView page={page} label={label} t={t} marks={marksFor(page.ref)} />
      </section>
    );
  }

  if (passing) {
    const nextPlayer = picks.length + 1;
    return (
      <section className="round round-pass" data-step="same_or_not" aria-labelledby="pass-heading">
        <p className="kicker">{progress}</p>
        <h2 id="pass-heading">{t.same.passTo(nextPlayer)}</h2>
        <p className="lede">{t.same.passLede}</p>
        <button type="button" className="btn btn-primary" data-primary onClick={() => setPassing(false)} autoFocus>
          {t.same.ready(nextPlayer)}
        </button>
      </section>
    );
  }

  const soloPick = !players && picks.length > 0 ? picks[0] : null;
  const answerBeat = players ? 3 : 2;
  return (
    <section className="round round-same" data-step="same_or_not" aria-labelledby="son-heading">
      <p className="kicker">
        {progress}
        {players && !revealed ? ` . ${t.same.playerTurn(picks.length + 1, players)}` : ""}
      </p>
      <h2 id="son-heading">{t.same.prompt}</h2>
      {round.level === 1 && !revealed && <p className="note level-one">{t.same.levelOneNote}</p>}
      <div className="claims">
        {[pa, pb].map((page, i) => (
          <div className="claim" key={page.ref}>
            <p className="claim-label">{i === 0 ? t.same.claimA : t.same.claimB}</p>
            <p className="claim-text">{round.play.claims[i].text[lang]}</p>
            <button type="button" className="btn btn-quiet" onClick={() => setReading(i === 0 ? 0 : 1)}>
              {i === 0 ? t.same.readA : t.same.readB}
            </button>
          </div>
        ))}
      </div>
      {!revealed && (
        <div className="choices" role="radiogroup" aria-labelledby="son-heading">
          {CHOICES.map((c, i) => (
            <button
              key={c}
              ref={(el) => {
                choiceRefs.current[i] = el;
              }}
              type="button"
              role="radio"
              aria-checked={false}
              className="choice"
              onClick={() => choose(c)}
              onKeyDown={(e) => {
                const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
                if (step !== 0) {
                  e.preventDefault();
                  choiceRefs.current[(i + step + CHOICES.length) % CHOICES.length]?.focus();
                }
              }}
            >
              <Shape index={i} className="choice-shape" />
              <span className="choice-key" aria-hidden="true">
                {String.fromCharCode(65 + i)}
              </span>
              <span className="choice-name">{t.same.choices[c]}</span>
              <span className="choice-help">{t.same.choiceHelp[c]}</span>
            </button>
          ))}
        </div>
      )}
      {revealed && (
        <div className="reveal" aria-live="polite" ref={revealRef}>
          {players && shown >= 1 && (
            <div className="beat">
              <SplitBar picks={picks} answer={answer} t={t} reducedMotion={reducedMotion} showCounts={shown >= 2} />
            </div>
          )}
          {soloPick && shown >= 1 && (
            <div className="beat pick-line">
              <Shape index={CHOICES.indexOf(soloPick)} className="inline-shape" />
              <p className="verdict-sub">{t.same.youSaid(t.same.choices[soloPick])}</p>
            </div>
          )}
          {shown >= answerBeat && (
            <div className="beat pick-line">
              <Shape index={CHOICES.indexOf(answer)} className="inline-shape" />
              <p className="verdict">
                {soloPick ? (soloPick === answer ? t.same.right : t.same.notQuite) + " " : ""}
                {t.same.answerWas(t.same.choices[answer])}
              </p>
            </div>
          )}
          {shown >= answerBeat + 1 && (
            <div className="beat">
              <p>{round.explanation[lang]}</p>
              <h3>{t.same.decisive}</h3>
              <ul className="quote-list">
                {decisive.map((q) => (
                  <li key={q.id}>
                    <blockquote>"{q.text}"</blockquote>
                    <span className="note">{q.page_ref === pa.ref ? t.same.pageA : t.same.pageB}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {shown >= answerBeat + 2 && (
            <div className="beat">
              <h3>{t.same.compared}</h3>
              <dl className="checklist">
                {CONSTRAINTS.filter((k) => round.play.constraints[k]).map((k) => {
                  const v = round.play.constraints[k];
                  return (
                    <div key={k} className={`check check-${v}`}>
                      <dt>{t.same.constraint[k] ?? k}</dt>
                      <dd>
                        <span className="check-mark" aria-hidden="true">
                          {MARK[v] ?? "?"}
                        </span>{" "}
                        {t.same.constraintValue[v] ?? v}
                      </dd>
                    </div>
                  );
                })}
              </dl>
            </div>
          )}
          {shown >= answerBeat + 2 && (
            <div className="beat">
              <StatusNote round={round} t={t} />
            </div>
          )}
          {shown >= answerBeat + 2 && (
            <div className="next-bar">
              <button type="button" className="btn btn-primary" data-primary onClick={() => onNext(picks)}>
                {nextLabel}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
