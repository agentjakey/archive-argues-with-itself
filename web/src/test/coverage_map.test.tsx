import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CoverageMapView } from "../components/CoverageMap";
import { bandOf } from "../lib/coverage";
import type { FeatureCollection } from "../lib/canadaMap";
import type { ScopeInfo } from "../types";

function scope(
  name: string, label: string, jurisdictions: { name: string; items: number }[],
  isFloor: boolean, unknownShare = 0.149,
): ScopeInfo {
  return {
    name, label, blurb: "", collection: name, collection_url: `https://archive.org/details/${name}`,
    collections: [name], item_count: jurisdictions.reduce((n, j) => n + j.items, 0),
    window: { min_year: 1960, max_year: 2009 },
    composition: {
      passages: 1, dated_span: { min_year: 1963, max_year: 2018 }, window: { min_year: 1960, max_year: 2009 },
      undated: { items: 0, item_share: 0, passages: 0, passage_share: 0 }, ocr: { high: 1, medium: 0, low: 0 },
      jurisdictions: jurisdictions.map((j) => ({ ...j, share: 0 })),
      jurisdiction_unknown_share: unknownShare, jurisdiction_is_floor: isFloor, date_method: {}, by_period: {},
    },
  };
}

const MICRO = scope("microlog", "National public health, all provinces", [
  { name: "federal", items: 5103 }, { name: "ontario", items: 1828 }, { name: "saskatchewan", items: 878 },
  { name: "alberta", items: 424 }, { name: "british_columbia", items: 261 }, { name: "manitoba", items: 332 },
  { name: "unknown", items: 2018 }, { name: "international", items: 1 },
], true);

const PILOT = scope("pilot", "Federal public health", [
  { name: "federal", items: 1198 }, { name: "ontario", items: 1024 }, { name: "alberta", items: 949 },
  { name: "unknown", items: 301 },
], false, 0.087);

const FC: FeatureCollection = {
  type: "FeatureCollection",
  features: [
    { type: "Feature", properties: { code: "CA-ON" }, geometry: { type: "Polygon", coordinates: [[[-80, 45], [-79, 45], [-79, 44], [-80, 44], [-80, 45]]] } },
    { type: "Feature", properties: { code: "CA-AB" }, geometry: { type: "Polygon", coordinates: [[[-114, 52], [-113, 52], [-113, 51], [-114, 51], [-114, 52]]] } },
    { type: "Feature", properties: { code: "CA-NU" }, geometry: { type: "Polygon", coordinates: [[[-95, 65], [-94, 65], [-94, 64], [-95, 64], [-95, 65]]] } },
  ],
};

const CAPTION =
  "Jurisdiction here is a rough proxy. About 15% of items could not be placed and are not shown on " +
  "the map. This is a rough picture of reach, not a scorecard.";

describe("bandOf", () => {
  it("coarse bands, null for none", () => {
    expect(bandOf(0)).toBeNull();
    expect(bandOf(10)?.label).toBe("sparse");
    expect(bandOf(120)?.label).toBe("some");
    expect(bandOf(878)?.label).toBe("well represented");
  });
});

describe("CoverageMapView (national)", () => {
  it("without the boundary file: text-alternative list, unknown figure, federal separate, fixed caption", () => {
    const { container } = render(<CoverageMapView scope={MICRO} geo={null} onExplore={vi.fn()} onNav={vi.fn()} />);
    expect(screen.getByText(/The same figures as a list/)).toBeInTheDocument();
    // unknown shown as a separate figure, never spread across provinces
    expect(container.textContent).toContain("About 15% of items (2,018)");
    expect(container.textContent).toContain("Federal (national): 5,103 items");
    // the author-fixed national caption, verbatim
    expect(container.textContent).toContain(CAPTION);
    // absent boundary file -> clean fallback, no error
    expect(screen.getByText(/map image is not on this device/)).toBeInTheDocument();
    // the table carries the band, not the exact count
    expect(container.textContent).toContain("Saskatchewan");
    expect(container.textContent).toContain("well represented");
    expect(container.textContent).not.toContain("878 items");
  });

  it("with the boundary file: province paths render; a shaded province is a button that explores it", () => {
    const onExplore = vi.fn();
    render(<CoverageMapView scope={MICRO} geo={FC} onExplore={onExplore} onNav={vi.fn()} />);
    const on = screen.getByRole("button", { name: /Ontario: well represented/ });
    expect(on).toBeInTheDocument();
    fireEvent.click(on);
    expect(onExplore).toHaveBeenCalledWith("ontario");
    // Nunavut has no data in this corpus -> present on the map but not a button
    expect(screen.queryByRole("button", { name: /Nunavut/ })).toBeNull();
  });
});

describe("CoverageMapView (pilot)", () => {
  it("no national ranking: pilot note, federal stated separately, no national caption or bands", () => {
    const { container } = render(<CoverageMapView scope={PILOT} geo={null} onExplore={vi.fn()} onNav={vi.fn()} />);
    expect(container.textContent).toContain("This pilot covers federal, Ontario, and Alberta only");
    expect(container.textContent).toContain("Federal (national): 1,198 items");
    expect(container.textContent).not.toContain("Jurisdiction here is a rough proxy");   // national caption absent
    expect(container.textContent).not.toContain("well represented");                     // no bands under pilot
  });
});
