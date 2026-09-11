// Highlights the answer's salient_terms inside a snippet using the same crude
// matching the backend uses for coverage: equal token, plural-stem equal, or a
// shared 5-character prefix for terms of length >= 5.

export interface Segment {
  text: string;
  hit: boolean;
}

const TOKEN = /[\p{L}\p{N}]+/gu;
const PREFIX = 5;

function stem(t: string): string {
  return t.length > 3 && t.endsWith("s") ? t.slice(0, -1) : t;
}

function matches(token: string, terms: string[]): boolean {
  const t = stem(token.toLowerCase());
  return terms.some((term) => {
    const s = stem(term.toLowerCase());
    return t === s || (s.length >= PREFIX && t.slice(0, PREFIX) === s.slice(0, PREFIX));
  });
}

export function highlight(text: string, terms: string[]): Segment[] {
  if (!text) return [];
  if (!terms.length) return [{ text, hit: false }];
  const out: Segment[] = [];
  let last = 0;
  for (const m of text.matchAll(TOKEN)) {
    const start = m.index ?? 0;
    const end = start + m[0].length;
    if (matches(m[0], terms)) {
      if (start > last) out.push({ text: text.slice(last, start), hit: false });
      out.push({ text: m[0], hit: true });
      last = end;
    }
  }
  if (last < text.length) out.push({ text: text.slice(last), hit: false });
  return out;
}
