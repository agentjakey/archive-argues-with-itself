// The ask page's layout: the landing only when nothing is being asked or shown. Regression: a
// question waiting for a waking engine showed the landing, with the waking card below the whole home
// page, so the visitor saw the home page with their question in the box and thought it had failed.
import { describe, expect, it } from "vitest";
import { showsLanding } from "../lib/layout";

describe("ask page layout", () => {
  it("shows the landing only when idle on the home page with nothing to show", () => {
    expect(showsLanding(null, false, "idle")).toBe(true);
  });

  it("keeps the results layout while a question waits for a waking engine", () => {
    expect(showsLanding(null, false, "waking")).toBe(false);
  });

  it("keeps the results layout while asking, on an error and with an answer", () => {
    expect(showsLanding(null, false, "waiting")).toBe(false);
    expect(showsLanding(null, false, "error")).toBe(false);
    expect(showsLanding(null, true, "done")).toBe(false);
  });

  it("never shows the landing on another page", () => {
    expect(showsLanding("about", false, "idle")).toBe(false);
  });
});
