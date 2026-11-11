import { act, fireEvent, render, screen } from "@testing-library/react";
import { App } from "../App";
import { FIXTURE } from "./fixture";
import { findQuote, maskSpans, score, segment } from "../lib/text";
import { DIAL_START_GAP, clampYear, dialStart, stepFromKey, wheelAccumulator } from "../lib/input";
import { buildArc, totalPoints } from "../lib/arc";
import { STRINGS } from "../lib/strings";

const ONLINE = { kiosk: false, idle_reset_seconds: 60, printer: false, counting: false };
const KIOSK = { kiosk: true, idle_reset_seconds: 60, printer: true, counting: true };
const en = STRINGS.en;
const SAMPLE_FR = "Le programme de sant\u00e9\npublique a COMMENC\u00c9 au printemps.";

// Reveals are paced; the tests switch on "Less motion" so every part shows at once, as it does for
// a visitor who asks for it.
function startVisit(kiosk = ONLINE) {
  render(<App initialDeck={FIXTURE} initialKiosk={kiosk} />);
  fireEvent.click(screen.getByRole("button", { name: en.reducedMotion }));
  fireEvent.click(screen.getByRole("button", { name: en.touchToStart }));
}

describe("text helpers", () => {
  it("finds a quote across line breaks, case and accents", () => {
    const span = findQuote(SAMPLE_FR, "programme de sante publique a commence");
    expect(span).not.toBeNull();
    expect(SAMPLE_FR.slice(span![0], span![1])).toBe(SAMPLE_FR.slice(3, SAMPLE_FR.indexOf(" au")));
    expect(findQuote(SAMPLE_FR, "programme de sante privee")).toBeNull();
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
  it("never starts When Was This? on the answer, or near enough to score", () => {
    for (let answer = 1955; answer <= 2025; answer++) {
      for (const id of ["wwt-1", "wwt-1bcb77f70b", "wwt-2c1562d68b", `wwt-${answer}`]) {
        const start = dialStart(1960, 2018, answer, id);
        expect(start).toBeGreaterThanOrEqual(1960);
        expect(start).toBeLessThanOrEqual(2018);
        expect(Math.abs(start - answer)).toBeGreaterThanOrEqual(DIAL_START_GAP);
        expect(score(start, answer)).toBe(0);
        expect(dialStart(1960, 2018, answer, id)).toBe(start); // the same card starts in the same place
      }
    }
    // 1989, the old midpoint start, is no longer where a 1989 card begins
    expect(dialStart(1960, 2018, 1989, "wwt-1bcb77f70b")).not.toBe(1989);
    // a range too short for the gap still never starts on the answer
    for (let answer = 2000; answer <= 2004; answer++) expect(dialStart(2000, 2004, answer, "x")).not.toBe(answer);
  });
});

describe("the visit", () => {
  it("alternates When Was This? and Same or Not?, then ends on one Time Dial question", () => {
    const steps = buildArc(FIXTURE, () => 0);
    expect(steps.map((s) => s.kind)).toEqual(["when_was_this", "same_or_not", "time_dial"]);
    const first = steps[0];
    if (first.kind !== "when_was_this") throw new Error("expected a When Was This? card first");
    expect(totalPoints([{ kind: "when_was_this", round: first.round, guess: 1972, points: 70 }])).toBe(70);
  });
});

describe("the exhibit", () => {
  it("opens on the attract screen with one button to play, the privacy line and the site's links online", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={ONLINE} />);
    expect(screen.getByRole("heading", { level: 1, name: en.title })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.touchToStart })).toBeInTheDocument();
    expect(screen.getByText(en.privacyWeb)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/?view=privacy");
    expect(screen.getByRole("link", { name: "Accessibility" })).toHaveAttribute("href", "/?view=accessibility");
  });

  it("has no site links on the kiosk", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={KIOSK} />);
    expect(screen.getByRole("button", { name: en.touchToStart })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Privacy" })).toBeNull();
  });

  it("starts with sound off and lets the visitor turn it on", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={ONLINE} />);
    const sound = screen.getByRole("button", { name: en.sound });
    expect(sound).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(sound);
    expect(sound).toHaveAttribute("aria-pressed", "true");
  });

  it("switches to French and says the French is pending review", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={ONLINE} />);
    fireEvent.click(screen.getByRole("button", { name: en.language }));
    expect(screen.getByRole("button", { name: STRINGS.fr.touchToStart })).toBeInTheDocument();
    expect(screen.getByText(STRINGS.fr.frenchPending)).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("fr");
  });

  it("plays a whole visit in one tap from the attract screen and ends in the chronicle", () => {
    startVisit();
    // When Was This?: the year is hidden until the guess, then scored and placed on a timeline.
    expect(screen.getByRole("heading", { name: en.when.prompt })).toBeInTheDocument();
    expect(screen.queryByText(/1975-76/)).toBeNull();
    const slider = screen.getByRole("slider", { name: "Year" });
    const startYear = Number(slider.getAttribute("aria-valuenow"));
    expect(Math.abs(startYear - 1975)).toBeGreaterThanOrEqual(DIAL_START_GAP);
    fireEvent.keyDown(slider, { key: "Home" });
    for (let i = 0; i < 15; i++) fireEvent.keyDown(slider, { key: "ArrowRight" });
    fireEvent.click(screen.getByRole("button", { name: en.when.guess }));
    expect(screen.getByText(en.when.actual(1975))).toBeInTheDocument();
    expect(screen.getByRole("img", { name: en.when.timeline(1975, 1975) })).toBeInTheDocument();
    expect(screen.getByText(/Your guess: 1975\. Exactly right\. 100 points\./)).toBeInTheDocument();
    expect(screen.getByText(en.status.modelReviewed + " " + en.status.drafted)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: en.next }));

    // Same or Not?: choices by shape, letter and words; the answer and the checklist in words.
    expect(screen.getByText(en.same.levelOneNote)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /A real disagreement/ }));
    expect(screen.getByText(en.same.youSaid(en.same.choices.real_disagreement))).toBeInTheDocument();
    expect(screen.getByText(/Not quite\. The answer: Not comparable\./)).toBeInTheDocument();
    expect(screen.getAllByText(/per 1,000 persons aged 65 and over/).length).toBeGreaterThan(0);
    expect(screen.getByText(en.same.constraint.population)).toBeInTheDocument();
    expect(screen.getByText(en.status.modelReviewed + " " + en.status.drafted)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: en.next }));

    // Time Dial: the answer is rebuilt from the pages published by the dial's year.
    expect(screen.getByText("The 1970 page calls smoking a hazard.")).toBeInTheDocument();
    const dial = screen.getByRole("slider", { name: "Year" });
    fireEvent.keyDown(dial, { key: "End" });
    expect(screen.getByText("By 1990, smoking in public places is restricted.")).toBeInTheDocument();
    fireEvent.keyDown(dial, { key: "Home" });
    expect(screen.getByText(en.dial.nothingYet(1960))).toBeInTheDocument();
    expect(screen.getByText(en.dial.notIndexed(1960))).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: en.done }));

    // The chronicle and the evidence card, with the review status said plainly.
    expect(screen.getByRole("heading", { name: en.chronicle.heading })).toBeInTheDocument();
    expect(screen.getByText(en.chronicle.summary(3, 100))).toBeInTheDocument();
    expect(screen.getByRole("article", { name: en.card.heading })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.card.print })).toBeInTheDocument();
    expect(screen.getByText(en.status.short + " " + en.status.drafted)).toBeInTheDocument();
  });

  it("plays Same or Not? as a group: secret picks passed along, then the room's split", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={ONLINE} />);
    fireEvent.click(screen.getByRole("button", { name: en.reducedMotion }));
    fireEvent.click(screen.getByRole("button", { name: en.attract.group }));
    fireEvent.click(screen.getByRole("button", { name: en.players.count(3) }));
    fireEvent.click(screen.getByRole("button", { name: en.when.guess }));
    fireEvent.click(screen.getByRole("button", { name: en.next }));
    fireEvent.click(screen.getByRole("radio", { name: /Not comparable/ }));
    fireEvent.click(screen.getByRole("button", { name: en.same.ready(2) }));
    fireEvent.click(screen.getByRole("radio", { name: /Not comparable/ }));
    fireEvent.click(screen.getByRole("button", { name: en.same.ready(3) }));
    fireEvent.click(screen.getByRole("radio", { name: /A real disagreement/ }));
    expect(screen.getByRole("img", { name: /How the room voted\. A real disagreement: 1, Not comparable: 2\./ })).toBeInTheDocument();
    expect(screen.getByText(en.same.split(2, 3))).toBeInTheDocument();
  });

  it("opens Gap Hunt from All games without calling not-indexed missing", () => {
    render(<App initialDeck={FIXTURE} initialKiosk={ONLINE} />);
    fireEvent.click(screen.getByRole("button", { name: en.attract.allGames }));
    fireEvent.click(screen.getByRole("button", { name: /Gap Hunt/ }));
    fireEvent.click(screen.getByRole("button", { name: /Ontario, 1970s/ }));
    expect(screen.getByText(/none are indexed here yet\. Not indexed is not the same as missing\./)).toBeInTheDocument();
    // An indexed square says its two counts measure different things, so a larger indexed count
    // than catalogue count does not read as a contradiction.
    fireEvent.click(screen.getByRole("button", { name: /Ontario, 1960s/ }));
    expect(screen.getByText(/120 indexed items are filed under Ontario\. That is a different count from the 1,698 items/)).toBeInTheDocument();
    expect(screen.getByText(/so either number can be the larger\./)).toBeInTheDocument();
  });

  it("resets the kiosk after a quiet minute, with sound off again", () => {
    vi.useFakeTimers();
    render(<App initialDeck={FIXTURE} initialKiosk={KIOSK} />);
    fireEvent.click(screen.getByRole("button", { name: en.sound }));
    fireEvent.click(screen.getByRole("button", { name: en.touchToStart }));
    expect(screen.getByRole("heading", { name: en.when.prompt })).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(61_000);
    });
    expect(screen.getByRole("button", { name: en.touchToStart })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.sound })).toHaveAttribute("aria-pressed", "false");
    vi.useRealTimers();
  });
});
