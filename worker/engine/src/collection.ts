// /ask?scope=collection: one question over the served shards of the whole collection. The Worker
// chooses the shards from the router index on R2, asks each chosen shard's engine for its record
// (evidence only, with its text and counts of the question's words), merges the candidates with
// collection-wide BM25, and makes one writer call on the merged top passages through the first chosen
// shard's engine (POST /compose). Each source carries its shard and the shard's audit tier, and the
// answer says which shards were searched and which were left out and why. Kept free of runtime-only
// imports: the engines are reached through the `forward` function the caller passes.
import { bareRequest } from "./ask";
import type { AskInput } from "./cache";
import { ENGINE_CONFIG, type Env } from "./config";
import {
  COLLECTION, NOT_SEARCHED_NOTE, choose, globalStats, loadPointer, loadTermDf, merge, routerFilters, servedInIndex,
  type Candidate, type Choice,
} from "./router";

export const ROUTER_HEADER = "x-civic-router";

export type Forward = (engine: string, request: Request) => Promise<Response>;

interface ShardReport {
  shard: string;
  tier: string | null;
  label?: string;
  candidates?: number;
  reason?: string;
}

function tierOf(shard: string): string | null {
  return ENGINE_CONFIG.scopes[shard]?.tier ?? null;
}

function routerBlock(searched: ShardReport[], leftOut: ShardReport[]) {
  return { scope: COLLECTION?.scope, label: COLLECTION?.label, searched, left_out: leftOut, note: NOT_SEARCHED_NOTE };
}

function nothingFound(message: string, searched: ShardReport[], leftOut: ShardReport[]) {
  return {
    answer: { text: message, abstained: true, abstention_text: message, sentences: [], verified_citations: [],
              unsupported: [], state: "INSUFFICIENT_EVIDENCE", cached: null },
    evidence: [], flagged: null, router: routerBlock(searched, leftOut),
  };
}

const leftReport = (c: Choice): ShardReport => ({ shard: c.shard, tier: tierOf(c.shard), reason: c.reason });

export async function askCollection(env: Pick<Env, "DATA" | "SHARDS" | "RELEASE_ID">, input: AskInput,
                                    evidenceOnly: boolean, budgetExhausted: boolean, forward: Forward,
                                    origin: string): Promise<Response> {
  if (!COLLECTION) return Response.json({ error: "no collection scope" }, { status: 422 });
  const pointer = await loadPointer(env.DATA);
  if (!pointer) {
    return Response.json({ status: "unavailable", error: "the whole collection's router index is not published yet" },
                         { status: 503 });
  }
  const { shards, missing } = servedInIndex(pointer, env.SHARDS);
  const notIndexed: ShardReport[] = missing.map((s) => ({ shard: s, tier: tierOf(s), reason: "not in the router index yet" }));
  const termDf = await loadTermDf(env.DATA, pointer, input.question);
  const [chosen, left] = choose(input.question, pointer, shards, termDf, routerFilters(input.filters as any),
                                COLLECTION.max_engines);
  const leftOut = [...left.map(leftReport), ...notIndexed];
  if (!chosen.length) {
    return Response.json(nothingFound("none of the searchable shards holds the question's words for these filters; "
                                      + "this is not the same as the archive not holding them.", [], leftOut));
  }
  // Every chosen engine at once: woken if asleep. A waking engine answers 503 with its state; the
  // whole answer then waits (503 with each engine's state), as a single-scope question does.
  const body = JSON.stringify({ question: input.question, filters: input.filters, evidence_only: true, nocache: true });
  const replies = await Promise.all(chosen.map(async (c) => {
    const req = bareRequest(`${origin}/ask?scope=${encodeURIComponent(c.shard)}`, "POST", body);
    req.headers.set(ROUTER_HEADER, "1");
    try {
      return { choice: c, resp: await forward(c.shard, req) };
    } catch {
      return { choice: c, resp: null };
    }
  }));
  const waking = replies.filter((r) => r.resp?.status === 503);
  if (waking.length) {
    const engines = await Promise.all(waking.map(async (r) => ({ shard: r.choice.shard, ...(await r.resp!.json().catch(() => ({}))) as object })));
    return Response.json({ status: "waking", retry_after_seconds: 3, engines,
                           router: routerBlock(chosen.map((c) => ({ shard: c.shard, tier: tierOf(c.shard) })), leftOut) },
                         { status: 503, headers: { "retry-after": "3" } });
  }
  const hitsByShard: Record<string, Candidate[]> = {};
  const searched: ShardReport[] = [];
  for (const { choice, resp } of replies) {
    if (!resp || resp.status !== 200) {
      leftOut.push({ shard: choice.shard, tier: tierOf(choice.shard), reason: "its engine did not answer" });
      continue;
    }
    const out = (await resp.json().catch(() => null)) as any;
    const hits = (out?.router?.hits ?? []) as Candidate[];
    hitsByShard[choice.shard] = hits;
    searched.push({ shard: choice.shard, tier: tierOf(choice.shard), candidates: hits.length });
  }
  if (!searched.length) {
    return Response.json({ status: "unavailable", error: "the chosen engines could not be reached",
                           router: routerBlock([], leftOut) }, { status: 503 });
  }
  const stats = globalStats(pointer, shards, termDf);
  const merged = merge(input.question, hitsByShard, stats, COLLECTION.pool_size);
  const shardOf = new Map(merged.map((m) => [m.passage_id, m.shard]));
  const writerEngine = searched[0].shard;
  const compose = bareRequest(`${origin}/compose?scope=${encodeURIComponent(writerEngine)}`, "POST", JSON.stringify({
    question: input.question, filters: input.filters, evidence_only: evidenceOnly,
    hits: merged.map(({ tf: _tf, dl: _dl, bm25: _b, rrf: _r, shard: _s, ...row }) => row),
    prompt_ids: merged.slice(0, COLLECTION.top_k).map((m) => m.passage_id),
  }));
  compose.headers.set(ROUTER_HEADER, "1");
  if (budgetExhausted) compose.headers.set("x-civic-model-budget", "exhausted");
  const resp = await forward(writerEngine, compose);
  if (resp.status !== 200) return resp;
  const answer = (await resp.json()) as any;
  for (const row of answer.evidence ?? []) {
    const shard = shardOf.get(row.passage_id) ?? null;
    row.shard = shard;
    row.tier = shard ? tierOf(shard) : null;
  }
  answer.router = routerBlock(searched, leftOut);
  return Response.json(answer);
}
