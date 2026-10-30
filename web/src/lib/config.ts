// Build-time settings (Vite env). In a static release the site reads its shards from STATIC_DATA
// and sends live questions to the engine Worker at API_BASE. Locally, with none set, the app talks
// to the FastAPI server on the same origin exactly as before.

/** The engine Worker (api.archiveargues.org), or "" for the same origin. */
export const API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? "").replace(/\/+$/, "");

/** The data folder a release's index.html names (<meta name="archive-data">): a folder named by
 *  the hash of its content, cached for a year, so the never-cached HTML is the pointer to it. */
function releaseDataFolder(): string | null {
  try {
    const meta = document.querySelector('meta[name="archive-data"]');
    const value = meta?.getAttribute("content") ?? "";
    return /^\/data\/[0-9a-f]{16}$/.test(value) ? value : null;
  } catch {
    return null;
  }
}

/** Where the release's data shards live, or "" when there are none: the folder index.html names,
 *  else the build setting (VITE_STATIC_DATA, for a build served without assembling a release). */
export const STATIC_DATA = (
  releaseDataFolder() ?? ((import.meta.env.VITE_STATIC_DATA as string | undefined) ?? "")
).replace(/\/+$/, "");

/** The Turnstile site key for the invisible widget, or "" (local development: no token is sent). */
export const TURNSTILE_SITEKEY = (import.meta.env.VITE_TURNSTILE_SITEKEY as string | undefined) ?? "";

/** True in a static release: recorded answers and the reading room work with the engine off. */
export function staticMode(): boolean {
  return STATIC_DATA !== "";
}
