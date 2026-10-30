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
import { API_BASE, staticMode } from "./config";
import * as shards from "./staticData";
import { turnstileToken } from "./turnstile";

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
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (init?.guarded) {
    const token = await turnstileToken();
    if (token) headers["x-turnstile-token"] = token;
  }
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
    throw new ApiError(res.status, errorDetail(res.status, body));
  }
  return (await res.json()) as T;
}

export async function ask(body: AskRequest): Promise<AskResponse> {
  if (staticMode() && !body.provider && !body.nocache) {
    const recorded = await shards.recordedAnswer(await staticScope(), body.question, body.filters);
    if (recorded) return recorded;
  }
  return request<AskResponse>(withQuery("/ask", scoped(new URLSearchParams())), {
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
export function engineStatus(): Promise<EngineStatus> {
  return request<EngineStatus>("/health");
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
    const recorded = await shards.recordedCoverage(await staticScope(), q, filters);
    if (recorded) return recorded;
  }
  const p = new URLSearchParams({ q });
  for (const k of ["period", "jurisdiction", "doc_type"] as const) {
    const v = filters[k];
    if (v) p.set(k, v);
  }
  return request<CoverageResponse>(withQuery("/coverage", scoped(p)));
}
