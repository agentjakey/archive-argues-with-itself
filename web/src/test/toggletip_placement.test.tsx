import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AbstentionCard } from "../components/AbstentionCard";
import { CorpusStrip } from "../components/CorpusStrip";
import { CoverageMap } from "../components/CoverageMap";
import { CoveragePanel } from "../components/CoveragePanel";
import { SourcesPage } from "../components/pages/Sources";
import { abstention } from "./fixtures";
import type { ScopeInfo } from "../types";

beforeEach(() => {
  // CoverageMap fetches a local boundary file on mount; stub it to a clean failure so the component
  // falls back to its text alternative with no real network call.
  vi.stubGlobal("fetch", () => Promise.reject(new Error("no network in test")));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const SCOPE: ScopeInfo = {
  name: "pilot",
  label: "Federal public health",
  blurb: "",
  collection: "governmentpublications",
  collection_url: "https://archive.org/details/governmentpublications",
  collections: ["governmentpublications"],
  item_count: 3477,
  window: { min_year: 1960, max_year: 2009 },
  coverage_window: { min_year: 1960, max_year: 2009 },
  harvested_count: 3477,
  composition: {
    passages: 745893,
    dated_span: { min_year: 1886, max_year: 2020 },
    window: { min_year: 1960, max_year: 2009 },
    undated: { items: 993, item_share: 0.2856, passages: 338338, passage_share: 0.4536 },
    ocr: { high: 547826, medium: 191881, low: 6186 },
    jurisdictions: [
      { name: "federal", items: 1198, share: 0.34 },
      { name: "ontario", items: 1024, share: 0.29 },
      { name: "alberta", items: 949, share: 0.27 },
    ],
    jurisdiction_unknown_share: 0.087,
    jurisdiction_is_floor: false,
    date_method: { exact: 2448, title_extracted: 36, unknown: 993 },
    by_period: { "1990s": 1352, "post-2009": 44, undated: 993 },
  },
};

describe("term toggletip placement", () => {
  it("places toggletips on the reading surfaces, none nested inside a button or a link", async () => {
    const { container } = render(
      <div>
        <SourcesPage scopes={[SCOPE]} />
        <CoverageMap scope={SCOPE} onExplore={() => {}} onNav={() => {}} />
        <CoveragePanel coverage={null} undatedShare={0.45} explanation scope={SCOPE} />
        <CorpusStrip scope={SCOPE} />
        <AbstentionCard answer={abstention()} />
      </div>,
    );
    // Flush the CoverageMap boundary-file fetch rejection so its state settles inside act.
    await act(async () => {});

    const terms = Array.from(container.querySelectorAll("button.term"));
    expect(terms.length).toBeGreaterThan(0);
    for (const t of terms) {
      // A term is itself a button; it must not be nested inside ANOTHER button or a link, which would
      // be invalid HTML and would swallow the click.
      expect(t.parentElement?.closest("button, a")).toBeNull();
    }
  });
});
