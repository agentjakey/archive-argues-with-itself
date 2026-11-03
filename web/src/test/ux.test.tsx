// The redesigned opening screen and header: the featured questions are real recorded answers that
// cite pages; the theme switch follows the device until a choice is made and stores only a choice
// that differs from it; the header marks the current section and folds into a menu; the example
// line pauses and never moves with reduced motion.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Header, sectionOf } from "../components/Header";
import { SectionNav } from "../components/SectionNav";
import { Suggestions } from "../components/Suggestions";
import { ThemeToggle } from "../components/ThemeToggle";
import { citationText } from "../components/Sources";
import { FEATURED, featuredFor, type FeaturedQuestion } from "../lib/featured";
import { currentTheme, setTheme } from "../lib/theme";
import type { EvidenceRow, Example } from "../types";

const DATA = resolve(process.cwd(), "../site/data") + "/";
const read = (path: string) => JSON.parse(readFileSync(`${DATA}${path}`, "utf-8"));

describe("featured questions", () => {
  for (const [scope, list] of Object.entries(FEATURED)) {
    it(`every ${scope} featured question is a recorded, cited, unflagged answer`, () => {
      const examples = read(`${scope}/examples.json`) as Example[];
      const index = read(`${scope}/answers/index.json`) as {
        answers: { question: string; filters: Record<string, string>; file: string | null }[];
      };
      const featured = featuredFor(scope, examples);
      expect(featured.map((f) => f.qid)).toEqual(list.map((f) => f.qid));
      for (const f of featured) {
        const entry = index.answers.find(
          (e) => e.question === f.text && JSON.stringify(e.filters) === JSON.stringify(f.filters ?? {}),
        );
        expect(entry?.file, f.qid).toBeTruthy();
        const answer = read(`${scope}/${entry!.file}`);
        expect(answer.answer.abstained, f.qid).toBe(false);
        expect(answer.flagged ?? null, f.qid).toBeNull();
        const cited = new Set(answer.answer.verified_citations.map((c: { passage_id: string }) => c.passage_id));
        expect(cited.size, f.qid).toBeGreaterThanOrEqual(2);
        const withImages = answer.evidence.filter((r: EvidenceRow) => cited.has(r.passage_id) && r.page_image);
        expect(withImages.length, f.qid).toBe(cited.size);
        expect(f.topic.length, f.qid).toBeLessThanOrEqual(24);
      }
    });
  }

  it("drops a featured question its corpus no longer lists, and never offers a refusal", () => {
    const examples: Example[] = [
      { qid: "q016", text: "Drug question?", gold: "answerable" } as Example,
      { qid: "q006", text: "SARS question?", gold: "abstain" } as Example,
    ];
    expect(featuredFor("pilot", examples).map((f) => f.qid)).toEqual(["q016"]);
    expect(featuredFor("unknown-scope", examples)).toEqual([]);
  });
});

describe("theme", () => {
  afterEach(() => {
    document.documentElement.removeAttribute("data-theme");
    delete (window as unknown as { archiveTheme?: unknown }).archiveTheme;
  });

  it("names what it will do and switches the page", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: "Switch to light theme" });
    fireEvent.click(button);
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
  });

  it("asks the boot script to store the choice when it is loaded", () => {
    const set = vi.fn((t: string) => {
      document.documentElement.setAttribute("data-theme", t);
      return t;
    });
    (window as unknown as { archiveTheme: unknown }).archiveTheme = { apply: vi.fn(), set, kiosk: false };
    document.documentElement.setAttribute("data-theme", "light");
    expect(setTheme("dark")).toBe("dark");
    expect(set).toHaveBeenCalledWith("dark");
    expect(currentTheme()).toBe("dark");
  });

  it("the boot script stores only a choice that differs from the device, and nothing in kiosk mode", () => {
    // A plain in-memory storage, so the test does not depend on the test browser providing one.
    const store = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
        setItem: (k: string, v: string) => void store.set(k, String(v)),
        removeItem: (k: string) => void store.delete(k),
        clear: () => store.clear(),
      },
    });
    const source = readFileSync(resolve(process.cwd(), "../design/theme-boot.js"), "utf-8");
    const run = (search: string, prefersLight: boolean) => {
      window.history.replaceState(null, "", `/${search}`);
      window.matchMedia = ((q: string) => ({
        matches: q.includes("light") ? prefersLight : false,
        addEventListener: () => undefined,
      })) as unknown as typeof window.matchMedia;
      new Function(source)();
      return (window as unknown as { archiveTheme: { set: (t: string) => string } }).archiveTheme;
    };
    localStorage.clear();
    let api = run("", false);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    api.set("light");
    expect(localStorage.getItem("theme")).toBe("light");
    api.set("dark");
    expect(localStorage.getItem("theme")).toBeNull();
    localStorage.setItem("theme", "light");
    api = run("?kiosk=1", false);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    api.set("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    localStorage.clear();
    window.history.replaceState(null, "", "/");
  });
});

