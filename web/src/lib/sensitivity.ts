// The one editable place for all visitor-facing sensitivity copy and its configuration.
// Jacob edits the strings and the per-topic config here; components below only render them.
// Everything is static (no network), so it all works offline (N6).

import type { Flagged } from "../types";

// 1. Entry advisory: persistent, small, shown at app entry.
// The compact, always-visible one-liner; the full advisory below is the expandable "why".
export const ENTRY_ADVISORY_SHORT =
  "Reader discretion: some documents carry outdated or harmful language.";
export const ENTRY_ADVISORY =
  "This tool surfaces Canadian government public-health documents. Some contain " +
  "outdated, inaccurate, or harmful language and reflect the government's position at the time. " +
  "Reader discretion is advised.";

// 2. Contextual note, in three proportionate care tiers (mirrors src/archive_debugger/flags.py
// TIERS). The tier decides the note copy AND whether crisis lines show: only Tier A maps to crisis
// resources (backend crisis.py), so a Tier B/C result renders its note with no crisis line, and
// neither of those notes references "help below". A result touching more than one tier takes the
// heaviest (A > B > C). Warn precisely and calmly: crisis lines belong only on the heaviest topics.
export const TIER_A_TOPICS = new Set<string>([
  "residential-school-health",
  "coerced-sterilization",             // generic: interstitial + note + 9-8-8 (no attribution notice)
  "coerced-sterilization-indigenous",  // upgraded when the record shows Indigenous context: full treatment
  "tainted-blood-krever",
  "early-hiv-aids",
]);
export const TIER_B_TOPICS = new Set<string>([
  "sterilization-reproductive",
  "sexual-content-minors",
]);
export const TIER_C_TOPICS = new Set<string>([
  "immunization-guidance",
  "hepatitis-transmission",
]);

export type CareTier = "A" | "B" | "C";

/** The heaviest care tier present among the flagged topics, or null when none is a known tier.
 *  A crisis topic (A) always outranks a lighter one, so a result that touches both still gets the
 *  crisis treatment and its crisis lines. */
export function careTier(flagged: Flagged | null | undefined): CareTier | null {
  if (!flagged) return null;
  if (flagged.topics.some((t) => TIER_A_TOPICS.has(t))) return "A";
  if (flagged.topics.some((t) => TIER_B_TOPICS.has(t))) return "B";
  if (flagged.topics.some((t) => TIER_C_TOPICS.has(t))) return "C";
  return null;
}

// Tier A (crisis care): year-aware, topic-agnostic so it never names a specific group. Its support
// lines render beneath it (crisis_lines is non-empty for Tier A), so it closes with "help below".
export function contextualNoteDefault(year: number | null): string {
  const dated = year != null ? ` from ${year}` : "";
  return (
    `This is a government document${dated}. Its language and claims reflect the government's position ` +
    "at the time and may be inaccurate or harmful. Use the timeline to compare it with what the record " +
    "said later. If you need support, help is available below."
  );
}

// Tier B (calm historical-content note, no crisis line): sensitive or outdated content that does not
// warrant crisis resources. No alarm, no reference to support below.
export function historicalContentNote(year: number | null): string {
  const dated = year != null ? ` from ${year}` : "";
  return (
    `This is a government document${dated}. Its language or framing reflects attitudes of its time, ` +
    "and some of it is sensitive or outdated. It is shown here unaltered, as part of the record."
  );
}

// Tier C (not current medical advice, no crisis line): health guidance a visitor could mistake for
// current advice. Copy per the project owner's proposed wording (revisable), made year-aware like
// the others.
export function medicalAdviceNote(year: number | null): string {
  const dated = year != null ? ` from ${year}` : "";
  return (
    `This is a historical record${dated}, not current medical advice. Health guidance changes over ` +
    "time, so rely on a current source or a professional for any health decision."
  );
}

// Per-topic overrides: add specificity later by mapping a topic key to a note function. Empty by
// default (topic-agnostic). An override, when present, wins over the tier note. Example:
//   "residential-school-health": (year) => `...`,
export const CONTEXTUAL_NOTE_BY_TOPIC: Record<string, (year: number | null) => string> = {};

