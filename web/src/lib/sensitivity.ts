// The one editable place for all visitor-facing sensitivity copy and its configuration.
// Jacob edits the strings and the per-topic config here; components below only render them.
// Everything is static (no network), so it all works offline (N6).

import type { Flagged } from "../types";

// 1. Entry advisory: persistent, small, shown at app entry.
export const ENTRY_ADVISORY =
  "This tool surfaces Canadian government public-health documents from 1960 to 2009. Some contain " +
  "outdated, inaccurate, or harmful language and reflect the government's position at the time. " +
  "Reader discretion is advised.";

// 2. Contextual note: year-aware, topic-agnostic by default so it never names a specific group
// (the sterilization topic can fire on broader eugenics-era content). [year] from flagged.year.
export function contextualNoteDefault(year: number | null): string {
  const dated = year != null ? ` from ${year}` : "";
  return (
    `This is a government document${dated}. Its language and claims reflect the government's position ` +
    "at the time and may be inaccurate or harmful. Use the timeline to compare it with what the record " +
    "said later. If you need support, help is available below."
  );
}

// Per-topic overrides: add specificity later by mapping a topic key to a note function.
// Empty by default (topic-agnostic). Example:
//   "residential-school-health": (year) => `...`,
export const CONTEXTUAL_NOTE_BY_TOPIC: Record<string, (year: number | null) => string> = {};

export function contextualNote(flagged: Flagged): string {
  for (const topic of flagged.topics) {
    const override = CONTEXTUAL_NOTE_BY_TOPIC[topic];
    if (override) return override(flagged.year);
  }
  return contextualNoteDefault(flagged.year);
}

// 4. Tap-through interstitial: per-topic opt-in. Default ON only for the heaviest topics, so the
// curated demo flow is not over-interrupted; the others get the inline note only.
export const INTERSTITIAL_TOPICS = new Set<string>([
  "residential-school-health",
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

// Union of two backend-computed flagged objects (e.g. the /ask answer's flag and a story's
// pins flag), so the compare's note reflects both the question and the compared documents.
// crisis_lines come pre-mapped from the backend, so this only de-duplicates them; it never
// maps topics to lines itself (that mapping stays solely in flags.py).
export function mergeFlagged(...args: (Flagged | null | undefined)[]): Flagged | null {
  const parts = args.filter(Boolean) as Flagged[];
  if (parts.length === 0) return null;
  const topics = Array.from(new Set(parts.flatMap((p) => p.topics))).sort();
  const years = parts.map((p) => p.year).filter((y): y is number => y != null);
  const lines: Flagged["crisis_lines"] = [];
  for (const p of parts) {
    for (const l of p.crisis_lines) {
      if (!lines.some((x) => x.name === l.name && x.number === l.number)) lines.push(l);
    }
  }
  return { topics, year: years.length ? Math.min(...years) : null, crisis_lines: lines };
}
