import { act, fireEvent, render, screen } from "@testing-library/react";
import { App } from "../App";
import { FIXTURE } from "./fixture";
import { findQuote, maskSpans, score, segment } from "../lib/text";
import { clampYear, stepFromKey, wheelAccumulator } from "../lib/input";
import { STRINGS } from "../lib/strings";

const ONLINE = { kiosk: false, idle_reset_seconds: 60, printer: false };
const KIOSK = { kiosk: true, idle_reset_seconds: 60, printer: true };

describe("text helpers", () => {
  it("finds a quote across line breaks, case and accents", () => {
    const text = "Le programme de sant\u00e9\npublique a COMMENC\u00c9 au printemps.";
    const span = findQuote(text, "programme de sante publique a commence");
    expect(span).not.toBeNull();
    expect(text.slice(span![0], span![1])).toBe("programme de sant\u00e9\npublique a COMMENC\u00c9");
    expect(findQuote(text, "programme de sante privee")).toBeNull();
  });
  it("masks years and lets a mask win over a mark", () => {
    const segs = segment("Report 1975 on beds", [{ id: "q", quote: "Report 1975 on" }], [[7, 11]]);
    expect(segs.map((s) => s.kind)).toEqual(["mark", "mask", "mark", "plain"]);
    expect(maskSpans("in 1975 and 1980", [[3, 7]]).map((s) => s.text)).toEqual(["in ", "1975", " and 1980"]);
  });
  it("scores by closeness", () => {
    expect(score(1975, 1975)).toBe(100);
    expect(score(1972, 1975)).toBe(70);
    expect(score(1900, 1975)).toBe(0);
  });
});

describe("dial input", () => {
  it("maps standard keys to steps", () => {
    expect(stepFromKey("ArrowRight")).toBe(1);
    expect(stepFromKey("ArrowLeft")).toBe(-1);
    expect(stepFromKey("Enter")).toBe(0);
  });
  it("turns wheel deltas into whole steps", () => {
    const acc = wheelAccumulator(60);
    expect(acc(30)).toBe(0);
    expect(acc(40)).toBe(-1);
    expect(acc(-130)).toBe(2);
  });
  it("keeps the year in range", () => {
    expect(clampYear(1950, 1960, 2018)).toBe(1960);
    expect(clampYear(2030, 1960, 2018)).toBe(2018);
  });
});

describe("the exhibit", () => {
  it("shows the menu online, with the privacy line and the site's Privacy and Accessibility links", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={ONLINE} />);
    expect(screen.getByRole("heading", { name: STRINGS.en.modesHeading })).toBeInTheDocument();
    expect(screen.getByText(STRINGS.en.privacy)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/?view=privacy");
    expect(screen.getByRole("link", { name: "Accessibility" })).toHaveAttribute("href", "/?view=accessibility");
  });

  it("starts the kiosk on the attract loop with no site links", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={KIOSK} />);
    expect(screen.getByRole("button", { name: STRINGS.en.touchToStart })).toBeInTheDocument();
    expect(screen.getByText(STRINGS.en.privacy)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Privacy" })).toBeNull();
  });

  it("switches to French", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={ONLINE} />);
    fireEvent.click(screen.getByRole("button", { name: "Fran\u00e7ais" }));
    expect(screen.getByRole("heading", { name: STRINGS.fr.modesHeading })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("fr");
  });

  it("plays Same or Not? and reveals the answer in words and the decisive lines", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={ONLINE} />);
    fireEvent.click(screen.getByRole("button", { name: /Same or Not\?/ }));
    expect(screen.getByText(STRINGS.en.same.levelOneNote)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /A real disagreement/ }));
    expect(screen.getByText(/Not quite\. The answer: Not comparable\./)).toBeInTheDocument();
    expect(screen.getAllByText(/per 1,000 persons aged 65 and over/).length).toBeGreaterThan(0);
    expect(screen.getByText(STRINGS.en.status.modelReviewed + " " + STRINGS.en.status.drafted)).toBeInTheDocument();
  });

  it("hides the year on When Was This? until the guess, then scores it", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={ONLINE} />);
    fireEvent.click(screen.getByRole("button", { name: /When Was This\?/ }));
    expect(screen.queryByText(/1975-76/)).toBeNull();
    const slider = screen.getByRole("slider", { name: "Year" });
    for (let i = 0; i < 14; i++) fireEvent.keyDown(slider, { key: "ArrowLeft" });
    fireEvent.click(screen.getByRole("button", { name: STRINGS.en.when.guess }));
    expect(screen.getAllByText(/Published in 1975\./).length).toBeGreaterThan(0);
    expect(screen.getByText(/Your guess: 1975/)).toBeInTheDocument();
  });

  it("rebuilds the Time Dial answer from the pages published by the dial year", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={ONLINE} />);
    fireEvent.click(screen.getByRole("button", { name: /Time Dial/ }));
    fireEvent.click(screen.getByRole("button", { name: "What did the record say about smoking?" }));
    expect(screen.getByText("The 1970 page calls smoking a hazard.")).toBeInTheDocument();
    const slider = screen.getByRole("slider", { name: "Year" });
    fireEvent.keyDown(slider, { key: "End" });
    expect(screen.getByText("By 1990, smoking in public places is restricted.")).toBeInTheDocument();
    fireEvent.keyDown(slider, { key: "Home" });
    expect(screen.getByText(STRINGS.en.dial.nothingYet(1960))).toBeInTheDocument();
    expect(screen.getByText(STRINGS.en.dial.notIndexed(1960))).toBeInTheDocument();
  });

  it("explains a Gap Hunt cell without calling not-indexed missing", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={ONLINE} />);
    fireEvent.click(screen.getByRole("button", { name: /Gap Hunt/ }));
    fireEvent.click(screen.getByRole("button", { name: /Ontario, 1970s/ }));
    expect(screen.getByText(/none are indexed here yet\. Not indexed is not the same as missing\./)).toBeInTheDocument();
  });

  it("resets the kiosk after a quiet minute", () => {
    vi.useFakeTimers();
    render(<App initialDeck={FIXTURE} initialKiosk={KIOSK} />);
    fireEvent.click(screen.getByRole("button", { name: STRINGS.en.touchToStart }));
    expect(screen.getByRole("heading", { name: STRINGS.en.modesHeading })).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(61_000);
    });
    expect(screen.getByRole("button", { name: STRINGS.en.touchToStart })).toBeInTheDocument();
    vi.useRealTimers();
  });
});
