import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnswerCard } from "../components/AnswerCard";
import { CompareView } from "../components/CompareView";
import { ThresholdHero } from "../components/ThresholdHero";
import { askedQuestion, attractStories, galleryStories, heroStory } from "../lib/stories";
import type { Answer, Comparability, EditorialNote, EvidenceRow, Story } from "../types";
import { row } from "./fixtures";

// The corrected Alberta story (config/stories.json). Its content is guarded on the server by
// tests/test_editorial.py and tests/test_api.py; here it drives the UI framing so the compare view,
// the hero and the answer card never present the two records as the same plan changing.
const ALBERTA_CAPTION =
  "Two Alberta government health records, twenty-five years apart. 1974: an inventory of provincial " +
  "services for First Nations and Metis people describes the basic health insurance plan and who paid its " +
  "premiums. 1998-99: a statistical supplement counts enrollment in Alberta Blue Cross non-group coverage, " +
  "a separate supplementary program. They describe different things and cannot, on their own, show how " +
  "coverage changed.";

const ALBERTA_V1_QUESTION = "How did Alberta health insurance coverage change between the 1970s and 1990s?";

const INCOMPATIBLE: Comparability = {
  outcome: "incompatible",
  label: "Incompatible",
  differs_on: ["program", "population", "measure"],
  note: "Different program, population and measure.",
};

const STORY_NOTE: EditorialNote = {
  id: "alberta-insurance-question-2026-10-29",
  date: "2026-10-29",
  text: "Corrected. The question above is new.",
  reason: "The story question presupposed a change.",
};

const PINS: [EvidenceRow, EvidenceRow] = [
  row({ passage_id: "ableg_33398004781505#52:0", year: 1974, jurisdiction: "alberta",
        title: "An inventory of provincial government services" }),
  row({ passage_id: "micro_IA40243301_0385#117:0", year: 1999, jurisdiction: "alberta",
        title: "Statistical supplement, 1998-99" }),
];

function story(over: Partial<Story>): Story {
  return { id: "s", question: "q", filters: {}, caption: "", pins: PINS, ...over };
}

describe("compare view framing", () => {
  it("labels a story caption as reading guidance and shows what the pair cannot show", () => {
    render(
      <CompareView
        a={PINS[0]}
        b={PINS[1]}
        salientTerms={[]}
        caption={ALBERTA_CAPTION}
        comparability={INCOMPATIBLE}
        notes={[STORY_NOTE]}
        onOpen={vi.fn()}
        onUnpin={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("How to read these sources")).toBeInTheDocument();
    expect(screen.queryByText("What changed")).toBeNull();
    expect(screen.getByText(/cannot, on their own, show how coverage changed/)).toBeInTheDocument();
    expect(screen.queryByText(/same insurance plan/i)).toBeNull();
    expect(screen.getByText("Incompatible")).toBeInTheDocument();
    expect(screen.getByText("Differs on program, population, measure")).toBeInTheDocument();
    expect(screen.getByText("Different program, population and measure.")).toBeInTheDocument();
    expect(screen.getByText("Editorial note, 2026-10-29")).toBeInTheDocument();
  });

  it("joins the two years with 'and', never 'vs'", () => {
    render(<CompareView a={PINS[0]} b={PINS[1]} salientTerms={[]} onOpen={vi.fn()} onUnpin={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "1974 and 1999" })).toBeInTheDocument();
    expect(screen.queryByText(/ vs /)).toBeNull();
  });
});

describe("threshold hero framing", () => {
  it("uses a neutral label and shows the pair's comparability", () => {
    const featured = story({ caption: ALBERTA_CAPTION, comparability: INCOMPATIBLE, question: "What do two records say?" });
    render(<ThresholdHero featured={featured} onOpen={vi.fn()} />);
    expect(screen.getByText("Two pages from the public record")).toBeInTheDocument();
    expect(screen.queryByText("One disagreement in the record")).toBeNull();
    expect(screen.getByText(/describe different things/)).toBeInTheDocument();
    expect(screen.getByText("Incompatible")).toBeInTheDocument();
  });
});

describe("story surfaces", () => {
  const hero = story({ id: "hero", surfaces: ["hero", "gallery", "attract"] });
  const galleryOnly = story({ id: "alberta", surfaces: ["gallery"] });
  const both = story({ id: "both", surfaces: ["gallery", "attract"] });
  const none = story({ id: "none" });
  const all = [galleryOnly, hero, both, none];

  it("puts the hero-marked story at the threshold, not whichever comes first", () => {
    expect(heroStory(all)?.id).toBe("hero");
    expect(heroStory([galleryOnly, both])).toBeNull();
  });

  it("keeps gallery-only stories out of the attract loop and the hero out of the gallery", () => {
    expect(galleryStories(all).map((s) => s.id)).toEqual(["alberta", "both"]);
    expect(attractStories(all).map((s) => s.id)).toEqual(["hero", "both"]);
  });

  it("asks a corrected story with its original wording", () => {
    expect(askedQuestion(story({ question: "new", answer_question: ALBERTA_V1_QUESTION }))).toBe(ALBERTA_V1_QUESTION);
    expect(askedQuestion(story({ question: "same" }))).toBe("same");
  });
});

describe("answer card editorial notes", () => {
  const answer: Answer = {
    text: "In 1972, Alberta implemented a policy.",
    sentences: [{ text: "In 1972, Alberta implemented a policy.", cited_ids: [] }],
    verified_citations: [],
    unsupported: [],
    abstained: false,
    coverage: { n_passages: 12, n_items: 4, single_source: false } as Answer["coverage"],
    abstention_text: null,
    generation: { provider: "anthropic", model: "m", temperature: 0, prompt_sha256: "x", max_tokens: 2048, top_k: 12 },
    cached: { created_at: "2026-10-16T20:11:54+00:00" },
  };

  it("shows a dated note above the stored answer and leaves the answer text as it was", () => {
    const note: EditorialNote = { id: "n", date: "2026-10-29", text: "Cites page 116, not page 117.", reason: "r" };
    render(<AnswerCard answer={answer} byId={new Map()} onOpen={vi.fn()} notes={[note]} />);
    expect(screen.getByText("Editorial note, 2026-10-29")).toBeInTheDocument();
    expect(screen.getByText(/Cites page 116, not page 117/)).toBeInTheDocument();
    expect(screen.getByText("In 1972, Alberta implemented a policy.")).toBeInTheDocument();
  });

  it("shows nothing extra without notes", () => {
    render(<AnswerCard answer={answer} byId={new Map()} onOpen={vi.fn()} />);
    expect(screen.queryByLabelText("Editorial notes")).toBeNull();
  });
});
