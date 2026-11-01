// The exhibit shell: the attract loop (Gap Hunt walking the map), the game menu, the four games, the
// language switch and the reset after a quiet minute. Online, the footer links the site's Privacy and
// Accessibility pages; on the kiosk the same one-line privacy note shows on every screen.
import { useCallback, useEffect, useState } from "react";
import type { Deck, Lang, WhenRound } from "./lib/deck";
import { loadDeck, roundsOf } from "./lib/deck";
import { countEvent, loadKiosk, type KioskConfig } from "./lib/kiosk";
import { useIdleReset } from "./lib/idle";
import { usePrimaryEnter } from "./lib/input";
import { STRINGS } from "./lib/strings";
import { GapHunt } from "./modes/GapHunt";
import { SameOrNot } from "./modes/SameOrNot";
import { TimeDial } from "./modes/TimeDial";
import { WhenWasThis } from "./modes/WhenWasThis";

type Screen = "attract" | "menu" | "time_dial" | "same_or_not" | "when_was_this" | "gap_hunt";
const MODES: Exclude<Screen, "attract" | "menu">[] = ["time_dial", "same_or_not", "when_was_this", "gap_hunt"];

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

// When Was This? draws a different short run of cards each visit, so a visitor is not shown the
// whole deck; the order is shuffled in memory only.
function sample<T>(items: T[], n: number): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy.slice(0, n);
}

export function App({ initialDeck, initialKiosk }: { initialDeck?: Deck; initialKiosk?: KioskConfig }) {
  const [deck, setDeck] = useState<Deck | null>(initialDeck ?? null);
  const [kiosk, setKiosk] = useState<KioskConfig>(initialKiosk ?? { kiosk: false, idle_reset_seconds: 60, printer: false });
  const [failed, setFailed] = useState(false);
  const [lang, setLang] = useState<Lang>("en");
  const [screen, setScreen] = useState<Screen>(initialKiosk?.kiosk ? "attract" : "menu");
  const [reducedMotion, setReducedMotion] = useState(prefersReducedMotion());
  const [visit, setVisit] = useState(0);
  const [whenRun, setWhenRun] = useState<WhenRound[]>([]);
  const t = STRINGS[lang];

  useEffect(() => {
    if (initialDeck) return;
    loadDeck().then(setDeck).catch(() => setFailed(true));
  }, [initialDeck]);
  useEffect(() => {
    if (initialKiosk) return;
    loadKiosk().then((k) => {
      setKiosk(k);
      if (k.kiosk) setScreen("attract");
    });
  }, [initialKiosk]);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = `${t.title}: ${lang === "fr" ? "exposition" : "exhibit"}`;
  }, [lang, t.title]);
  useEffect(() => {
    document.documentElement.classList.toggle("reduce-motion", reducedMotion);
  }, [reducedMotion]);

  const reset = useCallback(() => {
    setScreen(kiosk.kiosk ? "attract" : "menu");
    setLang("en");
    setVisit((v) => v + 1);
    window.scrollTo(0, 0);
  }, [kiosk.kiosk]);
  const warning = useIdleReset(kiosk.idle_reset_seconds, reset, kiosk.kiosk && screen !== "attract");
  usePrimaryEnter();
  const onEvent = useCallback((e: string) => countEvent(kiosk, e), [kiosk]);
  const go = (s: Screen) => {
    if (s !== "menu" && s !== "attract") onEvent(`${s}:start`);
    if (s === "when_was_this" && deck) setWhenRun(sample(roundsOf(deck, "when_was_this"), 5));
    setScreen(s);
    window.scrollTo(0, 0);
  };

  if (failed) {
    return (
      <main className="shell">
        <p role="alert" className="error">{t.error.deck}</p>
      </main>
    );
  }
  if (!deck) return <main className="shell" aria-busy="true" />;
  const [first, last] = deck.settings.dial;

  return (
    <div className="shell" key={visit}>
      <header className="top">
        <button type="button" className="brand" onClick={() => go("menu")}>
          <span className="brand-title">{t.title}</span>
          <span className="brand-sub">{t.subtitle}</span>
        </button>
        <div className="top-actions">
          <button type="button" className="btn btn-quiet" onClick={() => setLang(lang === "en" ? "fr" : "en")} lang={lang === "en" ? "fr" : "en"}>
            {t.language}
          </button>
          <button type="button" className="btn btn-quiet" aria-pressed={reducedMotion} onClick={() => setReducedMotion(!reducedMotion)}>
            {t.reducedMotion}
          </button>
          {screen !== "menu" && screen !== "attract" && (
            <button type="button" className="btn btn-quiet" onClick={() => go("menu")}>
              {t.home}
            </button>
          )}
        </div>
      </header>
      <main className="main" id="main">
        {screen === "attract" && deck.gap_hunt && (
          <>
            <GapHunt grid={deck.gap_hunt} lang={lang} t={t} attract reducedMotion={reducedMotion} onStart={() => go("menu")} />
            <button type="button" className="btn btn-big start" data-primary onClick={() => go("menu")}>
              {t.touchToStart}
            </button>
          </>
        )}
        {screen === "attract" && !deck.gap_hunt && (
          <button type="button" className="btn btn-big start" data-primary onClick={() => go("menu")}>
            {t.touchToStart}
          </button>
        )}
        {screen === "menu" && (
          <section className="mode" aria-labelledby="menu-heading">
            <h1 id="menu-heading">{t.modesHeading}</h1>
            <ul className="menu">
              {MODES.map((m) => (
                <li key={m}>
                  <button type="button" className="menu-item" onClick={() => go(m)}>
                    <span className="menu-name">{t.modes[m].name}</span>
                    <span className="menu-blurb">{t.modes[m].blurb}</span>
                  </button>
                </li>
              ))}
            </ul>
            <ul className="lessons" aria-label="Lessons">
              <li>{t.lessons.read}</li>
              <li>{t.lessons.changes}</li>
              <li>{t.lessons.gaps}</li>
              <li>{t.lessons.compare}</li>
            </ul>
          </section>
        )}
        {screen === "time_dial" && <TimeDial rounds={roundsOf(deck, "time_dial")} lang={lang} t={t} first={first} last={last} onEvent={onEvent} />}
        {screen === "same_or_not" && (
          <SameOrNot rounds={roundsOf(deck, "same_or_not")} lang={lang} t={t} canPrint={kiosk.printer || !kiosk.kiosk} onEvent={onEvent} onDone={() => go("menu")} />
        )}
        {screen === "when_was_this" && (
          <WhenWasThis
            rounds={whenRun}
            lang={lang}
            t={t}
            first={first}
            last={last}
            canPrint={kiosk.printer || !kiosk.kiosk}
            onEvent={onEvent}
            onDone={() => go("menu")}
          />
        )}
        {screen === "gap_hunt" && deck.gap_hunt && <GapHunt grid={deck.gap_hunt} lang={lang} t={t} reducedMotion={reducedMotion} />}
      </main>
      {warning && (
        <p className="idle-warning" role="status">
          {t.idle}
        </p>
      )}
      <footer className="foot">
        <p>{t.privacy}</p>
        {!kiosk.kiosk && (
          <p>
            <a href="/?view=privacy">{t.footer.privacy}</a> . <a href="/?view=accessibility">{t.footer.accessibility}</a> .{" "}
            <a href="/">{t.footer.site}</a>
          </p>
        )}
      </footer>
    </div>
  );
}
