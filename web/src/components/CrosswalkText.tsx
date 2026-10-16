import { highlight } from "../lib/highlight";
import { CROSSWALK_ENABLED, crosswalkSegments } from "../lib/sensitivity";

interface Props {
  text: string;
  salientTerms: string[];
}

/** Renders an excerpt with the salient-term highlight (exactly as before) and, ONLY when the
 *  reparative crosswalk is enabled, a non-destructive annotation on unambiguous historical terms in
 *  the non-highlighted spans. With the crosswalk OFF (the default) this renders the same marks and
 *  spans the inline highlight produced before, so no benign content is ever annotated and the excerpt
 *  text is never rewritten. The matched word is shown unchanged; the contemporary term is the tool's
 *  annotation beside it. */
export function CrosswalkText({ text, salientTerms }: Props) {
  return (
    <>
      {highlight(text, salientTerms).map((seg, i) => {
        if (seg.hit) return <mark key={i}>{seg.text}</mark>;
        if (!CROSSWALK_ENABLED) return <span key={i}>{seg.text}</span>;
        return crosswalkSegments(seg.text).map((cs, j) =>
          cs.term ? (
            <span
              key={`${i}-${j}`}
              className="underline decoration-dotted decoration-muted underline-offset-2"
              title={`The record's historical term. Today: ${cs.term.contemporary}.`}
            >
              {cs.text}
              <span className="ml-1 text-xs text-muted" aria-hidden="true">
                [today: {cs.term.contemporary}]
              </span>
              <span className="sr-only"> (the record's historical term; today: {cs.term.contemporary})</span>
            </span>
          ) : (
            <span key={`${i}-${j}`}>{cs.text}</span>
          ),
        );
      })}
    </>
  );
}
