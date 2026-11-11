import { fireEvent, render, screen } from "@testing-library/react";
import { App } from "../App";
import type { Deck, WhenRound } from "../lib/deck";
import { STRINGS } from "../lib/strings";
import published from "../../../../site/exhibit/deck.json";

// Every When Was This? card in the published deck, before the guess: nothing a visitor can read or
// hear (the page text, the title, the issuer, the label, the scan's alt text and every accessible name)
// contains the card's own answer year. Run against site/exhibit/deck.json, the deck that ships.
const DECK = published as unknown as Deck;
const ONLINE = { kiosk: false, idle_reset_seconds: 60, printer: false, counting: false };
const en = STRINGS.en;
const WHEN = DECK.rounds.filter((r): r is WhenRound => r.mode === "when_was_this");

function everythingReadable(root: HTMLElement): string {
  const parts = [root.textContent ?? ""];
  for (const el of Array.from(root.querySelectorAll("*"))) {
    for (const name of ["alt", "aria-label", "title", "aria-valuetext"]) {
      const value = el.getAttribute(name);
      if (value) parts.push(value);
    }
  }
  return parts.join("\n");
}

describe("When Was This? cards keep their year hidden until the guess", () => {
  it("the published deck has cards to check", () => {
    expect(WHEN.length).toBeGreaterThan(10);
  });

  it.each(WHEN.map((r) => [r.id, r] as const))("%s shows no trace of its answer year", (_id, round) => {
    const deck = { ...DECK, rounds: [round] } as Deck;
    const { container, unmount } = render(<App initialDeck={deck} initialKiosk={ONLINE} />);
    fireEvent.click(screen.getByRole("button", { name: en.reducedMotion }));
    fireEvent.click(screen.getByRole("button", { name: en.touchToStart }));
    expect(screen.getByRole("heading", { name: en.when.prompt })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: en.showPage }));
    const year = String(round.play.year);
    const readable = everythingReadable(container);
    expect(readable).not.toMatch(new RegExp(`(?<![0-9])${year}(?![0-9])`));
    unmount();
  });
});