describe("header", () => {
  it("has four destinations, marks the current section and folds into a menu", () => {
    const onView = vi.fn();
    render(<Header kiosk={false} view="timeline" onView={onView} onAsk={vi.fn()} />);
    const wide = screen.getAllByRole("navigation", { name: "Main" })[0];
    expect(wide.textContent).toContain("Ask");
    expect(wide.textContent).toContain("Explore");
    expect(wide.textContent).toContain("Exhibit");
    expect(wide.textContent).toContain("How it works");
    const current = wide.querySelector('[aria-current="page"]');
    expect(current?.textContent).toBe("Explore");
    const menu = screen.getByRole("button", { name: /Menu/ });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
  });

  it("kiosk mode has no theme switch and no exhibit link", () => {
    render(<Header kiosk view={null} onView={vi.fn()} />);
    expect(screen.queryByTestId("theme-toggle")).toBeNull();
    expect(screen.queryAllByRole("link", { name: "Exhibit" })).toHaveLength(0);
  });

  it("every page belongs to a section or is a footer page", () => {
    expect(sectionOf(null)).toBe("ask");
    expect(sectionOf("map")).toBe("explore");
    expect(sectionOf("gaps")).toBe("how");
    expect(sectionOf("privacy")).toBeNull();
  });

  it("the section row links the pages of Explore, including the full catalogue", () => {
    const onView = vi.fn();
    render(<SectionNav view="explore" onView={onView} />);
    expect(screen.getByRole("link", { name: "Full catalogue" })).toHaveAttribute("href", "/catalogue/");
    fireEvent.click(screen.getByRole("button", { name: "Through time" }));
    expect(onView).toHaveBeenCalledWith("timeline");
  });
});

describe("example questions", () => {
  const questions: FeaturedQuestion[] = [
    { qid: "a", text: "First full question?", topic: "First" } as FeaturedQuestion,
    { qid: "b", text: "Second full question?", topic: "Second" } as FeaturedQuestion,
  ];

  afterEach(() => vi.useRealTimers());

  it("keeps every topic on screen, each named with its full question", () => {
    const onPick = vi.fn();
    render(<Suggestions questions={questions} onPick={onPick} />);
    fireEvent.click(screen.getByRole("button", { name: "Second: Second full question?" }));
    expect(onPick).toHaveBeenCalledWith(questions[1]);
  });

  it("rotates the example line, and stops while the visitor types", () => {
    vi.useFakeTimers();
    window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => undefined })) as unknown as typeof window.matchMedia;
    const { rerender } = render(<Suggestions questions={questions} onPick={vi.fn()} />);
    expect(screen.getByRole("button", { name: "First full question?" })).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(6400));
    expect(screen.getByRole("button", { name: "Second full question?" })).toBeInTheDocument();
    rerender(<Suggestions questions={questions} onPick={vi.fn()} paused />);
    act(() => vi.advanceTimersByTime(20000));
    expect(screen.getByRole("button", { name: "Second full question?" })).toBeInTheDocument();
  });

  it("never moves with reduced motion", () => {
    vi.useFakeTimers();
    window.matchMedia = ((q: string) => ({ matches: q.includes("reduce"), media: q, addEventListener: () => undefined })) as unknown as typeof window.matchMedia;
    render(<Suggestions questions={questions} onPick={vi.fn()} />);
    act(() => vi.advanceTimersByTime(30000));
    expect(screen.getByRole("button", { name: "First full question?" })).toBeInTheDocument();
  });
});

describe("copy citations", () => {
  it("lists every numbered source with its page and archive.org link", () => {
    const row = {
      passage_id: "p1",
      title: "Annual report",
      year: 1965,
      printed_page: "12",
      leaf_index: 14,
      deep_link: "https://archive.org/details/x/page/n13",
    } as unknown as EvidenceRow;
    const text = citationText(new Map([["p1", 1]]), new Map([["p1", row]]));
    expect(text).toBe("1. Annual report (1965), p. 12 (leaf 14). https://archive.org/details/x/page/n13");
  });
});
