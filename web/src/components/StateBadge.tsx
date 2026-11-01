import type { Answer } from "../types";

/** What each evidence state tells the reader, in plain words. The state comes from the engine
 *  (generate/answer_v2.py, governance); nothing here decides it. */
export const STATE_TEXT: Record<string, { label: string; line: string }> = {
  SUPPORTED: { label: "Answered", line: "The cited pages answer the question." },
  PARTIALLY_SUPPORTED: {
    label: "Partly answered",
    line: "The cited pages are relevant but answer only part of the question.",
  },
  CONFLICTING: {
    label: "Records disagree",
    line: "Comparable records report different things. Both are shown; neither is picked.",
  },
  INCOMPARABLE: {
    label: "Not comparable",
    line: "The records describe different populations, periods, programs or measures, so they are shown separately and not compared.",
  },
  INSUFFICIENT_EVIDENCE: { label: "Not enough evidence", line: "The searched pages do not answer this question." },
  RESTRICTED: {
    label: "Restricted",
    line: "Records this question needs are restricted by the authority named below and are not used here.",
  },
};

const COVERAGE_TEXT: Record<string, string> = {
  not_indexed: "The question asks about a period or place this collection does not index. That says nothing about the archive as a whole.",
  absent_from_examined_holdings:
    "The indexed pages were searched and none answers it. Pages not yet indexed were not searched.",
};

interface Props {
  answer: Answer;
}

/** The evidence state of an answer, with the engine's reason and any downgrade it made. Shows
 *  nothing for answers written before states existed. */
export function StateBadge({ answer }: Props) {
  if (answer.reviewed) {
    return (
      <p className="mt-2 text-sm text-muted" data-testid="reviewed-line">
        <span className="tag mr-2">Reviewed answer</span>
        Kept as reviewed from the earlier version of the tool.
      </p>
    );
  }
  const state = answer.state;
  if (!state || !STATE_TEXT[state]) return null;
  const info = STATE_TEXT[state];
  return (
    <div className="mt-2" data-testid="state-badge">
      <p className="text-sm">
        <span className="tag mr-2">{info.label}</span>
        {info.line}
      </p>
      {answer.state_reason && <p className="mt-1 text-sm text-muted">{answer.state_reason}</p>}
      {state === "INSUFFICIENT_EVIDENCE" && answer.coverage_state && COVERAGE_TEXT[answer.coverage_state] && (
        <p className="mt-1 text-sm text-muted">{COVERAGE_TEXT[answer.coverage_state]}</p>
      )}
      {(answer.gate_notes ?? []).map((n) => (
        <p key={n} className="mt-1 text-sm text-muted">
          {n}
        </p>
      ))}
    </div>
  );
}
