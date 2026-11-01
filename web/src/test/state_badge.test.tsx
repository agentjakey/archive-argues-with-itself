import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StateBadge, STATE_TEXT } from "../components/StateBadge";
import { abstention } from "./fixtures";

describe("StateBadge", () => {
  it("shows nothing for a v1 answer", () => {
    const { container } = render(<StateBadge answer={abstention()} />);
    expect(container.textContent).toBe("");
  });

  it("has a plain label for each of the six states", () => {
    expect(Object.keys(STATE_TEXT).sort()).toEqual(
      ["CONFLICTING", "INCOMPARABLE", "INSUFFICIENT_EVIDENCE", "PARTIALLY_SUPPORTED", "RESTRICTED", "SUPPORTED"],
    );
  });

  it("says not indexed is not the same as not in the archive", () => {
    const a = { ...abstention(), state: "INSUFFICIENT_EVIDENCE", coverage_state: "not_indexed", state_reason: "r" };
    render(<StateBadge answer={a} />);
    expect(screen.getByText("Not enough evidence")).toBeInTheDocument();
    expect(screen.getByText(/says nothing about the archive as a whole/)).toBeInTheDocument();
  });

  it("labels a reviewed answer kept from the earlier pipeline", () => {
    const a = { ...abstention(), state: "SUPPORTED", reviewed: { answer_version: "v1", note: "n" } };
    render(<StateBadge answer={a} />);
    expect(screen.getByTestId("reviewed-line")).toBeInTheDocument();
  });
});
