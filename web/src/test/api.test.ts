import { describe, expect, it } from "vitest";
import { errorDetail } from "../lib/api";
import { formatInt, formatShare, windowLabel } from "../lib/format";

describe("errorDetail", () => {
  it("prefers the server's own words and never returns a bare status", () => {
    expect(errorDetail(503, { error: "ANTHROPIC_API_KEY is not set on the server" })).toBe(
      "ANTHROPIC_API_KEY is not set on the server",
    );
    expect(errorDetail(502, { error: "RuntimeError: boom" })).toBe("RuntimeError: boom");
    expect(errorDetail(404, { detail: "Not Found" })).toBe("Not Found");
    expect(errorDetail(422, { detail: [{ loc: ["body", "question"], msg: "field required" }] })).toBe("field required");
    expect(errorDetail(500, null)).toBe("The server returned an error (status 500) with no detail.");
  });
});

describe("corpus strip formatting", () => {
  it("formats the four figures", () => {
    expect(formatInt(745893)).toBe("745,893");
    expect(formatShare(0.4536)).toBe("45%");
    expect(windowLabel({ window: { min_year: 1960, max_year: 2009 } })).toBe("1960 to 2009");
    expect(windowLabel({ window: { min_year: null, max_year: null } })).toBe("undated only");
  });
});
