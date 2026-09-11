import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EvidenceTrail } from "../components/EvidenceTrail";
import { row } from "./fixtures";

describe("EvidenceTrail", () => {
  it("renders the fixed lanes in order with undated last, collapses empty ones, and draws the timeline", () => {
    const rows = [
      row({ passage_id: "a", year: 1990, decade: "1990s" }),
      row({ passage_id: "b", year: null, decade: null }),
      row({ passage_id: "c", year: 1975, decade: "1970s", cited: true }),
    ];
    render(
      <EvidenceTrail
        rows={rows}
        salientTerms={[]}
        pinned={[]}
        heading="Evidence trail"
        matched={{ "1970s": 40, "1990s": 12, undated: 300 }}
        onOpen={() => {}}
        onPin={() => {}}
      />,
    );
    const lanes = within(screen.getByTestId("lanes")).getAllByRole("heading", { level: 3 });
    expect(lanes.map((h) => h.textContent?.split(" ")[0])).toEqual(["1960s", "1970s", "1980s", "1990s", "2000s", "undated"]);
    expect(screen.getAllByText(/no passages retrieved/)).toHaveLength(3); // 1960s, 1980s, 2000s
    expect(screen.getAllByText("Cited")).toHaveLength(1);
    const timeline = screen.getByRole("navigation", { name: "Decades" });
    expect(within(timeline).getByRole("button", { name: /1970s: 1 retrieved, 40 matching/ })).toBeInTheDocument();
    expect(within(timeline).getByRole("button", { name: /1960s: 0 retrieved, 0 matching/ })).toHaveClass("is-zero");
  });
});
