// The deck format (docs/formats/exhibit-deck.md), as the app reads it. The app never changes a
// deck: it only shows what the builder published.

export type Lang = "en" | "fr";
export type Text = { en: string; fr: string };

export type PageDate = {
  year: number | null;
  method: "read_from_page" | "read_from_front_matter" | "not_found";
  page_ref: string | null;
  line: string | null;
};

export type Page = {
  ref: string;
  collection: string;
  item_id: string;
  leaf: number;
  title: string;
  issuer: string | null;
  jurisdiction: string | null;
  language: string | null;
  catalogue_date: { year: number | null; raw: string | null; method: string };
  page_date: PageDate;
  date_verified: boolean;
  date_verification: string;
  text: string;
  text_cut: boolean;
  details_url: string;
  image_url: string;
  thumb_url: string;
  qr?: { size: number; path: string };
};

export type Quote = { id: string; page_ref: string; role: string; text: string };

export type Choice = "same_thing_changed" | "real_disagreement" | "not_comparable" | "not_enough_evidence";
export const CHOICES: Choice[] = ["same_thing_changed", "real_disagreement", "not_comparable", "not_enough_evidence"];

export type Review = {
  panel_calibrated: boolean;
  reviewer?: { model: string | null; date: string };
  flags?: string[];
  author: { decision: string; date: string; notes?: string; reviewer?: string } | null;
};

type RoundBase = {
  id: string;
  level: number;
  collection: string;
  pages: Page[];
  quotes: Quote[];
  explanation: Text;
  explanation_status: "model-drafted" | "author-reviewed" | "author-edited";
  status: "model-reviewed" | "ai-adjudicated" | "author-reviewed";
  review: Review;
  provenance: { drafted_by: string; prompt_version: string; drafted_at: string; edits: unknown[] };
};

export type SameOrNotRound = RoundBase & {
  mode: "same_or_not";
  play: {
    claims: { page_ref: string; quote: string; text: Text }[];
    answer: Choice;
    decisive: string[];
    constraints: Record<string, "same" | "differs" | "unclear">;
  };
};

export type WhenRound = RoundBase & {
  mode: "when_was_this";
  play: { year: number; label: Text; clues: string[]; masked_text: [number, number][]; masked_title: [number, number][] };
};

export type DialYear = { year: number; state: "not_indexed" | "quiet" | "recorded"; items: number | null };

export type DialRound = RoundBase & {
  mode: "time_dial";
  play: {
    question: Text;
    question_id: string;
    jurisdiction: string | null;
    epochs: { year: number; state: "answer" | "insufficient"; answer: Text; quotes: string[]; pages_by_then: string[] }[];
    years: DialYear[];
    collection_period: [number, number];
  };
};

export type Round = SameOrNotRound | WhenRound | DialRound;

export type GapCell = {
  place: string;
  iso: string | null;
  decade: number;
  catalogue_items: number | null;
  indexed_items: number;
  state: "recorded" | "not_indexed" | "quiet_examined" | "unknown";
};

export type GapHunt = {
  decades: number[];
  jurisdictions: string[];
  cells: GapCell[];
  indexed_collections: Record<string, [number, number]>;
  catalogue: { fetched_at: string; method: string; total: number } | null;
  unknown_place_indexed: number;
};

export type Deck = {
  format: string;
  deck_id: string;
  built_at: string;
  settings: { dial: [number, number]; idle_reset_seconds: number; offline_image_cache: boolean; panel_calibrated: boolean };
  counts: Record<string, number>;
  rounds: Round[];
  gap_hunt: GapHunt | null;
};

export function roundsOf<M extends Round["mode"]>(deck: Deck, mode: M): Extract<Round, { mode: M }>[] {
  return deck.rounds.filter((r): r is Extract<Round, { mode: M }> => r.mode === mode);
}

export function quoteById(round: Round, id: string): Quote | undefined {
  return round.quotes.find((q) => q.id === id);
}

export function pageByRef(round: Round, ref: string): Page | undefined {
  return round.pages.find((p) => p.ref === ref);
}

// The current deck is named by a small pointer file (exhibit/current-deck.json, never cached), so a
// new deck goes live by moving one pointer; the decks themselves are named by their content.
export async function loadDeck(base: string = "./"): Promise<Deck> {
  const pointer = await fetch(base + "current-deck.json", { cache: "no-cache" });
  if (!pointer.ok) throw new Error(`deck pointer ${pointer.status}`);
  const { deck } = (await pointer.json()) as { deck: string };
  if (!/^[A-Za-z0-9._-]+\.json$/.test(deck)) throw new Error("deck pointer names an unexpected file");
  const res = await fetch(base + "decks/" + deck);
  if (!res.ok) throw new Error(`deck ${res.status}`);
  const parsed = (await res.json()) as Deck;
  if (parsed.format !== "exhibit-deck/1") throw new Error(`unknown deck format ${parsed.format}`);
  return parsed;
}