export function contextualNote(flagged: Flagged): string {
  for (const topic of flagged.topics) {
    const override = CONTEXTUAL_NOTE_BY_TOPIC[topic];
    if (override) return override(flagged.year);
  }
  const tier = careTier(flagged);
  if (tier === "B") return historicalContentNote(flagged.year);
  if (tier === "C") return medicalAdviceNote(flagged.year);
  return contextualNoteDefault(flagged.year);   // Tier A, and the defensive null fallback
}

// 4. Tap-through interstitial: per-topic opt-in. Default ON only for the heaviest topics, so the
// curated demo flow is not over-interrupted; the others get the inline note only.
export const INTERSTITIAL_TOPICS = new Set<string>([
  "residential-school-health",
  "coerced-sterilization",             // both coerced-sterilization variants carry the interstitial
  "coerced-sterilization-indigenous",
]);

export function needsInterstitial(flagged: Flagged | null | undefined): boolean {
  return !!flagged && flagged.topics.some((t) => INTERSTITIAL_TOPICS.has(t));
}

export const INTERSTITIAL_COPY = {
  eyebrow: "Before you continue",
  heading: "This result includes difficult historical content",
  body:
    "The document behind this result reflects the government's position at the time and may be " +
    "inaccurate or harmful. Take a moment before you continue.",
  continueLabel: "Continue",
  backLabel: "Go back",
};

// 5. OCR badge: shown when a row's ocr_quality is present and below this threshold.
export const OCR_THRESHOLD = 0.8;
export const OCR_BADGE_LABEL = "OCR uncertain";
export const OCR_BADGE_TITLE = "This line was read by OCR with low confidence and may contain errors.";

export function ocrUncertain(ocr: number | null | undefined): boolean {
  return typeof ocr === "number" && ocr < OCR_THRESHOLD;
}

// 4b. Attribution-incomplete notice (CARE-aligned). Shown ALONGSIDE the existing care note and the
// interstitial for records that are about an Indigenous community but were created by the state
// without that community's involvement. It is a FACTUAL claim about the record ("a government record
// about an Indigenous community"), so it is shown only where that is true: residential-school content
// (inherently about Indigenous communities) and the Indigenous VARIANT of coerced sterilization
// (coerced-sterilization-indigenous, upgraded in flags.py only when Indigenous context appears in the
// question, answer, or evidence). The generic "coerced-sterilization" topic is deliberately NOT here,
// so a non-Indigenous eugenics/sterilization result (e.g. a provincial Sexual Sterilization Act and
// institution patients) keeps the interstitial, the note, and 9-8-8 but NOT this notice. It is in the
// spirit of the Local Contexts Attribution Incomplete Notice, but it is the tool's OWN honest
// acknowledgement, NOT an official Notice: real Notices are generated by the holding institution with
// the community through the Local Contexts Hub. It is additive and never alters the record.
export const ATTRIBUTION_TOPICS = new Set<string>([
  "residential-school-health",
  "coerced-sterilization-indigenous",
]);

export function needsAttribution(flagged: Flagged | null | undefined): boolean {
  return !!flagged && flagged.topics.some((t) => ATTRIBUTION_TOPICS.has(t));
}

export const ATTRIBUTION_NOTICE = {
  eyebrow: "Attribution incomplete",
  body:
    "This is a government record about an Indigenous community, created without that community's " +
    "involvement or consent. It is shown here unaltered. Cultural rights and protocols may apply.",
};

// Locked governance statement (final festival wording). Used verbatim in About and in both scopes'
// Gaps care notes, from this one constant so the three can never drift. CARE-aligned and
// Notices-ready, with the plain non-overclaim disclaimer.
export const GOVERNANCE_STATEMENT =
  "This tool is aligned with the CARE Principles for Indigenous Data Governance, and informed by the " +
  "Local Contexts Notices and the First Nations principles of OCAP. It is not community-governed, not " +
  "certified, and has not been reviewed or endorsed by any community. Real governance notices are " +
  "created by the holding institution together with the communities concerned, through the Local " +
  "Contexts Hub. This tool only adds context alongside the record. It never changes the record, and " +
  "it does not speak for any community.";

