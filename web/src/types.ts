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
  offline?: boolean;                // page images come from the offline pack (API path), not archive.org
  ocr_quality?: number | null;      // 0..1 OCR confidence for the passage; a low value means shaky text
  date_method?: string | null;      // how the item's date was resolved: exact | title_extracted | unknown
}

export interface Story {
  id: string;
  question: string;
  filters: Filters;
  caption: string;
  pins: [EvidenceRow, EvidenceRow];
  flagged?: Flagged | null;   // computed on serve over the two pins (the shown basis)
}

/** Present only when the server could not generate an answer (offline, model
 *  unreachable/timeout, rate-limited, or empty input) and returned the record in a
 *  designed limited-mode state instead of a written answer. */
export interface Degraded {
  reason: "no_key" | "model_unreachable" | "rate_limited" | "empty" | string;
  live_url: string;
}

/** Present when the served record touches a harm-adjacent historical topic. Keyed on the
 *  retrieved evidence, so it is set for cached answers, real abstentions, and the limited-mode
 *  state alike. The visitor-facing note is rendered client-side from topics + year. */
export interface Flagged {
  topics: string[];
  year: number | null;
  crisis_lines: { name: string; number: string }[];
}

export interface AskResponse {
  answer: Answer;
  evidence: EvidenceRow[];
  degraded?: Degraded;
  flagged?: Flagged | null;
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

// Real per-scope composition for the sources view, computed live from the scope's own DBs.
export interface OcrDistribution {
  high: number;
  medium: number;
  low: number;
}

export interface JurisdictionShare {
  name: string;
  items: number;
  share: number;   // 0..1 of items
}

export interface Composition {
  passages: number;
  dated_span: YearWindow;   // true MIN/MAX year of dated items
  window: YearWindow;       // config binning window
  undated: { items: number; item_share: number; passages: number; passage_share: number };
  ocr: OcrDistribution;     // passage-weighted bucket counts
  jurisdictions: JurisdictionShare[];
  jurisdiction_unknown_share: number;
  jurisdiction_is_floor: boolean;   // issuer-derived proxy; not full provincial coverage
  date_method: Record<string, number>;   // exact | title_extracted | unknown -> item count
}

// One served corpus for the scope switcher, from GET /scopes. Mirrors api/app.py scope_facts.
export interface ScopeInfo {
  name: string;
  label: string;
  blurb: string;
  collection: string | null;
  collection_url: string | null;
  collections: string[];
  item_count: number;
  window: YearWindow;
  composition?: Composition;
}

export interface ScopesResponse {
  default: string;
  scopes: ScopeInfo[];
}
