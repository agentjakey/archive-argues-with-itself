// Bindings, variables and the generated engine config, in one place.
import generated from "./generated/engine_config.json";
import type { EngineContainer } from "./container";

export interface Env {
  // Bindings (worker/engine/wrangler.jsonc)
  ENGINE: DurableObjectNamespace<EngineContainer>;
  DB: D1Database;
  DATA: R2Bucket;
  RL_ASK: RateLimit;
  RL_WAKE: RateLimit;
  RL_ADMIN: RateLimit;          // the operator wake (src/admin.ts)
  // Variables
  RELEASE_ID: string;
  ENGINE_LAYOUT: string;         // "single" | "split"
  INSTANCE_TYPE: string;         // instance for the single container: a named type or JSON {vcpu,memoryMib,diskMb}
  INSTANCE_TYPES: string;        // split layout: JSON {scope: instance}; a scope not named uses INSTANCE_TYPE
  SLEEP_AFTER_MINUTES: string;
  PROVISION_MODE: string;        // "r2-binding" | "snapshot" | "image"
  SNAPSHOT_VERIFY?: string;      // "full" (default) | "trust": hash a restored disk again or not
  DENSE_BACKEND: string;         // "numpy" | "sqlite"
  ALLOWED_ORIGINS: string;       // comma-separated
  DAILY_MODEL_CALLS: string;
  TURNSTILE_REQUIRED: string;    // "true" | "false"
  KEEP_WARM_WINDOWS: string;     // "" (off) or e.g. "mon-fri 13:00-23:00" in UTC
  PUBLIC_MODELS?: string;        // what a public /ask may choose besides the configured model: "" or e.g. "stub"
  PUBLIC_NOCACHE?: string;       // "true" lets a public /ask skip the answer cache (staging); off in production
  PUBLIC_URL: string;
  WRITER_CANDIDATE?: string;     // staging flag: an open writer candidate (config/writers.toml) answers in place of the configured one
  RERANK_DEPTH?: string;         // the reranker flag: passages of the pool it reorders, "" or "0" for off
  SHARDS?: string;               // the whole collection's shard scopes this deployment serves: comma-separated ids, or "" for none
  AI?: Ai;                       // Workers AI binding, staging only: the container reaches it through AIProxy
  // Secrets (wrangler secret put)
  ANTHROPIC_API_KEY?: string;
  TURNSTILE_SECRET_KEY?: string;
  ADMIN_WAKE_TOKEN?: string;     // the operator wake; unset means /admin/wake answers 404
}

export interface CandidateConfig {
  context: string;
  provider: string;
  model: string;
}

export interface ScopeConfig {
  context: string;
  curated_context?: string;   // the v1 context reviewed answers were stored under
  provider: string;
  model: string;
  candidates?: Record<string, CandidateConfig>;   // open writer candidates for the staging flag
  shard?: boolean;            // a shard of the whole collection (config/shards/served.toml)
  tier?: string | null;       // its audit tier: INDEXED, AI-AUDITED or HUMAN-AUDITED
}

export interface AnswerNote {
  id: string;
  date: string;
  text: string;
  reason: string;
  target: { scope: string; question: string; cached_only: boolean };
}

export interface EngineConfig {
  key_version: number;
  retention_days: number;
  extras_version: string;
  default_scope: string;
  scopes: Record<string, ScopeConfig>;
  stopwords: string[];
  answer_notes: AnswerNote[];
  r2_keys: string[];
}

export const ENGINE_CONFIG = generated as EngineConfig;
export const STOPWORDS: ReadonlySet<string> = new Set(ENGINE_CONFIG.stopwords);
export const SCOPES = Object.keys(ENGINE_CONFIG.scopes);

/** Whether this deployment serves a scope. Every scope that is not a shard is served everywhere; a
 *  shard of the whole collection only where SHARDS names it, so a shard reaches production by
 *  adding its id to production's SHARDS, one at a time, after its audit and smoke tests. */
export function scopeServed(scope: string, shards: string | undefined): boolean {
  const configured = ENGINE_CONFIG.scopes[scope];
  if (!configured) return false;
  if (!configured.shard) return true;
  return (shards || "").split(",").map((s) => s.trim()).filter(Boolean).includes(scope);
}

