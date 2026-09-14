import { useEffect, useState } from "react";
import { ATTRACT_HOOK, ATTRACT_QUESTIONS, ATTRACT_SUBHOOK, DECADES } from "../lib/attract";

/** The idle/home attract beat: the hook, a rotating provocative question (motion), and an
 *  animated decade rail teasing the change-over-time payoff. Not a search box. All copy lives
 *  in lib/attract. Pure client, works offline (N6). */
export function AttractHero() {
  const [i, setI] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    let inner: number | undefined;
    const outer = window.setInterval(() => {
      setVisible(false);   // fade out, swap, fade in -> visible motion even without a story open
      inner = window.setTimeout(() => {
        setI((n) => (n + 1) % ATTRACT_QUESTIONS.length);
        setVisible(true);
      }, 350);
    }, 4500);
    return () => {
      window.clearInterval(outer);
      if (inner) window.clearTimeout(inner);
    };
  }, []);

  return (
    <section className="rule-left my-4" aria-label="What this is">
      <h2 className="font-serif text-3xl leading-tight">{ATTRACT_HOOK}</h2>
      <p className="mt-2 max-w-prose text-lg">{ATTRACT_SUBHOOK}</p>
      <p className={`mt-3 max-w-prose italic text-muted transition-opacity duration-300 ${visible ? "opacity-100" : "opacity-0"}`}>
        {ATTRACT_QUESTIONS[i]}
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1" aria-hidden="true">
        {DECADES.map((d, k) => (
          <span key={d} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-ink animate-pulse" style={{ animationDelay: `${k * 300}ms` }} />
            <span className="text-xs text-muted">{d}</span>
          </span>
        ))}
      </div>
    </section>
  );
}
