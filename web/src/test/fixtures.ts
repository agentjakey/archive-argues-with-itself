import type { Answer, EvidenceRow } from "../types";

export function row(over: Partial<EvidenceRow> = {}): EvidenceRow {
  return {
    passage_id: "itemA#29:0",
    item_id: "itemA",
    title: "Report of the Ontario Tobacco Strategy Steering Committee",
    year: 1985,
    decade: "1980s",
    jurisdiction: "ontario",
    doc_type: "annual_report",
    leaf_index: 29,
    printed_page: "10",
    deep_link: "https://archive.org/details/itemA/page/n29",
    page_thumb: "https://archive.org/download/itemA/page/n29_thumb.jpg",
    page_image: "https://archive.org/download/itemA/page/n29_medium.jpg",
    embed_url: "https://archive.org/embed/itemA#page/n29",
    snippet: "Tobacco prices should be raised to reduce smoking among young people.",
    bm25_rank: 1,
    dense_rank: 3,
    cited: false,
    in_prompt: true,
    section_class: "body",
    later_years: null,
    ...over,
  };
}

export function abstention(over: Partial<Answer> = {}): Answer {
  return {
    text: "the record here is thin: no retrieved passage mentions covid, 2020 (0 of 12 retrieved passages are undated)",
    sentences: [],
    verified_citations: [],
    unsupported: [],
    abstained: true,
    coverage: {
      n_items: 4,
      n_passages: 12,
      n_undated: 0,
      periods: { "1980s": 7, "2000s": 5 },
      jurisdictions: { federal: 7, ontario: 5 },
      salient_terms: ["public", "health", "covid", "pandemic", "2020"],
      uncovered_terms: ["covid", "2020"],
      single_source: false,
    },
    abstention_text: "the record here is thin: no retrieved passage mentions covid, 2020 (0 of 12 retrieved passages are undated)",
    generation: {
      provider: "stub",
      model: "m",
      temperature: null,
      prompt_sha256: "0".repeat(64),
      max_tokens: 2048,
      top_k: 12,
    },
    ...over,
  };
}