/** The scopes this deployment serves, in the generated config's order. */
export function servedScopes(shards: string | undefined): string[] {
  return SCOPES.filter((scope) => scopeServed(scope, shards));
}

/** A scope's writer and cache context: the configured writer, or, while the staging flag
 *  WRITER_CANDIDATE names one of the scope's generated candidates, that candidate (the engine reads
 *  the same name from CIVIC_WRITER_CANDIDATE and computes the same context). */
export function scopeConfig(scope: string, candidate?: string): ScopeConfig | undefined {
  const configured = ENGINE_CONFIG.scopes[scope];
  if (!configured || !candidate) return configured;
  const c = configured.candidates?.[candidate];
  if (!c) return configured;
  return { context: c.context, curated_context: configured.curated_context, provider: c.provider, model: c.model };
}

/** The engine's robots.txt: it is an API, not pages, so nothing is for crawlers. */
export const ROBOTS = ["User-agent: *", "Disallow: /", ""].join("\n");

export function flag(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined || value === "") return fallback;
  return value.trim().toLowerCase() === "true";
}

export function whole(value: string | undefined, fallback: number): number {
  const n = Number.parseInt(value ?? "", 10);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

/** How the engine checks data files already on its disk. Image layers are verified by digest on
 *  pull. A restored snapshot was taken only after a wake of the same release verified every file,
 *  so SNAPSHOT_VERIFY=trust skips hashing it again; anything else hashes in full. */
export function verifyPolicy(mode: string, restoredFromSnapshot: boolean, snapshotVerify: string | undefined): string {
  if (mode === "image") return "trust-image";
  if (restoredFromSnapshot && (snapshotVerify || "").trim() === "trust") return "trust-snapshot";
  return "full";
}

/** Whether a public request may use this provider and model. The scope's configured provider and
 *  model always may; anything else only when PUBLIC_MODELS names it, as "provider" (any model) or
 *  "provider:model", comma-separated. Production leaves PUBLIC_MODELS empty. */
export function modelAllowed(provider: string | null, model: string | null, configured: ScopeConfig,
                             publicModels: string | undefined): boolean {
  const wantProvider = provider || configured.provider;
  const wantModel = model || configured.model;
  if (wantProvider === configured.provider && wantModel === configured.model) return true;
  const allowed = (publicModels || "").split(",").map((s) => s.trim()).filter(Boolean);
  return allowed.includes(wantProvider) || allowed.includes(`${wantProvider}:${wantModel}`);
}

/** The instance for one engine: its entry in INSTANCE_TYPES (split layout) or INSTANCE_TYPE. A
 *  malformed INSTANCE_TYPES is ignored rather than stopping every wake. */
export function instanceFor(engineName: string, instanceTypes: string | undefined, fallback: string): string {
  try {
    const map = JSON.parse(instanceTypes || "{}") as Record<string, unknown>;
    const chosen = map[engineName];
    if (typeof chosen === "string" && chosen.trim()) return chosen;
    if (chosen && typeof chosen === "object") return JSON.stringify(chosen);
  } catch {
    // fall through to the default size
  }
  return fallback;
}

/** The open writer model the staging flag names, when the flag is set, the generated config lists
 *  the candidate for every scope, all with one model, and the Workers AI binding is present; else null. */
export function candidateModel(env: Pick<Env, "WRITER_CANDIDATE" | "AI">): string | null {
  const name = env.WRITER_CANDIDATE;
  if (!name || !env.AI) return null;
  const models = new Set(Object.values(ENGINE_CONFIG.scopes).map((s) => s.candidates?.[name]?.model));
  if (models.size !== 1) return null;
  const model = [...models][0];
  return model ?? null;
}

/** An OpenAI-style chat completion from whatever the Workers AI binding returned: newer models
 *  already answer in that shape; older ones return {response, usage}. */
export function asChatCompletion(model: string, result: any): Record<string, unknown> {
  if (result && Array.isArray(result.choices)) return result;
  const response = result?.response;
  const content = typeof response === "string" ? response : JSON.stringify(response ?? "");
  return {
    model,
    choices: [{ index: 0, message: { role: "assistant", content }, finish_reason: "stop" }],
    usage: result?.usage ?? {},
  };
}
