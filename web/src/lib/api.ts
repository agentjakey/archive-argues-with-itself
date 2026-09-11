import type { AskRequest, AskResponse, CoverageResponse, Example, Filters, Health, Story } from "../types";

// Empty VITE_API_BASE means same-origin (the FastAPI app serves web/dist).
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

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
  const res = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
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
  return request<AskResponse>("/ask", { method: "POST", body: JSON.stringify(body) });
}

export function examples(): Promise<Example[]> {
  return request<Example[]>("/examples");
}

export function health(): Promise<Health> {
  return request<Health>("/health");
}

export function stories(): Promise<Story[]> {
  return request<Story[]>("/stories");
}

export function coverage(q: string, filters: Filters): Promise<CoverageResponse> {
  const p = new URLSearchParams({ q });
  for (const k of ["period", "jurisdiction", "doc_type"] as const) {
    const v = filters[k];
    if (v) p.set(k, v);
  }
  return request<CoverageResponse>(`/coverage?${p.toString()}`);
}
