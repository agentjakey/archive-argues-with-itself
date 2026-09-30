import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StoryGallery } from "../components/Stories";
import { useAttractLoop } from "../hooks/useAttractLoop";
import type { Story } from "../types";
import { row } from "./fixtures";

const story = (id: string): Story => ({
  id,
  question: `Question ${id}`,
  filters: {},
  caption: `Caption ${id}`,
  pins: [row({ passage_id: `${id}-a`, year: 1974 }), row({ passage_id: `${id}-b`, year: 1999 })],
});

describe("story gallery", () => {
  it("renders a lead card plus a grid, each a button that opens its story with two scanned pages", () => {
    const onOpen = vi.fn();
    render(<StoryGallery stories={[story("s1"), story("s2"), story("s3")]} loading={false} onOpen={onOpen} />);
    const cards = screen.getAllByRole("button", { name: /See the full answer/ });
    expect(cards).toHaveLength(3);                                         // lead + two grid cards
    fireEvent.click(screen.getByRole("button", { name: /See the full answer: Question s2/ }));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "s2" }));
    const imgs = screen.getAllByRole("img");
    expect(imgs).toHaveLength(6);                                          // two scanned pages per card
    expect(imgs[0]).toHaveAttribute("src", story("s1").pins[0].page_image);  // the full page image, not the thumb
  });
  it("renders nothing when there are no stories and not loading", () => {
    const { container } = render(<StoryGallery stories={[]} loading={false} onOpen={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });
  it("holds a stable placeholder while stories load", () => {
    const { container } = render(<StoryGallery stories={[]} loading={true} onOpen={() => {}} />);
    expect(container.querySelector(".sk-page")).not.toBeNull();
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
