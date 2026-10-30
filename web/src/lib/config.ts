// Build-time settings (Vite env). In a static release the site reads its shards from STATIC_DATA
// and sends live questions to the engine Worker at API_BASE. Locally, with none set, the app talks
// to the FastAPI server on the same origin exactly as before.

/** The engine Worker (api.archiveargues.org), or "" for the same origin. */
export const API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? "").replace(/\/+$/, "");

/** Where the release's data shards live (for example "/data"), or "" when there are none. */
export const STATIC_DATA = ((import.meta.env.VITE_STATIC_DATA as string | undefined) ?? "").replace(/\/+$/, "");

/** The Turnstile site key for the invisible widget, or "" (local development: no token is sent). */
export const TURNSTILE_SITEKEY = (import.meta.env.VITE_TURNSTILE_SITEKEY as string | undefined) ?? "";

/** True in a static release: recorded answers and the reading room work with the engine off. */
export function staticMode(): boolean {
  return STATIC_DATA !== "";
}
