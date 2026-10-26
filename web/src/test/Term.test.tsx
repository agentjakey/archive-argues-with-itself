import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Term } from "../components/Term";
import { GLOSSARY } from "../lib/glossary";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const def = (key: keyof typeof GLOSSARY) => GLOSSARY[key].definition;

describe("Term toggletip", () => {
  it("renders the term as a real button in the tab order, collapsed by default", () => {
    render(
      <p>
        text <Term def="ocr" /> more
      </p>,
    );
    const btn = screen.getByRole("button", { name: /OCR/ });
    expect(btn.tagName).toBe("BUTTON");
    expect(btn.getAttribute("type")).toBe("button");
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(btn.tabIndex).not.toBe(-1);
    expect(screen.queryByText(def("ocr"))).toBeNull();
  });

  it("click toggles the definition open and closed and tracks aria-expanded", () => {
    render(<Term def="passage" />);
    const btn = screen.getByRole("button", { name: /passage/ });
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("status")).toHaveTextContent(def("passage"));
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("activates with the keyboard (native button): Enter and Space fire a click that opens it", () => {
    // A native <button type="button"> is activated by Enter (keydown) and Space (keyup); the browser
    // delivers that activation as a click, which opens the toggletip. jsdom does not synthesize that
    // click from a key event, so we exercise the click a native button produces and assert the element
    // is a real button in the tab order so Enter/Space work in a browser (covered live in Playwright).
    render(<Term def="undated" />);
    const btn = screen.getByRole("button", { name: /undated/ });
    expect(btn.tagName).toBe("BUTTON");
    expect(btn.tabIndex).not.toBe(-1);
    fireEvent.click(btn);
    expect(screen.getByRole("status")).toHaveTextContent(def("undated"));
  });

  it("Escape closes it and returns focus to the term", () => {
    render(<Term def="jurisdiction" />);
    const btn = screen.getByRole("button", { name: /jurisdiction/ });
    btn.focus();
    fireEvent.click(btn);
    expect(screen.getByRole("status")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("status")).toBeNull();
    expect(document.activeElement).toBe(btn);
  });

  it("an outside pointer press closes it", () => {
    render(
      <div>
        <Term def="ocr" />
        <span data-testid="outside">elsewhere</span>
      </div>,
    );
    const btn = screen.getByRole("button", { name: /OCR/ });
    fireEvent.click(btn);
    expect(screen.getByRole("status")).toBeInTheDocument();
    fireEvent.pointerDown(screen.getByTestId("outside"));
    expect(screen.queryByRole("status")).toBeNull();
    expect(btn.getAttribute("aria-expanded")).toBe("false");
  });

  it("opens only one at a time: opening a second closes the first", () => {
    render(
      <div>
        <Term def="ocr" />
        <Term def="passage" />
      </div>,
    );
    const a = screen.getByRole("button", { name: /OCR/ });
    const b = screen.getByRole("button", { name: /passage/ });
    fireEvent.click(a);
    expect(a.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(b);
    expect(b.getAttribute("aria-expanded")).toBe("true");
    expect(a.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("hover opens after a delay and survives the pointer moving into the bubble (fake timers)", () => {
    vi.useFakeTimers();
    render(<Term def="lexical-matches" />);
    const btn = screen.getByRole("button", { name: /lexical matches/ });
    fireEvent.mouseEnter(btn);
    expect(screen.queryByRole("status")).toBeNull(); // waits the open delay before showing
    act(() => void vi.advanceTimersByTime(120));
    const bubble = screen.getByRole("status");
    expect(bubble).toBeInTheDocument();
    // leave the term but move into the bubble before the close delay elapses: it stays open
    fireEvent.mouseLeave(btn);
    fireEvent.mouseEnter(bubble);
    act(() => void vi.advanceTimersByTime(150));
    expect(screen.getByRole("status")).toBeInTheDocument();
    // leave the bubble: it closes after the delay
    fireEvent.mouseLeave(bubble);
    act(() => void vi.advanceTimersByTime(150));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("does not render its trigger inside another button or link", () => {
    render(
      <p>
        a <Term def="ocr" /> b
      </p>,
    );
    const btn = screen.getByRole("button", { name: /OCR/ });
    expect(btn.parentElement?.closest("button, a")).toBeNull();
  });

  it("an unknown key renders plain text with no button", () => {
    render(
      <p>
        <Term def="not-a-term">plain words</Term>
      </p>,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("plain words")).toBeInTheDocument();
  });
});
