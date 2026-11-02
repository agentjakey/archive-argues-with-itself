// The cross-shard router's port (src/router.ts) against the Python router's own results on the same
// inputs (tests/fixtures/router_parity.json, written by tests/fixtures/make_router_parity.py), and
// the whole-collection scope's gating and flow with fake engines.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { readAsk } from "../src/ask";
import { askCollection } from "../src/collection";
import { ENGINE_CONFIG, SCOPES } from "../src/config";
import {
  COLLECTION, bucketName, choose, collectionServed, fnv1a, globalStats, merge, parseBuckets, resetRouterCache, terms,
  type RouterPointer, type TermDf,
} from "../src/router";

const parity = JSON.parse(readFileSync(new URL("../../../tests/fixtures/router_parity.json", import.meta.url), "utf-8"));

function pointerFrom(coverages: any[]): { pointer: RouterPointer; termDf: TermDf; shards: string[] } {
  const shards: RouterPointer["shards"] = {};
  const termDf: TermDf = {};
  for (const c of coverages) {
    shards[c.shard_id] = { jurisdictions: c.jurisdictions, years: c.years, passages: c.passages, tokens: c.tokens };
    for (const [t, df] of Object.entries(c.df as Record<string, number>)) (termDf[t] ??= {})[c.shard_id] = df;
  }
  const n = coverages.reduce((s, c) => s + c.passages, 0);
  const tokens = coverages.reduce((s, c) => s + c.tokens, 0);
  return { pointer: { format: 1, digest: "d", prefix: "router/v1/d", buckets: 16, N: n, tokens, avgdl: tokens / n, shards },
           termDf, shards: coverages.map((c) => c.shard_id) };
}

function fakeData(objects: Map<string, string>): R2Bucket {
  return { get: async (key: string) => objects.has(key)
    ? { json: async () => JSON.parse(objects.get(key)!), text: async () => objects.get(key)! } : null } as unknown as R2Bucket;
}

describe("router port", () => {
  it("hashes terms to buckets as the Python index does", () => {
    // The same values as tests/test_router_index.py HASH_FIXTURES.
    expect(fnv1a("hospital")).toBe(1335678899);
    expect(fnv1a("vaccination")).toBe(2013792114);
    expect(fnv1a("sant" + String.fromCharCode(0xe9))).toBe(994107771);
    expect(fnv1a("")).toBe(2166136261);
    expect(bucketName("hospital", 4096)).toBe(String(1335678899 % 4096).padStart(4, "0"));
  });

  it("tokenizes like shards/coverage.terms()", () => {
    for (const row of parity.terms) expect(terms(row.text)).toEqual(row.terms);
  });

  it("chooses the same shards for the same reasons", () => {
    const { pointer, termDf, shards } = pointerFrom(parity.coverages);
    for (const c of parity.choices) {
      const [chosen, left] = choose(c.question, pointer, shards, termDf,
                                    { jurisdiction: c.filters.jurisdiction, firstYear: c.filters.first_year,
                                      lastYear: c.filters.last_year }, c.max_engines);
      expect(chosen.map((x) => [x.shard, x.reason])).toEqual(c.chosen.map((x: any[]) => [x[0], x[2]]));
      chosen.forEach((x, i) => expect(x.score).toBeCloseTo(c.chosen[i][1], 6));
      expect(left.map((x) => [x.shard, x.reason]).sort()).toEqual(c.left);
    }
  });

  it("merges with collection-wide BM25 as the Python router does", () => {
    const { pointer, termDf, shards } = pointerFrom(parity.coverages);
    const stats = globalStats(pointer, shards, termDf);
    const merged = merge(parity.merge.question, parity.merge.hits, stats, 10);
    expect(merged.map((m) => [m.passage_id, m.shard, m.rrf, m.bm25_rank])).toEqual(
      parity.merge.result.map((r: any[]) => [r[0], r[1], r[3], r[4]]));
    merged.forEach((m, i) => expect(m.bm25).toBeCloseTo(parity.merge.result[i][2], 6));
  });

  it("reads bucket lines for the wanted terms only", () => {
    const got = parseBuckets(["hospital\ts1:3,s2:5\nbeds\ts1:2\n", "x\ts9:1\n"], new Set(["hospital", "x"]));
    expect(got).toEqual({ hospital: { s1: 3, s2: 5 }, x: { s9: 1 } });
  });
});

const shardScopes = SCOPES.filter((s) => ENGINE_CONFIG.scopes[s].shard);

