import { describe, expect, it } from "vitest";
import { highlight } from "../lib/highlight";

describe("highlight", () => {
  it("marks salient terms by equality, plural stem, and 5-char prefix", () => {
    const segs = highlight("Tobacco prices and smoking risks in sanatoria", ["tobacco", "risk", "sanatorium"]);
    const hits = segs.filter((s) => s.hit).map((s) => s.text);
    expect(hits).toEqual(["Tobacco", "risks", "sanatoria"]);
  });
  it("returns the text untouched when there are no terms", () => {
    expect(highlight("plain text", [])).toEqual([{ text: "plain text", hit: false }]);
  });
  it("round-trips the original text", () => {
    const text = "Alberta Health 1985 report on vaccination.";
    expect(highlight(text, ["vaccination", "1985"]).map((s) => s.text).join("")).toBe(text);
  });
});
