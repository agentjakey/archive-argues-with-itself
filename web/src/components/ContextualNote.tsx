import type { Flagged } from "../types";
import { contextualNote } from "../lib/sensitivity";
import { CrisisLines } from "./CrisisLines";

interface Props {
  flagged: Flagged;
}

/** A dignified, year-aware note shown near a flagged result in every path (normal answer,
 *  compare view, limited-mode card), with its topic-appropriate support lines beneath. No
 *  alarm styling; a quiet left rule. All copy comes from lib/sensitivity. Renders offline. */
export function ContextualNote({ flagged }: Props) {
  return (
    <aside className="rule-left mt-4" role="note" aria-label="A note on this record">
      <p className="font-sans text-xs uppercase tracking-wide text-muted">A note on this record</p>
      <p className="mt-1 max-w-prose leading-relaxed">{contextualNote(flagged)}</p>
      <CrisisLines lines={flagged.crisis_lines} />
    </aside>
  );
}
