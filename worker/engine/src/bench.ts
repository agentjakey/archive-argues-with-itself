// Staging only: how fast the Worker can read one stored answer from D1, KV and R2, so the answer
// cache's home is chosen from measurements (docs/v2/DECISIONS.md). The route exists only where the
// BENCH_KV and BENCH_R2 bindings do (the staging environment); production has neither and answers
// 404. It copies one curated row's stored body into KV and R2 under the same key, then times
// sequential reads of that one key from each store inside the Worker, where a visitor's request
// pays for them. Nothing about a visitor is read or written.
import { isKey, readRow } from "./cache";
import type { Env } from "./config";

export interface BenchBindings {
  BENCH_KV?: KVNamespace;
  BENCH_R2?: R2Bucket;
}

const MAX_READS = 50;

export interface Timing {
  reads: number;
  first_ms: number;
  p50_ms: number;
  p95_ms: number;
  max_ms: number;
  bytes: number;
}

export function summarize(samples: number[], bytes: number): Timing {
  const sorted = [...samples].sort((a, b) => a - b);
  const at = (q: number) => sorted[Math.min(sorted.length - 1, Math.ceil(q * sorted.length) - 1)];
  return {
    reads: samples.length,
    first_ms: samples[0],
    p50_ms: at(0.5),
    p95_ms: at(0.95),
    max_ms: sorted[sorted.length - 1],
    bytes,
  };
}

async function timed(read: () => Promise<number>, reads: number): Promise<Timing> {
  const samples: number[] = [];
  let bytes = 0;
  for (let i = 0; i < reads; i++) {
    const t0 = performance.now();
    bytes = await read();
    samples.push(performance.now() - t0);
  }
  return summarize(samples, bytes);
}

/** Time `reads` reads of the curated row `key` from each store. Null when the bindings are absent. */
export async function benchCacheStores(env: Env & BenchBindings, key: string, reads: number): Promise<Record<string, unknown> | null> {
  const kv = env.BENCH_KV;
  const r2 = env.BENCH_R2;
  if (!kv || !r2) return null;
  if (!isKey(key)) return { error: "key must be a stored answer's sha256 key" };
  const row = await readRow(env.DB, key);
  if (!row || !row.curated) return { error: "no curated row with that key" };
  const body = String(row.response_json);
  const objectKey = `answers/${key}.json`;
  if ((await kv.get(key)) === null) await kv.put(key, body);
  if ((await r2.head(objectKey)) === null) await r2.put(objectKey, body, { httpMetadata: { contentType: "application/json" } });
  const n = Math.max(1, Math.min(MAX_READS, reads));
  const d1 = await timed(async () => String((await readRow(env.DB, key))?.response_json ?? "").length, n);
  const kvTiming = await timed(async () => ((await kv.get(key)) ?? "").length, n);
  const r2Timing = await timed(async () => ((await (await r2.get(objectKey))?.text()) ?? "").length, n);
  return { key, colo: null, d1, kv: kvTiming, r2: r2Timing };
}
