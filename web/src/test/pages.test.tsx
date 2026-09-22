import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { About } from "../components/pages/About";
import { Gaps } from "../components/pages/Gaps";
import { HowItWorks } from "../components/pages/HowItWorks";
import { readState, writeState } from "../lib/urlstate";
import type { Crisis, ScopeInfo } from "../types";

const PILOT_SCOPE: ScopeInfo = {
  name: "pilot", label: "Federal public health", blurb: "", collection: "governmentpublications",
  collection_url: null, collections: ["governmentpublications"], item_count: 3477,
  window: { min_year: 1960, max_year: 2009 }, coverage_window: { min_year: 1960, max_year: 2009 },
  harvested_count: 3477,
};

const MICROLOG_SCOPE: ScopeInfo = {
  name: "microlog", label: "National public health, all provinces", blurb: "", collection: "microlog",
  collection_url: null, collections: ["microlog"], item_count: 13539,
  window: { min_year: 1960, max_year: 2009 }, coverage_window: { min_year: 1963, max_year: 2018 },
  harvested_count: 13544,
  composition: {
    passages: 1136827, dated_span: { min_year: 1963, max_year: 2018 }, window: { min_year: 1960, max_year: 2009 },
    undated: { items: 0, item_share: 0, passages: 0, passage_share: 0 }, ocr: { high: 0, medium: 0, low: 0 },
    jurisdictions: [], jurisdiction_unknown_share: 0.149, jurisdiction_is_floor: true, date_method: {}, by_period: {},
  },
};

// Placeholder resources: the real numbers live only in src/archive_debugger/crisis.py, so this
// frontend fixture carries none. It proves the care note renders whatever the API serves as
// default_indigenous_sensitive; the actual numbers are pinned in tests/test_flags.py.
const CRISIS: Crisis = {
  resources: {}, topic_resources: {},
  defaults: {
    indigenous_sensitive: [
      { key: "res_a", label: "Support Line A", contact: "How to reach A", hours: "hours A", for: "who A is for", link: "example.ca" },
      { key: "res_b", label: "Support Line B", contact: "How to reach B", hours: "hours B", for: "who B is for" },
    ],
    other_sensitive: [],
  },
};

describe("reading pages", () => {
  it("url state carries the view and rejects unknown views", () => {
    expect(readState("?view=gaps").view).toBe("gaps");
    expect(readState("?view=nope").view).toBeUndefined();
    expect(writeState({ q: "", filters: {}, pins: [], kiosk: false, view: "how" })).toBe("?view=how");
  });

  it("How this works states the four rules and what a citation means", () => {
    render(<HowItWorks />);
    expect(screen.getByRole("heading", { name: "How this works" })).toBeInTheDocument();
    expect(screen.getByText(/three structural checks/)).toBeInTheDocument();
    expect(screen.getByText(/mean the sentence is true/)).toBeInTheDocument();
    expect(screen.getAllByText("docs/evaluation/abstention_sweeps.md").length).toBeGreaterThan(0);
  });

  it("Gaps under the pilot scope shows the pilot window and the pilot audit numbers", () => {
    render(<Gaps scope={PILOT_SCOPE} crisis={null} />);
    expect(screen.getByText(/runs from 1960 to 2009/)).toBeInTheDocument();   // window from data/config, not a literal
    expect(screen.getByText(/338,338 of 745,893 passages \(45\.4%\)/)).toBeInTheDocument();
    expect(screen.getByText(/12,684 pages front matter and 3,823 back matter/)).toBeInTheDocument();
    expect(screen.getByText(/10 of 35 answerable questions would/)).toBeInTheDocument();
    expect(screen.getByText(/mentions 2010 \(item dated 1984\)/)).toBeInTheDocument();
    expect(screen.getAllByText("reports/coverage_audit/finalist_sizing.md").length).toBe(1);
    // microlog content must not bleed into the pilot scope
    expect(screen.queryByText(/reaches every province and all three territories/)).toBeNull();
  });

  it("Gaps under the microlog scope shows its own window, support audit, and care lines", () => {
    render(<Gaps scope={MICROLOG_SCOPE} crisis={CRISIS} />);
    expect(screen.getByText(/runs from 1963 to 2018/)).toBeInTheDocument();          // microlog window, not 2009
    expect(screen.getByText(/reaches every province and all three territories/)).toBeInTheDocument();
    expect(screen.getByText(/about 15% of the items/)).toBeInTheDocument();           // 0.149 -> 15%
    expect(screen.getByText(/298 were fully supported, 6 were partly supported/)).toBeInTheDocument();
    expect(screen.getByText(/eligibility for Medicaid/)).toBeInTheDocument();
    // care-note crisis lines are rendered from the served defaults (the single source of truth)
    expect(screen.getByText("Support Line A")).toBeInTheDocument();
    expect(screen.getByText("Support Line B")).toBeInTheDocument();
    expect(screen.getByText(/How to reach A/)).toBeInTheDocument();
    // no pilot audit numbers bleed into microlog
    expect(screen.queryByText(/338,338 of 745,893/)).toBeNull();
  });

  it("About names the partners, the image source, and the licence", () => {
    render(<About />);
    expect(screen.getByText(/AI Builders Fellowship of the BC \+ AI Ecosystem, with the Internet Archive/)).toBeInTheDocument();
    expect(screen.getByText(/served by archive.org/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /github.com\/agentjakey/ })).toHaveAttribute("href", "https://github.com/agentjakey/archive-argues-with-itself");
    expect(screen.getByText(/MIT licence/)).toBeInTheDocument();
  });
});
