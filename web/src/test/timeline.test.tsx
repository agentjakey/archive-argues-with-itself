import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { periodOfRow, timelineBars } from "../lib/timeline";
import { TimelinePage } from "../components/pages/Timeline";
import type { Composition, ScopeInfo } from "../types";

describe("timelineBars", () => {
  it("builds a contiguous decade axis, fills interior gaps with zero, and keeps undated separate", () => {
    // no 1980s -> shown as a zero bar; no post-2009 -> omitted (no fabricated tail)
    const { dated, undated } = timelineBars({ "pre-1960": 2, "1970s": 5, "1990s": 3, undated: 10 });
    expect(dated.map((b) => b.key)).toEqual(["pre-1960", "1970s", "1980s", "1990s"]);
    expect(dated.map((b) => b.count)).toEqual([2, 5, 0, 3]);
    expect(dated.every((b) => b.kind === "dated")).toBe(true);
    expect(dated.some((b) => b.key === "post-2009")).toBe(false);
    expect(undated).toEqual({ key: "undated", label: "undated", count: 10, kind: "undated" });
  });

  it("shows pre-1960 and post-2009 only when the corpus has documents there", () => {
    const { dated } = timelineBars({ "1980s": 4, "2000s": 7, "post-2009": 1 });
    expect(dated.map((b) => b.key)).toEqual(["1980s", "1990s", "2000s", "post-2009"]);
    expect(dated.find((b) => b.key === "post-2009")?.count).toBe(1);
    expect(dated.some((b) => b.key === "pre-1960")).toBe(false);
  });

  it("undated defaults to zero when the corpus has none", () => {
    const { undated } = timelineBars({ "1990s": 3 });
    expect(undated.count).toBe(0);
  });
});

describe("periodOfRow", () => {
  it("maps a year to the same buckets the histogram uses", () => {
    expect(periodOfRow({ year: null })).toBe("undated");
    expect(periodOfRow({ year: 1955 })).toBe("pre-1960");
    expect(periodOfRow({ year: 1988 })).toBe("1980s");
    expect(periodOfRow({ year: 2005 })).toBe("2000s");
    expect(periodOfRow({ year: 2015 })).toBe("post-2009");
  });
});

const COMPOSITION: Composition = {
  passages: 700000,
  dated_span: { min_year: 1968, max_year: 2008 },
  window: { min_year: 1960, max_year: 2009 },
  undated: { items: 420, item_share: 0.12, passages: 60000, passage_share: 0.086 },
  ocr: { high: 8, medium: 2, low: 0 },
  jurisdictions: [{ name: "federal", items: 1000, share: 0.3 }],
  jurisdiction_unknown_share: 0.15,
  jurisdiction_is_floor: false,
  date_method: {},
  by_period: { "1970s": 500, "1980s": 900, "1990s": 700, "2000s": 300, undated: 420 },
};

const SCOPE: ScopeInfo = {
  name: "pilot",
  label: "Federal public health, 1960-2009",
  blurb: "",
  collection: "governmentpublications",
  collection_url: "https://archive.org/details/governmentpublications",
  collections: ["governmentpublications"],
  item_count: 3477,
  window: { min_year: 1960, max_year: 2009 },
  composition: COMPOSITION,
};

describe("TimelinePage", () => {
  it("renders a bar per period with its real document count, plus a separate undated bar", () => {
    render(
      <TimelinePage scope={SCOPE} initialQuestion="" onDrillDecade={vi.fn()} onCompareDecades={vi.fn()} />,
    );
    // each period a clickable bar labelled with its real count
    expect(screen.getByRole("button", { name: /^1970s: 500 documents/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^2000s: 300 documents/ })).toBeInTheDocument();
    // undated is its own bar with the composition's undated item count (same basis as Sources)
    expect(screen.getByRole("button", { name: /^undated: 420 documents/ })).toBeInTheDocument();
    // the undated count is single-sourced with composition.undated.items
    expect(screen.getByText(/Undated documents \(420\)/)).toBeInTheDocument();
  });

  it("clicking a decade drills into it with the current question", () => {
    const onDrill = vi.fn();
    render(
      <TimelinePage scope={SCOPE} initialQuestion="smoking" onDrillDecade={onDrill} onCompareDecades={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^1980s: 900 documents/ }));
    expect(onDrill).toHaveBeenCalledWith("1980s", "smoking");
  });

  it("comparing two decades passes the question and both periods to the compare handler", () => {
    const onCompare = vi.fn();
    render(
      <TimelinePage scope={SCOPE} initialQuestion="smoking" onDrillDecade={vi.fn()} onCompareDecades={onCompare} />,
    );
    // defaults: from = first dated period, to = last dated period
    fireEvent.click(screen.getByRole("button", { name: "Compare in the record" }));
    expect(onCompare).toHaveBeenCalledWith("smoking", "1970s", "2000s");
  });

  it("does not compare without a question", () => {
    const onCompare = vi.fn();
    render(
      <TimelinePage scope={SCOPE} initialQuestion="" onDrillDecade={vi.fn()} onCompareDecades={onCompare} />,
    );
    const btn = screen.getByRole("button", { name: "Compare in the record" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);
    expect(onCompare).not.toHaveBeenCalled();
  });

  it("shows a loading line until the composition arrives", () => {
    render(
      <TimelinePage scope={null} initialQuestion="" onDrillDecade={vi.fn()} onCompareDecades={vi.fn()} />,
    );
    expect(screen.getByText("Loading the timeline.")).toBeInTheDocument();
  });

  it("shows the honest window note with the out-of-window count from by_period", () => {
    const s: ScopeInfo = {
      ...SCOPE,
      composition: { ...COMPOSITION, by_period: { "pre-1960": 12, "1980s": 100, "post-2009": 8, undated: 30 } },
    };
    render(<TimelinePage scope={s} initialQuestion="" onDrillDecade={vi.fn()} onCompareDecades={vi.fn()} />);
    // 12 pre-1960 + 8 post-2009 = 20 out of window; nominal window stated, catalog-metadata caveat
    expect(screen.getByText(/nominal collection window is 1960 to 2009/)).toBeInTheDocument();
    expect(screen.getByText(/20 items carry metadata dates outside it/)).toBeInTheDocument();
  });
});
