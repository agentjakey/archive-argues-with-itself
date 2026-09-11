import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CoveragePanel } from "../components/CoveragePanel";
import type { CoverageResponse } from "../types";

const cov: CoverageResponse = {
  salient_terms: ["covid", "vaccination"],
  by_decade: [
    { decade: "1980s", items: 5, passages: 7, undated_passages: 0, matched: 3, terms: { covid: 0, vaccination: 3 } },
    { decade: "undated", items: 2, passages: 4, undated_passages: 4, matched: 1, terms: { covid: 0, vaccination: 1 } },
  ],
  by_jurisdiction: [{ jurisdiction: "federal", passages: 11, terms: { covid: 0, vaccination: 4 } }],
};

describe("CoveragePanel", () => {
  it("shows zeros as zeros, a baseline row, the jurisdiction row, and the fixed caveat", () => {
    render(<CoveragePanel coverage={cov} undatedShare={0.4536} explanation />);
    const grid = screen.getByTestId("coverage-grid");
    const covidRow = within(grid).getByRole("rowheader", { name: "covid" }).closest("tr")!;
    expect(within(covidRow).getAllByRole("cell").map((c) => c.textContent)).toEqual(["0", "0"]);
    const baseline = within(grid).getByRole("rowheader", { name: "all passages, current filters" }).closest("tr")!;
    expect(within(baseline).getAllByRole("cell").map((c) => c.textContent)).toEqual(["7", "4"]);
    expect(screen.getByText(/by jurisdiction/)).toBeInTheDocument();
    expect(screen.getByText(/federal/)).toBeInTheDocument();
    expect(screen.getByText(/45% of passages carry no date; counts are lexical matches, not relevance/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Why the record is thin here" })).toBeInTheDocument();
  });
  it("renders a waiting line before coverage arrives", () => {
    render(<CoveragePanel coverage={null} undatedShare={null} />);
    expect(screen.getByText(/Counting lexical matches/)).toBeInTheDocument();
    expect(screen.getByText(/45% of passages carry no date/)).toBeInTheDocument(); // fallback share
  });
});
