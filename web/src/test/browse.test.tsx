import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BrowseSection } from "../components/BrowseSection";

// The home page's coverage figures all come from the catalogue summary, the same source as the
// coverage line. The collections card used to sum the engine's own scopes (the first two
// collections only), which drifted from the coverage line once shards were served.
describe("BrowseSection", () => {
  it("states only catalogue-summary figures", () => {
    const { container } = render(
      <BrowseSection catalogue={{ documents: 118044, coverage: { indexed: 33925 }, built_at: "2026-11-03T00:00:00Z" }} onView={vi.fn()} />,
    );
    const text = container.textContent ?? "";
    expect(text).toContain("All 118,044 publications in the catalogue");
    expect(text).toContain("33,925 of them have searchable text so far");
    const numbers = text.match(/\d[\d,]*\d/g) ?? [];
    expect(numbers.sort()).toEqual(["118,044", "33,925"]);
  });

  it("leaves figures out while the summary has not loaded", () => {
    const { container } = render(<BrowseSection catalogue={null} onView={vi.fn()} />);
    expect(container.textContent).not.toMatch(/\d/);
  });
});
