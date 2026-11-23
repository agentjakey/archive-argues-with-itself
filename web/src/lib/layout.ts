// Which layout the ask page shows: the landing (hero, stories, browse) or the results layout (the
// sticky ask bar, then the answer, the waiting line, an error or the waking card).
import type { AskStatus } from "../hooks/useAsk";

/** The landing shows only when nothing is being asked or shown. While a question waits for a
 *  waking engine it is still being asked: the results layout keeps the waking card ("your question
 *  is kept") right under the ask bar. Showing the landing then put that card below the whole home
 *  page, so a visitor saw the home page with their question in the box and thought it had failed. */
export function showsLanding(view: string | null, hasResponse: boolean, status: AskStatus): boolean {
  return view === null && !hasResponse && status !== "waiting" && status !== "waking" && status !== "error";
}
