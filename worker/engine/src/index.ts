// The engine Worker on api.archiveargues.org: the only way to reach the engine container.
//
//   GET  /health      the engine's state (asleep, waking with its stage, ready, failed); never wakes it
//   POST /wake        pre-wake from the site (Turnstile, rate limited)
//   GET|POST /ask     a stored answer straight from D1 when there is one; otherwise Turnstile, the
//                     rate limit and the daily model budget, then the engine (woken if asleep)
//   GET  /coverage    forwarded only while the engine is awake
//   GET  /flag        forwarded only while the engine is awake
//   GET  /__bench/cache?key=K&reads=N   staging only (needs the BENCH_* bindings): D1, KV and R2 read times
//
// Logs carry the route, the outcome and timings, never a question or an address.
import { readAsk, engineFor, engineNames } from "./ask";
import { servedHit, purgeExpired, storedAnswerResponse } from "./cache";
import { benchCacheStores, type BenchBindings } from "./bench";
import { ENGINE_CONFIG, type Env } from "./config";
import { checkRate, checkTurnstile, clientKey, corsHeaders, takeModelBudget, type GuardResult } from "./guard";
import { keepWarmNow } from "./schedule";

export { EngineContainer, R2Proxy, CacheProxy } from "./container";

const BUDGET_HEADER = "x-civic-model-budget";

function json(body: unknown, status: number, extra: Record<string, string>): Response {
  return Response.json(body, { status, headers: { "cache-control": "no-store", ...extra } });
}

function withHeaders(resp: Response, extra: Record<string, string>): Response {
  const out = new Response(resp.body, resp);
  for (const [k, v] of Object.entries(extra)) out.headers.set(k, v);
  out.headers.set("cache-control", "no-store");
  return out;
}

function log(fields: Record<string, unknown>): void {
  console.log(JSON.stringify(fields));
}

function stub(env: Env, name: string) {
  return env.ENGINE.get(env.ENGINE.idFromName(name));
}

async function guard(request: Request, env: Env, limiter: RateLimit): Promise<GuardResult> {
  const turnstile = await checkTurnstile(request, env);
  if (!turnstile.ok) return turnstile;
  return checkRate(limiter, await clientKey(request, env));
}

async function handleAsk(request: Request, env: Env, cors: Record<string, string>): Promise<Response> {
  const t0 = Date.now();
  const parsed = await readAsk(request);
  if (!parsed) return json({ error: "a question and a served scope are required" }, 422, cors);
  const { input, cacheable } = parsed;
  if (cacheable) {
    const hit = await servedHit(env.DB, input);
    if (hit) {
      log({ route: "/ask", scope: input.scope, outcome: "stored", ms: Date.now() - t0 });
      return storedAnswerResponse(request, hit, cors);
    }
  }
  const checked = await guard(request, env, env.RL_ASK);
  if (!checked.ok) {
    log({ route: "/ask", scope: input.scope, outcome: checked.reason, ms: Date.now() - t0 });
    return json({ error: checked.reason }, checked.status ?? 403, cors);
  }
  const forwarded = new Request(request);
  forwarded.headers.delete("x-turnstile-token");
  if (!(await takeModelBudget(env.DB, env))) forwarded.headers.set(BUDGET_HEADER, "exhausted");
  const resp = await stub(env, engineFor(env, input.scope)).forward(forwarded, true);
  log({ route: "/ask", scope: input.scope, outcome: resp.status === 200 ? "engine" : `engine_${resp.status}`, ms: Date.now() - t0 });
  return withHeaders(resp, { ...cors, "x-answer-source": "engine" });
}

async function handleHealth(env: Env, cors: Record<string, string>, wakes: boolean): Promise<Response> {
  const engines = await Promise.all(engineNames(env).map((name) => stub(env, name).status()));
  const states = engines.map((e) => e.status);
  const status = states.includes("failed") ? "failed" : states.every((s) => s === "ready")
    ? "ready" : states.some((s) => s === "waking") ? "waking" : states.every((s) => s === "asleep") ? "asleep" : "waking";
  const body: Record<string, unknown> = { status, release: env.RELEASE_ID, engines };
  if (wakes) body.wakes = (await Promise.all(engineNames(env).map((name) => stub(env, name).wakeLog()))).flat();
  return json(body, 200, cors);
}

async function handleWake(request: Request, env: Env, cors: Record<string, string>): Promise<Response> {
  const checked = await guard(request, env, env.RL_WAKE);
  if (!checked.ok) return json({ error: checked.reason }, checked.status ?? 403, cors);
  const url = new URL(request.url);
  const scope = url.searchParams.get("scope");
  const names = scope && env.ENGINE_LAYOUT === "split" ? [engineFor(env, scope)] : engineNames(env);
  const engines = await Promise.all(names.map((name) => stub(env, name).wakeUp()));
  log({ route: "/wake", engines: engines.map((e) => `${e.name}:${e.status}`) });
  return json({ engines }, 202, cors);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const cors = corsHeaders(request, env);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    try {
      if (url.pathname === "/health" && request.method === "GET") {
        return await handleHealth(env, cors, url.searchParams.get("wakes") === "1");
      }
      if (url.pathname === "/wake" && request.method === "POST") return await handleWake(request, env, cors);
      if (url.pathname === "/ask" && (request.method === "GET" || request.method === "POST")) {
        return await handleAsk(request, env, cors);
      }
      if (url.pathname === "/__bench/cache" && request.method === "GET") {
        const limited = await checkRate(env.RL_WAKE, await clientKey(request, env));
        if (!limited.ok) return json({ error: limited.reason }, limited.status ?? 429, cors);
        const result = await benchCacheStores(env as Env & BenchBindings, url.searchParams.get("key") ?? "",
                                              Number(url.searchParams.get("reads") ?? "20"));
        return result ? json({ ...result, colo: (request as any).cf?.colo ?? null }, 200, cors) : json({ error: "not found" }, 404, cors);
      }
      if ((url.pathname === "/coverage" || url.pathname === "/flag") && request.method === "GET") {
        const scope = url.searchParams.get("scope") || ENGINE_CONFIG.default_scope;
        const resp = await stub(env, engineFor(env, scope)).forward(request, false);
        return withHeaders(resp, cors);
      }
      return json({ error: "not found" }, 404, cors);
    } catch (err) {
      log({ route: url.pathname, outcome: "worker_error", error: String((err as Error)?.name ?? "Error") });
      return json({ status: "unavailable", error: "the engine could not be reached; the stories still work" }, 503, cors);
    }
  },

  async scheduled(controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    const now = new Date(controller.scheduledTime);
    // Once a day (the 04:00 UTC run): drop visitor answers past their 180-day retention.
    if (now.getUTCHours() === 4 && now.getUTCMinutes() < 10) {
      ctx.waitUntil(purgeExpired(env.DB, now).then((n) => log({ event: "purge", rows: n })));
    }
    // Keep-warm windows, off unless KEEP_WARM_WINDOWS is set.
    if (keepWarmNow(env.KEEP_WARM_WINDOWS, now)) {
      ctx.waitUntil(Promise.all(engineNames(env).map((name) => stub(env, name).wakeUp())).then(() => log({ event: "keep_warm" })));
    }
  },
} satisfies ExportedHandler<Env>;
