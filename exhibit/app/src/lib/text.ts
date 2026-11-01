// Page text helpers: hiding years on a When Was This? card and marking quoted lines. Matching is on
// letters and digits only, so the scanner's line breaks and punctuation do not hide a quote.

export type Segment = { text: string; kind: "plain" | "mask" | "mark"; quoteId?: string };

export function maskSpans(text: string, spans: [number, number][]): Segment[] {
  const out: Segment[] = [];
  let at = 0;
  for (const [a, b] of [...spans].sort((x, y) => x[0] - y[0])) {
    if (a < at || b > text.length) continue;
    if (a > at) out.push({ text: text.slice(at, a), kind: "plain" });
    out.push({ text: text.slice(a, b), kind: "mask" });
    at = b;
  }
  if (at < text.length) out.push({ text: text.slice(at), kind: "plain" });
  return out;
}

function words(s: string): { word: string; start: number; end: number }[] {
  const out: { word: string; start: number; end: number }[] = [];
  const re = /[\p{L}\p{N}]+/gu;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    const folded = m[0].normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    out.push({ word: folded, start: m.index, end: m.index + m[0].length });
  }
  return out;
}

// Character spans in `text` where each quote's words appear in order.
export function findQuote(text: string, quote: string): [number, number] | null {
  const hay = words(text);
  const needle = words(quote).map((w) => w.word);
  if (needle.length === 0) return null;
  outer: for (let i = 0; i + needle.length <= hay.length; i++) {
    for (let j = 0; j < needle.length; j++) {
      if (hay[i + j].word !== needle[j]) continue outer;
    }
    return [hay[i].start, hay[i + needle.length - 1].end];
  }
  return null;
}

// Segments with marks for quotes and masks for years. A mask wins over a mark where they overlap.
export function segment(text: string, marks: { id: string; quote: string }[], masks: [number, number][]): Segment[] {
  const type = new Array<string | null>(text.length).fill(null);
  for (const m of marks) {
    const span = findQuote(text, m.quote);
    if (!span) continue;
    for (let i = span[0]; i < span[1]; i++) type[i] = "mark:" + m.id;
  }
  for (const [a, b] of masks) for (let i = a; i < Math.min(b, text.length); i++) type[i] = "mask";
  const out: Segment[] = [];
  let start = 0;
  for (let i = 1; i <= text.length; i++) {
    if (i === text.length || type[i] !== type[start]) {
      const t = type[start];
      const piece = text.slice(start, i);
      if (t === null) out.push({ text: piece, kind: "plain" });
      else if (t === "mask") out.push({ text: piece, kind: "mask" });
      else out.push({ text: piece, kind: "mark", quoteId: t.slice(5) });
      start = i;
    }
  }
  return out;
}

export function maskYears(s: string): string {
  return s.replace(/(?<![0-9])(1[89][0-9]{2}|20[0-2][0-9])(\s?[-/]\s?[0-9]{2,4})?(?![0-9])/g, (m) => "\u2588".repeat(Math.min(m.length, 4)));
}

export function score(guess: number, actual: number): number {
  const off = Math.abs(guess - actual);
  return Math.max(0, 100 - off * 10);
}
