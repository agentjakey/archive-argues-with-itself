import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Stories } from "../components/Stories";
import { useAttractLoop } from "../hooks/useAttractLoop";
import type { Story } from "../types";
import { row } from "./fixtures";

const story = (id: string): Story => ({
  id,
  question: `Question ${id}`,
  filters: {},
  caption: `Caption ${id}`,
  pins: [row({ passage_id: `${id}-a`, year: 1974 }), row({ passage_id: `${id}-b`, year: 1999, page_thumb: "/pages/x/n1_thumb.jpg" })],
});

describe("stories", () => {
  it("renders a card per story with both years and opens on click", () => {
    const onOpen = vi.fn();
    render(<Stories stories={[story("s1"), story("s2")]} onOpen={onOpen} />);
    expect(screen.getByRole("heading", { name: "Stories" })).toBeInTheDocument();
    expect(screen.getAllByText(/1974 and 1999/)).toHaveLength(2);
    expect(screen.getAllByRole("img")[1]).toHaveAttribute("src", "/pages/x/n1_thumb.jpg");   // offline pack path used as-is
    fireEvent.click(screen.getByText("Question s2"));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "s2" }));
  });
  it("renders nothing without stories", () => {
    const { container } = render(<Stories stories={[]} onOpen={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("attract loop", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("starts after the idle period, cycles stories, and goes home on input", () => {
    const onShow = vi.fn();
    const onHome = vi.fn();
    const stories = [story("a"), story("b")];
    renderHook(() => useAttractLoop({ enabled: true, stories, onShow, onHome, idleMs: 1000, stepMs: 500 }));
    act(() => vi.advanceTimersByTime(900));
    expect(onShow).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(100));
    expect(onShow).toHaveBeenCalledTimes(1);
    expect(onShow.mock.calls[0][0].id).toBe("a");
    act(() => vi.advanceTimersByTime(1000));
    expect(onShow).toHaveBeenCalledTimes(3);
    expect(onShow.mock.calls[1][0].id).toBe("b");
    expect(onShow.mock.calls[2][0].id).toBe("a");                                    // wraps around
    act(() => fireEvent.pointerDown(window));
    expect(onHome).toHaveBeenCalledTimes(1);
    act(() => vi.advanceTimersByTime(600));
    expect(onShow).toHaveBeenCalledTimes(3);                                         // loop stopped
  });

  it("input while idle only resets the timer; disabled outside kiosk", () => {
    const onShow = vi.fn();
    const onHome = vi.fn();
    renderHook(() => useAttractLoop({ enabled: true, stories: [story("a")], onShow, onHome, idleMs: 1000, stepMs: 500 }));
    act(() => vi.advanceTimersByTime(800));
    act(() => fireEvent.keyDown(window, { key: "a" }));
    act(() => vi.advanceTimersByTime(800));
    expect(onShow).not.toHaveBeenCalled();
    expect(onHome).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(300));
    expect(onShow).toHaveBeenCalledTimes(1);
    const off = vi.fn();
    renderHook(() => useAttractLoop({ enabled: false, stories: [story("a")], onShow: off, onHome, idleMs: 100 }));
    act(() => vi.advanceTimersByTime(1000));
    expect(off).not.toHaveBeenCalled();
  });
});
