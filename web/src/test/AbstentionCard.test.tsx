import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AbstentionCard } from "../components/AbstentionCard";
import { abstention } from "./fixtures";

describe("AbstentionCard", () => {
  it("renders the abstention text, uncovered terms, and no error semantics", () => {
    render(<AbstentionCard answer={abstention()} />);
    expect(screen.getByText(/the record here is thin/)).toBeInTheDocument();
    expect(screen.getByText("covid")).toBeInTheDocument();
    expect(screen.getByText("2020")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("leads with a plain line that the refusal is deliberate and points to the evidence below", () => {
    render(<AbstentionCard answer={abstention()} />);
    expect(screen.getByText(/deliberate refusal, not an error/)).toBeInTheDocument();
    expect(screen.getByText(/nearest evidence it does hold is below/)).toBeInTheDocument();
  });

  it("shows the single source badge when flagged", () => {
    const a = abstention();
    a.coverage.single_source = true;
    render(<AbstentionCard answer={a} />);
    expect(screen.getByText("single source")).toBeInTheDocument();
  });
});
