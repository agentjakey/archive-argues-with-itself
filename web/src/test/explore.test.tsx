import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ExplorePage } from "../components/pages/Explore";
import type { Example, ScopeInfo } from "../types";

function scope(
  name: string,
  label: string,
  collection: string,
  collections: string[],
  items: number,
  passages: number,
  span: [number, number],
  jurisdictions: { name: string; items: number }[],
  isFloor: boolean,
  byPeriod: Record<string, number> = {},
): ScopeInfo {
  return {
    name,
    label,
    blurb: "",
    collection,
    collection_url: `https://archive.org/details/${collection}`,
    collections,
    item_count: items,
    window: { min_year: 1960, max_year: 2009 },
    composition: {
      passages,
      dated_span: { min_year: span[0], max_year: span[1] },
      window: { min_year: 1960, max_year: 2009 },
      undated: { items: 0, item_share: 0, passages: 0, passage_share: 0 },
      ocr: { high: 8, medium: 2, low: 0 },
      jurisdictions: jurisdictions.map((j) => ({ ...j, share: 0 })),
      jurisdiction_unknown_share: 0.149,
      jurisdiction_is_floor: isFloor,
      date_method: {},
      by_period: byPeriod,
    },
  };
}

const PILOT = scope("pilot", "Federal public health, 1960-2009", "governmentpublications",
  ["governmentpublications", "albertagovernmentpublications"], 3477, 745893, [1886, 2020],
  [{ name: "federal", items: 1198 }, { name: "ontario", items: 1024 }, { name: "unknown", items: 301 }], false);

const MICROLOG = scope("microlog", "National public health, all provinces", "microlog",
  ["microlog"], 13539, 1136827, [1963, 2018],
  [{ name: "federal", items: 5103 }, { name: "saskatchewan", items: 878 }, { name: "unknown", items: 2018 }], true);

const PILOT_SEED: Example = { qid: "q1", text: "What did Ontario recommend about smoking?", filters: { jurisdiction: "ontario" }, gold: "answerable" };

describe("ExplorePage", () => {
  it("rolls up totals across served corpora and shows each corpus's live stats", () => {
    const { container } = render(
      <ExplorePage
        scopes={[PILOT, MICROLOG]}
        examplesByScope={{ pilot: [PILOT_SEED], microlog: [] }}
        onExploreScope={vi.fn()}
        onEnterQuestion={vi.fn()}
      />,
    );
    // roll-up: summed items/passages, combined span, union of collections
    expect(container.textContent).toContain("all 2 corpora");
    expect(container.textContent).toContain("17,016"); // 3477 + 13539
    expect(container.textContent).toContain("1,882,720"); // 745893 + 1136827
    expect(container.textContent).toContain("1886 to 2020"); // min..max
    // per-corpus source links and floor caveat only where is_floor
    expect(screen.getByRole("link", { name: /governmentpublications on archive.org/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /microlog on archive.org/ })).toBeInTheDocument();
    expect(container.textContent).toContain("proxy floor"); // microlog is_floor
    // pilot has a seed question; microlog says it has none
    expect(screen.getByRole("button", { name: /What did Ontario/ })).toBeInTheDocument();
    expect(container.textContent).toContain("No seed questions yet");
  });

  it("a seed question enters its scope with the question and filters", () => {
    const onEnter = vi.fn();
    render(
      <ExplorePage scopes={[PILOT, MICROLOG]} examplesByScope={{ pilot: [PILOT_SEED], microlog: [] }} onExploreScope={vi.fn()} onEnterQuestion={onEnter} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /What did Ontario/ }));
    expect(onEnter).toHaveBeenCalledWith("pilot", PILOT_SEED.text, { jurisdiction: "ontario" });
  });

  it("Explore this corpus selects that scope", () => {
    const onExplore = vi.fn();
    render(
      <ExplorePage scopes={[PILOT, MICROLOG]} examplesByScope={{ pilot: [], microlog: [] }} onExploreScope={onExplore} onEnterQuestion={vi.fn()} />,
    );
    const buttons = screen.getAllByRole("button", { name: "Explore this corpus" });
    expect(buttons).toHaveLength(2);
    fireEvent.click(buttons[0]);
    expect(onExplore).toHaveBeenCalledWith("pilot");
  });

  it("degrades to the single served scope: the roll-up equals that scope", () => {
    const { container } = render(
      <ExplorePage scopes={[PILOT]} examplesByScope={{ pilot: [PILOT_SEED] }} onExploreScope={vi.fn()} onEnterQuestion={vi.fn()} />,
    );
    expect(container.textContent).toContain("Across the corpus served now");
    expect(container.textContent).toContain("3,477"); // roll-up items == pilot
    expect(container.textContent).toContain("745,893"); // roll-up passages == pilot
  });

  it("roll-up items/passages equal the sum of served scopes and the span is the min/max (invariant)", () => {
    // Arbitrary numbers, not the pilot's, so this proves the sum/min-max logic rather than a constant.
    const a = scope("a", "A", "ca", ["ca"], 100, 2000, [1970, 2000], [{ name: "federal", items: 100 }], false);
    const b = scope("b", "B", "cb", ["cb"], 250, 5000, [1965, 2015], [{ name: "unknown", items: 250 }], true);
    const { container } = render(
      <ExplorePage scopes={[a, b]} examplesByScope={{ a: [], b: [] }} onExploreScope={vi.fn()} onEnterQuestion={vi.fn()} />,
    );
    expect(container.textContent).toContain("350"); // 100 + 250 items
    expect(container.textContent).toContain("7,000"); // 2000 + 5000 passages
    expect(container.textContent).toContain("1965 to 2015"); // min(1970,1965) .. max(2000,2015)
    expect(container.textContent).toContain("proxy floor"); // is_floor shown where a proxy scope is served
  });

  it("the roll-up window note carries the summed out-of-window count from by_period", () => {
    const a = scope("a", "A", "ca", ["ca"], 100, 2000, [1955, 2000],
      [{ name: "federal", items: 100 }], false, { "pre-1960": 5, "1980s": 90, "post-2009": 5 });
    const b = scope("b", "B", "cb", ["cb"], 60, 1200, [1958, 2012],
      [{ name: "federal", items: 60 }], false, { "pre-1960": 2, "1990s": 55, "post-2009": 3 });
    const { container } = render(
      <ExplorePage scopes={[a, b]} examplesByScope={{ a: [], b: [] }} onExploreScope={vi.fn()} onEnterQuestion={vi.fn()} />,
    );
    // 5 + 5 + 2 + 3 = 15 out-of-window items across the served corpora; nominal window stated honestly
    expect(container.textContent).toContain("The nominal collection window is 1960 to 2009");
    expect(container.textContent).toContain("15 items carry metadata dates outside it");
    expect(container.textContent).toContain("may not equal the publication year");
  });
});
