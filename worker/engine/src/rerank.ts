// The reranker flag (RERANK_DEPTH): the engine reorders the head of each retrieved pool with this one
// Workers AI model (src/archive_debugger/retrieve/rerank.py), through the container's AI proxy. Kept free
// of runtime-only imports so the request parsing and its tests can use it.
import type { Env } from "./config";

export const RERANK_MODEL = "@cf/baai/bge-reranker-base";

/** The reranker flag: how many passages of each pool the engine reorders (RERANK_DEPTH), 0 when off. */
export function rerankDepth(env: Pick<Env, "RERANK_DEPTH">): number {
  const n = Number.parseInt(env.RERANK_DEPTH ?? "", 10);
  return Number.isFinite(n) && n > 0 ? Math.min(n, 100) : 0;
}

