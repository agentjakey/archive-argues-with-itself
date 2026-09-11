import { describe, expect, it } from "vitest";
import { readState, writeState } from "../lib/urlstate";

describe("url state", () => {
  it("round-trips question, filters, pins, and kiosk", () => {
    const s = { q: "tobacco control", filters: { period: "1980s" as const, jurisdiction: "ontario" as const }, pins: ["a#1:0", "b#2:0"], kiosk: true };
    const search = writeState(s);
    expect(search).toContain("q=tobacco+control");
    expect(search).toContain("pins=a%231%3A0%2Cb%232%3A0");
    expect(readState(search)).toEqual(s);
  });
  it("caps pins at two, drops empty filters, and yields an empty string for empty state", () => {
    expect(readState("?pins=a,b,c").pins).toEqual(["a", "b"]);
    expect(readState("?period=&q=x").filters).toEqual({});
    expect(writeState({ q: "", filters: {}, pins: [], kiosk: false })).toBe("");
  });
});
