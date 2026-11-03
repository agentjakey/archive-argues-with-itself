import { useEffect, useRef, useState } from "react";
import type { FeaturedQuestion } from "../lib/featured";

interface Props {
  questions: FeaturedQuestion[];
  onPick: (q: FeaturedQuestion) => void;
  disabled?: boolean;
  /** Stop the rotation: the visitor is typing or has text in the box. */
  paused?: boolean;
}

const DWELL_MS = 6000;

function prefersReducedMotion(): boolean {
  return !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Example questions under the search box. Every one is a recorded answer that cites its pages, so
 *  a click always lands on a real, checkable result. The topics stay on screen as buttons; one line
 *  above them shows a full question and crossfades to the next every few seconds. The line pauses
 *  while the pointer or focus is on it, while the visitor types, and never moves at all with reduced
 *  motion. Its changes are not announced (aria-live off), so a screen reader is never interrupted. */
export function Suggestions({ questions, onPick, disabled, paused }: Props) {
  const [index, setIndex] = useState(0);
  const [hover, setHover] = useState(false);
  const [fading, setFading] = useState(false);
  const reduced = useRef(prefersReducedMotion());
  const stopped = paused || hover || reduced.current || questions.length < 2;

  useEffect(() => {
    if (stopped) return;
    let fadeTimer = 0;
    const id = window.setInterval(() => {
      setFading(true);
      fadeTimer = window.setTimeout(() => {
        setIndex((i) => (i + 1) % questions.length);
        setFading(false);
      }, 260);
    }, DWELL_MS);
    return () => {
      window.clearInterval(id);
      window.clearTimeout(fadeTimer);
      setFading(false);
    };
  }, [stopped, questions.length]);

  if (!questions.length) return null;
  const current = questions[index % questions.length];

  return (
    <div className="suggestions">
      <p
        className="suggestion-line"
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        onFocus={() => setHover(true)}
        onBlur={() => setHover(false)}
        aria-live="off"
      >
        <span className="suggestion-try">Try</span>{" "}
        <button
          type="button"
          className={`suggestion-question${fading ? " is-fading" : ""}`}
          onClick={() => onPick(current)}
          disabled={disabled}
        >
          {current.text}
        </button>
      </p>
      <div className="topic-row" role="group" aria-label="Example topics with recorded, cited answers">
        {questions.map((q) => (
          <button
            key={q.qid}
            type="button"
            className="topic-chip"
            onClick={() => onPick(q)}
            disabled={disabled}
            aria-label={`${q.topic}: ${q.text}`}
            title={q.text}
          >
            {q.topic}
          </button>
        ))}
      </div>
    </div>
  );
}
