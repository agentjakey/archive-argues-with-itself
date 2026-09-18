import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CoverageMap } from "../components/CoverageMap";
import { bucketOf } from "../lib/coverage";
import type { ScopeInfo } from "../types";

function scope(jurisdictions: { name: string; items: number }[], isFloor: boolean): ScopeInfo {
  return {
    name: "microlog",
    label: "National public health, all provinces",
    blurb: "",
    collection: "microlog",
    collection_url: "https://archive.org/details/microlog",
    collections: ["microlog"],
    item_count: jurisdictions.reduce((n, j) => n + j.items, 0),
    window: { min_year: 1960, max_year: 2009 },
    composition: {
      passages: 1,
      dated_span: { min_year: 1963, max_year: 2018 },
      window: { min_year: 1960, max_year: 2009 },
      undated: { items: 0, item_share: 0, passages: 0, passage_share: 0 },
      ocr: { high: 1, medium: 0, low: 0 },
      jurisdictions: jurisdictions.map((j) => ({ ...j, share: 0 })),
      jurisdiction_unknown_share: 0.149,
      jurisdiction_is_floor: isFloor,
      date_method: {},
      by_period: {},
    },
  };
}

describe("bucketOf", () => {
  it("returns null for no data and the right bin otherwise", () => {
    expect(bucketOf(0)).toBeNull();
    expect(bucketOf(50)?.label).toBe("1 to 99");
    expect(bucketOf(250)?.label).toBe("100 to 299");
    expect(bucketOf(400)?.label).toBe("300 to 599");
    expect(bucketOf(878)?.label).toBe("600 or more");
  });
});

describe("CoverageMap", () => {
  const juris = [
    { name: "federal", items: 5103 },
    { name: "ontario", items: 1828 },
    { name: "saskatchewan", items: 878 },
    { name: "unknown", items: 2018 },
    { name: "international", items: 1 },
  ];

  it("renders resolved tiles with counts, no-data tiles, off-map counts, and the floor caveat", () => {
    const { container } = render(
      <CoverageMap scope={scope(juris, true)} onExplore={vi.fn()} onNav={vi.fn()} />,
    );
    // a resolved province tile is a button carrying its count
    expect(screen.getByRole("button", { name: /Saskatchewan: 878 items/ })).toBeInTheDocument();
    // absent provinces render as no data (e.g. Nunavut, Quebec) and are not buttons
    expect(screen.queryByRole("button", { name: /Nunavut/ })).toBeNull();
    expect(container.textContent).toContain("no data");
    // off-map: federal and unknown shown as numbers, never folded into a province
    expect(container.textContent).toContain("federal 5,103");
    expect(container.textContent).toContain("2,018");
    // floor caveat present when is_floor
    expect(container.textContent).toContain("a floor");
  });

  it("clicking a resolved province calls onExplore with its slug", () => {
    const onExplore = vi.fn();
    render(<CoverageMap scope={scope(juris, true)} onExplore={onExplore} onNav={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Saskatchewan/ }));
    expect(onExplore).toHaveBeenCalledWith("saskatchewan");
  });

  it("hides the floor caveat when is_floor is false (pilot)", () => {
    const pilot = [
      { name: "federal", items: 1198 },
      { name: "ontario", items: 1024 },
      { name: "alberta", items: 949 },
      { name: "unknown", items: 301 },
    ];
    const { container } = render(
      <CoverageMap scope={scope(pilot, false)} onExplore={vi.fn()} onNav={vi.fn()} />,
    );
    expect(container.textContent).not.toContain("a floor");
    // territories and most provinces are no data on the pilot
    expect(screen.queryByRole("button", { name: /Yukon/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Ontario: 1,024 items/ })).toBeInTheDocument();
  });
});
