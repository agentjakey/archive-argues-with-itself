// The exhibit shell. The attract screen is one tap from play: "Touch to start" runs the four-minute
// visit (two When Was This? cards and two Same or Not? rounds, then one Time Dial question), which
// ends in the chronicle and the evidence card. "Play as a group" runs the same visit with secret
// votes and the split-bar reveal; "All games" opens each game on its own, Gap Hunt included.
// Language, sound (off by default) and less motion are one touch away on every screen, and the
// kiosk returns to the attract screen after a quiet minute. Online, the footer links the site's
// Privacy and Accessibility pages; on the kiosk the same one-line privacy note shows on every screen.
import { useCallback, useEffect, useRef, useState } from "react";
import type { Choice, Deck, DialRound, Lang } from "./lib/deck";
import { loadDeck, roundsOf } from "./lib/deck";
import type { Result, Step } from "./lib/arc";
import { buildArc, buildSingle } from "./lib/arc";
import { countEvent, loadKiosk, type KioskConfig } from "./lib/kiosk";
import { useIdleReset } from "./lib/idle";
import { usePrimaryEnter } from "./lib/input";
import { SettingsContext } from "./lib/settings";
import { STRINGS } from "./lib/strings";
import { Chronicle } from "./modes/Chronicle";
import { GapHunt } from "./modes/GapHunt";
import { SameOrNot } from "./modes/SameOrNot";
import { TimeDial, TimeDialPicker } from "./modes/TimeDial";
import { WhenWasThis } from "./modes/WhenWasThis";

type Screen = "attract" | "players" | "menu" | "picker" | "run" | "chronicle" | "gap_hunt";
type Run = { steps: Step[]; index: number; results: Result[]; players: number | null };
const MENU = ["when_was_this", "same_or_not", "time_dial", "gap_hunt"] as const;
const PLAYER_COUNTS = [2, 3, 4, 5, 6];

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

