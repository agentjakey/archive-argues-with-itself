// The operator wake: POST /admin/wake?scope=<name> with "authorization: Bearer <ADMIN_WAKE_TOKEN>".
// It wakes one named collection (or every engine when no scope is given) without Turnstile, so the
// operator can warm the engines after a deploy from a terminal. It is never linked from the site,
// it is rate limited before the token is even compared, and it does not exist (404) when no token
// is configured. The token is a Worker secret; it is never logged.
import { type Env } from "./config";
import { sha256Hex } from "./key";

export interface AdminCheck {
  ok: boolean;
  status: number;
  reason: string;
}

const BEARER = /^Bearer\s+(\S{16,512})$/;

/** Compare two strings in time that does not depend on where they first differ. Both are hashed
 *  first, so their lengths do not leak either. */
export async function sameSecret(given: string, expected: string): Promise<boolean> {
  const [a, b] = await Promise.all([sha256Hex(`admin:${given}`), sha256Hex(`admin:${expected}`)]);
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0 && a.length === b.length;
}

/** Decide whether a request may use the operator wake. The rate limit runs first and is keyed on
 *  the route alone, so guessing tokens from many addresses shares one small allowance. */
export async function checkAdmin(request: Request, env: Env, limiter: RateLimit): Promise<AdminCheck> {
  const expected = (env.ADMIN_WAKE_TOKEN ?? "").trim();
  if (!expected) return { ok: false, status: 404, reason: "not_found" };
  const { success } = await limiter.limit({ key: "admin-wake" });
  if (!success) return { ok: false, status: 429, reason: "rate_limited" };
  const match = BEARER.exec(request.headers.get("authorization") ?? "");
  if (!match || !(await sameSecret(match[1], expected))) return { ok: false, status: 401, reason: "unauthorized" };
  return { ok: true, status: 200, reason: "ok" };
}
