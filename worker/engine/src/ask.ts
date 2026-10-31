// Reading an /ask request, and which engine serves a scope. Kept free of runtime-only imports so
// the tests can run it under Node.
import type { AskInput } from "./cache";
import { ENGINE_CONFIG, flag, modelAllowed, type Env } from "./config";

/** Which engine serves a scope: the single "engine" container, or the scope's own (split layout). */
export function engineFor(env: Env, scope: string): string {
  return env.ENGINE_LAYOUT === "split" ? scope : "engine";
}

export function engineNames(env: Env): string[] {
  return env.ENGINE_LAYOUT === "split" ? Object.keys(ENGINE_CONFIG.scopes) : ["engine"];
}

export interface ParsedAsk {
  input: AskInput;
  cacheable: boolean;     // the Worker may serve it from the cache
  allowed: boolean;       // the provider and model are allowed from the public (PUBLIC_MODELS)
  evidenceOnly: boolean;  // retrieval only: no model call, so no model budget
  nocacheDropped: boolean;  // the request asked for nocache and this deployment ignores it
}

/** The question, filters and scope of an /ask request; whether the Worker may serve it from the
 *  cache (not with evidence_only, nor with a provider or model other than the configured one, nor
 *  with nocache where PUBLIC_NOCACHE allows it); and whether the provider and model it asks for are
 *  allowed here. Production leaves PUBLIC_NOCACHE off, so a public nocache is ignored. */
export async function readAsk(request: Request, env: Pick<Env, "PUBLIC_MODELS" | "PUBLIC_NOCACHE">): Promise<ParsedAsk | null> {
  const url = new URL(request.url);
  const scope = url.searchParams.get("scope") || ENGINE_CONFIG.default_scope;
  if (!ENGINE_CONFIG.scopes[scope]) return null;
  const configured = ENGINE_CONFIG.scopes[scope];
  let question: string;
  let filters: Record<string, string> | null;
  let provider: string | null;
  let model: string | null;
  let nocache: boolean;
  let evidenceOnly: boolean;
  if (request.method === "GET") {
    question = url.searchParams.get("q") ?? "";
    filters = {};
    for (const name of ["period", "jurisdiction", "doc_type"]) {
      const value = url.searchParams.get(name);
      if (value) filters[name] = value;
    }
    provider = url.searchParams.get("provider");
    model = null;
    nocache = Boolean(Number(url.searchParams.get("nocache") ?? "0"));
    evidenceOnly = Boolean(Number(url.searchParams.get("evidence_only") ?? "0"));
  } else {
    let body: Record<string, any>;
    try {
      body = (await request.clone().json()) as Record<string, any>;
    } catch {
      return null;
    }
    if (typeof body.question !== "string") return null;
    question = body.question;
    filters = body.filters ?? null;
    provider = typeof body.provider === "string" && body.provider ? body.provider : null;
    model = typeof body.model === "string" && body.model ? body.model : null;
    nocache = Boolean(body.nocache);
    evidenceOnly = Boolean(body.evidence_only);
  }
  const configuredModel = (!provider || provider === configured.provider) && (!model || model === configured.model);
  const nocacheAllowed = flag(env.PUBLIC_NOCACHE, false);
  return {
    input: { scope, question, filters },
    cacheable: !(nocache && nocacheAllowed) && !evidenceOnly && configuredModel,
    allowed: modelAllowed(provider, model, configured, env.PUBLIC_MODELS),
    evidenceOnly,
    nocacheDropped: nocache && !nocacheAllowed,
  };
}

/** A request for the engine carrying only what it needs: the method, the URL and, for a POST, the
 *  JSON body. The visitor's headers (address, user agent, language, referrer, cookies, the Turnstile
 *  token) stay at the Worker. */
export function bareRequest(url: string, method: string, body: string | null): Request {
  const headers = new Headers();
  if (body !== null) headers.set("content-type", "application/json");
  return new Request(url, { method, headers, body });
}

/** The /ask request the engine receives: bare, and without nocache when this deployment ignores it
 *  (so the engine reads and writes its cache as usual). */
export async function engineRequest(request: Request, parsed: ParsedAsk): Promise<Request> {
  const url = new URL(request.url);
  if (request.method === "GET") {
    if (parsed.nocacheDropped) url.searchParams.delete("nocache");
    return bareRequest(url.toString(), "GET", null);
  }
  const body = (await request.clone().json()) as Record<string, unknown>;
  if (parsed.nocacheDropped) delete body.nocache;
  return bareRequest(url.toString(), "POST", JSON.stringify(body));
}
