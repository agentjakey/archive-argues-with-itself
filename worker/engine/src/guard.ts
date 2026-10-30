// What stands in front of anything that can wake the engine or call the model: Turnstile, the
// per-client rate limits, and the daily model budget kept in D1. Nothing here logs a question or
// an address; a client is identified only by a salted hash of its address, for the rate limiter.
import { type Env, flag, whole } from "./config";
import { sha256Hex } from "./key";

const SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
export const TURNSTILE_HEADER = "x-turnstile-token";

export interface GuardResult {
  ok: boolean;
  status?: number;
  reason?: string;
}

/** Check a Turnstile token with siteverify. Off only when TURNSTILE_REQUIRED is "false" (local
 *  development); with it on and no secret configured, every request is refused. */
export async function checkTurnstile(request: Request, env: Env, fetcher: typeof fetch = fetch): Promise<GuardResult> {
  if (!flag(env.TURNSTILE_REQUIRED, true)) return { ok: true };
  const token = request.headers.get(TURNSTILE_HEADER);
  if (!token || token.length > 2048) return { ok: false, status: 403, reason: "turnstile_missing" };
  if (!env.TURNSTILE_SECRET_KEY) return { ok: false, status: 503, reason: "turnstile_not_configured" };
  const body = new FormData();
  body.append("secret", env.TURNSTILE_SECRET_KEY);
  body.append("response", token);
  const ip = request.headers.get("cf-connecting-ip");
  if (ip) body.append("remoteip", ip);
  try {
    const resp = await fetcher(SITEVERIFY, { method: "POST", body });
    const result = (await resp.json()) as { success?: boolean };
    return result.success ? { ok: true } : { ok: false, status: 403, reason: "turnstile_failed" };
  } catch {
    return { ok: false, status: 503, reason: "turnstile_unreachable" };
  }
}

/** The rate limiter key for a client: a hash of its address and the release, never the address. */
export async function clientKey(request: Request, env: Env): Promise<string> {
  const ip = request.headers.get("cf-connecting-ip") ?? "unknown";
  return (await sha256Hex(`${env.RELEASE_ID}:${ip}`)).slice(0, 32);
}

export async function checkRate(limiter: RateLimit, key: string): Promise<GuardResult> {
  const { success } = await limiter.limit({ key });
  return success ? { ok: true } : { ok: false, status: 429, reason: "rate_limited" };
}

/** Count one forwarded question against today's model budget (UTC day). Returns false once the
 *  day's DAILY_MODEL_CALLS is reached; the engine then shows the record without a model call. */
export async function takeModelBudget(db: D1Database, env: Env, now: Date = new Date()): Promise<boolean> {
  const day = now.toISOString().slice(0, 10);
  const limit = whole(env.DAILY_MODEL_CALLS, 0);
  const row = await db
    .prepare(
      "INSERT INTO model_budget (day, calls) VALUES (?, 1) " +
        "ON CONFLICT(day) DO UPDATE SET calls = calls + 1 RETURNING calls",
    )
    .bind(day)
    .first<{ calls: number }>();
  return (row?.calls ?? Number.POSITIVE_INFINITY) <= limit;
}

/** CORS headers for an allowed origin; none for any other. */
export function corsHeaders(request: Request, env: Env): Record<string, string> {
  const origin = request.headers.get("origin");
  const allowed = (env.ALLOWED_ORIGINS ?? "").split(",").map((o) => o.trim()).filter(Boolean);
  if (!origin || !allowed.includes(origin)) return {};
  return {
    "access-control-allow-origin": origin,
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": `content-type, ${TURNSTILE_HEADER}`,
    "access-control-max-age": "600",
    vary: "Origin",
  };
}
