import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CompareView } from "../components/CompareView";
import { ThresholdHero } from "../components/ThresholdHero";
import type { EvidenceRow, Story } from "../types";
import { row } from "./fixtures";

// The corrected featured-story caption (config/stories.json). Its content is guarded on the server
// by tests/test_api.py::test_featured_alberta_story_caption_is_accurate; here it drives the UI framing
// so the compare view and the landing hero never present the two records as the same plan changing.
const ALBERTA_CAPTION =
  "1974: an Alberta inventory describes government services for First Nations and Metis people, " +
  "including health coverage. 1998-99: a health-insurance statistical supplement reports enrollment " +
  "in Alberta Blue Cross non-group coverage. These records describe different things; they cannot, " +
  "by themselves, establish how coverage changed.";

const PINS: [EvidenceRow, EvidenceRow] = [
  row({ passage_id: "ableg_33398004781505#52:0", year: 1974, jurisdiction: "alberta",
        title: "An inventory of provincial government services" }),
  row({ passage_id: "micro_IA40243301_0385#117:0", year: 1999, jurisdiction: "alberta",
        title: "Statistical supplement, 1998-99" }),
];

describe("compare view framing", () => {
  it("labels a story caption as reading guidance, not a verdict on what changed", () => {
    render(
      <CompareView
        a={PINS[0]}
        b={PINS[1]}
        salientTerms={[]}
        caption={ALBERTA_CAPTION}
        onOpen={vi.fn()}
        onUnpin={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("How to read these sources")).toBeInTheDocument();
    expect(screen.queryByText("What changed")).toBeNull();
    expect(screen.getByText(/cannot, by themselves, establish how coverage changed/)).toBeInTheDocument();
    expect(screen.queryByText(/same insurance plan/i)).toBeNull();
  });
});

describe("threshold hero framing", () => {
  const featured: Story = {
    id: "alberta-insurance-1974-1999",
    question: "How did Alberta health insurance coverage change between the 1970s and 1990s?",
    filters: { jurisdiction: "alberta" },
    caption: ALBERTA_CAPTION,
    pins: PINS,
  };

  it("uses a neutral label, not a claim that the record disagrees with itself", () => {
    render(<ThresholdHero featured={featured} onOpen={vi.fn()} />);
    expect(screen.getByText("Two pages from the public record")).toBeInTheDocument();
    expect(screen.queryByText("One disagreement in the record")).toBeNull();
    expect(screen.getByText(/describe different things/)).toBeInTheDocument();
  });
});
