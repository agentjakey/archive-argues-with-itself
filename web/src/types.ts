// API contracts. Mirrors src/archive_debugger/api/app.py and api/coverage.py exactly.

export type Period =
  | "pre-1960"
  | "1960s"
  | "1970s"
  | "1980s"
  | "1990s"
  | "2000s"
  | "post-2009"
  | "undated";
export type Jurisdiction = "federal" | "ontario" | "alberta" | "international" | "unknown";
export type DocType =
  | "royal_commission"
  | "commission"
  | "annual_report"
  | "statistical_report"
  | "standing_committee"
  | "board_or_appeal"
  | "other"
  | "unknown";

export interface Filters {
  period?: Period;
  jurisdiction?: Jurisdiction;
  doc_type?: DocType;
  min_ocr?: number;
}

export interface AskRequest {
  question: string;
  filters?: Filters;
  provider?: "stub" | "anthropic";
  model?: string;
  nocache?: boolean;
}

export interface Sentence {
  text: string;
  cited_ids: string[];
}

export interface Citation {
  passage_id: string;
  item_id: string;
  leaf_index: number;
  printed_page: string | null;
  deep_link: string;
}

export interface Unsupported {
  text: string;
  cited_ids: string[];
  reason: string;
}

export interface Coverage {
  n_items: number;
  n_passages: number;
  n_undated: number;
  periods: Record<string, number>;
  jurisdictions: Record<string, number>;
  salient_terms: string[];
  uncovered_terms: string[];
  single_source: boolean;
}

export interface Generation {
  provider: string;
  model: string;
  temperature: number | null;
  prompt_sha256: string;
  max_tokens: number;
  top_k: number;
}

export interface Answer {
  text: string;
  sentences: Sentence[];
  verified_citations: Citation[];
  unsupported: Unsupported[];
  abstained: boolean;
  coverage: Coverage;
  abstention_text: string | null;
  generation: Generation;
  cached?: { created_at: string } | null;
}

export interface EvidenceRow {
  passage_id: string;
  item_id: string;
  title: string | null;
  year: number | null;
  decade: string | null;
  jurisdiction: string | null;
  doc_type: string | null;
  leaf_index: number;
  printed_page: string | null;
  deep_link: string;
  page_thumb: string;
  page_image: string;
  embed_url: string;
  snippet: string;
  bm25_rank: number | null;
  dense_rank: number | null;
  cited: boolean;
  in_prompt: boolean;               // false for pool rows the model never saw
  section_class: "front" | "body" | "back" | string;
  later_years: number[] | null;     // years in the text later than the item year + 1
}

export interface AskResponse {
  answer: Answer;
  evidence: EvidenceRow[];
}

export interface Example {
  qid: string;
  text: string;
  filters: Filters;
  gold: "answerable" | "abstain" | null;
}

export interface YearWindow {
  min_year: number | null;
  max_year: number | null;
}

export interface CorpusFacts {
  items: number;
  passages: number;
  passages_undated: number;
  undated_share: number;
  window: YearWindow;        // true dated span
  pilot_window: YearWindow;  // config binning window
}

export interface Health {
  status: "ok";
  provider: string;
  model: string;
  corpus: CorpusFacts;
}

export interface DecadeCoverage {
  decade: string;
  items: number;
  passages: number;
  undated_passages: number;
  matched: number;                 // passages matching ANY salient term
  terms: Record<string, number>;   // passages matching each term
}

export interface JurisdictionCoverage {
  jurisdiction: string;
  passages: number;
  terms: Record<string, number>;
}

export interface CoverageResponse {
  salient_terms: string[];
  by_decade: DecadeCoverage[];
  by_jurisdiction: JurisdictionCoverage[];
}
