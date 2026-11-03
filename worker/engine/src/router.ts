// The cross-shard router: one question over the whole collection (docs/formats/shards.md, "Router
// index"). Kept free of runtime-only imports so the tests can run it under Node.
//
// choose() reads only the router index on R2 (scripts/v2/router_index.py), never an engine: a served
// shard is eligible when its places and years can satisfy the question's filters and at least one of
// the question's words occurs in it; eligible shards are ranked by how much of the question's
// evidence they hold, and at most max_engines are woken. A shard left out is reported with why, so an
// answer can say what it did not search: not searched is never "not in the archive".
//
// merge() takes each woken engine's candidates. BM25 from different engines does not compare (each
// engine's idf comes from its own passages), so each candidate carries its counts of the question's
// words and its length, and merge() scores it again with the collection's N, document frequencies and
// average length over the served shards. A port of src/archive_debugger/shards/router.py; the
// tokenizer matches src/archive_debugger/shards/coverage.py terms().
import { ENGINE_CONFIG, STOPWORDS, scopeServed } from "./config";

export const RRF_K = 60;
const K1 = 1.2;
const B = 0.75;
const WORD = /[\p{L}\p{N}]+/gu;     // Python's [^\W_]+ with re.UNICODE: letters and numbers, no underscore

export interface CollectionConfig {
  scope: string;
  label: string;
  max_engines: number;
  top_k: number;
  pool_size: number;
  provider: string;
  model: string;
  parts?: string[];   // collections served before the shards, always part of the whole collection
}

export const COLLECTION: CollectionConfig | null = (ENGINE_CONFIG as any).collection ?? null;

/** The scopes the whole collection searches here: its always-served parts (the collections served
 *  before the shards) and every shard SHARDS names. */
export function collectionScopes(shards: string | undefined): string[] {
  if (!COLLECTION) return [];
  const parts = (COLLECTION.parts ?? []).filter((s) => s in ENGINE_CONFIG.scopes);
  const served = Object.keys(ENGINE_CONFIG.scopes).filter((s) => ENGINE_CONFIG.scopes[s].shard && scopeServed(s, shards));
  return [...parts, ...served];
}

/** Whether this deployment serves the whole-collection scope: it does wherever it has a part or SHARDS
 *  names at least one shard the generated config knows. */
export function collectionServed(shards: string | undefined): boolean {
  return collectionScopes(shards).length > 0;
}

export function isCollection(scope: string): boolean {
  return COLLECTION !== null && scope === COLLECTION.scope;
}

/** The question's (or a passage's) BM25 terms: lower-cased words, the frozen stopwords removed. */
export function terms(text: string): string[] {
  const out: string[] = [];
  for (const m of (text || "").matchAll(WORD)) {
    const w = m[0].toLowerCase();
    if (!STOPWORDS.has(w)) out.push(w);
  }
  return out;
}

