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
  // Variables
  RELEASE_ID: string;
  ENGINE_LAYOUT: string;         // "single" | "split"
  INSTANCE_TYPE: string;         // instance for the single container: a named type or JSON {vcpu,memoryMib,diskMb}
  INSTANCE_TYPE_PILOT: string;   // split layout
  INSTANCE_TYPE_MICROLOG: string;
  SLEEP_AFTER_MINUTES: string;
  PROVISION_MODE: string;        // "r2-binding" | "snapshot" | "image"
  SNAPSHOT_VERIFY?: string;      // "full" (default) | "trust": hash a restored disk again or not
  DENSE_BACKEND: string;         // "numpy" | "sqlite"
  ALLOWED_ORIGINS: string;       // comma-separated
  DAILY_MODEL_CALLS: string;
  TURNSTILE_REQUIRED: string;    // "true" | "false"
  KEEP_WARM_WINDOWS: string;     // "" (off) or e.g. "mon-fri 13:00-23:00" in UTC
  PUBLIC_URL: string;
  // Secrets (wrangler secret put)
  ANTHROPIC_API_KEY?: string;
  TURNSTILE_SECRET_KEY?: string;
}

export interface ScopeConfig {
  context: string;
  provider: string;
  model: string;
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