describe("the whole-collection scope", () => {
  const ask = (scope: string) =>
    new Request(`https://x/ask?scope=${scope}`, { method: "POST", body: JSON.stringify({ question: "q" }) });

  it("is served only where SHARDS names a shard, and never from the cache", async () => {
    expect(COLLECTION?.scope).toBe("collection");
    const base = { PUBLIC_MODELS: "", PUBLIC_NOCACHE: "" };
    expect(collectionServed("")).toBe(false);
    expect(await readAsk(ask("collection"), { ...base, SHARDS: "" })).toBeNull();
    const parsed = await readAsk(ask("collection"), { ...base, SHARDS: shardScopes[0] });
    expect(parsed?.input.scope).toBe("collection");
    expect(parsed?.cacheable).toBe(false);
  });

  it("asks the chosen engines for their record, merges, and composes once on the first", async () => {
    resetRouterCache();
    const [s1, s2] = shardScopes;
    const pointer: RouterPointer = { format: 1, digest: "d", prefix: "router/v1/d", buckets: 4096, N: 300, tokens: 30000,
      avgdl: 100, shards: {
        [s1]: { jurisdictions: ["british_columbia"], years: { "british_columbia|1990": 5 }, passages: 100, tokens: 10000 },
        [s2]: { jurisdictions: ["british_columbia"], years: { "british_columbia|2002": 5 }, passages: 200, tokens: 20000 },
      } };
    const DATA = fakeData(new Map<string, string>([["router/v1/shards.json", JSON.stringify(pointer)],
      [`router/v1/d/df/${bucketName("forest", 4096)}.tsv`, `forest\t${s1}:4,${s2}:9\n`],
      [`router/v1/d/df/${bucketName("fire", 4096)}.tsv`, `fire\t${s2}:2\n`]]));
    const calls: { engine: string; path: string; router: string | null; body: any }[] = [];
    const forward = async (engine: string, req: Request) => {
      const body = (await req.json()) as any;
      const path = new URL(req.url).pathname;
      calls.push({ engine, path, router: req.headers.get("x-civic-router"), body });
      if (path === "/ask") {
        const hits = engine === s2
          ? [{ passage_id: "b#1:0", text: "forest fire", item_id: "b", leaf_index: 1, tf: { forest: 1, fire: 1 }, dl: 2 }]
          : [{ passage_id: "a#3:0", text: "forest", item_id: "a", leaf_index: 3, tf: { forest: 1 }, dl: 1 }];
        return Response.json({ evidence_only: true, router: { hits } });
      }
      return Response.json({ answer: { text: "ok", abstained: false },
                             evidence: body.hits.map((h: any) => ({ passage_id: h.passage_id })) });
    };
    const resp = await askCollection({ DATA, SHARDS: `${s1},${s2}`, RELEASE_ID: "t" },
                                     { scope: "collection", question: "forest fire", filters: null }, false, false, forward,
                                     "https://x");
    const out = (await resp.json()) as any;
    expect(resp.status).toBe(200);
    const asks = calls.filter((c) => c.path === "/ask");
    expect(asks.map((c) => c.engine).sort()).toEqual([s1, s2].sort());
    expect(asks.every((c) => c.router === "1" && c.body.evidence_only === true)).toBe(true);
    const compose = calls.filter((c) => c.path === "/compose");
    expect(compose).toHaveLength(1);
    expect(compose[0].engine).toBe(s2);                        // the shard that holds most of the question
    expect(compose[0].body.prompt_ids[0]).toBe("b#1:0");      // both words outrank one
    expect(compose[0].body.hits[0].tf).toBeUndefined();        // the counts stay at the Worker
    expect(out.evidence.find((e: any) => e.passage_id === "b#1:0")).toMatchObject({ shard: s2, tier: ENGINE_CONFIG.scopes[s2].tier });
    expect(out.router.searched.map((r: any) => r.shard).sort()).toEqual([s1, s2].sort());
    expect(out.router.note).toMatch(/not the same as the archive not holding/);
  });

  it("waits, with each engine's state, while a chosen engine wakes", async () => {
    resetRouterCache();
    const [s1] = shardScopes;
    const pointer = { format: 1, digest: "e", prefix: "router/v1/e", buckets: 4096, N: 10, tokens: 100, avgdl: 10,
      shards: { [s1]: { jurisdictions: ["british_columbia"], years: { "british_columbia|1990": 1 }, passages: 10, tokens: 100 } } };
    const DATA = fakeData(new Map<string, string>([["router/v1/shards.json", JSON.stringify(pointer)],
      [`router/v1/e/df/${bucketName("forest", 4096)}.tsv`, `forest\t${s1}:4\n`]]));
    const resp = await askCollection({ DATA, SHARDS: s1, RELEASE_ID: "t" },
                                     { scope: "collection", question: "forest", filters: null }, false, false,
                                     async () => Response.json({ status: "waking", stage: "downloading" }, { status: 503 }),
                                     "https://x");
    expect(resp.status).toBe(503);
    const out = (await resp.json()) as any;
    expect(out.status).toBe("waking");
    expect(out.engines[0]).toMatchObject({ shard: s1, stage: "downloading" });
  });
});
