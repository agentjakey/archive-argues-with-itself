import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { About } from "../components/pages/About";
import { Gaps } from "../components/pages/Gaps";
import { HowItWorks } from "../components/pages/HowItWorks";
import { readState, writeState } from "../lib/urlstate";

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
    expect(screen.getAllByText("reports/phase9/generation_report.md").length).toBeGreaterThan(0);
  });

  it("Gaps carries the report numbers with their source files", () => {
    render(<Gaps />);
    expect(screen.getByText(/338,338 of 745,893 passages \(45\.4%\)/)).toBeInTheDocument();
    expect(screen.getByText(/12,684 pages front matter and 3,823 back matter/)).toBeInTheDocument();
    expect(screen.getByText(/10 of 35 answerable questions would/)).toBeInTheDocument();
    expect(screen.getByText(/mentions 2010 \(item dated 1984\)/)).toBeInTheDocument();
    expect(screen.getAllByText("reports/coverage_audit/finalist_sizing.md").length).toBe(2);
  });

  it("About names the partners, the image source, and the licence", () => {
    render(<About />);
    expect(screen.getByText(/AI Builders Fellowship of the BC \+ AI Ecosystem, with the Internet Archive/)).toBeInTheDocument();
    expect(screen.getByText(/served by archive.org/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /github.com\/agentjakey/ })).toHaveAttribute("href", "https://github.com/agentjakey/archive-argues-with-itself");
    expect(screen.getByText(/MIT licence/)).toBeInTheDocument();
  });
});
