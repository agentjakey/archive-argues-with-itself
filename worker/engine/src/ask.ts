// Reading an /ask request, and which engine serves a scope. Kept free of runtime-only imports so
// the tests can run it under Node.
import type { AskInput } from "./cache";
import { ENGINE_CONFIG, type Env } from "./config";

/** Which engine serves a scope: the single "engine" container, or the scope's own (split layout). */
export function engineFor(env: Env, scope: string): string {
  return env.ENGINE_LAYOUT === "split" ? scope : "engine";
}

export function engineNames(env: Env): string[] {
  return env.ENGINE_LAYOUT === "split" ? Object.keys(ENGINE_CONFIG.scopes) : ["engine"];
}

/** The question, filters and scope of an /ask request, and whether the Worker may serve it from
 *  the cache (not with nocache, nor with a provider or model other than the configured one). */
export async function readAsk(request: Request): Promise<{ input: AskInput; cacheable: boolean } | null> {
  const url = new URL(request.url);
  const scope = url.searchParams.get("scope") || ENGINE_CONFIG.default_scope;
  if (!ENGINE_CONFIG.scopes[scope]) return null;
  const configured = ENGINE_CONFIG.scopes[scope];
  if (request.method === "GET") {
    const question = url.searchParams.get("q") ?? "";
    const filters: Record<string, string> = {};
    for (const name of ["period", "jurisdiction", "doc_type"]) {
      const value = url.searchParams.get(name);
      if (value) filters[name] = value;
    }
    const provider = url.searchParams.get("provider");
    const nocache = Boolean(Number(url.searchParams.get("nocache") ?? "0"));
    return { input: { scope, question, filters }, cacheable: !nocache && (!provider || provider === configured.provider) };
  }
  let body: Record<string, any>;
  try {
    body = (await request.clone().json()) as Record<string, any>;
  } catch {
    return null;
  }
  if (typeof body.question !== "string") return null;
  const cacheable =
    !body.nocache && (!body.provider || body.provider === configured.provider) && (!body.model || body.model === configured.model);
  return { input: { scope, question: body.question, filters: body.filters ?? null }, cacheable };
}

