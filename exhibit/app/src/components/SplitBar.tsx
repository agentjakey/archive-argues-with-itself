// How the room voted, as one bar split by choice. The reveal is paced the way Agora paces it: the
// bar starts evenly split and settles to the real split, then the counts appear. Each part of the
// bar carries its shape, and the counts are written out below it, so nothing rests on colour.
import { useEffect, useState } from "react";
import type { Choice } from "../lib/deck";
import { CHOICES } from "../lib/deck";
import type { Strings } from "../lib/strings";
import { Shape } from "./Shape";

type Props = { picks: Choice[]; answer: Choice; t: Strings; reducedMotion: boolean; showCounts: boolean };

export function SplitBar({ picks, answer, t, reducedMotion, showCounts }: Props) {
  const counts = CHOICES.map((c) => picks.filter((p) => p === c).length);
  const total = Math.max(1, picks.length);
  const used = CHOICES.map((_, i) => i).filter((i) => counts[i] > 0);
  const real = CHOICES.map((_, i) => (counts[i] / total) * 100);
  const even = CHOICES.map((_, i) => (counts[i] > 0 ? 100 / used.length : 0));
  const [settled, setSettled] = useState(reducedMotion);
  useEffect(() => {
    if (reducedMotion) {
      setSettled(true);
      return;
    }
    setSettled(false);
    const timer = window.setTimeout(() => setSettled(true), 100);
    return () => window.clearTimeout(timer);
  }, [reducedMotion, picks.length]);
  const widths = settled ? real : even;
  const matched = counts[CHOICES.indexOf(answer)];
  const summary = CHOICES.filter((_, i) => counts[i] > 0)
    .map((c) => `${t.same.choices[c]}: ${counts[CHOICES.indexOf(c)]}`)
    .join(", ");
  return (
    <figure className="split">
      <figcaption className="split-caption">{t.same.splitLabel}</figcaption>
      <div className="split-bar" role="img" aria-label={`${t.same.splitLabel}. ${summary}.`}>
        {CHOICES.map((c, i) =>
          counts[i] > 0 ? (
            <div key={c} className={`split-part split-part-${i}`} style={{ width: `${widths[i]}%` }}>
              <Shape index={i} />
            </div>
          ) : null,
        )}
      </div>
      {showCounts && (
        <>
          <ul className="split-counts">
            {CHOICES.map((c, i) => (
              <li key={c} className={c === answer ? "split-answer" : undefined}>
                <Shape index={i} />
                <span className="choice-key" aria-hidden="true">
                  {String.fromCharCode(65 + i)}
                </span>
                <span className="split-count">{counts[i]}</span>
                <span>
                  {t.same.choices[c]}
                  {c === answer ? <strong className="split-tag"> ({t.same.recordAnswer})</strong> : null}
                </span>
              </li>
            ))}
          </ul>
          <p className="split-result">{t.same.split(matched, picks.length)}</p>
        </>
      )}
    </figure>
  );
}

export function MiniSplit({ picks, answer, t }: { picks: Choice[]; answer: Choice; t: Strings }) {
  const total = Math.max(1, picks.length);
  const matched = picks.filter((p) => p === answer).length;
  return (
    <span className="mini-split">
      <span className="mini-bar" aria-hidden="true">
        <span className="mini-bar-hit" style={{ width: `${(matched / total) * 100}%` }} />
      </span>
      <span>{t.chronicle.groupMatched(matched, picks.length)}</span>
    </span>
  );
}
