// Single source of truth for the plain-language term definitions shown by the Term toggletip
// (components/Term.tsx). ASCII only, one or two short sentences each, written to match what the code
// actually does, not to sound good. Extend this map to gloss more terms; the toggletip reads only
// from here, so a term with no entry renders as plain text with no toggle.

export interface GlossaryEntry {
  /** The canonical term. Used as the visible label and accessible name when no child text is given. */
  term: string;
  /** One or two plain sentences. Keep accurate to the behavior described elsewhere in the app. */
  definition: string;
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  ocr: {
    term: "OCR",
    definition:
      "The computer's reading of a scanned page's text. It can misread, so the scan is always one click away.",
  },
  "ocr-quality": {
    term: "OCR quality",
    definition:
      "How cleanly the text was read, estimated from simple signals. Low-quality pages rank lower but are never hidden.",
  },
  passage: {
    term: "passage",
    definition:
      "A short chunk of a page's text, the unit the tool searches and cites. Each one links back to its page.",
  },
  undated: {
    term: "undated",
    definition: "No reliable date in the catalogue or the title. The tool never guesses one.",
  },
  jurisdiction: {
    term: "jurisdiction",
    definition:
      "Worked out from who published the item, so the counts are a minimum, not full coverage.",
  },
  "dated-span": {
    term: "dated span",
    definition:
      "The earliest and latest catalogue dates. A few items fall outside the main window, and catalogue dates may not match the publication year.",
  },
  "lexical-matches": {
    term: "lexical matches",
    definition:
      "Passages that contain the word, whether or not they are actually about your question.",
  },
};

/** The glossary entry for a key, or null when the key is not defined (the toggletip then renders the
 *  visible text as plain, non-interactive text). */
export function glossaryEntry(key: string): GlossaryEntry | null {
  return GLOSSARY[key] ?? null;
}
