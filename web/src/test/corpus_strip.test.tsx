import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CorpusStrip } from "../components/CorpusStrip";
import type { ScopeInfo, YearWindow } from "../types";

function mkScope(
  name: string, label: string, items: number, passages: number,
  cov: YearWindow, span: YearWindow, undatedItemShare: number, jurUnknown: number, isFloor: boolean,
): ScopeInfo {
  return {
    name, label, blurb: "", collection: name, collection_url: null, collections: [name],
    item_count: items, window: { min_year: 1960, max_year: 2009 }, coverage_window: cov,
    composition: {
      passages, dated_span: span, window: { min_year: 1960, max_year: 2009 },
      undated: { items: 0, item_share: undatedItemShare, passages: 0, passage_share: 0 },
      ocr: { high: 1, medium: 0, low: 0 }, jurisdictions: [],
      jurisdiction_unknown_share: jurUnknown, jurisdiction_is_floor: isFloor, date_method: {}, by_period: {},
    },
  };
}

// Pilot: displayed window clamped 1960-2009 though catalog dates run 1886-2020; ~9% jurisdiction unknown.
const PILOT = mkScope("pilot", "Federal public health", 3477, 745893,
  { min_year: 1960, max_year: 2009 }, { min_year: 1886, max_year: 2020 }, 0.2856, 0.0866, false);
// Microlog: unclamped 1963-2018; ~15% jurisdiction unknown, an issuer-proxy floor.
const MICRO = mkScope("microlog", "National public health, all provinces", 13539, 1136827,
  { min_year: 1963, max_year: 2018 }, { min_year: 1963, max_year: 2018 }, 0.0315, 0.1491, true);

describe("CorpusStrip (home stat band, per scope)", () => {
  it("microlog: shows microlog's own figures and no pilot value bleeds in", () => {
    const { container } = render(<CorpusStrip scope={MICRO} />);
    const t = container.textContent ?? "";
    expect(t).toContain("13,539");         // microlog items
    expect(t).toContain("1,136,827");      // microlog passages
    expect(t).toContain("1963 to 2018");   // microlog coverage window
    expect(t).toContain("15%");            // jurisdiction unknown (0.1491)
    expect(t).toContain("issuer-derived proxy");   // floor caveat present for microlog
    // no pilot value under microlog
    expect(t).not.toContain("3,477");
    expect(t).not.toContain("745,893");
    expect(t).not.toContain("1886 to 2020");
    expect(t).not.toContain("pilot window");
  });

  it("pilot: shows the clamped window and discloses the true dated span, no microlog value", () => {
    const { container } = render(<CorpusStrip scope={PILOT} />);
    const t = container.textContent ?? "";
    expect(t).toContain("3,477");
    expect(t).toContain("745,893");
    expect(t).toContain("1960 to 2009");   // clamped coverage window headline
    expect(t).toContain("1886 to 2020");   // true dated span, disclosed in the clamp note
    expect(t).toContain("clamped");
    expect(t).not.toContain("13,539");
    expect(t).not.toContain("1963 to 2018");
  });

  it("no active scope: shows a loading state, never another scope's number", () => {
    render(<CorpusStrip scope={null} />);
    expect(screen.getByText(/Loading corpus facts/)).toBeInTheDocument();
  });
});