/** FNV-1a, 32 bit, over the term's UTF-8 bytes: the router index's bucket hash (same as Python's). */
export function fnv1a(term: string): number {
  let h = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(term)) {
    h = Math.imul((h ^ byte) >>> 0, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

export function bucketName(term: string, buckets: number): string {
  return String(fnv1a(term) % buckets).padStart(4, "0");
}

export interface ShardCoverage {
  jurisdictions: string[];
  years: Record<string, number>;
  passages: number;
  tokens: number;
  tier?: string | null;
}

export interface RouterPointer {
  format: number;
  digest: string;
  prefix: string;
  buckets: number;
  N: number;
  tokens: number;
  avgdl: number;
  shards: Record<string, ShardCoverage>;
}

/** {term: {shard: df}} for the question's terms. */
export type TermDf = Record<string, Record<string, number>>;

export interface Stats {
  N: number;
  avgdl: number;
  df: Record<string, number>;
}

export interface Choice {
  shard: string;
  score: number;
  reason: string;
}

export interface Filters {
  jurisdiction?: string | null;
  firstYear?: number | null;
  lastYear?: number | null;
  undated?: boolean;
}

/** The shards of the index this deployment serves (SHARDS), and which served shards the index
 *  does not hold yet. */
export function servedInIndex(pointer: RouterPointer, shards: string | undefined): { shards: string[]; missing: string[] } {
  const served = collectionScopes(shards);
  return {
    shards: served.filter((s) => s in pointer.shards),
    missing: served.filter((s) => !(s in pointer.shards)),
  };
}

export function globalStats(pointer: RouterPointer, shards: string[], termDf: TermDf): Stats {
  let n = 0;
  let tokens = 0;
  for (const s of shards) {
    n += pointer.shards[s].passages;
    tokens += pointer.shards[s].tokens;
  }
  const df: Record<string, number> = {};
  for (const [term, byShard] of Object.entries(termDf)) {
    df[term] = shards.reduce((sum, s) => sum + (byShard[s] ?? 0), 0);
  }
  return { N: n, avgdl: n ? tokens / n : 0, df };
}

export function idf(term: string, stats: Stats): number {
  const df = stats.df[term] ?? 0;
  return Math.log(1 + (stats.N - df + 0.5) / (df + 0.5));
}

function yearOk(cov: ShardCoverage, f: Filters): boolean {
  for (const [key, n] of Object.entries(cov.years)) {
    if (n <= 0) continue;
    const bar = key.indexOf("|");
    const place = key.slice(0, bar);
    const year = key.slice(bar + 1);
    if (f.jurisdiction && place !== f.jurisdiction) continue;
    if (year === "undated") {
      if (f.undated || (f.firstYear == null && f.lastYear == null)) return true;
      continue;
    }
    const y = Number.parseInt(year, 10);
    if ((f.firstYear == null || y >= f.firstYear) && (f.lastYear == null || y <= f.lastYear)) return true;
  }
  return false;
}

/** [chosen, leftOut]: which served shards to wake, and why every other one was not. */
export function choose(question: string, pointer: RouterPointer, shards: string[], termDf: TermDf, f: Filters,
                       maxEngines: number): [Choice[], Choice[]] {
  const q = [...new Set(terms(question))];
  const stats = globalStats(pointer, shards, termDf);
  const eligible: Choice[] = [];
  const left: Choice[] = [];
  for (const shard of shards) {
    const cov = pointer.shards[shard];
    if (f.jurisdiction && !cov.jurisdictions.includes(f.jurisdiction)) {
      left.push({ shard, score: 0, reason: "other jurisdictions" });
      continue;
    }
    if (!yearOk(cov, f)) {
      left.push({ shard, score: 0, reason: "no documents in the period" });
      continue;
    }
    const score = q.reduce((sum, t) => sum + (termDf[t]?.[shard] ?? 0) * idf(t, stats), 0);
    if (score <= 0) {
      left.push({ shard, score: 0, reason: "none of the question's words occur in it" });
      continue;
    }
    eligible.push({ shard, score: score / Math.sqrt(Math.max(1, cov.passages)), reason: "holds the question's words" });
  }
  eligible.sort((a, b) => b.score - a.score || (a.shard < b.shard ? -1 : 1));
  for (const c of eligible.slice(maxEngines)) left.push({ ...c, reason: "ranked below the engines woken" });
  return [eligible.slice(0, maxEngines), left];
}

export function bm25(tf: Record<string, number>, dl: number, q: string[], stats: Stats): number {
  const avg = stats.avgdl || 1;
  let score = 0;
  for (const t of q) {
    const n = tf[t] ?? 0;
    if (!n) continue;
    score += idf(t, stats) * (n * (K1 + 1)) / (n + K1 * (1 - B + (B * dl) / avg));
  }
  return score;
}

export interface Candidate {
  passage_id: string;
  tf?: Record<string, number>;
  dl?: number;
  dense?: number | null;
  [field: string]: unknown;
}

export interface Merged extends Candidate {
  shard: string;
  bm25: number;
  rrf: number;
  bm25_rank: number | null;
  dense_rank: number | null;
}

/** The fused top passages over every woken engine, each with its shard, collection-wide BM25 and ranks. */
export function merge(question: string, hitsByShard: Record<string, Candidate[]>, stats: Stats, topK: number): Merged[] {
  const q = [...new Set(terms(question))];
  const rows: (Candidate & { shard: string; bm25: number })[] = [];
  for (const [shard, hits] of Object.entries(hitsByShard)) {
    for (const h of hits) rows.push({ ...h, shard, bm25: bm25(h.tf ?? {}, Number(h.dl ?? 0), q, stats) });
  }
  const byId = (a: { passage_id: string }, b: { passage_id: string }) => (a.passage_id < b.passage_id ? -1 : a.passage_id > b.passage_id ? 1 : 0);
  const byBm25 = rows.filter((r) => r.bm25 > 0).sort((a, b) => b.bm25 - a.bm25 || byId(a, b));
  const byDense = rows.filter((r) => r.dense != null).sort((a, b) => Number(b.dense) - Number(a.dense) || byId(a, b));
  const fused = new Map<string, { row: (typeof rows)[number]; score: number; br: number | null; dr: number | null }>();
  byBm25.forEach((r, i) => {
    const e = fused.get(r.passage_id) ?? { row: r, score: 0, br: null, dr: null };
    e.score += 1 / (RRF_K + i + 1);
    e.br = i + 1;
    fused.set(r.passage_id, e);
  });
  byDense.forEach((r, i) => {
    const e = fused.get(r.passage_id) ?? { row: r, score: 0, br: null, dr: null };
    e.score += 1 / (RRF_K + i + 1);
    e.dr = i + 1;
    fused.set(r.passage_id, e);
  });
  return [...fused.values()]
    .sort((a, b) => b.score - a.score || byId(a.row, b.row))
    .slice(0, topK)
    .map((e) => ({ ...e.row, rrf: Math.round(e.score * 1e6) / 1e6, bm25_rank: e.br, dense_rank: e.dr }));
}

/** The router's filters from an /ask request's: a place, and a year range from year_from/year_to, a
 *  decade period ("1980s") or as_of_year. */
export function routerFilters(filters: Record<string, string> | null): Filters {
  const f: Filters = {};
  if (!filters) return f;
  if (filters.jurisdiction) f.jurisdiction = filters.jurisdiction;
  const decade = /^(\d{4})s$/.exec(filters.period ?? "");
  if (decade) {
    f.firstYear = Number(decade[1]);
    f.lastYear = Number(decade[1]) + 9;
  }
  const from = Number.parseInt(filters.year_from ?? "", 10);
  const to = Number.parseInt(filters.year_to ?? filters.as_of_year ?? "", 10);
  if (Number.isFinite(from)) f.firstYear = from;
  if (Number.isFinite(to)) f.lastYear = to;
  return f;
}

/** Parse the bucket files' lines for the wanted terms into {term: {shard: df}}. */
export function parseBuckets(bodies: string[], wanted: Set<string>): TermDf {
  const out: TermDf = {};
  for (const body of bodies) {
    for (const line of body.split("\n")) {
      const tab = line.indexOf("\t");
      if (tab < 0) continue;
      const term = line.slice(0, tab);
      if (!wanted.has(term)) continue;
      const byShard: Record<string, number> = {};
      for (const part of line.slice(tab + 1).split(",")) {
        const colon = part.lastIndexOf(":");
        if (colon > 0) byShard[part.slice(0, colon)] = Number(part.slice(colon + 1));
      }
      out[term] = byShard;
    }
  }
  return out;
}

// --- the R2 reads, cached in this isolate -----------------------------------------------------------

const POINTER_KEY = "router/v1/shards.json";
const POINTER_TTL_MS = 300_000;
const BUCKET_CACHE_MAX = 512;
let pointerCache: { at: number; value: RouterPointer | null } | null = null;
const bucketCache = new Map<string, string>();

export function resetRouterCache(): void {
  pointerCache = null;
  bucketCache.clear();
}

export async function loadPointer(data: R2Bucket, now = Date.now()): Promise<RouterPointer | null> {
  if (pointerCache && now - pointerCache.at < POINTER_TTL_MS) return pointerCache.value;
  const obj = await data.get(POINTER_KEY);
  const value = obj ? ((await obj.json()) as RouterPointer) : null;
  pointerCache = { at: now, value };
  return value;
}

export async function loadTermDf(data: R2Bucket, pointer: RouterPointer, question: string): Promise<TermDf> {
  const wanted = new Set(terms(question));
  const names = [...new Set([...wanted].map((t) => bucketName(t, pointer.buckets)))];
  const bodies = await Promise.all(names.map(async (name) => {
    const key = `${pointer.prefix}/df/${name}.tsv`;
    const cached = bucketCache.get(key);
    if (cached !== undefined) return cached;
    const obj = await data.get(key);
    const body = obj ? await obj.text() : "";
    if (bucketCache.size >= BUCKET_CACHE_MAX) bucketCache.delete(bucketCache.keys().next().value as string);
    bucketCache.set(key, body);
    return body;
  }));
  return parseBuckets(bodies, wanted);
}

/** The words an answer says about what was and was not searched. */
export const NOT_SEARCHED_NOTE =
  "Shards left out were not searched for this question. That is not the same as the archive not holding an answer.";
