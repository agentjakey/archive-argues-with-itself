import { describe, expect, it } from "vitest";
import { chipLabel, decadeKey, laneOrder, shortTitle } from "../lib/format";
import { row } from "./fixtures";

describe("chipLabel", () => {
  it("reads: short title, year, p. N (leaf L)", () => {
    // 48-char short title: 45 chars of title + "..."
    expect(chipLabel(row())).toBe("Report of the Ontario Tobacco Strategy Steeri..., 1985, p. 10 (leaf 29)");
  });
  it("falls back to the leaf when the printed page is unknown, and to undated when the year is", () => {
    expect(chipLabel(row({ title: "Short", printed_page: null, year: null, leaf_index: 5 }))).toBe("Short, undated, leaf 5");
  });
  it("shortTitle truncates with ASCII ellipsis", () => {
    expect(shortTitle("abcdefghij", 8)).toBe("abcde...");
    expect(shortTitle(null)).toBe("untitled");
  });
});

describe("lanes", () => {
  it("orders decades ascending with undated last", () => {
    expect(laneOrder(["1990s", "undated", "1970s", "2000s"])).toEqual(["1970s", "1990s", "2000s", "undated"]);
    expect(laneOrder(["1980s"])).toEqual(["1980s"]);
  });
  it("derives the decade key from the year when decade is missing", () => {
    expect(decadeKey({ year: 1975, decade: null })).toBe("1970s");
    expect(decadeKey({ year: null, decade: null })).toBe("undated");
  });
});
