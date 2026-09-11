import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnswerCard } from "../components/AnswerCard";
import { cardId, numberCitations } from "../lib/citations";
import type { Answer } from "../types";
import { abstention, row } from "./fixtures";

describe("citation numbering", () => {
  it("numbers by first appearance across sentences", () => {
    const n = numberCitations([{ text: "", cited_ids: ["b", "a"] }, { text: "", cited_ids: ["a", "c"] }]);
    expect([...n.entries()]).toEqual([["b", 1], ["a", 2], ["c", 3]]);
    expect(cardId("item#12:0")).toBe("card-item-12-0");
  });

  it("renders marks and a Sources list, plus the cache line when served from cache", () => {
    const a: Answer = {
      ...abstention(),
      abstained: false,
      abstention_text: null,
      text: "Prices rose. Clinics opened.",
      sentences: [
        { text: "Prices rose.", cited_ids: ["itemA#29:0"] },
        { text: "Clinics opened.", cited_ids: ["itemB#3:0", "itemA#29:0"] },
      ],
      verified_citations: [
        { passage_id: "itemA#29:0", item_id: "itemA", leaf_index: 29, printed_page: "10", deep_link: "u1" },
        { passage_id: "itemB#3:0", item_id: "itemB", leaf_index: 3, printed_page: null, deep_link: "u2" },
      ],
      cached: { created_at: "2026-09-10T21:25:00+00:00" },
    };
    const byId = new Map([
      ["itemA#29:0", row()],
      ["itemB#3:0", row({ passage_id: "itemB#3:0", item_id: "itemB", title: "Clinic report", year: 1999, leaf_index: 3, printed_page: null })],
    ]);
    render(<AnswerCard answer={a} byId={byId} onOpen={() => {}} />);
    expect(screen.getAllByRole("button", { name: /^Citation 1:/ })).toHaveLength(2); // itemA cited twice -> same number
    expect(screen.getByRole("button", { name: /^Citation 2:/ })).toBeInTheDocument();
    const sources = screen.getByRole("heading", { name: "Sources" }).closest("section");
    expect(sources).toHaveTextContent("1. Report of the Ontario Tobacco Strategy Steering Committee (1985), p. 10 (leaf 29), archive.org");
    expect(sources).toHaveTextContent("2. Clinic report (1999), leaf 3, archive.org");
    expect(screen.getByText(/served from cache, generated/)).toBeInTheDocument();
  });
});
