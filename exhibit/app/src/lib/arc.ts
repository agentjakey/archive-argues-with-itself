// A visit: the rounds one tap from the attract screen plays, and what the visitor answered in each.
// The arc is about four minutes: two When Was This? cards and two Same or Not? rounds, alternating,
// then one Time Dial question, then the chronicle. Results live in memory only and are gone when the
// visit resets.
import type { Choice, DialRound, Deck, SameOrNotRound, WhenRound } from "./deck";
import { roundsOf } from "./deck";

export type Step =
  | { kind: "when_was_this"; round: WhenRound }
  | { kind: "same_or_not"; round: SameOrNotRound }
  | { kind: "time_dial"; round: DialRound };

export type Result =
  | { kind: "when_was_this"; round: WhenRound; guess: number; points: number | null }
  | { kind: "same_or_not"; round: SameOrNotRound; picks: Choice[] }
  | { kind: "time_dial"; round: DialRound; year: number };

export function shuffle<T>(items: T[], random: () => number = Math.random): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

export function buildArc(deck: Deck, random: () => number = Math.random): Step[] {
  const when = shuffle(roundsOf(deck, "when_was_this"), random).slice(0, 2);
  const same = shuffle(roundsOf(deck, "same_or_not"), random).slice(0, 2);
  const dial = shuffle(roundsOf(deck, "time_dial"), random).slice(0, 1);
  const steps: Step[] = [];
  for (let i = 0; i < Math.max(when.length, same.length); i++) {
    if (when[i]) steps.push({ kind: "when_was_this", round: when[i] });
    if (same[i]) steps.push({ kind: "same_or_not", round: same[i] });
  }
  for (const round of dial) steps.push({ kind: "time_dial", round });
  return steps;
}

// The runs the "All games" menu starts: one game, a few rounds, the same chronicle at the end.
export function buildSingle(deck: Deck, kind: Step["kind"], random: () => number = Math.random): Step[] {
  if (kind === "when_was_this") return shuffle(roundsOf(deck, "when_was_this"), random).slice(0, 5).map((round) => ({ kind, round }));
  if (kind === "same_or_not") return shuffle(roundsOf(deck, "same_or_not"), random).slice(0, 3).map((round) => ({ kind, round }));
  return [];
}

export function totalPoints(results: Result[]): number {
  return results.reduce((sum, r) => sum + (r.kind === "when_was_this" ? r.points ?? 0 : 0), 0);
}
