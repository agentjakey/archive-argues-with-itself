import type {
  AskRequest,
  AskResponse,
  CoverageResponse,
  EngineStatus,
  Example,
  Filters,
  Flagged,
  Health,
  ScopesResponse,
  Story,
} from "../types";
import { FILTER_KEYS } from "../types";
import { API_BASE, staticMode } from "./config";
import * as shards from "./staticData";
import { turnstileResult, type TokenFailure } from "./turnstile";

// Empty API_BASE means same-origin (the FastAPI app serves web/dist). In a static release the
// reading room comes from the release's shards (staticData.ts) and only live questions reach the
// engine Worker.
const BASE = API_BASE;

// Hard client timeout, longer than the server's generation timeout so the server's
// own graceful limited-mode fallback arrives first; only a truly unreachable server
// hits this. A network fault or this timeout becomes a friendly message, never a raw
// "Failed to fetch" (N6).
const REQUEST_TIMEOUT_MS = 30_000;
const OFFLINE_MESSAGE =
  "Can't reach the archive server. If you are at the exhibit, the record is still here; try an example question or a story below.";
const TIMEOUT_MESSAGE =
  "That took too long to load. The record is still here; try an example question or a story below.";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** The person check (Turnstile) did not pass, ran out of time or did not load, so the question was
 *  not sent or was refused. Shown as a plain message with a retry. */
export class TurnstileError extends ApiError {
  constructor(detail: string) {
    super(403, detail);
    this.name = "TurnstileError";
  }
}

export const CHECK_MESSAGES: Record<TokenFailure | "refused" | "unreachable", string> = {
  failed: "We could not confirm that this question came from a person, so it was not sent. Please try again.",
  refused: "We could not confirm that this question came from a person, so it was not sent. Please try again.",
  expired: "The check that this question came from a person ran out of time, so it was not sent. Please try again.",
  timeout: "The check that this question came from a person ran out of time, so it was not sent. Please try again.",
  unavailable:
    "The check that this question came from a person did not load, so it was not sent. If something blocks " +
    "challenges.cloudflare.com on your connection, allow it, then try again.",
  unreachable: "The site could not run its check that this question came from a person just now. Please try again in a minute.",
};

export const RATE_LIMIT_MESSAGE = "Too many questions from this connection in the last minute. Wait a minute, then try again.";

/** A refusal from the engine Worker's guards, as a plain sentence, or null for any other error. */
export function guardError(status: number, body: unknown): ApiError | null {
  const code = body && typeof body === "object" ? (body as Record<string, unknown>).error : null;
  if (code === "turnstile_missing" || code === "turnstile_failed") return new TurnstileError(CHECK_MESSAGES.refused);
  if (code === "turnstile_unreachable" || code === "turnstile_not_configured") return new TurnstileError(CHECK_MESSAGES.unreachable);
  if (status === 429 || code === "rate_limited") return new ApiError(429, RATE_LIMIT_MESSAGE);
  return null;
}

/** The engine was asleep or is still waking: the request was not lost, it can be retried once the
 *  engine is ready. Carries the engine's reported state for the waking screen. */
export class EngineWaking extends ApiError {
  engine: EngineStatus;
  constructor(engine: EngineStatus) {
    super(503, "The archive engine is waking up.");
    this.name = "EngineWaking";
    this.engine = engine;
  }
}

/** The active scope from the URL, set only by the scope switcher (via a full reload).
 *  Appended to every data request so each corpus hits only its own DBs. Absent for the
 *  pilot default, so the pilot request path is byte-identical to before. */
export function activeScope(): string | null {
  try {
    return new URLSearchParams(window.location.search).get("scope");
  } catch {
    return null;
  }
}

function scoped(params: URLSearchParams): URLSearchParams {
  const s = activeScope();
  if (s) params.set("scope", s);
  return params;
}

function withQuery(path: string, params: URLSearchParams): string {
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

/** The scope a static lookup uses: the URL's, else the release's landing scope. */
async function staticScope(): Promise<string> {
  const s = activeScope();
  if (s) return s;
  return (await shards.scopes()).default;
}

/** The engine's whole-collection scope: its router searches every served part (the collections
 *  served first and every promoted shard) for one question. */
export const COLLECTION_SCOPE = "collection";

/** Where a typed question goes: the collection a link named (?scope=), else, in a static release,
 *  the whole collection. Locally (no static data) the default engine scope, as before. */
export function askScope(): string | null {
  const s = activeScope();
  if (s) return s;
  return staticMode() ? COLLECTION_SCOPE : null;
}

/** The parts whose recorded answers a question may match: the named collection, or every collection
 *  of the release, the landing one first. */
async function recordedScopes(): Promise<string[]> {
  const s = activeScope();
  if (s) return [s];
  const all = await shards.scopes();
  return [all.default, ...all.scopes.map((x) => x.name).filter((n) => n !== all.default)];
}

/** The server's own words, verbatim: our {"error"} shape, FastAPI's {"detail"}
 *  (string or validation list), else a sentence that still names the status. */
export function errorDetail(status: number, body: unknown): string {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (typeof b.error === "string" && b.error) return b.error;
    if (typeof b.detail === "string" && b.detail) return b.detail;
    if (Array.isArray(b.detail)) {
      const msgs = b.detail.map((d) =>
        d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : JSON.stringify(d),
      );
      if (msgs.length) return msgs.join("; ");
    }
  }
  return `The server returned an error (status ${status}) with no detail.`;
}

/** True when a 503 body is the engine Worker's waking state rather than an error. */
function wakingState(body: unknown): EngineStatus | null {
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;
  if (typeof b.status === "string" && ["asleep", "waking", "failed"].includes(b.status)) return b as unknown as EngineStatus;
  return null;
}

