// The answer-cache key, the cleaned question and the question's salient terms, exactly as the
// Python engine computes them (src/archive_debugger/api/cache.py, api/app.py clean_question,
// generate/answer.py salient_terms). config/cache_key_vectors.json holds shared test vectors that
// both implementations must reproduce. When this file and the engine ever disagree on an input,
// the only effect is a cache miss here: the request goes to the engine, which keys it itself.

export const KEY_VERSION = 2;
const MAX_QUESTION_CHARS = 500;
const TEXT_FILTERS = ["period", "jurisdiction", "doc_type"] as const;

// Code points Python's str.split() treats as whitespace (str.isspace), as a character class.
const PYTHON_SPACE_CODES = [
  0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680,
  0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a,
  0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
];
const PYTHON_SPACES = new Set(PYTHON_SPACE_CODES);

export type Filters = Record<string, unknown> | null | undefined;

/** NFC, lone surrogates as U+FFFD, every control character (U+0000-U+001F, U+007F) as a space,
 *  runs of spaces collapsed, ends trimmed. Case, punctuation and other spaces are kept. */
export function normalizeQuestion(text: string | null | undefined): string {
  let out = (text ?? "").toWellFormed().normalize("NFC");
  out = out.replace(/[\x00-\x1f\x7f]/g, " ");
  out = out.replace(/ {2,}/g, " ");
  return out.replace(/^ +| +$/g, "");
}

/** The filters the key uses: the three text filters as normalized strings when non-empty, and
 *  min_ocr as a four-decimal string when set and not zero. null when min_ocr is not a number (the
 *  engine would reject it; the Worker then skips its cache and forwards). */
export function canonicalFilters(filters: Filters): Record<string, string> | null {
  const source = filters ?? {};
  const out: Record<string, string> = {};
  for (const name of TEXT_FILTERS) {
    const value = source[name];
    if (value === null || value === undefined) continue;
    const text = normalizeQuestion(String(value));
    if (text) out[name] = text;
  }
  const minOcr = source["min_ocr"];
  if (minOcr !== null && minOcr !== undefined && minOcr !== "" && minOcr !== 0) {
    const number = Number(minOcr);
    if (!Number.isFinite(number)) return null;
    if (number !== 0) out["min_ocr"] = number.toFixed(4);
  }
  return out;
}

/** JSON with sorted keys and no spaces, as Python's json.dumps(sort_keys=True,
 *  separators=(",", ":"), ensure_ascii=False) writes strings and string-keyed objects. */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const entries = Object.keys(value as Record<string, unknown>)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${canonicalJson((value as Record<string, unknown>)[k])}`);
  return `{${entries.join(",")}}`;
}

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** The cache key of one question under one scope context, or null when the filters cannot be
 *  keyed here. */
export async function contentKey(context: string, question: string, filters: Filters): Promise<string | null> {
  const canonical = canonicalFilters(filters);
  if (canonical === null) return null;
  return sha256Hex(
    canonicalJson({ v: String(KEY_VERSION), context, question: normalizeQuestion(question), filters: canonical }),
  );
}

/** The engine's clean_question: control characters except tab, newline and carriage return become
 *  spaces, whitespace runs collapse (Python's definition of whitespace), capped at 500 characters. */
export function cleanQuestion(question: string | null | undefined): string {
  const replaced = (question ?? "").replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, " ");
  const words: string[] = [];
  let current = "";
  for (const ch of replaced) {
    if (PYTHON_SPACES.has(ch.codePointAt(0) ?? 0)) {
      if (current) words.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  if (current) words.push(current);
  return Array.from(words.join(" ")).slice(0, MAX_QUESTION_CHARS).join("");
}

/** The engine's salient_terms: lowercase word tokens that are not stopwords and are at least three
 *  characters long or a four-digit number, first occurrence first. */
export function salientTerms(question: string, stopwords: ReadonlySet<string>): string[] {
  const out: string[] = [];
  for (const token of question.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []) {
    if (stopwords.has(token)) continue;
    const length = Array.from(token).length;
    const year = /^\p{Nd}+$/u.test(token) && length === 4;
    if ((length >= 3 || year) && !out.includes(token)) out.push(token);
  }
  return out;
}

type Coverage = Record<string, unknown> & {
  terms_withheld?: { salient_count: number; uncovered_index: number[] };
};

/** Put the asker's question terms back into a stored row whose coverage block withheld them (a
 *  visitor's row). Returns false, changing nothing, when the count does not match. */
export function restoreTerms(response: { answer?: { coverage?: Coverage } }, salient: string[]): boolean {
  const coverage = response.answer?.coverage;
  if (!coverage || !coverage.terms_withheld) return true;
  const withheld = coverage.terms_withheld;
  if (withheld.salient_count !== salient.length) return false;
  coverage.salient_terms = [...salient];
  coverage.uncovered_terms = (withheld.uncovered_index ?? [])
    .filter((i) => i >= 0 && i < salient.length)
    .map((i) => salient[i]);
  delete coverage.terms_withheld;
  return true;
}
