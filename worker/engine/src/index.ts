// The engine Worker on api.archiveargues.org: the only way to reach the engine container.
//
//   GET  /health      the engine's state (asleep, waking with its stage, ready, failed); never wakes it.
//                     ?scope=a,b reports only those scopes' engines (a waiting visitor's question)
//   POST /wake        pre-wake from the site (Turnstile, rate limited)
//   POST /admin/wake  operator wake with ADMIN_WAKE_TOKEN (src/admin.ts); 404 when no token is set.
//                     The same bearer token on /ask replaces Turnstile for operator smoke tests
//   GET|POST /ask     a stored answer straight from D1 when there is one; otherwise Turnstile, the
//                     rate limit and the daily model budget, then the engine (woken if asleep).
//                     A provider or model other than the scope's own is refused unless
//                     PUBLIC_MODELS names it; evidence_only asks for the record alone (no model).
//                     scope=collection (where SHARDS names a shard): the whole collection through the
//                     cross-shard router (src/collection.ts), never from the cache
//   GET  /coverage    forwarded only while the engine is awake
//   GET  /flag        forwarded only while the engine is awake
//   GET  /__bench/cache?key=K&reads=N   staging only (needs the BENCH_* bindings): D1, KV and R2 read times
//   GET  /robots.txt  disallows everything: the engine is not for crawlers
//
// Logs carry the route, the outcome and timings, never a question or an address.
import { checkAdmin } from "./admin";
import { bareRequest, readAsk, engineFor, engineNames, engineRequest, healthEngines } from "./ask";
import { servedHit, purgeExpired, storedAnswerResponse } from "./cache";
import { benchCacheStores, type BenchBindings } from "./bench";
import { ENGINE_CONFIG, ROBOTS, scopeServed, type Env } from "./config";
import { checkRate, checkTurnstile, clientKey, corsHeaders, takeModelBudget, type GuardResult } from "./guard";
import { keepWarmNow } from "./schedule";
import { askCollection } from "./collection";
import { isCollection } from "./router";

export { EngineContainer, R2Proxy, CacheProxy, AIProxy } from "./container";

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
  const parsed = await readAsk(request, env);
  if (!parsed) return json({ error: "a question and a served scope are required" }, 422, cors);
  const { input, cacheable, allowed, evidenceOnly } = parsed;
  if (!allowed) {
    log({ route: "/ask", scope: input.scope, outcome: "model_refused", ms: Date.now() - t0 });
    return json({ error: "that provider or model is not available here" }, 422, cors);
  }
  if (cacheable) {
    const hit = await servedHit(env.DB, input, env.WRITER_CANDIDATE);
    if (hit) {
      log({ route: "/ask", scope: input.scope, outcome: "stored", ms: Date.now() - t0 });
      return storedAnswerResponse(request, hit, cors);
    }
  }
  // The operator's token stands in for Turnstile and the visitor rate limit (smoke tests after a
  // deploy); the daily model budget still applies. A wrong token is refused, never downgraded.
  const operator = request.headers.has("authorization");
  const checked = operator ? await checkAdmin(request, env, env.RL_ADMIN) : await guard(request, env, env.RL_ASK);
  if (!checked.ok) {
    log({ route: "/ask", scope: input.scope, outcome: checked.reason, ms: Date.now() - t0 });
    return json({ error: checked.reason }, checked.status ?? 403, cors);
  }
  if (isCollection(input.scope)) {
    // The whole collection: the router chooses the shard engines and merges their records (src/collection.ts).
    const exhausted = !evidenceOnly && !(await takeModelBudget(env.DB, env));
    const resp = await askCollection(env, input, evidenceOnly, exhausted,
                                     (name, req) => stub(env, engineFor(env, name)).forward(req, true), new URL(request.url).origin);
    log({ route: "/ask", scope: input.scope, outcome: resp.status === 200 ? "collection" : `collection_${resp.status}`, operator, ms: Date.now() - t0 });
    return withHeaders(resp, { ...cors, "x-answer-source": "collection" });
  }
  const forwarded = await engineRequest(request, parsed);
  // The record alone makes no model call, so it does not spend the daily model budget.
  if (!evidenceOnly && !(await takeModelBudget(env.DB, env))) forwarded.headers.set(BUDGET_HEADER, "exhausted");
  const resp = await stub(env, engineFor(env, input.scope)).forward(forwarded, true);
  log({ route: "/ask", scope: input.scope, outcome: resp.status === 200 ? "engine" : `engine_${resp.status}`, operator, ms: Date.now() - t0 });
  return withHeaders(resp, { ...cors, "x-answer-source": "engine" });
}

async function handleHealth(env: Env, cors: Record<string, string>, wakes: boolean, scopeParam: string | null = null): Promise<Response> {
  const engines = await Promise.all(healthEngines(env, scopeParam).map((name) => stub(env, name).status()));
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
  if (scope && !scopeServed(scope, env.SHARDS)) return json({ error: "unknown scope" }, 422, cors);
  const names = scope && env.ENGINE_LAYOUT === "split" ? [engineFor(env, scope)] : engineNames(env);
  const engines = await Promise.all(names.map((name) => stub(env, name).wakeUp()));
  log({ route: "/wake", engines: engines.map((e) => `${e.name}:${e.status}`) });
  return json({ engines }, 202, cors);
}

async function handleAdminWake(request: Request, env: Env): Promise<Response> {
  const checked = await checkAdmin(request, env, env.RL_ADMIN);
  if (!checked.ok) {
    log({ route: "/admin/wake", outcome: checked.reason });
    return json({ error: checked.reason }, checked.status, {});
  }
  const scope = new URL(request.url).searchParams.get("scope");
  if (scope && !engineNames(env).includes(engineFor(env, scope))) return json({ error: "unknown scope" }, 422, {});
  const names = scope ? [engineFor(env, scope)] : engineNames(env);
  const engines = await Promise.all(names.map((name) => stub(env, name).wakeUp()));
  log({ route: "/admin/wake", outcome: "woken", engines: engines.map((e) => `${e.name}:${e.status}`) });
  return json({ release: env.RELEASE_ID, engines }, 202, {});
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const cors = corsHeaders(request, env);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    try {
      if (url.pathname === "/robots.txt" && request.method === "GET") {
        return new Response(ROBOTS, { headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "public, max-age=86400" } });
      }
      if (url.pathname === "/health" && request.method === "GET") {
        return await handleHealth(env, cors, url.searchParams.get("wakes") === "1", url.searchParams.get("scope"));
      }
      if (url.pathname === "/wake" && request.method === "POST") return await handleWake(request, env, cors);
      if (url.pathname === "/admin/wake" && request.method === "POST") return await handleAdminWake(request, env);
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
        if (!scopeServed(scope, env.SHARDS)) return json({ error: "unknown scope" }, 422, cors);
        const resp = await stub(env, engineFor(env, scope)).forward(bareRequest(request.url, "GET", null), false);
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
    // Once a day (the 04:00 UTC run): drop visitor answers past their retention (ENGINE_CONFIG.retention_days).
    if (now.getUTCHours() === 4 && now.getUTCMinutes() < 10) {
      ctx.waitUntil(purgeExpired(env.DB, now).then((n) => log({ event: "purge", rows: n })));
    }
    // Keep-warm windows, off unless KEEP_WARM_WINDOWS is set.
    if (keepWarmNow(env.KEEP_WARM_WINDOWS, now)) {
      ctx.waitUntil(Promise.all(engineNames(env).map((name) => stub(env, name).wakeUp())).then(() => log({ event: "keep_warm" })));
    }
  },
} satisfies ExportedHandler<Env>;