// 6. Reparative term crosswalk (additive, precision-first, OFF by default). When enabled, a displayed
// EXCERPT containing an unambiguous historical/colonial term may carry a small annotation naming it as
// the record's historical language and the contemporary term. The excerpt text is NEVER rewritten; the
// annotation is the tool's, layered over the unchanged word. Only clear, unambiguous terms are listed.
// Contested or legal/administrative terms (for example "Indian", which is also a legal status and part
// of place and institution names) are deliberately excluded. Enabling this, and the term list, are
// Jake's / IAC's call; see docs/CARE.md.
export const CROSSWALK_ENABLED = false;

export interface CrosswalkTerm {
  pattern: RegExp;      // matched case-insensitively as a whole word
  historical: string;   // the record's own term (shown unchanged)
  contemporary: string; // the unambiguous current term (the tool's annotation)
}

export const COLONIAL_TERM_CROSSWALK: CrosswalkTerm[] = [
  { pattern: /\beskimos?\b/i, historical: "Eskimo", contemporary: "Inuit" },
  { pattern: /\bhalf-breeds?\b/i, historical: "half-breed", contemporary: "Metis" },
];

export interface CrosswalkSegment {
  text: string;
  term: CrosswalkTerm | null;
}

/** Split text into segments, marking spans that exactly match a listed crosswalk term, without ever
 *  altering the matched text. Returns a single plain segment when the crosswalk is disabled or no
 *  listed term is present, so an OFF crosswalk and benign text render identically to the input. The
 *  `enabled` parameter defaults to the module flag and exists so tests can exercise the match logic. */
export function crosswalkSegments(text: string, enabled: boolean = CROSSWALK_ENABLED): CrosswalkSegment[] {
  if (!enabled || !text) return [{ text, term: null }];
  const hits: { start: number; end: number; term: CrosswalkTerm }[] = [];
  for (const term of COLONIAL_TERM_CROSSWALK) {
    const re = new RegExp(term.pattern.source, "gi");
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      hits.push({ start: m.index, end: m.index + m[0].length, term });
      if (m.index === re.lastIndex) re.lastIndex++; // guard against a zero-width match looping
    }
  }
  if (hits.length === 0) return [{ text, term: null }];
  hits.sort((a, b) => a.start - b.start);
  const out: CrosswalkSegment[] = [];
  let last = 0;
  for (const h of hits) {
    if (h.start < last) continue; // skip an overlapping later match
    if (h.start > last) out.push({ text: text.slice(last, h.start), term: null });
    out.push({ text: text.slice(h.start, h.end), term: h.term });
    last = h.end;
  }
  if (last < text.length) out.push({ text: text.slice(last), term: null });
  return out;
}

// Union of two backend-computed flagged objects (e.g. the /ask answer's flag and a story's
// pins flag), so the compare's note reflects both the question and the compared documents.
// crisis_lines come pre-mapped and resolved from the backend (src/archive_debugger/crisis.py via
// flags.py), so this only de-duplicates them by resource key; it never maps topics to lines itself.
export function mergeFlagged(...args: (Flagged | null | undefined)[]): Flagged | null {
  const parts = args.filter(Boolean) as Flagged[];
  if (parts.length === 0) return null;
  const topics = Array.from(new Set(parts.flatMap((p) => p.topics))).sort();
  const years = parts.map((p) => p.year).filter((y): y is number => y != null);
  const lines: Flagged["crisis_lines"] = [];
  for (const p of parts) {
    for (const l of p.crisis_lines) {
      if (!lines.some((x) => x.key === l.key)) lines.push(l);
    }
  }
  return { topics, year: years.length ? Math.min(...years) : null, crisis_lines: lines };
}
