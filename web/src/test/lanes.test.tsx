import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EvidenceTrail } from "../components/EvidenceTrail";
import { row } from "./fixtures";

describe("EvidenceTrail", () => {
  it("renders the fixed lanes in order with undated last, greys empty ones, and marks cited cards", () => {
    const rows = [
      row({ passage_id: "a", year: 1990, decade: "1990s" }),
      row({ passage_id: "b", year: null, decade: null }),
      row({ passage_id: "c", year: 1975, decade: "1970s", cited: true }),
    ];
    render(
      <EvidenceTrail rows={rows} salientTerms={[]} pinned={[]} heading="Evidence trail" onOpen={() => {}} onPin={() => {}} />,
    );
    const lanes = within(screen.getByTestId("lanes")).getAllByRole("heading", { level: 3 });
    expect(lanes.map((h) => h.textContent?.replace(/\s*\(\d+\)$/, ""))).toEqual([
      "1960s",
      "1970s",
      "1980s",
      "1990s",
      "2000s",
      "undated",
    ]);
    expect(screen.getAllByText("no passages retrieved for this lane")).toHaveLength(3); // 1960s, 1980s, 2000s
    expect(screen.getAllByText("Cited")).toHaveLength(1);
    // the rail shows per-lane counts
    const rail = screen.getByRole("navigation", { name: "Decades" });
    expect(within(rail).getByRole("button", { name: /1970s \(1\)/ })).toBeInTheDocument();
    expect(within(rail).getByRole("button", { name: /1960s \(0\)/ })).toHaveAttribute("aria-disabled", "true");
  });
});
