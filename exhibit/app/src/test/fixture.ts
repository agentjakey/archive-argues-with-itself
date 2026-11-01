// A small synthetic deck for unit tests only. Its pages are invented test text, never shown to a
// visitor; real decks come from the deck builder.
import type { Deck, Page } from "../lib/deck";

function page(ref: string, year: number, text: string, title = "Annual report"): Page {
  const [item, leaf] = ref.split("#");
  return {
    ref,
    collection: "test",
    item_id: item,
    leaf: Number(leaf),
    title,
    issuer: "Test Board",
    jurisdiction: "ontario",
    language: "eng",
    catalogue_date: { year, raw: `${year}-01-01`, method: "exact" },
    page_date: { year, method: "read_from_front_matter", page_ref: `${item}#1`, line: `ANNUAL REPORT ${year}` },
    date_verified: true,
    date_verification: "catalogue_and_page_agree",
    text,
    text_cut: false,
    details_url: `https://archive.org/details/${item}/page/n${leaf}`,
    image_url: `https://archive.org/download/${item}/page/n${leaf}_medium.jpg`,
    thumb_url: `https://archive.org/download/${item}/page/n${leaf}_thumb.jpg`,
    qr: { size: 21, path: "M4 4h1v1h-1z" },
  };
}

const review = { panel_calibrated: false, reviewer: { model: "m", date: "2026-11-01" }, flags: [], author: null };
const provenance = { drafted_by: "m", prompt_version: "p", drafted_at: "2026-11-01T00:00:00Z", edits: [] };

export const FIXTURE: Deck = {
  format: "exhibit-deck/1",
  deck_id: "test",
  built_at: "2026-11-01T00:00:00Z",
  settings: { dial: [1960, 2018], idle_reset_seconds: 60, offline_image_cache: false, panel_calibrated: false },
  counts: { same_or_not: 1, when_was_this: 1, time_dial: 1 },
  rounds: [
    {
      id: "son-1",
      mode: "same_or_not",
      level: 1,
      collection: "test",
      pages: [
        page("a#3", 1980, "Hospital beds per 1,000 population in general hospitals: 6.9 in 1980."),
        page("b#4", 1981, "Extended care beds per 1,000 persons aged 65 and over: 41.2."),
      ],
      quotes: [
        { id: "a1", page_ref: "a#3", role: "claim", text: "Hospital beds per 1,000 population in general hospitals" },
        { id: "b1", page_ref: "b#4", role: "claim", text: "Extended care beds per 1,000 persons aged 65 and over" },
        { id: "d1", page_ref: "b#4", role: "decisive", text: "per 1,000 persons aged 65 and over" },
      ],
      play: {
        claims: [
          { page_ref: "a#3", quote: "a1", text: { en: "There were 6.9 hospital beds per 1,000 people.", fr: "Il y avait 6,9 lits par 1 000 personnes." } },
          { page_ref: "b#4", quote: "b1", text: { en: "There were 41.2 beds per 1,000 people.", fr: "Il y avait 41,2 lits par 1 000 personnes." } },
        ],
        answer: "not_comparable",
        decisive: ["d1"],
        constraints: { period: "same", jurisdiction: "same", population: "differs", program: "differs", measure: "differs" },
      },
      explanation: { en: "Page B counts beds for people aged 65 and over only.", fr: "La page B ne compte que les 65 ans et plus." },
      explanation_status: "model-drafted",
      status: "model-reviewed",
      review,
      provenance,
    },
    {
      id: "wwt-1",
      mode: "when_was_this",
      level: 1,
      collection: "test",
      pages: [page("c#9", 1975, "Report for 1975-76. A new program for sawmill workers began in the spring.")],
      quotes: [{ id: "c1", page_ref: "c#9", role: "clue", text: "A new program for sawmill workers began in the spring." }],
      play: { year: 1975, label: { en: "A board's report", fr: "Le rapport d'une commission" }, clues: ["c1"], masked_text: [[11, 18]], masked_title: [] },
      explanation: { en: "A new program is described.", fr: "Un nouveau programme est d\u00e9crit." },
      explanation_status: "model-drafted",
      status: "model-reviewed",
      review,
      provenance,
    },
    {
      id: "dial-test",
      mode: "time_dial",
      level: 1,
      collection: "test",
      pages: [page("d#2", 1970, "Smoking is a hazard to health."), page("e#5", 1990, "Smoking in public places is now restricted.")],
      quotes: [
        { id: "y1970q1", page_ref: "d#2", role: "evidence", text: "Smoking is a hazard to health." },
        { id: "y1990q1", page_ref: "e#5", role: "evidence", text: "Smoking in public places is now restricted." },
      ],
      play: {
        question: { en: "What did the record say about smoking?", fr: "Que disent les documents sur le tabac?" },
        question_id: "test",
        jurisdiction: null,
        epochs: [
          { year: 1970, state: "answer", answer: { en: "The 1970 page calls smoking a hazard.", fr: "La page de 1970 dit que le tabac est un danger." }, quotes: ["y1970q1"], pages_by_then: ["d#2"] },
          { year: 1990, state: "answer", answer: { en: "By 1990, smoking in public places is restricted.", fr: "En 1990, fumer en public est restreint." }, quotes: ["y1990q1"], pages_by_then: ["d#2", "e#5"] },
        ],
        years: [
          { year: 1960, state: "not_indexed", items: null },
          { year: 1970, state: "recorded", items: 3 },
          { year: 1971, state: "quiet", items: 0 },
        ],
        collection_period: [1963, 2018],
      },
      explanation: { en: "", fr: "" },
      explanation_status: "model-drafted",
      status: "model-reviewed",
      review,
      provenance,
    },
  ],
  gap_hunt: {
    decades: [1960, 1970],
    jurisdictions: ["ontario", "nunavut"],
    cells: [
      { place: "ontario", iso: "CA-ON", decade: 1960, catalogue_items: 1698, indexed_items: 120, state: "recorded" },
      { place: "ontario", iso: "CA-ON", decade: 1970, catalogue_items: 3286, indexed_items: 0, state: "not_indexed" },
      { place: "nunavut", iso: "CA-NU", decade: 1960, catalogue_items: 0, indexed_items: 0, state: "quiet_examined" },
      { place: "nunavut", iso: "CA-NU", decade: 1970, catalogue_items: 0, indexed_items: 0, state: "quiet_examined" },
    ],
    indexed_collections: { test: [1963, 2018] },
    catalogue: { fetched_at: "2026-11-01T00:00:00Z", method: "m", total: 104529 },
    unknown_place_indexed: 5,
  },
};
