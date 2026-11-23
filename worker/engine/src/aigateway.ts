// Every Workers AI call the engine makes goes through here: one explicit AI Gateway per environment
// (AI_GATEWAY_ID), a per-day ceiling on model calls counted at the call itself (DAILY_AI_CALLS, kept
// in D1), and a clear 429 when the gateway's spend limit or the ceiling is reached.
//
// Why (billing audit, 2026-11-23): AIProxy called env.AI.run(model, inputs) with no gateway, so its
// GLM-5.3 traffic was invisible to AI Gateway analytics, outside every gateway spend limit, and could
// not draw on Unified Billing credits. There is no ungated path: with AI_GATEWAY_ID unset, no model
// is called at all (fail closed), so a missing variable can never turn into unbudgeted spend.
import { type Env, whole } from "./config";

/** The header the Worker already uses to tell the site the model budget is spent (src/index.ts). */
export const BUDGET_HEADER = "x-civic-model-budget";

export type AiEnv = Pick<Env, "AI" | "AI_GATEWAY_ID" | "DAILY_AI_CALLS" | "RELEASE_ID"> & {
  DB?: D1Database;
};

export class AiRefused extends Error {
  constructor(readonly status: number, readonly reason: string) {
    super(reason);
  }
}

/** The configured gateway id, or null. Only letters, digits, - and _ are accepted. */
export function gatewayId(env: Pick<Env, "AI_GATEWAY_ID">): string | null {
  const id = (env.AI_GATEWAY_ID ?? "").trim();
  return /^[A-Za-z0-9_-]{1,64}$/.test(id) ? id : null;
}

/** The day's ceiling on model calls: DAILY_AI_CALLS. Unset or malformed is 0, so nothing is called:
 *  every deployment states its own ceiling (wrangler.jsonc), and none inherits one by accident. */
export function dailyAiCalls(env: Pick<Env, "DAILY_AI_CALLS">): number {
  return whole(env.DAILY_AI_CALLS, 0);
}

/** Count one model call against today's ceiling (UTC day). False once it is reached, and false when
 *  the count cannot be kept (no D1, or D1 failed): the ceiling fails closed. The upsert is one
 *  statement, so concurrent calls each see their own count; the call that makes it limit+1 and every
 *  later one are refused (refused attempts still count, which only makes the ceiling stricter). */
export async function takeAiCall(db: D1Database | undefined, env: Pick<Env, "DAILY_AI_CALLS">,
                                 now: Date = new Date()): Promise<boolean> {
  const limit = dailyAiCalls(env);
  if (limit <= 0 || !db) return false;
  try {
    const row = await db
      .prepare("INSERT INTO ai_call_budget (day, calls) VALUES (?, 1) " +
               "ON CONFLICT(day) DO UPDATE SET calls = calls + 1 RETURNING calls")
      .bind(now.toISOString().slice(0, 10))
      .first<{ calls: number }>();
    return (row?.calls ?? Number.POSITIVE_INFINITY) <= limit;
  } catch {
    return false;
  }
}

/** Whether an error from the binding is the gateway refusing on a spend limit or rate limit, or on
 *  Unified Billing's credit balance (HTTP 402, "Insufficient unified billing balance", codes 2021/2052/2049). */
export function isBudgetError(err: unknown): boolean {
  const message = String((err as Error)?.message ?? err);
  return /\b429\b|\b402\b|rate.?limit|spend.?limit|budget|quota|too many requests|insufficient.*balance/i.test(message);
}

/** Run one model through the environment's gateway, after counting the call. Throws AiRefused
 *  (503 no binding / no gateway, 429 over the daily ceiling or the gateway's spend limit); any other
 *  binding error is passed on unchanged for the caller's own handling. */
export async function runGated(env: AiEnv, model: string, inputs: Record<string, unknown>,
                               now: Date = new Date()): Promise<unknown> {
  if (!env.AI) throw new AiRefused(503, "no AI binding");
  const id = gatewayId(env);
  if (!id) throw new AiRefused(503, "ai_gateway_not_configured");
  if (!(await takeAiCall(env.DB, env, now))) throw new AiRefused(429, "daily_ai_calls_exhausted");
  try {
    return await env.AI.run(model as any, inputs as any, {
      gateway: { id, metadata: { release: env.RELEASE_ID ?? "", source: "engine" } },
    } as any);
  } catch (err) {
    if (isBudgetError(err)) throw new AiRefused(429, "ai_gateway_budget_exhausted");
    throw err;
  }
}

/** The response for a refusal: JSON, with the budget header on a 429 so the site shows the record. */
export function refusalResponse(err: AiRefused): Response {
  const headers: Record<string, string> = {};
  if (err.status === 429) headers[BUDGET_HEADER] = "exhausted";
  return Response.json({ error: err.reason }, { status: err.status, headers });
}
