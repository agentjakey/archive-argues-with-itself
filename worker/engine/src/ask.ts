// Reading an /ask request, and which engine serves a scope. Kept free of runtime-only imports so
// the tests can run it under Node.
import type { AskInput } from "./cache";
import { ENGINE_CONFIG, modelAllowed, type Env } from "./config";

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
}

/** The question, filters and scope of an /ask request; whether the Worker may serve it from the
 *  cache (not with nocache or evidence_only, nor with a provider or model other than the configured
 *  one); and whether the provider and model it asks for are allowed here. */
export async function readAsk(request: Request, env: Pick<Env, "PUBLIC_MODELS">): Promise<ParsedAsk | null> {
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
  return {
    input: { scope, question, filters },
    cacheable: !nocache && !evidenceOnly && configuredModel,
    allowed: modelAllowed(provider, model, configured, env.PUBLIC_MODELS),
    evidenceOnly,
  };
}
