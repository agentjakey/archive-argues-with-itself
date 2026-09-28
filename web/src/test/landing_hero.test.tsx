import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LandingHero } from "../components/LandingHero";
import type { Story } from "../types";
import { row } from "./fixtures";

const story = (id: string, question: string, caption: string): Story => ({
  id,
  question,
  filters: {},
  caption,
  pins: [row({ passage_id: `${id}-a`, year: 1974 }), row({ passage_id: `${id}-b`, year: 1999 })],
});

const noop = () => {};

describe("LandingHero", () => {
  it("shows a curated example: the question, two numbered pages, the caption, and the primary CTA", () => {
    const onAsk = vi.fn();
    render(
      <LandingHero
        stories={[story("s1", "How did the advice change?", "In 1974 one thing; by 1999 another.")]}
        loading={false}
        canAsk={true}
        busy={false}
        onAsk={onAsk}
        onOpenStory={noop}
        onOpen={noop}
      />,
    );
    // Clearly labelled a curated example, not a live verified answer
    expect(screen.getByText(/curated example/i)).toBeInTheDocument();
    // The question is the headline
    expect(screen.getByRole("heading", { name: "How did the advice change?" })).toBeInTheDocument();
    // The two numbered pages are present (asserted via their source alt text)
    expect(screen.getByAltText(/source 1/)).toBeInTheDocument();
    expect(screen.getByAltText(/source 2/)).toBeInTheDocument();
    // The author caption is shown
    expect(screen.getByText(/In 1974 one thing; by 1999 another\./)).toBeInTheDocument();
    // The one primary call to action
    fireEvent.click(screen.getByRole("button", { name: "Ask your own question" }));
    expect(onAsk).toHaveBeenCalledTimes(1);
  });

  it("falls back to the static hook when the scope ships no stories", () => {
    render(
      <LandingHero
        stories={[]}
        loading={false}
        canAsk={true}
        busy={false}
        onAsk={noop}
        onOpenStory={noop}
        onOpen={noop}
      />,
    );
    expect(screen.getByText("The record argues with itself.")).toBeInTheDocument();
  });

  it("holds a stable placeholder while stories load, never flashing the hook", () => {
    render(
      <LandingHero
        stories={[]}
        loading={true}
        canAsk={true}
        busy={false}
        onAsk={noop}
        onOpenStory={noop}
        onOpen={noop}
      />,
    );
    expect(screen.queryByText("The record argues with itself.")).toBeNull();
  });
});
