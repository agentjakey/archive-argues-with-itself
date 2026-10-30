// How the site recognizes a seed or story question in a typed or linked question: the same
// normalization the engine uses for its cache key (src/archive_debugger/api/cache.py,
// worker/engine/src/key.ts), checked against the shared vectors in config/cache_key_vectors.json.
import type { Filters } from "../types";

const TEXT_FILTERS = ["period", "jurisdiction", "doc_type"] as const;

/** Lone UTF-16 surrogates become U+FFFD (String.prototype.toWellFormed, written out). */
function wellFormed(text: string): string {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = i + 1 < text.length ? text.charCodeAt(i + 1) : 0;
      if (next >= 0xdc00 && next <= 0xdfff) {
        out += text[i] + text[i + 1];
        i++;
      } else {
        out += String.fromCharCode(0xfffd);
      }
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      out += String.fromCharCode(0xfffd);
    } else {
      out += text[i];
    }
  }
  return out;
}

/** NFC, control characters as spaces, runs of spaces collapsed, ends trimmed. */
export function normalizeQuestion(text: string | null | undefined): string {
  let out = wellFormed(text ?? "").normalize("NFC");
  out = out.replace(/[\x00-\x1f\x7f]/g, " ");
  out = out.replace(/ {2,}/g, " ");
  return out.replace(/^ +| +$/g, "");
}

/** The text filters as normalized strings when non-empty, min_ocr as four decimals when set. */
export function canonicalFilters(filters: Filters | Record<string, unknown> | null | undefined): Record<string, string> | null {
  const source = (filters ?? {}) as Record<string, unknown>;
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

export function sameFilters(a: Record<string, string> | null, b: Record<string, string> | null): boolean {
  if (a === null || b === null) return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every((k) => a[k] === b[k]);
}