export function App({ initialDeck, initialKiosk }: { initialDeck?: Deck; initialKiosk?: KioskConfig }) {
  const [deck, setDeck] = useState<Deck | null>(initialDeck ?? null);
  const [kiosk, setKiosk] = useState<KioskConfig>(initialKiosk ?? { kiosk: false, idle_reset_seconds: 60, printer: false });
  const [failed, setFailed] = useState(false);
  const [lang, setLang] = useState<Lang>("en");
  const [screen, setScreen] = useState<Screen>("attract");
  const [reducedMotion, setReducedMotion] = useState(prefersReducedMotion());
  const [sound, setSound] = useState(false);
  const [visit, setVisit] = useState(0);
  const [run, setRun] = useState<Run | null>(null);
  const [quoteIndex, setQuoteIndex] = useState(0);
  const main = useRef<HTMLElement>(null);
  const t = STRINGS[lang];

  useEffect(() => {
    if (initialDeck) return;
    loadDeck().then(setDeck).catch(() => setFailed(true));
  }, [initialDeck]);
  useEffect(() => {
    if (initialKiosk) return;
    loadKiosk().then(setKiosk);
  }, [initialKiosk]);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = `${t.title}: ${lang === "fr" ? "exposition" : "exhibit"}`;
  }, [lang, t.title]);
  useEffect(() => {
    document.documentElement.classList.toggle("reduce-motion", reducedMotion);
  }, [reducedMotion]);

  // The attract screen shows one real line at a time from the When Was This? clues (page text,
  // with no year in it), changing every few seconds unless the visitor asked for less motion.
  const attractQuotes = deck
    ? roundsOf(deck, "when_was_this")
        .flatMap((r) => r.quotes.filter((q) => q.role === "clue" && q.text.length >= 40 && q.text.length <= 160).map((q) => ({ text: q.text, label: r.play.label })))
        .slice(0, 24)
    : [];
  useEffect(() => {
    if (screen !== "attract" || reducedMotion || attractQuotes.length < 2) return;
    const timer = window.setInterval(() => setQuoteIndex((n) => n + 1), 7000);
    return () => window.clearInterval(timer);
  }, [screen, reducedMotion, attractQuotes.length]);

  const reset = useCallback(() => {
    setScreen("attract");
    setLang("en");
    setSound(false);
    setRun(null);
    setReducedMotion(prefersReducedMotion());
    setVisit((v) => v + 1);
    window.scrollTo(0, 0);
  }, []);
  const warning = useIdleReset(kiosk.idle_reset_seconds, reset, kiosk.kiosk && screen !== "attract");
  usePrimaryEnter();
  const onEvent = useCallback((e: string) => countEvent(kiosk, e), [kiosk]);

  const show = (s: Screen) => {
    setScreen(s);
    window.scrollTo(0, 0);
  };
  // A new screen or round starts reading from the top: focus moves to the main area (so the dial's
  // press still finds the screen's main button), unless the visitor has already moved focus on.
  const stepIndex = run?.index ?? -1;
  useEffect(() => {
    const active = document.activeElement;
    if (!active || active === document.body || !active.isConnected) main.current?.focus({ preventScroll: true });
  }, [screen, stepIndex]);
  const startRun = (steps: Step[], players: number | null, event: string) => {
    if (steps.length === 0) return;
    onEvent(event);
    setRun({ steps, index: 0, results: [], players });
    show("run");
  };
  const startVisit = (players: number | null) => {
    if (!deck) return;
    startRun(buildArc(deck), players, players ? "visit:group" : "visit:start");
  };
  const finishStep = (result: Result) => {
    if (!run) return;
    const results = [...run.results, result];
    if (run.index + 1 < run.steps.length) {
      setRun({ ...run, index: run.index + 1, results });
      show("run");
    } else {
      onEvent("visit:finish");
      setRun({ ...run, results });
      show("chronicle");
    }
  };

  if (failed) {
    return (
      <main className="shell">
        <p role="alert" className="error">
          {t.error.deck}
        </p>
      </main>
    );
  }
  if (!deck) return <main className="shell" aria-busy="true" />;
  const [first, last] = deck.settings.dial;
  const canPrint = kiosk.printer || !kiosk.kiosk;
  const step = run && screen === "run" ? run.steps[run.index] : null;
  const progress = run ? t.progress(run.index + 1, run.steps.length) : "";
  const nextLabel = run && run.index + 1 < run.steps.length ? t.next : t.done;
  const quote = attractQuotes.length ? attractQuotes[quoteIndex % attractQuotes.length] : null;

  return (
    <SettingsContext.Provider value={{ sound, reducedMotion }}>
      <div className={`shell screen-${screen}`} key={visit}>
        <header className="top">
          <p className="brand">
            <span className="brand-title">{t.title}</span>
          </p>
          <div className="top-actions">
            <button type="button" className="btn btn-quiet" onClick={() => setLang(lang === "en" ? "fr" : "en")} lang={lang === "en" ? "fr" : "en"}>
              {t.language}
            </button>
            <button type="button" className="btn btn-quiet toggle" aria-pressed={sound} onClick={() => setSound(!sound)}>
              {t.sound}
            </button>
            <button type="button" className="btn btn-quiet toggle" aria-pressed={reducedMotion} onClick={() => setReducedMotion(!reducedMotion)}>
              {t.reducedMotion}
            </button>
            {screen !== "attract" && (
              <button type="button" className="btn btn-quiet" onClick={reset}>
                {t.home}
              </button>
            )}
          </div>
        </header>
        <main className="main" id="main" ref={main} tabIndex={-1}>
          {screen === "attract" && (
            <section className="attract" aria-labelledby="attract-heading">
              <h1 id="attract-heading">{t.title}</h1>
              <p className="attract-hook">{t.attract.hook}</p>
              {quote && (
                <figure className="attract-quote" key={quoteIndex}>
                  <blockquote>"{quote.text}"</blockquote>
                  <figcaption>
                    {t.attract.quoteFrom}: {quote.label[lang]}
                  </figcaption>
                </figure>
              )}
              <button type="button" className="btn btn-start" data-primary onClick={() => startVisit(null)}>
                {t.touchToStart}
              </button>
              <p className="attract-length">{t.attract.length}</p>
              <div className="attract-more">
                <button type="button" className="btn btn-quiet" onClick={() => show("players")}>
                  {t.attract.group}
                </button>
                <button type="button" className="btn btn-quiet" onClick={() => show("menu")}>
                  {t.attract.allGames}
                </button>
              </div>
            </section>
          )}
          {screen === "players" && (
            <section className="round round-players" aria-labelledby="players-heading">
              <h2 id="players-heading">{t.players.heading}</h2>
              <p className="lede">{t.players.lede}</p>
              <ul className="player-counts">
                {PLAYER_COUNTS.map((n) => (
                  <li key={n}>
                    <button type="button" className="btn btn-count" onClick={() => startVisit(n)}>
                      {t.players.count(n)}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {screen === "menu" && (
            <section className="round round-menu" aria-labelledby="menu-heading">
              <h2 id="menu-heading">{t.modesHeading}</h2>
              <ul className="menu">
                {MENU.map((m) => (
                  <li key={m}>
                    <button
                      type="button"
                      className="menu-item"
                      onClick={() => {
                        if (m === "gap_hunt") {
                          onEvent("gap_hunt:start");
                          show("gap_hunt");
                        } else if (m === "time_dial") show("picker");
                        else startRun(buildSingle(deck, m), null, `${m}:start`);
                      }}
                    >
                      <span className="menu-name">{t.modes[m].name}</span>
                      <span className="menu-blurb">{t.modes[m].blurb}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <ul className="lessons" aria-label={lang === "fr" ? "Le\u00e7ons" : "Lessons"}>
                <li>{t.lessons.read}</li>
                <li>{t.lessons.changes}</li>
                <li>{t.lessons.gaps}</li>
                <li>{t.lessons.compare}</li>
              </ul>
            </section>
          )}
          {screen === "picker" && (
            <TimeDialPicker
              rounds={roundsOf(deck, "time_dial")}
              lang={lang}
              t={t}
              onPick={(round: DialRound) => startRun([{ kind: "time_dial", round }], null, "time_dial:start")}
            />
          )}
          {screen === "gap_hunt" && deck.gap_hunt && <GapHunt grid={deck.gap_hunt} lang={lang} t={t} reducedMotion={reducedMotion} />}
          {step?.kind === "when_was_this" && (
            <WhenWasThis
              key={`${run!.index}-${step.round.id}`}
              round={step.round}
              lang={lang}
              t={t}
              first={first}
              last={last}
              progress={progress}
              nextLabel={nextLabel}
              onEvent={onEvent}
              onNext={(guess: number, points: number | null) => finishStep({ kind: "when_was_this", round: step.round, guess, points })}
            />
          )}
          {step?.kind === "same_or_not" && (
            <SameOrNot
              key={`${run!.index}-${step.round.id}`}
              round={step.round}
              lang={lang}
              t={t}
              players={run!.players}
              progress={progress}
              nextLabel={nextLabel}
              onEvent={onEvent}
              onNext={(picks: Choice[]) => finishStep({ kind: "same_or_not", round: step.round, picks })}
            />
          )}
          {step?.kind === "time_dial" && (
            <TimeDial
              key={`${run!.index}-${step.round.id}`}
              round={step.round}
              lang={lang}
              t={t}
              first={first}
              last={last}
              progress={progress}
              nextLabel={nextLabel}
              onNext={(year: number) => finishStep({ kind: "time_dial", round: step.round, year })}
            />
          )}
          {screen === "chronicle" && run && (
            <Chronicle
              results={run.results}
              lang={lang}
              t={t}
              canPrint={canPrint}
              onEvent={onEvent}
              onAgain={() => startVisit(run.players)}
              onDone={reset}
            />
          )}
        </main>
        {warning && (
          <p className="idle-warning" role="status">
            {t.idle}
          </p>
        )}
        <footer className="foot">
          <p>{t.privacy}</p>
          {t.frenchPending && <p lang="fr">{t.frenchPending}</p>}
          {!kiosk.kiosk && (
            <p>
              <a href="/?view=privacy">{t.footer.privacy}</a> . <a href="/?view=accessibility">{t.footer.accessibility}</a> .{" "}
              <a href="/">{t.footer.site}</a>
            </p>
          )}
        </footer>
      </div>
    </SettingsContext.Provider>
  );
}
