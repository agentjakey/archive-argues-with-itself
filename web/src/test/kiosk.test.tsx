import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { readKioskFlag, useKiosk } from "../hooks/useKiosk";

function Probe() {
  const kiosk = useKiosk();
  return <span data-testid="flag">{kiosk ? "kiosk" : "normal"}</span>;
}

describe("kiosk flag", () => {
  afterEach(() => {
    window.history.replaceState({}, "", "/");
    document.body.classList.remove("kiosk");
  });
  it("is off by default", () => {
    expect(readKioskFlag("")).toBe(false);
    render(<Probe />);
    expect(screen.getByTestId("flag")).toHaveTextContent("normal");
    expect(document.body.classList.contains("kiosk")).toBe(false);
  });
  it("turns on with ?kiosk=1 and marks the body", () => {
    window.history.replaceState({}, "", "/?kiosk=1");
    expect(readKioskFlag("?kiosk=1")).toBe(true);
    render(<Probe />);
    expect(screen.getByTestId("flag")).toHaveTextContent("kiosk");
    expect(document.body.classList.contains("kiosk")).toBe(true);
  });
});
