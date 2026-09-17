import type {
  AskRequest,
  AskResponse,
  CoverageResponse,
  Example,
  Filters,
  Flagged,
  Health,
  ScopesResponse,
  Story,
} from "../types";

// Empty VITE_API_BASE means same-origin (the FastAPI app serves web/dist).
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "content-type": "application/json" },
      ...init,
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
    throw new ApiError(res.status, errorDetail(res.status, body));
  }
  return (await res.json()) as T;
}

export function ask(body: AskRequest): Promise<AskResponse> {
  return request<AskResponse>(withQuery("/ask", scoped(new URLSearchParams())), {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function examples(): Promise<Example[]> {
  return request<Example[]>(withQuery("/examples", scoped(new URLSearchParams())));
}

export function health(): Promise<Health> {
  return request<Health>(withQuery("/health", scoped(new URLSearchParams())));
}

/** The corpora this server exposes, for the switcher. Never scoped (it lists all of them). */
export function scopes(): Promise<ScopesResponse> {
  return request<ScopesResponse>("/scopes");
}

export function stories(): Promise<Story[]> {
  return request<Story[]>(withQuery("/stories", scoped(new URLSearchParams())));
}

/** Harm-adjacent flag over exactly the pinned passages (a free user comparison), in the same
 *  shape as /ask and /stories. The local API computes it via flags.detect; on any failure the
 *  caller degrades to no note. */
export function flag(pins: string[]): Promise<{ flagged: Flagged | null }> {
  const p = scoped(new URLSearchParams({ pins: pins.join(",") }));
  return request<{ flagged: Flagged | null }>(withQuery("/flag", p));
}

export function coverage(q: string, filters: Filters): Promise<CoverageResponse> {
  const p = new URLSearchParams({ q });
  for (const k of ["period", "jurisdiction", "doc_type"] as const) {
    const v = filters[k];
    if (v) p.set(k, v);
  }
  return request<CoverageResponse>(withQuery("/coverage", scoped(p)));
}