async function request<T>(path: string, init?: RequestInit & { guarded?: boolean }): Promise<T> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  // The person check comes first and has its own time limits (a visitor may be answering a
  // challenge); the request timeout starts when the request does.
  if (init?.guarded) {
    const check = await turnstileResult();
    if (check.failure) throw new TurnstileError(CHECK_MESSAGES[check.failure]);
    if (check.token) headers["x-turnstile-token"] = check.token;
  }
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers,
      signal: ctrl.signal,
    });
  } catch (e) {
    // A network fault or our own timeout abort: surface friendly copy, never a raw
    // "Failed to fetch" (N6). status 0 marks a transport-level failure.
    const aborted = e instanceof DOMException && e.name === "AbortError";
    throw new ApiError(0, aborted ? TIMEOUT_MESSAGE : OFFLINE_MESSAGE);
  } finally {
    window.clearTimeout(timer);
  }
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    const waking = res.status === 503 ? wakingState(body) : null;
    if (waking) throw new EngineWaking(waking);
    const refused = init?.guarded ? guardError(res.status, body) : null;
    if (refused) throw refused;
    throw new ApiError(res.status, errorDetail(res.status, body));
  }
  return (await res.json()) as T;
}

export async function ask(body: AskRequest): Promise<AskResponse> {
  if (staticMode() && !body.provider && !body.nocache && !body.evidence_only) {
    // A seed or story question is answered from its recording, in whichever part recorded it.
    for (const scope of await recordedScopes()) {
      const recorded = await shards.recordedAnswer(scope, body.question, body.filters);
      if (recorded) return recorded;
    }
  }
  const target = askScope();
  const params = new URLSearchParams();
  if (target) params.set("scope", target);
  return request<AskResponse>(withQuery("/ask", params), {
    method: "POST",
    body: JSON.stringify(body),
    guarded: true,
  });
}

export async function examples(): Promise<Example[]> {
  if (staticMode()) return shards.examples(await staticScope());
  return request<Example[]>(withQuery("/examples", scoped(new URLSearchParams())));
}

/** Seed questions for a named scope (the explorer lists several scopes at once, so it asks for
 *  each scope's own examples explicitly rather than the active-scope default). */
export function examplesForScope(scope: string): Promise<Example[]> {
  if (staticMode()) return shards.examples(scope);
  const p = new URLSearchParams();
  if (scope) p.set("scope", scope);
  return request<Example[]>(withQuery("/examples", p));
}

export async function health(): Promise<Health> {
  if (staticMode()) return shards.health(await staticScope());
  return request<Health>(withQuery("/health", scoped(new URLSearchParams())));
}

/** The engine's state from the engine Worker (asleep, waking with its stage, ready, failed). Never
 *  wakes it. Only meaningful in a static release. */
/** The engines' state. With scopes, only the engines those scopes run on: the parts one waiting
 *  question woke, so it is not held up by parts it does not need. */
export function engineStatus(scopes?: string[] | null): Promise<EngineStatus> {
  const named = (scopes ?? []).filter(Boolean);
  return request<EngineStatus>(named.length ? `/health?scope=${encodeURIComponent(named.join(","))}` : "/health");
}

/** The parts a waking engine reply names: each engine of a whole-collection question, or the one engine. */
export function wakingParts(engine: EngineStatus): string[] {
  // "engine" is the single-engine layout's one container, not a part of the archive.
  const isPart = (n: string | undefined): n is string => !!n && n !== "engine";
  const listed = (engine.engines ?? []).map((e) => e.shard ?? e.name).filter(isPart);
  if (listed.length) return [...new Set(listed)];
  return isPart(engine.name) ? [engine.name] : [];
}

/** Ask the engine Worker to start the engine ahead of a question (page load, question focus).
 *  Best effort: any failure is ignored. */
export async function wake(): Promise<void> {
  try {
    await request<unknown>(withQuery("/wake", scoped(new URLSearchParams())), { method: "POST", guarded: true });
  } catch {
    // a refused or failed pre-wake changes nothing for the visitor
  }
}

/** The corpora this server exposes, for the switcher. Never scoped (it lists all of them). */
export function scopes(): Promise<ScopesResponse> {
  if (staticMode()) return shards.scopes();
  return request<ScopesResponse>("/scopes");
}

export async function stories(): Promise<Story[]> {
  if (staticMode()) return shards.stories(await staticScope());
  return request<Story[]>(withQuery("/stories", scoped(new URLSearchParams())));
}

/** Harm-adjacent flag over exactly the pinned passages (a free user comparison), in the same
 *  shape as /ask and /stories. The local API computes it via flags.detect; on any failure the
 *  caller degrades to no note. */
export function flag(pins: string[]): Promise<{ flagged: Flagged | null }> {
  const p = scoped(new URLSearchParams({ pins: pins.join(",") }));
  return request<{ flagged: Flagged | null }>(withQuery("/flag", p));
}

export async function coverage(q: string, filters: Filters): Promise<CoverageResponse> {
  if (staticMode()) {
    for (const scope of await recordedScopes()) {
      const recorded = await shards.recordedCoverage(scope, q, filters);
      if (recorded) return recorded;
    }
    // The decade counts come from one collection's engine; a whole-collection answer has none.
    if (askScope() === COLLECTION_SCOPE) throw new ApiError(404, "no decade coverage for the whole collection");
  }
  const p = new URLSearchParams({ q });
  for (const k of FILTER_KEYS) {
    const v = filters[k];
    if (v) p.set(k, v);
  }
  return request<CoverageResponse>(withQuery("/coverage", scoped(p)));
}
