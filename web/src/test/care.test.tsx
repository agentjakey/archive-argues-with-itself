import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  ATTRIBUTION_TOPICS,
  CROSSWALK_ENABLED,
  crosswalkSegments,
  needsAttribution,
} from "../lib/sensitivity";
import { CrosswalkText } from "../components/CrosswalkText";
import type { Flagged } from "../types";

function flagged(topics: string[]): Flagged {
  return { topics, year: 1990, crisis_lines: [] };
}

describe("attribution-incomplete notice gating", () => {
  it("fires only for the two state-created-about-Indigenous topics", () => {
    expect(needsAttribution(flagged(["residential-school-health"]))).toBe(true);
    expect(needsAttribution(flagged(["coerced-sterilization-indigenous"]))).toBe(true);
    expect(needsAttribution(flagged(["early-hiv-aids"]))).toBe(false);
    expect(needsAttribution(flagged(["tainted-blood-krever"]))).toBe(false);
    expect(needsAttribution(flagged([]))).toBe(false);
    expect(needsAttribution(null)).toBe(false);
    expect([...ATTRIBUTION_TOPICS].sort()).toEqual([
      "coerced-sterilization-indigenous",
      "residential-school-health",
    ]);
  });
});

describe("reparative term crosswalk", () => {
  it("is off by default and returns excerpt text unchanged (no annotation on any excerpt)", () => {
    expect(CROSSWALK_ENABLED).toBe(false);
    expect(crosswalkSegments("Resettlement of Eskimo families in the north")).toEqual([
      { text: "Resettlement of Eskimo families in the north", term: null },
    ]);
  });

  it("when enabled, marks only the exact unambiguous term and never rewrites it", () => {
    const segs = crosswalkSegments("the Eskimo were relocated; the fishermen stayed", true);
    const marked = segs.filter((s) => s.term);
    expect(marked.length).toBe(1);
    expect(marked[0].text).toBe("Eskimo"); // the record's word, shown unchanged
    expect(marked[0].term?.contemporary).toBe("Inuit");
    // every character of the original is preserved across the segments (nothing dropped or rewritten)
    expect(segs.map((s) => s.text).join("")).toBe("the Eskimo were relocated; the fishermen stayed");
  });

  it("when enabled, leaves contested or benign terms alone", () => {
    // 'Indian' is deliberately excluded: it is a legal status and part of place/institution names.
    expect(crosswalkSegments("the Indian Act and Indian Affairs", true)).toEqual([
      { text: "the Indian Act and Indian Affairs", term: null },
    ]);
    expect(crosswalkSegments("the fishermen and farmers", true)).toEqual([
      { text: "the fishermen and farmers", term: null },
    ]);
  });

  it("CrosswalkText renders the excerpt intact with the crosswalk off", () => {
    const { container } = render(<CrosswalkText text="Eskimo settlement policy" salientTerms={[]} />);
    expect(container.textContent).toBe("Eskimo settlement policy");
    expect(container.textContent).not.toContain("today:");
  });
});
